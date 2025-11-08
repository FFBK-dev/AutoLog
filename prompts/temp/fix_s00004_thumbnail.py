#!/usr/bin/env python3
"""
Fix S00004 by regenerating its thumbnail to match the standard workflow
This will make it consistent with S00509 for proper duplicate detection
"""

import sys
import os
import warnings
from pathlib import Path
from PIL import Image

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "server_path": "SPECS_Filepath_Server",
    "thumbnail": "SPECS_Thumbnail"
}

def create_standard_thumbnail(stills_id, token):
    """Create a standard 588x588 @ 85% thumbnail from the server file."""
    try:
        print(f"\n{'='*80}")
        print(f"Creating standard thumbnail for {stills_id}")
        print(f"{'='*80}")
        
        # Find record
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        print(f"Record ID: {record_id}")
        
        # Get server path
        record_data = config.get_record(token, "Stills", record_id)
        server_path = record_data.get(FIELD_MAPPING["server_path"])
        
        if not server_path or not os.path.exists(server_path):
            print(f"❌ Server file not found: {server_path}")
            return False
        
        print(f"Server file: {server_path}")
        
        # Open the server image
        with Image.open(server_path) as img:
            original_size = img.size
            print(f"Original size: {original_size[0]}x{original_size[1]}")
            
            # Convert to RGB if needed
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            
            # Create thumbnail (maintains aspect ratio)
            thumb_img = img.copy()
            thumb_img.thumbnail((588, 588), Image.Resampling.LANCZOS)
            
            thumb_size = thumb_img.size
            print(f"Thumbnail size: {thumb_size[0]}x{thumb_size[1]}")
            
            # Save with standard compression
            temp_thumb = f"/tmp/standard_thumb_{stills_id}.jpg"
            thumb_img.save(temp_thumb, 'JPEG', quality=85)
            
            thumb_file_size = os.path.getsize(temp_thumb)
            print(f"Thumbnail file size: {thumb_file_size:,} bytes ({thumb_file_size/1024:.1f} KB)")
            
            # Upload to FileMaker
            print(f"Uploading to FileMaker...")
            config.upload_to_container(token, "Stills", record_id, FIELD_MAPPING['thumbnail'], temp_thumb)
            
            # Clean up
            os.remove(temp_thumb)
            
            print(f"✅ Successfully updated thumbnail to standard format")
            return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("="*80)
    print("FIXING S00004 THUMBNAIL")
    print("="*80)
    print("\nThis will replace S00004's full-resolution thumbnail")
    print("with a standard 588x588 @ 85% compressed thumbnail")
    print("to match S00509 and the rest of the database.")
    
    # Get FileMaker token
    token = config.get_token()
    
    # Fix S00004
    success = create_standard_thumbnail("S00004", token)
    
    if success:
        print(f"\n{'='*80}")
        print("SUCCESS!")
        print(f"{'='*80}")
        print("\nNext steps:")
        print("1. Regenerate S00004's embedding from FileMaker")
        print("2. Run comparison script again")
        print("3. Embeddings should now match at ~99%+ similarity")
    else:
        print(f"\n{'='*80}")
        print("FAILED - see errors above")
        print(f"{'='*80}")

