#!/usr/bin/env python3
"""
TEMPORARY SCRIPT: Upload server files to container field for S00001-S00005
This properly uploads the files so FileMaker displays the image content, not just an icon
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

def upload_server_file_as_thumbnail(stills_id, token):
    """Upload the server file as the thumbnail so it displays image content."""
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
        
        # Upload the actual file to the container field
        # This way FileMaker recognizes it as an image and displays the content
        print(f"  -> Uploading file to container field...")
        config.upload_to_container(token, "Stills", record_id, FIELD_MAPPING['thumbnail'], server_path)
        
        print(f"  -> ✅ Successfully uploaded file as thumbnail - should display image content")
        return True
        
    except Exception as e:
        print(f"  -> ❌ ERROR uploading {stills_id}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 80)
    print("UPLOADING SERVER FILES AS THUMBNAILS")
    print("(FileMaker should display image content, not icons)")
    print("=" * 80)
    
    # Get FileMaker token
    token = config.get_token()
    
    # Update S00001 through S00005
    stills_ids = ["S00001", "S00002", "S00003", "S00004", "S00005"]
    
    results = []
    for stills_id in stills_ids:
        success = upload_server_file_as_thumbnail(stills_id, token)
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
    print("Check FileMaker - thumbnails should now display FULL SERVER image content")
    print("(These are the full-resolution server files, not compressed thumbnails)")
    print("=" * 80)

