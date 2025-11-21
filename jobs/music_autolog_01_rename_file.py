#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path
import os
import time
from datetime import datetime

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["music_id"]

FIELD_MAPPING = {
    "music_id": "INFO_MUSIC_ID",
    "filepath_server": "SPECS_Filepath_Server",
    "filepath_import": "SPECS_Filepath_Import",
    "import_timestamp": "SPECS_File_Import_Timestamp",
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
        
        # Get current file path with retry logic (handles race condition where FileMaker
        # hasn't finished populating the field during large batch imports)
        # Also handles cases where long filenames or special characters cause FileMaker
        # to take longer processing the import
        current_filepath = ""
        current_import_path = ""
        current_import_timestamp = ""
        max_retries = 15  # Wait up to 15 seconds for file path to be populated (increased for complex filenames)
        retry_delay = 1.0  # Check every 1 second
        
        for attempt in range(max_retries):
            record_data = config.get_record(token, "Music", record_id)
            current_filepath = record_data.get(FIELD_MAPPING["filepath_server"], "")
            current_import_path = record_data.get(FIELD_MAPPING["filepath_import"], "")
            current_import_timestamp = record_data.get(FIELD_MAPPING["import_timestamp"], "")
            
            if current_filepath and current_filepath.strip():
                # File path found, proceed
                # Log if it took multiple attempts (indicates potential filename complexity issue)
                if attempt > 0:
                    path_length = len(current_filepath)
                    filename = Path(current_filepath).name
                    print(f"  -> File path populated after {attempt + 1} attempts")
                    print(f"  -> Path length: {path_length} characters, Filename: {filename[:80]}{'...' if len(filename) > 80 else ''}")
                break
            
            if attempt < max_retries - 1:
                print(f"  -> Waiting for file path to be populated (attempt {attempt + 1}/{max_retries})...")
                print(f"  -> This may take longer for files with long names or special characters")
                time.sleep(retry_delay)
            else:
                print(f"  -> ERROR: No file path found in SPECS_Filepath_Server after {max_retries} attempts")
                print(f"  -> Possible causes:")
                print(f"     - FileMaker is still processing a large batch import")
                print(f"     - Filename is too long or contains problematic special characters")
                print(f"     - File import failed or was incomplete")
                print(f"  -> Check FileMaker to verify the file was actually imported")
                return False
        
        print(f"  -> Current path: {current_filepath}")
        
        # Store original filename and import timestamp if not already set
        if not current_import_path or not current_import_timestamp:
            print(f"  -> Storing original filename and import timestamp")
            current_filename = Path(current_filepath).name
            
            # Extract original filename (remove ID prefix if present)
            # Check for both single and double underscore formats
            if current_filename.startswith(f"{music_id}_"):
                # Remove Music ID prefix (single underscore format)
                original_filename = current_filename[len(f"{music_id}_"):]
                # If it was originally double underscore format, restore it
                # We can't perfectly restore, but we'll keep the extracted name
                print(f"  -> Extracted original filename (removed ID prefix): {original_filename}")
            else:
                original_filename = current_filename
                print(f"  -> Using current filename as original: {original_filename}")
            
            # Generate import timestamp
            import_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"  -> Import timestamp: {import_timestamp}")
            
            # Prepare update data
            update_import_data = {}
            if not current_import_path:
                update_import_data[FIELD_MAPPING["filepath_import"]] = original_filename
            if not current_import_timestamp:
                update_import_data[FIELD_MAPPING["import_timestamp"]] = import_timestamp
            
            config.update_record(token, "Music", record_id, update_import_data)
            print(f"  -> Original filename and import timestamp stored")
        
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
        
        # Parse filename: Extract artist (before "__") and song title (after "__")
        # Standard format: "Artist__Song Title.wav" (double underscore)
        if "__" in filename:
            # Split on double underscore
            parts = filename.split("__", 1)
            original_artist = parts[0]
            song_title_with_ext = parts[1]
            
            print(f"  -> Original filename format detected: Artist__Song (double underscore)")
            print(f"  -> Original artist: {original_artist}")
            print(f"  -> Song title: {song_title_with_ext}")
            
            # Replace artist with music_id (output uses single underscore)
            new_filename = f"{music_id}_{song_title_with_ext}"
            print(f"  -> Replacing artist '{original_artist}' with Music ID '{music_id}'")
        elif "_" in filename:
            # Fallback: Single underscore (old format for backwards compatibility)
            parts = filename.split("_", 1)
            original_artist = parts[0]
            song_title_with_ext = parts[1]
            
            print(f"  -> ⚠️  Single underscore detected (old format) - using fallback")
            print(f"  -> Original artist: {original_artist}")
            print(f"  -> Song title: {song_title_with_ext}")
            
            # Replace artist with music_id
            new_filename = f"{music_id}_{song_title_with_ext}"
            print(f"  -> Replacing artist '{original_artist}' with Music ID '{music_id}'")
        else:
            # Final fallback: No underscore found, prepend music_id
            print(f"  -> ⚠️  No underscore found in filename - using fallback (prepend ID)")
            print(f"  -> Filename doesn't match 'Artist__Song Title.wav' format")
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

