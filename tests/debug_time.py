import pandas as pd
import numpy as np
import xarray as xr
from datetime import datetime, timezone, timedelta

def test_time_index():
    # Simulate OpenMeteo timestamps
    start = 1672531200 # 2023-01-01 00:00:00 UTC
    end = 1672617600   # 2023-01-02 00:00:00 UTC
    interval = 3600
    
    time_steps = pd.to_datetime(np.arange(start, end, interval), unit='s', utc=True)
    print(f"Time steps dtype: {time_steps.dtype}")
    print(f"Time steps tz: {time_steps.tz}")
    
    ds = xr.Dataset(coords={"time": time_steps})
    print(f"DS time index: {ds.indexes['time']}")
    
    # Simulate User Input (Naive constructed, then forced to UTC)
    start_user = datetime(2023, 1, 1, 0, 0, 0)
    start_user = start_user.replace(tzinfo=timezone.utc)
    
    print(f"Query time: {start_user} (tz={start_user.tzinfo})")
    
    try:
        sel = ds.sel(time=start_user, method="nearest")
        print("Selection SUCCESS")
    except Exception as e:
        print(f"Selection FAILED: {e}")

    # What if we use Naive?
    start_naive = datetime(2023, 1, 1, 0, 0, 0)
    print(f"Query time naive: {start_naive}")
    try:
        sel = ds.sel(time=start_naive, method="nearest")
        print("Selection Naive SUCCESS")
    except Exception as e:
        print(f"Selection Naive FAILED: {e}")

if __name__ == "__main__":
    test_time_index()
