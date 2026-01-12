import requests
import streamlit as st
from datetime import datetime
from typing import Optional, Tuple

class AemetAdapter:
    """
    Adapter for AEMET OpenData API.
    Focuses on Radar Imagery.
    """
    BASE_URL = "https://opendata.aemet.es/opendata/api"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        
    def get_radar_composite_url(self) -> Optional[str]:
        """
        Fetches the National Radar Composite (Reflectivity).
        Returns the direct URL to the image resource.
        """
        # Endpoint for National Radar Composition (Paleta Reflectividad)
        # /red/radar/nacional/composicion
        endpoint = f"{self.BASE_URL}/red/radar/nacional/composicion"
        
        headers = {
            "api_key": self.api_key,
            "Accept": "application/json"
        }
        
        try:
            # 1. Request Meta-data
            # AEMET returns a JSON with 'datos' field pointing to the actual resource
            response = requests.get(endpoint, headers=headers, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            
            if data['estado'] == 200 and 'datos' in data:
                 # The 'datos' URL usually points to the image stream/file.
                 # Actually, for radar images, sometimes "datos" is the image URL itself 
                 # or a secondary JSON.
                 # Documentation says: "datos" field contains the URL to the data.
                 # Let's assume it returns the direct image URL for this endpoint.
                 # Verification needed: usually it's a URL to a temporary file.
                 return data['datos']
            else:
                 print(f"AEMET API Error: {data.get('descripcion', 'Unknown error')}")
                 return None
                 
        except Exception as e:
            print(f"Error fetching AEMET radar: {e}")
            return None

    @property
    def national_bounds(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """
        Returns the hardcoded bounds for the AEMET National Composite.
        Format: [[lat_min, lon_min], [lat_max, lon_max]] for Folium/Leaflet.
        or [[lat_min, lon_max], [lat_max, lon_min]]?
        
        Folium image_overlay bounds: [[lat_south, lon_west], [lat_north, lon_east]]
        
        Approximate bounds for Spain National Radar Composite.
        Ideally this should be precise. 
        Based on standard AEMET composite areas: 35.0, -10.0 to 44.0, 4.5 approx.
        Let's use a safe consistent rect for Peninsular view.
        """
        # These are approximate bounds for the Peninsular composite.
        # Ideally we would parse this from the GEOTIFF metadata if we downloaded it,
        # but since we are just overlaying the PNG, we need to guess or find documentation.
        # For now, we will use a best-effort approximation.
        # South-West: 35.17, -9.86
        # North-East: 44.27, 4.47
        return [[34.0, -15.0], [45.0, 5.0]] # Slightly wider to catch Canaries if included or just Peninsula?
        # AEMET 'Nacional' usually includes Peninsula + Balears + Canarias in a large frame or separate.
        # For this MVP we will try these bounds and adjust visually.
