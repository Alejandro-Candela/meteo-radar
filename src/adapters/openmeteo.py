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
        # Definir variables a pedir
        requested_vars = [
            "precipitation", 
            "temperature_2m", 
            "surface_pressure", 
            "wind_speed_10m", 
            "wind_direction_10m",
            "relative_humidity_2m",
            "apparent_temperature",
            "cloud_cover",
            "wind_gusts_10m"
        ]
        
        # Mapping API names to Internal names
        name_map = {
            "precipitation": "precipitation",
            "temperature_2m": "temperature",
            "surface_pressure": "pressure",
            "wind_speed_10m": "wind_speed",
            "wind_direction_10m": "wind_direction",
            "relative_humidity_2m": "humidity",
            "apparent_temperature": "apparent_temp",
            "cloud_cover": "cloud_cover",
            "wind_gusts_10m": "wind_gusts"
        }

        params = {
            "latitude": flat_lats,
            "longitude": flat_lons,
            "hourly": requested_vars,
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
        
        # Prepare Data Dict
        data_arrays = {}
        
        # Initialize containers
        # We need a dict of numpy arrays: { "temp": np.zeros(...) }
        temp_containers = {}
        for var_api in requested_vars:
            internal_name = name_map[var_api]
            temp_containers[internal_name] = np.zeros((n_points, n_times), dtype=np.float32)
            
        # Fill containers
        for i, response in enumerate(responses):
            hourly_data = response.Hourly()
            for v_idx, var_api in enumerate(requested_vars):
                 internal_name = name_map[var_api]
                 # ValuesAsNumpy casts to float32 usually
                 temp_containers[internal_name][i] = hourly_data.Variables(v_idx).ValuesAsNumpy()
        
        # Reshape and add to DataVars
        data_vars_dict = {}
        for internal_name, flat_data in temp_containers.items():
            # Reshape (N_Points, Time) -> (Lat, Lon, Time)
            # Correct logic:
            # Grid was constructed with meshgrid(lons, lats).
            # Flatten order: default C (row-major). 
            # So rows are Lats, Cols are Lons.
            
            # NOTE: flat_lats = grid_lat.flatten()
            # If shape was (N_Lats, N_Lons), flatten walks Lons then Lats?
            # grid_lon, grid_lat = meshgrid(lons, lats) -> shape (N_Lats, N_Lons)
            # flatten() -> [ (lat0, lon0), (lat0, lon1)... ]
            # So first dimension of reshape should be N_Lats, second N_Lons.
            
            reshaped = flat_data.reshape((n_lats, n_lons, n_times))
            
            # Transpose to (Time, Lat, Lon) standard Xarray
            reshaped = np.transpose(reshaped, (2, 0, 1))
            
            data_vars_dict[internal_name] = (("time", "y", "x"), reshaped)

        ds = xr.Dataset(
            data_vars=data_vars_dict,
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
