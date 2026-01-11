from abc import ABC, abstractmethod
import xarray as xr
from .model import BoundingBox, TimeRange

class WeatherDataProvider(ABC):
    """
    Interfaz Strategy para proveedores de datos meteorológicos.
    """
    @abstractmethod
    def get_forecast(self, region: BoundingBox, time_window: TimeRange) -> xr.Dataset:
        """
        Obtiene el pronóstico o datos observados para una región y tiempo dados.

        Args:
            region (BoundingBox): Área de interés.
            time_window (TimeRange): Ventana temporal.

        Returns:
            xr.Dataset: Cubo de datos normalizado (time, y, x) con variables estándar.
        """
        pass
