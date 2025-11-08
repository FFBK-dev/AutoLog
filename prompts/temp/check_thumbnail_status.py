#!/usr/bin/env python3
"""
Check the current state of S00001-S00005 thumbnails and file paths
"""

import sys
import os
import warnings
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "server_path": "SPECS_Filepath_Server",
    "thumbnail": "SPECS_Thumbnail"
}

def check_record(stills_id, token):
    """Check a single record's current state."""
    try:
        print(f"\n{'='*80}")
        print(f"Checking {stills_id}...")
        print(f"{'='*80}")
        
        # Find the record
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        print(f"Record ID: {record_id}")
        
        # Get the record data
        record_data = config.get_record(token, "Stills", record_id)
        
        # Check server path
        server_path = record_data.get(FIELD_MAPPING["server_path"])
        print(f"\nServer Path Field Value:")
        print(f"  {server_path}")
        
        # Check if file exists
        if server_path and os.path.exists(server_path):
            print(f"  ✅ File exists at this path")
            file_size = os.path.getsize(server_path)
            print(f"  📊 File size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
        else:
            print(f"  ❌ File NOT found at this path")
        
        # Check thumbnail field
        thumbnail_value = record_data.get(FIELD_MAPPING["thumbnail"])
        print(f"\nThumbnail Field Value:")
        print(f"  {thumbnail_value}")
        print(f"  Type: {type(thumbnail_value)}")
        
        if isinstance(thumbnail_value, str):
            print(f"  Length: {len(thumbnail_value)} characters")
            if thumbnail_value.startswith("filemac:"):
                print(f"  ✅ Appears to be a file reference")
            elif thumbnail_value.startswith("file:"):
                print(f"  ⚠️ Using 'file:' prefix (should be 'filemac:' for macOS)")
            else:
                print(f"  ℹ️ Unknown format")
        
        return True
        
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("="*80)
    print("CHECKING S00001-S00005 THUMBNAIL STATUS")
    print("="*80)
    
    # Get FileMaker token
    token = config.get_token()
    
    # Check S00001 through S00005
    stills_ids = ["S00001", "S00002", "S00003", "S00004", "S00005"]
    
    for stills_id in stills_ids:
        check_record(stills_id, token)
    
    print(f"\n{'='*80}")
    print("Check complete!")
    print("="*80)

