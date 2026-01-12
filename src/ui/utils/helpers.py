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


def get_or_upload_layer(client, da: xr.DataArray, variable: str, bbox: tuple, timestamp: datetime, colormap='viridis', vmin=None, vmax=None) -> str:
    """
    Ensures BOTH PNG (for map) and TIFF (for download) exist in Supabase.
    Uses st.session_state to cache URLs and avoid repeated DB calls.
    Returns: URL of the PNG for rendering.
    """
    # 0. Check Session Cache (RAM)
    if 'layer_cache' not in st.session_state:
        st.session_state['layer_cache'] = {}
        
    cache_key = f"{bbox}_{variable}_{timestamp.isoformat()}_{colormap}"
    if cache_key in st.session_state['layer_cache']:
        # print(f"DEBUG: Cache Hit for {cache_key}")
        return st.session_state['layer_cache'][cache_key]

    # 1. Local Fallback (if no client)
    if client is None:
        # Just generate PNG locally for map
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        generate_colored_png(da, tmp.name, colormap, vmin, vmax)
        return tmp.name
        
    # 2. Check Exists (PNG is the critical one for map)
    # Use "radar_pngs" bucket
    png_url = client.get_layer_url(bbox, variable, timestamp, ext=".png", bucket="radar_pngs")

    if png_url:
        st.session_state['layer_cache'][cache_key] = png_url
        return png_url
        
    # 3. Not found, Generate & Upload BOTH
    
    # A) Generate PNG (Local)
    tmp_png = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp_png.close()
    
    # B) Generate TIFF (Local)
    tmp_tif = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
    tmp_tif.close()
    
    try:
        # Create PNG
        generate_colored_png(da, tmp_png.name, colormap, vmin, vmax)
        
        # Create TIFF (using existing logic pattern or rioxarray)
        # We need to ensure CRS is set for rioxarray
        if da.rio.crs is None:
             da.rio.write_crs("EPSG:4326", inplace=True)
        
        da.rio.to_raster(tmp_tif.name)
        
        # C) Upload TIFF (to radar_tiffs)
        client.upload_file(tmp_tif.name, bbox, variable, timestamp, ext=".tif", mime="image/tiff", bucket="radar_tiffs")
        
        # D) Upload PNG (to radar_pngs) - This returns the URL we need
        final_url = client.upload_file(tmp_png.name, bbox, variable, timestamp, ext=".png", mime="image/png", bucket="radar_pngs")
        
        # Cleanup
        try:
            os.remove(tmp_png.name)
            os.remove(tmp_tif.name)
        except:
            pass
            
        if final_url:
             st.session_state['layer_cache'][cache_key] = final_url
             return final_url
        
        return tmp_png.name

    except Exception as e:
        print(f"Error dual-uploading: {e}")
        # Fallback to local path if upload fails
        return tmp_png.name

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
