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
    
    def get_radar_view(
        self, 
        region: BoundingBox, 
        time_window: TimeRange,
        high_resolution: bool = True
    ) -> xr.Dataset:
        """
        Devuelve la vista de 'Radar' completa: Datos obtenidos + Interpolados.
        """
        # 1. Obtener datos crudos (Estrategia seleccionada)
        raw_ds = self.provider.get_forecast(region, time_window)
        
        if not high_resolution:
            return raw_ds
            
        # 2. Aplicar interpolación (Dominio)
        # 0.01 grados approx 1.1km latitud -> resolución tipo Radar
        interpolated_ds = InterpolationService.interpolate(
            raw_ds, 
            target_resolution=0.01, 
            method="linear" # Cubic es mas suave pero mas lento y puede generar artefactos negativos
        )
        
        # 3. Post-procesamiento opcional (Filtro Gaussiano para 'nubes', Clipping)
        # Aseguramos que no haya precipitacion negativa por artefactos de interpolación
        if 'precipitation' in interpolated_ds:
             interpolated_ds['precipitation'] = interpolated_ds['precipitation'].clip(min=0)
             
        return interpolated_ds
