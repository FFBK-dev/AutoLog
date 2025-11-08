#!/usr/bin/env python3
"""
TEMPORARY SCRIPT: Convert S00001-S00005 thumbnails to file references
This script updates the SPECS_Thumbnail field to point to the server file as a reference
instead of containing an embedded JPEG.
"""

import sys
import warnings
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "server_path": "SPECS_Filepath_Server",
    "import_path": "SPECS_Filepath_Import",
    "thumbnail": "SPECS_Thumbnail"
}

def update_thumbnail_to_reference(stills_id, token):
    """Update a single record's thumbnail to be a file reference."""
    try:
        print(f"\n🔄 Processing {stills_id}...")
        
        # Find the record
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        print(f"  -> Found record ID: {record_id}")
        
        # Get both server and import paths
        record_data = config.get_record(token, "Stills", record_id)
        server_path = record_data.get(FIELD_MAPPING["server_path"])
        import_path = record_data.get(FIELD_MAPPING["import_path"])
        
        # Use whichever file actually exists
        import os
        file_path = None
        
        if server_path and os.path.exists(server_path):
            file_path = server_path
            print(f"  -> Using server path: {server_path}")
        elif import_path and os.path.exists(import_path):
            file_path = import_path
            print(f"  -> Server file not found, using import path: {import_path}")
        else:
            print(f"  -> ❌ ERROR: No valid file path found for {stills_id}")
            if server_path:
                print(f"     Server path (doesn't exist): {server_path}")
            if import_path:
                print(f"     Import path (doesn't exist): {import_path}")
            return False
        
        # Create FileMaker container reference format for macOS
        # Convert /Volumes/VolumeName/path to filemac:/VolumeName/path
        if file_path.startswith("/Volumes/"):
            # Remove /Volumes/ prefix and use filemac:
            path_without_volumes = file_path.replace("/Volumes/", "", 1)
            container_reference = f"filemac:/{path_without_volumes}"
        else:
            # Fallback to file: prefix
            container_reference = f"file:{file_path}"
        
        print(f"  -> Container reference: {container_reference}")
        
        # Update the thumbnail field with the reference
        payload = {FIELD_MAPPING["thumbnail"]: container_reference}
        config.update_record(token, "Stills", record_id, payload)
        
        print(f"  -> ✅ Successfully updated thumbnail to reference: {container_reference}")
        return True
        
    except Exception as e:
        print(f"  -> ❌ ERROR updating {stills_id}: {e}")
        return False

if __name__ == "__main__":
    print("=" * 80)
    print("TEMPORARY TEST: Converting thumbnails to file references")
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
    print("Test complete! Check FileMaker to see how the client handles references.")
    print("=" * 80)

