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
        Obtiene pronóstico futuro (Forecast API).
        """
        return self._fetch_openmeteo(region, time_window, is_history=False)

    def get_history(self, region: BoundingBox, time_window: TimeRange) -> xr.Dataset:
        """
        Obtiene datos históricos (Forecast API con past_days o Archive API).
        Para los últimos 10 días, la Forecast API con 'past_days' suele funcionar 
        y es más consistente (mismo modelo).
        """
        # Usamos la misma lógica base pero conceptualmente separado
        return self._fetch_openmeteo(region, time_window, is_history=False)

    def _fetch_openmeteo(self, region: BoundingBox, time_window: TimeRange, is_history: bool) -> xr.Dataset:
        # 1. Definir Grid de Consulta Optimizado
        # Open-Meteo GET requests have URL length limits.
        # We must limit the number of points requested.
        # Max ~150 points keeps URL safe (~4-6kb).
        MAX_POINTS = 100
        
        lat_span = region.max_lat - region.min_lat
        lon_span = region.max_lon - region.min_lon
        
        # Calculate resolution to stay within MAX_POINTS
        # (lat_points * lon_points) = (span/res) * (span/res) = MAX_POINTS
        # res = sqrt((lat_span * lon_span) / MAX_POINTS)
        resolution = np.sqrt((lat_span * lon_span) / MAX_POINTS)
        
        # Ensure minimal resolution (e.g. not denser than 0.05)
        resolution = max(0.05, resolution)
        
        lats = np.arange(region.min_lat, region.max_lat, resolution)
        lons = np.arange(region.min_lon, region.max_lon, resolution)
        
        # Meshgrid para coordinadas
        grid_lon, grid_lat = np.meshgrid(lons, lats)
        flat_lats = grid_lat.flatten()
        flat_lons = grid_lon.flatten()
        
        # Calculamos start/end
        start_str = time_window.start.strftime("%Y-%m-%d")
        end_str = time_window.end.strftime("%Y-%m-%d")

        # 2. Configurar params API
        params = {
            "latitude": flat_lats,
            "longitude": flat_lons,
            "hourly": ["precipitation", "weather_code", "cloud_cover"],
            "start_date": start_str,
            "end_date": end_str,
            "models": "best_match"
        }

        # 3. Llamada API
        responses = self.client.weather_api(self.url, params=params)
        
        # 4. Procesamiento a Xarray
        first_resp = responses[0]
        hourly = first_resp.Hourly()
        
        # Extraer tiempo
        start = hourly.Time()
        end = hourly.TimeEnd()
        interval = hourly.Interval()
        time_steps = pd.to_datetime(np.arange(start, end, interval), unit='s', utc=True)
        
        n_times = len(time_steps)
        n_points = len(responses)
        n_lats = len(lats)
        n_lons = len(lons)
        
        precip_values = np.zeros((n_points, n_times), dtype=np.float32)
        
        for i, response in enumerate(responses):
            precip_values[i] = response.Hourly().Variables(0).ValuesAsNumpy()
            
        precip_3d = precip_values.reshape((n_lats, n_lons, n_times))
        precip_3d = np.transpose(precip_3d, (2, 0, 1))
        
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
