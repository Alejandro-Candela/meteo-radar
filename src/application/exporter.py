import os
import zipfile
import tempfile
from datetime import datetime, timedelta
import pandas as pd
import xarray as xr
from typing import Tuple, List
import shutil

# Importing facade or adapter directly? 
# Better to use the existing abstractions. We need to fetch data.
# Since app.py uses functions to fetch data, we might need to refactor fetching logic 
# or import it. However, the fetching logic in app.py is tied to Streamlit caching.
# We should probably define a cleaner interface or pass the data fetcher.
# For now, we will replicate the fetch pattern using the Domain/Adapter 
# or accept the Facade instance.

# Let's import the necessary modules to reconstruct the fetch
from src.adapters.openmeteo import OpenMeteoAdapter
from src.application.facade import MeteorologicalFacade
from src.domain.model import BoundingBox, TimeRange

class BulkExportService:
    def __init__(self):
        self.adapter = OpenMeteoAdapter()
        self.facade = MeteorologicalFacade(self.adapter)

    def generate_bulk_zip(
        self, 
        start_date: datetime, 
        end_date: datetime, 
        interval_hours: int, 
        region_bbox: Tuple[float, float, float, float], 
        resolution: float
    ) -> Tuple[str, int]:
        """
        Generates a ZIP file containing TIFF images for the specified range and interval.
        Returns: (zip_file_path, image_count)
        """
        min_lat, max_lat, min_lon, max_lon = region_bbox
        bbox = BoundingBox(min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon)
        
        # Extend range to ensure we cover the full requested period
        # OpenMeteo works with days.
        tr = TimeRange(start=start_date, end=end_date + timedelta(days=1)) 
        
        # Fetch ONE dataset covering the whole range (OpenMeteo Forecast endpoint handles recent past)
        # using get_history_view which returns interpolated data
        ds = self.facade.get_history_view(bbox, tr, resolution)
        
        # Create Temp Dir for Tiffs
        tmp_dir = tempfile.mkdtemp()
        tiff_dir = os.path.join(tmp_dir, "tiffs")
        os.makedirs(tiff_dir, exist_ok=True)
        
        image_count = 0
        
        # Iterate and Save
        current_time = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        # Determine strict cutoff
        # Ensure we don't go beyond user request
        final_cutoff = end_date + timedelta(days=1) - timedelta(seconds=1)

        while current_time <= final_cutoff:
            try:
                # Select frame (nearest to handle potential slight offsets, though ideally exact)
                # ds has 'precipitation' data_var
                frame = ds['precipitation'].sel(time=current_time, method="nearest", tolerance=timedelta(minutes=30))
                
                # Create Structure: /YYYY/MM/DD/filename.tiff
                year = current_time.strftime("%Y")
                month = current_time.strftime("%m")
                day = current_time.strftime("%d")
                
                day_dir = os.path.join(tiff_dir, year, month, day)
                os.makedirs(day_dir, exist_ok=True)
                
                fname = list(current_time.timetuple())[0:5] # Y, M, D, H, M
                filename = f"{fname[0]}_{fname[1]:02d}_{fname[2]:02d}_{fname[3]:02d}_{fname[4]:02d}.tiff"
                full_path = os.path.join(day_dir, filename)
                
                # Write GeoTIFF using rio accessor (already loaded by facade imports usually, but ensuring)
                # Ensure CRS is written (Facade might set it in attrs but rio needs write_crs)
                frame = frame.rio.write_crs("EPSG:4326")
                frame.rio.to_raster(full_path)
                
                image_count += 1
            except (KeyError, ValueError):
                # Data might be missing for this specific time
                pass
            
            current_time += timedelta(hours=interval_hours)
            
        # Zip It
        zip_filename = f"meteo_radar_{start_date.strftime('%Y_%m_%d')}_{end_date.strftime('%Y_%m_%d')}.zip"
        zip_path = os.path.join(tmp_dir, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(tiff_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, tiff_dir)
                    zipf.write(file_path, arcname)
                    
        return zip_path, image_count

