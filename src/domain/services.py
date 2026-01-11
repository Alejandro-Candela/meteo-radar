import xarray as xr
import numpy as np
from .model import BoundingBox

class InterpolationService:
    """
    Servicio de dominio puro encargado de transformar la resolución de los datos.
    Utiliza algoritmos de Scipy optimizados a través de Xarray.
    """
    
    @staticmethod
    def interpolate(ds: xr.Dataset, target_resolution: float = 0.01, method: str = "linear") -> xr.Dataset:
        """
        Aumenta la resolución espacial del dataset mediante interpolación.
        
        Args:
            ds (xr.Dataset): Dataset original con coordenadas 'x' (lon) e 'y' (lat).
            target_resolution (float): Nueva resolución en grados (Default 0.01deg ~= 1km).
            method (str): Método de interpolación ('linear', 'nearest', 'cubic').
            
        Returns:
            xr.Dataset: Nuevo dataset con la malla re-muestreada.
        """
        # Obtenemos los límites actuales
        min_lon = ds.x.min().item()
        max_lon = ds.x.max().item()
        min_lat = ds.y.min().item()
        max_lat = ds.y.max().item()
        
        # Generamos la nueva malla densa
        new_lons = np.arange(min_lon, max_lon, target_resolution)
        new_lats = np.arange(min_lat, max_lat, target_resolution)
        
        # Xarray interp realiza la interpolación N-dimensional automáticamente.
        # Es eficiente porque usa scipy.interpolate.interp1d/interpn internamente.
        interpolated_ds = ds.interp(
            y=new_lats, 
            x=new_lons, 
            method=method,
            kwargs={"fill_value": "extrapolate"} # Evitar NaNs en bordes
        )
        
        interpolated_ds.attrs["processing"] = f"Interpolated with {method} at {target_resolution} deg"
        return interpolated_ds
