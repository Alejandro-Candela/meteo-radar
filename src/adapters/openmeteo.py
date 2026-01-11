import xarray as xr
import numpy as np
import pandas as pd
import openmeteo_requests
import requests_cache
from retry_requests import retry
from datetime import timezone

from src.domain.ports import WeatherDataProvider
from src.domain.model import BoundingBox, TimeRange

class OpenMeteoAdapter(WeatherDataProvider):
    """
    Implementación de WeatherDataProvider usando la API de Open-Meteo.
    Utiliza FlatBuffers para transferencia eficiente.
    """
    def __init__(self):
        # Setup caching and retry mechanism
        # .cache directoy handles local caching of requests
        cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
        retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        self.client = openmeteo_requests.Client(session=retry_session)
        self.url = "https://api.open-meteo.com/v1/forecast"

    def get_forecast(self, region: BoundingBox, time_window: TimeRange) -> xr.Dataset:
        """
        Obtiene pronóstico de precipitación interpolando una malla de puntos.
        """
        # 1. Definir Grid de Consulta (Resolución "Coarse" para reducir llamadas)
        # En MVP: 0.25 grados (~25km) es el estándar de modelos globales como GFS.
        # ICON-D2 es 2km (0.02 deg), pero pedir cada punto es excesivo.
        # Pediremos 0.1 deg (~11km) y luego interpolaremos.
        resolution = 0.1 
        
        lats = np.arange(region.min_lat, region.max_lat, resolution)
        lons = np.arange(region.min_lon, region.max_lon, resolution)
        
        # Meshgrid para coordinadas
        # Nota: Open-Meteo espera arrays planos de lat/lon pareados.
        grid_lon, grid_lat = np.meshgrid(lons, lats)
        flat_lats = grid_lat.flatten()
        flat_lons = grid_lon.flatten()
        
        # 2. Configurar params API
        params = {
            "latitude": flat_lats,
            "longitude": flat_lons,
            "hourly": ["precipitation", "weather_code", "cloud_cover"],
            "start_date": time_window.start.strftime("%Y-%m-%d"),
            "end_date": time_window.end.strftime("%Y-%m-%d"),
            # 'best_match' usa ICON-D2 en Europa, GFS globalmente, etc.
            "models": "best_match" 
        }

        # 3. Llamada API (Retorna lista de objetos WeatherResponse, uno por punto)
        # WARNING: Si pedimos muchos puntos, esto puede ser lento en el cliente al procesar.
        responses = self.client.weather_api(self.url, params=params)
        
        # 4. Procesamiento a Xarray
        # Asumimos que todos los puntos devuelven la misma serie temporal (time steps)
        first_resp = responses[0]
        hourly = first_resp.Hourly()
        
        # Extraer tiempo
        start = hourly.Time()
        end = hourly.TimeEnd()
        interval = hourly.Interval()
        # Generar array de tiempos (segundos Unix a datetime)
        time_steps = pd.to_datetime(np.arange(start, end, interval), unit='s', utc=True)
        
        n_times = len(time_steps)
        n_points = len(responses)
        n_lats = len(lats)
        n_lons = len(lons)
        
        # Pre-alocar arrays para variables (Flat: Points x Time)
        # Queremos: (Time, Lat, Lon)
        # Estructura de responses: Lista de 'Locations'.
        
        # Extraer variables de cada respuesta
        # Indices de variables en 'hourly': 0->precip, 1->code, 2->cloud
        precip_values = np.zeros((n_points, n_times), dtype=np.float32)
        
        for i, response in enumerate(responses):
            # Nota: hourly.Variables(0) es precipitation
            precip_values[i] = response.Hourly().Variables(0).ValuesAsNumpy()
            
        # Reshape de (Points, Time) a (Lat, Lon, Time) para luego transponer a (Time, Lat, Lon)
        # Ojo con el orden del meshgrid y flatten.
        # grid_lat fue row-major default? meshgrid: x is columns (lon), y is rows (lat).
        # flatten default es 'C' (row-major): recorre filas (lats constantes) luego columnas?
        # Check numpy: flatten() row-major means process first row (lat[0], all lons), then second row...
        # So structure is (Lat, Lon).
        
        precip_3d = precip_values.reshape((n_lats, n_lons, n_times))
        
        # Transpose a (Time, Lat, Lon) que es el estándar meteorológico
        precip_3d = np.transpose(precip_3d, (2, 0, 1))
        
        # Crear Xarray Dataset
        ds = xr.Dataset(
            data_vars={
                "precipitation": (("time", "y", "x"), precip_3d),
            },
            coords={
                "time": time_steps,
                "y": lats,
                "x": lons
            },
            attrs={
                "source": "Open-Meteo",
                "crs": "EPSG:4326"
            }
        )
        
        return ds
