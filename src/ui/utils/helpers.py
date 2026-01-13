import streamlit as st
import tempfile
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import os
import shutil
import xarray as xr
import rioxarray
from datetime import datetime
from src.adapters.supabase_client import SupabaseClient
import base64
import threading
import time

def inject_custom_css():
    st.markdown("""
        <style>
        html {
            font-size: 80% !important;
        }
        /* Compact Sliders */
        .stSlider {
            padding-top: 0rem !important;
            padding-bottom: 0rem !important;
        }
        div[data-testid="stSliderTickBar"] {
            display: none;
        }
        
        /* Legend Table Styles */
        .sidebar-legend {
            background-color: rgba(255, 255, 255, 0.1);
            padding: 10px;
            border-radius: 5px;
            margin-top: 20px;
            border: 1px solid rgba(0,0,0,0.1);
        }
        .legend-gradient {
            height: 10px;
            width: 100%;
            background: linear-gradient(to right, 
                rgba(0,0,0,0), 
                #7CFC00, 
                #32CD32, 
                #FFFF00, 
                #FF8C00, 
                #FF0000
            );
            border-radius: 5px;
            margin-bottom: 5px;
            border: 1px solid #ccc;
        }
        .legend-labels {
            display: flex;
            justify-content: space-between;
            color: gray;
            font-size: 0.8em;
        }
        
        /* Blue Slider for Prediction (Targeting by Label content) */
        div.stSlider:has(div[aria-label="Seleccionar hora futura"]) {
            --streamlit-theme-primary-color: #00BFFF !important;
            --primary-color: #00BFFF !important;
        }
        
        /* Compact Metrics */
        div[data-testid="stMetric"] {
            padding: 0px !important;
        }
        </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def get_supabase():
    try:
        return SupabaseClient()
    except:
        return None

def generate_colored_png(da: xr.DataArray, filename: str, colormap='viridis', vmin=None, vmax=None):
    """
    Saves the data array as a colored PNG image without geospatial metadata embedded.
    Enforces Lat Descending (North -> South) to match origin='upper'.
    Handles 'latitude'/'lat'/'y' and 'longitude'/'lon'/'x'.
    """
    t_start = time.time()
    # Identify coords
    lat_dim = None
    lon_dim = None
    
    for dim in ['latitude', 'lat', 'y']:
        if dim in da.coords:
            lat_dim = dim
            break
            
    for dim in ['longitude', 'lon', 'x']:
        if dim in da.coords:
            lon_dim = dim
            break

    # Sort Lat Descending (North -> South)
    if lat_dim:
        da = da.sortby(lat_dim, ascending=False)
        
    # Transpose to (Lat, Lon)
    if lat_dim and lon_dim and len(da.dims) >= 2:
        try:
            da = da.transpose(lat_dim, lon_dim)
        except Exception:
            pass

    # Normalize data
    data = da.values
    if vmin is None: vmin = np.nanmin(data)
    if vmax is None: vmax = np.nanmax(data)
    
    # Handle NaN for transparency
    # Create matplotlib Normalize
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    
    # Choose colormap
    if isinstance(colormap, list):
         cmap = mcolors.LinearSegmentedColormap.from_list("custom", colormap)
    else:
         cmap = plt.get_cmap(colormap)
         
    # Apply colormap (returns RGBA)
    colored_data = cmap(norm(data))
    
    # Set Alpha for NaNs
    mask = np.isnan(data)
    colored_data[mask] = [0, 0, 0, 0] # Transparent
    
    # Save using imsave (origin='upper' matches lat descending)
    plt.imsave(filename, colored_data, origin='upper', format='png')
    
    print(f"   [IMG] Pixels generated in {time.time()-t_start:.4f}s")


def _background_upload_task(client, da_bytes_or_copy, bbox, variable, timestamp, colormap, vmin, vmax):
    """
    Background worker to Handle TIFF generation (CPU Heavy) + Supabase Uploads (IO Heavy).
    """
    start_time = time.time()
    print(f"[BG] Starting persistence for {variable} @ {timestamp}...")
    
    tmp_png = None
    tmp_tif = None
    
    try:
        # 1. Setup Files
        tmp_png = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp_png.close()
        tmp_tif = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
        tmp_tif.close()
        
        # 2. Convert raw bytes/copy back to logic if needed, or just use da
        # For safety/simplicity we assume 'da_bytes_or_copy' is a safe separate instance or fast clone
        da = da_bytes_or_copy 
        
        # 3. Generate PNG (Redundant extraction but ensures clean file for upload)
        generate_colored_png(da, tmp_png.name, colormap, vmin, vmax)
        
        # 4. Generate TIFF (Heavy Operation)
        t_tiff = time.time()
        if not hasattr(da, 'rio'):
            import rioxarray
        
        if da.rio.crs is None:
             da.rio.write_crs("EPSG:4326", inplace=True)
             
        da.rio.to_raster(tmp_tif.name)
        print(f"   [BG] TIFF Generated in {time.time()-t_tiff:.3f}s")
        
        # 5. Upload BOTH
        # Even if PNG exists (local render), we want it on cloud for future cache
        t_up = time.time()
        client.upload_file(tmp_tif.name, bbox, variable, timestamp, ext=".tif", mime="image/tiff", bucket="radar_tiffs")
        client.upload_file(tmp_png.name, bbox, variable, timestamp, ext=".png", mime="image/png", bucket="radar_pngs")
        print(f"   [BG] Uploads completed in {time.time()-t_up:.3f}s")
        
        print(f"[BG] Task COMPLETED for {variable} in {time.time()-start_time:.3f}s")

    except Exception as e:
        print(f"[BG] ERROR in background task: {e}")
    finally:
        # Cleanup
        try:
            if tmp_png: os.remove(tmp_png.name)
            if tmp_tif: os.remove(tmp_tif.name)
        except:
            pass


def get_or_upload_layer(client, da: xr.DataArray, variable: str, bbox: tuple, timestamp: datetime, colormap='viridis', vmin=None, vmax=None) -> str:
    """
    OPTIMIZED for Speed Parity:
    1. IMMEDAITELY generates PNG locally and returns Base64 (Blocking only for rendering).
    2. Spawns Background Thread to handle TIFF conversion + Cloud Uploads.
    """
    t_start = time.time()
    print(f"[LAYER] Request: {variable} | {timestamp.strftime('%H:%M')}")

    # 0. Check Session Cache (RAM)
    if 'layer_cache' not in st.session_state:
        st.session_state['layer_cache'] = {}
        
    cache_key = f"{bbox}_{variable}_{timestamp.isoformat()}_{colormap}"
    
    # If valid cache, return immediately
    if cache_key in st.session_state['layer_cache']:
        # print(f"   [CACHE] Hit! ({time.time()-t_start:.4f}s)")
        return st.session_state['layer_cache'][cache_key]

    # 1. Fast Path: Generate Local PNG for Map
    tmp_png = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp_png.close()
    
    base64_url = ""
    
    try:
        # Generate Pixels
        generate_colored_png(da, tmp_png.name, colormap, vmin, vmax)
        
        # Read as Base64
        with open(tmp_png.name, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode()
        base64_url = f"data:image/png;base64,{b64_data}"
        
        # Cache RAM
        st.session_state['layer_cache'][cache_key] = base64_url
        print(f"   [UI] Ready to render in {time.time()-t_start:.4f}s")
        
    except Exception as e:
        print(f"   [ERROR] Generating local preview: {e}")
        return ""
    finally:
        try:
             os.remove(tmp_png.name)
        except:
             pass

    # 2. Persistence Path: Background Thread (If Client is Available)
    if client:
        # Clone DataArray to ensure thread safety (shallow copy is usually enough for reading, deep if needed)
        # Using .copy(deep=True) is safer but slower. 
        # Since we are just reading, shallow copy + in-memory data is fine.
        da_safe = da.copy() 
        
        t = threading.Thread(
            target=_background_upload_task,
            args=(client, da_safe, bbox, variable, timestamp, colormap, vmin, vmax),
            name=f"Upload-{variable}-{timestamp.strftime('%H%M')}"
        )
        t.daemon = True
        t.start()
        print(f"   [THREAD] Background Persistence Started.")
    else:
        print("   [WARN] No Supabase Client - Skipping Persistence.")

    return base64_url

def get_radar_legend_html():
    return """
    <div class="sidebar-legend">
        <label>Intensidad de Lluvia (mm/h)</label>
        <div class="legend-gradient"></div>
        <div class="legend-labels">
            <span>Ligera</span>
            <span>Moderada</span>
            <span>Intensa</span>
            <span>Torrencial</span>
        </div>
    </div>
    """
