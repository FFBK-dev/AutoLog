#!/usr/bin/env python3
"""
TEMPORARY SCRIPT: Convert S00001-S00005 thumbnails to file references (v2)
Uses the corrected SPECS_Filepath_Server paths
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

def update_thumbnail_to_reference(stills_id, token):
    """Update a single record's thumbnail to be a file reference."""
    try:
        print(f"\n🔄 Processing {stills_id}...")
        
        # Find the record
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        print(f"  -> Found record ID: {record_id}")
        
        # Get the server path
        record_data = config.get_record(token, "Stills", record_id)
        server_path = record_data.get(FIELD_MAPPING["server_path"])
        
        if not server_path:
            print(f"  -> ❌ ERROR: No server path found for {stills_id}")
            return False
        
        print(f"  -> Server path: {server_path}")
        
        # Verify the file exists
        if not os.path.exists(server_path):
            print(f"  -> ❌ ERROR: File does not exist at: {server_path}")
            return False
        
        file_size = os.path.getsize(server_path)
        print(f"  -> ✅ File exists ({file_size:,} bytes / {file_size/1024/1024:.2f} MB)")
        
        # Create FileMaker container reference format for macOS
        # Format: filemac:/VolumeName/path
        # This should display the image content, not just an icon
        if server_path.startswith("/Volumes/"):
            # Remove /Volumes/ prefix and use filemac:
            path_without_volumes = server_path.replace("/Volumes/", "", 1)
            container_reference = f"filemac:/{path_without_volumes}"
        else:
            print(f"  -> ⚠️ WARNING: Path doesn't start with /Volumes/")
            container_reference = f"file:{server_path}"
        
        print(f"  -> Container reference: {container_reference}")
        
        # Update the thumbnail field with the reference
        payload = {FIELD_MAPPING["thumbnail"]: container_reference}
        config.update_record(token, "Stills", record_id, payload)
        
        print(f"  -> ✅ Successfully updated thumbnail to reference")
        return True
        
    except Exception as e:
        print(f"  -> ❌ ERROR updating {stills_id}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 80)
    print("CONVERTING THUMBNAILS TO FILE REFERENCES (using corrected server paths)")
    print("=" * 80)
    
    # Get FileMaker token
    token = config.get_token()
    
    # Update S00001 through S00005
    stills_ids = ["S00001", "S00002", "S00003", "S00004", "S00005"]
    
    results = []
    for stills_id in stills_ids:
        success = update_thumbnail_to_reference(stills_id, token)
        results.append((stills_id, success))
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY:")
    print("=" * 80)
    
    successful = sum(1 for _, success in results if success)
    failed = len(results) - successful
    
    print(f"✅ Successful: {successful}/{len(results)}")
    print(f"❌ Failed: {failed}/{len(results)}")
    
    if failed > 0:
        print("\nFailed items:")
        for stills_id, success in results:
            if not success:
                print(f"  - {stills_id}")
    
    print("\n" + "=" * 80)
    print("Check FileMaker - thumbnails should display image content, not just icons")
    print("=" * 80)

