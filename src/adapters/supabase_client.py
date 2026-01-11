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

    def _generate_filename(self, region_hash: str, variable: str, timestamp: datetime, ext=".tif") -> str:
        # e.g. 20261011_1200_precipitation_hash123.png
        ts_str = timestamp.strftime("%Y%m%d_%H%M")
        return f"{ts_str}_{variable}_{region_hash}{ext}"

    def _get_region_hash(self, bbox_tuple: tuple) -> str:
        # Simple hash of bbox coordinates to identify "same region"
        s = f"{bbox_tuple[0]:.2f}_{bbox_tuple[1]:.2f}_{bbox_tuple[2]:.2f}_{bbox_tuple[3]:.2f}"
        return hashlib.md5(s.encode()).hexdigest()[:8]

    def get_layer_url(self, bbox: tuple, variable: str, timestamp: datetime, ext=".tiff", bucket="radar_tiffs") -> Optional[str]:
        """
        Checks DB for existing cache entry. 
        Returns the Public URL of the file if found, else None.
        """
        region_hash = self._get_region_hash(bbox)
        try:
             # Find matching entry with correct extension/filename pattern
             # We filter by filename extension implicitly via the 'ext' arg check or DB Query
             # We should probably filter by filename 'like' logic or just matching filename construction
             
             expected_filename = self._generate_filename(region_hash, variable, timestamp, ext)
             
             # Check if file exists in DB registry (optional, for metadata)
             # But for Speed, we could just check Storage direct? 
             # No, better to check DB to ensure we "know" it's there.
             
             response = self.client.table(self.table)\
                 .select("filename")\
                 .eq("filename", expected_filename)\
                 .execute()
             
             if response.data and len(response.data) > 0:
                 # It exists in DB, assume it exists in Bucket
                 return self.client.storage.from_(bucket).get_public_url(expected_filename)
             return None
        except Exception as e:
            # print(f"Supabase Read Error: {e}")
            return None

    def upload_file(self, file_path: str, bbox: tuple, variable: str, timestamp: datetime, ext=".png", mime="image/png", bucket="radar_pngs") -> Optional[str]:
        """
        Uploads a local file -> Supabase Storage -> Records in DB.
        Returns the Public URL.
        """
        region_hash = self._get_region_hash(bbox)
        filename = self._generate_filename(region_hash, variable, timestamp, ext)
        
        try:
            # 1. Upload to Storage
            with open(file_path, 'rb') as f:
                self.client.storage.from_(bucket).upload(
                    file=f,
                    path=filename,
                    file_options={"content-type": mime, "upsert": "true"}
                )
            
            # 2. Record in DB
            # We treat filename as unique Key.
            self.client.table(self.table).upsert({
                "filename": filename,
                "variable": variable,
                "timestamp": timestamp.isoformat(),
                "region_hash": region_hash
            }).execute()
            
            return self.client.storage.from_(bucket).get_public_url(filename)
            
        except Exception as e:
            print(f"Supabase Upload Error: {e}")
            return None
            return None
