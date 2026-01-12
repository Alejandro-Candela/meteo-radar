import xarray as xr
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import sys
import os
import shutil
import rioxarray

# Ensure we can import src
sys.path.append(os.getcwd())

from src.application.exporter import BulkExportService
from src.domain.model import BoundingBox, TimeRange

# Mock Facade that can switch between UTC and Naive
class MockFacade:
    def __init__(self, mode='utc'):
        self.mode = mode

    def get_history_view(self, region, time_window, resolution):
        print(f"MockFacade ({self.mode}) received time_window: {time_window.start} to {time_window.end}")
        
        # Create timestamps
        freq = '1H'
        tz = 'UTC' if self.mode == 'utc' else None
        
        # We need to handle the fact that time_window might be mixed awareness if logic isn't perfect
        # But here we just produce the dataset requested by the test setup
        if time_window.start.tzinfo and self.mode == 'naive':
             s = time_window.start.replace(tzinfo=None)
             e = time_window.end.replace(tzinfo=None)
        else:
             s = time_window.start
             e = time_window.end
             
        times = pd.date_range(start=s, end=e, freq=freq, tz=tz)
        
        lats = [region.min_lat, region.max_lat]
        lons = [region.min_lon, region.max_lon]
        data = np.random.rand(len(times), 2, 2)
        
        ds = xr.Dataset(
            data_vars={'precipitation': (('time', 'y', 'x'), data)},
            coords={'time': times, 'y': lats, 'x': lons}
        )
        return ds

def test_dynamic_scenarios():
    bbox = (36.0, 37.0, -5.0, -4.0)
    resolution = 0.1
    interval = 1
    
    scenarios = [
        ("utc_ds_naive_input", "utc", None),
        ("naive_ds_naive_input", "naive", None),
        # ("utc_ds_aware_input", "utc", timezone.utc), # Less likely from streamlit but good to support
    ]
    
    for name, ds_mode, input_tz in scenarios:
        print(f"\n--- Testing Scenario: {name} ---")
        exporter = BulkExportService()
        exporter.facade = MockFacade(mode=ds_mode)
        
        start = datetime(2023, 1, 1, 0, 0, 0, tzinfo=input_tz)
        end = datetime(2023, 1, 2, 0, 0, 0, tzinfo=input_tz)
        
        try:
            zip_path, count = exporter.generate_bulk_zip(start, end, interval, bbox, resolution)
            print(f"SUCCESS: Generated {count} images.")
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except Exception as e:
            print(f"FAIL: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_dynamic_scenarios()
