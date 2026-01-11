import os
import hashlib
from typing import Optional
from datetime import datetime
from supabase import create_client, Client
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(env_path)

class SupabaseClient:
    def __init__(self):
        # Try finding keys in Env, then st.secrets
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")

        if not url or not key:
            try:
                import streamlit as st
                url = st.secrets["SUPABASE_URL"]
                key = st.secrets["SUPABASE_KEY"]
            except Exception:
                pass
        
        if not url or not key:
             raise ValueError("Supabase Keys not found in environment or secrets.")
        
        self.client: Client = create_client(url, key)
        self.bucket = "radar_cache"
        self.table = "cache_entries"

    def _generate_filename(self, region_hash: str, variable: str, timestamp: datetime) -> str:
        # e.g. 20261011_1200_precipitation_hash123.tif
        ts_str = timestamp.strftime("%Y%m%d_%H%M")
        return f"{ts_str}_{variable}_{region_hash}.tif"

    def _get_region_hash(self, bbox_tuple: tuple) -> str:
        # Simple hash of bbox coordinates to identify "same region"
        s = f"{bbox_tuple[0]:.2f}_{bbox_tuple[1]:.2f}_{bbox_tuple[2]:.2f}_{bbox_tuple[3]:.2f}"
        return hashlib.md5(s.encode()).hexdigest()[:8]

    def get_tiff_url(self, bbox: tuple, variable: str, timestamp: datetime) -> Optional[str]:
        """
        Checks DB for existing cache entry. 
        Returns the Public URL of the file if found, else None.
        """
        region_hash = self._get_region_hash(bbox)
        # We need a predictable filename OR query by metadata
        # Query DB
        try:
             # Find matching entry
             response = self.client.table(self.table)\
                 .select("filename")\
                 .eq("region_hash", region_hash)\
                 .eq("variable", variable)\
                 .eq("timestamp", timestamp.isoformat())\
                 .execute()
             
             if response.data and len(response.data) > 0:
                 filename = response.data[0]['filename']
                 # Get Public URL
                 return self.client.storage.from_(self.bucket).get_public_url(filename)
             return None
        except Exception as e:
            print(f"Supabase Read Error: {e}")
            return None

    def upload_tiff(self, file_path: str, bbox: tuple, variable: str, timestamp: datetime) -> Optional[str]:
        """
        Uploads a local TIFF -> Supabase Storage -> Records in DB.
        Returns the Public URL.
        """
        region_hash = self._get_region_hash(bbox)
        filename = self._generate_filename(region_hash, variable, timestamp)
        
        try:
            # 1. Upload to Storage
            with open(file_path, 'rb') as f:
                self.client.storage.from_(self.bucket).upload(
                    file=f,
                    path=filename,
                    file_options={"content-type": "image/tiff", "upsert": "true"}
                )
            
            # 2. Record in DB
            self.client.table(self.table).upsert({
                "filename": filename,
                "variable": variable,
                "timestamp": timestamp.isoformat(),
                "region_hash": region_hash
            }).execute()
            
            return self.client.storage.from_(self.bucket).get_public_url(filename)
            
        except Exception as e:
            print(f"Supabase Upload Error: {e}")
            return None
