import streamlit as st
from datetime import datetime, timedelta, timezone
from src.adapters.openmeteo import OpenMeteoAdapter
from src.application.facade import MeteorologicalFacade
from src.domain.model import BoundingBox, TimeRange

@st.cache_resource
def get_facade():
    adapter = OpenMeteoAdapter()
    return MeteorologicalFacade(provider=adapter)

@st.cache_resource(ttl=3600, show_spinner=False)
def fetch_data_blocks(min_lat, max_lat, min_lon, max_lon, resolution):
    """
    Fetches both History (Past 3 days) and Forecast (Next 3 days).
    Returns two separate datasets.
    Uses cache_resource to avoid pickling large Xarray datasets.
    """
    facade = get_facade()
    bbox = BoundingBox(
        min_lat=min_lat, max_lat=max_lat,
        min_lon=min_lon, max_lon=max_lon
    )
    
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    
    # 1. History Block (Last 15 days)
    history_start = now - timedelta(days=15)
    history_window = TimeRange(start=history_start, end=now)
    ds_history = facade.get_history_view(bbox, history_window, resolution=resolution)
    
    # Subsample History to every 2 hours
    if ds_history is not None:
         ds_history = ds_history.sel(time=slice(None, None, 2))
    
    # 2. Forecast Block (Next 10 days)
    forecast_end = now + timedelta(days=10)
    forecast_window = TimeRange(start=now, end=forecast_end)
    ds_forecast = facade.get_forecast_view(bbox, forecast_window, resolution=resolution)
    
    return ds_history, ds_forecast
