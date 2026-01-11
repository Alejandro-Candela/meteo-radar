import xarray as xr
from typing import Optional
from src.domain.ports import WeatherDataProvider
from src.domain.model import BoundingBox, TimeRange
from src.domain.services import InterpolationService

class MeteorologicalFacade:
    """
    Fachada principal de la aplicación.
    Orquesta la obtención de datos y su post-procesamiento.
    Oculta la complejidad de fuentes y algoritmos al UI.
    """
    
    def __init__(self, provider: WeatherDataProvider):
        self.provider = provider
        # En el futuro, aquí inyectaremos el repositorio de caché
    
    def get_forecast_view(
        self, 
        region: BoundingBox, 
        time_window: TimeRange,
        resolution: float = 0.01
    ) -> xr.Dataset:
        """
        Devuelve el pronóstico futuro interpolado.
        """
        raw_ds = self.provider.get_forecast(region, time_window)
        return self._process_dataset(raw_ds, resolution)

    def get_history_view(
        self, 
        region: BoundingBox, 
        time_window: TimeRange,
        resolution: float = 0.01
    ) -> xr.Dataset:
        """
        Devuelve el histórico interpolado.
        """
        # En el adapter usamos get_history (que actualmente reusa _fetch_openmeteo)
        if hasattr(self.provider, 'get_history'):
            raw_ds = self.provider.get_history(region, time_window)
        else:
            # Fallback
            raw_ds = self.provider.get_forecast(region, time_window)
            
        return self._process_dataset(raw_ds, resolution)

    def _process_dataset(self, raw_ds: xr.Dataset, resolution: float) -> xr.Dataset:
        # 2. Aplicar interpolación (Dominio)
        # target_resolution define la calidad final (0.01=High, 0.05=Low)
        interpolated_ds = InterpolationService.interpolate(
            raw_ds, 
            target_resolution=resolution, 
            method="linear" 
        )
        
        # 3. Post-procesamiento
        if 'precipitation' in interpolated_ds:
             interpolated_ds['precipitation'] = interpolated_ds['precipitation'].clip(min=0)
             
        return interpolated_ds
