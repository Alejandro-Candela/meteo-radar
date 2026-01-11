from datetime import datetime
from pydantic import BaseModel, Field

class BoundingBox(BaseModel):
    """
    Representa un área geográfica rectangular.
    """
    min_lat: float = Field(..., ge=-90, le=90, description="Latitud mínima (Sur)")
    max_lat: float = Field(..., ge=-90, le=90, description="Latitud máxima (Norte)")
    min_lon: float = Field(..., ge=-180, le=180, description="Longitud mínima (Oeste)")
    max_lon: float = Field(..., ge=-180, le=180, description="Longitud máxima (Este)")

class TimeRange(BaseModel):
    """
    Representa una ventana de tiempo para la predicción.
    """
    start: datetime
    end: datetime
