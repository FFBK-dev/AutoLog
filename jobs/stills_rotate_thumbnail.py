#!/usr/bin/env python3
# jobs/stills_rotate_thumbnail.py
import sys, os, json, time, requests
import warnings
from pathlib import Path
from PIL import Image, ImageFile

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

# Add the parent directory to the path to import your existing config
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

ImageFile.LOAD_TRUNCATED_IMAGES = True
__ARGS__ = ["stills_id"]

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "import_path": "SPECS_Filepath_Import",
    "server_path": "SPECS_Filepath_Server",
    "thumbnail": "SPECS_Thumbnail"
}

def get_image_path(record_data):
    """Get the best available image path, preferring server path over import path."""
    server_path = record_data.get(FIELD_MAPPING["server_path"])
    import_path = record_data.get(FIELD_MAPPING["import_path"])
    
    # Prefer server path if it exists and the file is accessible
    if server_path and os.path.exists(server_path):
        print(f"  -> Using server path: {server_path}")
        return server_path
    elif import_path and os.path.exists(import_path):
        print(f"  -> Using import path: {import_path}")
        return import_path
    else:
        raise FileNotFoundError(f"No accessible image file found. Server: {server_path}, Import: {import_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2: 
        sys.exit(1)
    
    stills_id = sys.argv[1]
    
    # Flexible token handling - detect call mode
    if len(sys.argv) == 2:
        # Direct API call mode - create own token/session
        token = config.get_token()
        print(f"Direct mode: Created new FileMaker session for {stills_id}")
    elif len(sys.argv) == 3:
        # Subprocess mode - use provided token from parent process
        token = sys.argv[2]
        print(f"Subprocess mode: Using provided token for {stills_id}")
    else:
        sys.stderr.write(f"ERROR: Invalid arguments. Expected: script.py stills_id [token]\n")
        sys.exit(1)
    
    try:
        print(f"🔄 Rotating server image and regenerating thumbnail for {stills_id}")
        
        # Find the record and get current data
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        record_data = config.get_record(token, "Stills", record_id)
        
        # Get server path - this script requires the server path to exist
        server_path = record_data.get(FIELD_MAPPING["server_path"])
        if not server_path:
            raise ValueError(f"No server path found for {stills_id} - file must be copied to server first")
        
        if not os.path.exists(server_path):
            raise FileNotFoundError(f"Server file not found: {server_path}")
        
        print(f"  -> Rotating server image: {server_path}")
        
        # Open and rotate the server image
        with Image.open(server_path) as img:
            # Convert to RGB if necessary
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            
            # Rotate 90 degrees clockwise
            rotated_img = img.rotate(-90, expand=True)
            
            # Save the rotated image back to the server path
            rotated_img.save(server_path, 'JPEG', quality=95)
            print(f"  -> Server image rotated and saved: {rotated_img.size}")
            
            # Create thumbnail from the rotated image
            thumb_img = rotated_img.copy()
            thumb_img.thumbnail((588, 588), Image.Resampling.LANCZOS)
            
            # Save thumbnail to temporary file
            thumb_path = f"/tmp/thumb_rotated_{stills_id}.jpg"
            thumb_img.save(thumb_path, 'JPEG', quality=85)
            
            print(f"  -> Created rotated thumbnail: {thumb_img.size}")
            
            # Upload thumbnail using config function
            config.upload_to_container(token, "Stills", record_id, FIELD_MAPPING['thumbnail'], thumb_path)
            
            # Clean up temporary file
            os.remove(thumb_path)
            
        print(f"✅ SUCCESS [rotate_thumbnail]: {stills_id}")
        sys.exit(0)
        
    except Exception as e:
        sys.stderr.write(f"❌ ERROR [rotate_thumbnail] on {stills_id}: {e}\n")
        sys.exit(1) 