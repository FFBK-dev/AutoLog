#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path
import os

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["music_id"]

FIELD_MAPPING = {
    "music_id": "INFO_MUSIC_ID",
    "filepath_server": "SPECS_Filepath_Server",
    "status": "AutoLog_Status"
}

def rename_file_with_id_prefix(music_id, token):
    """Rename the file at SPECS_Filepath_Server by prepending the music_id."""
    try:
        print(f"📝 Step 1: Rename File with ID Prefix")
        print(f"  -> Music ID: {music_id}")
        
        # Get record ID
        record_id = config.find_record_id(
            token, 
            "Music", 
            {FIELD_MAPPING["music_id"]: f"=={music_id}"}
        )
        print(f"  -> Record ID: {record_id}")
        
        # Get current file path
        record_data = config.get_record(token, "Music", record_id)
        current_filepath = record_data.get(FIELD_MAPPING["filepath_server"], "")
        
        if not current_filepath:
            print(f"  -> ERROR: No file path found in SPECS_Filepath_Server")
            return False
        
        print(f"  -> Current path: {current_filepath}")
        
        # Ensure volume is mounted
        if not config.ensure_volume_mounted(current_filepath):
            print(f"  -> ERROR: Failed to mount volume for path: {current_filepath}")
            return False
        
        # Check if file exists
        if not os.path.exists(current_filepath):
            print(f"  -> ERROR: File not found at path: {current_filepath}")
            return False
        
        # Parse the file path
        file_path = Path(current_filepath)
        directory = file_path.parent
        filename = file_path.name
        
        # Check if already renamed (starts with music_id)
        if filename.startswith(f"{music_id}_"):
            print(f"  -> File already has ID prefix: {filename}")
            print(f"  -> Skipping rename operation")
            return True
        
        # Create new filename with music_id prefix
        new_filename = f"{music_id}_{filename}"
        new_filepath = directory / new_filename
        
        print(f"  -> New filename: {new_filename}")
        print(f"  -> New path: {new_filepath}")
        
        # Rename the file
        try:
            os.rename(current_filepath, new_filepath)
            print(f"  -> File renamed successfully")
        except Exception as e:
            print(f"  -> ERROR: Failed to rename file: {e}")
            return False
        
        # Update FileMaker with new path
        update_data = {
            FIELD_MAPPING["filepath_server"]: str(new_filepath)
        }
        
        config.update_record(token, "Music", record_id, update_data)
        print(f"  -> FileMaker record updated with new path")
        
        print(f"✅ Step 1 complete: File renamed from '{filename}' to '{new_filename}'")
        return True
        
    except Exception as e:
        print(f"❌ Error in rename_file_with_id_prefix: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: music_autolog_01_rename_file.py <music_id> <token>")
        sys.exit(1)
    
    music_id = sys.argv[1]
    token = sys.argv[2]
    
    success = rename_file_with_id_prefix(music_id, token)
    sys.exit(0 if success else 1)

