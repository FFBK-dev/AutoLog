#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path
import subprocess
import json
import os

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["music_id"]

FIELD_MAPPING = {
    "music_id": "INFO_MUSIC_ID",
    "filepath_server": "SPECS_Filepath_Server",
    "file_format": "SPECS_File_Format",
    "sample_rate": "SPECS_File_Sample_Rate",
    "duration": "SPECS_Duration",
    "status": "AutoLog_Status"
}

def format_duration(seconds):
    """Convert seconds to HH:MM:SS or MM:SS format."""
    if not seconds:
        return ""
    
    try:
        total_seconds = float(seconds)
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        secs = int(total_seconds % 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"
    except:
        return str(seconds)

def extract_file_specs(music_id, token):
    """Extract file specifications using exiftool and ffprobe."""
    try:
        print(f"🔍 Step 2: Extract File Specs")
        print(f"  -> Music ID: {music_id}")
        
        # Get record ID
        record_id = config.find_record_id(
            token, 
            "Music", 
            {FIELD_MAPPING["music_id"]: f"=={music_id}"}
        )
        print(f"  -> Record ID: {record_id}")
        
        # Get file path
        record_data = config.get_record(token, "Music", record_id)
        filepath = record_data.get(FIELD_MAPPING["filepath_server"], "")
        
        if not filepath:
            print(f"  -> ERROR: No file path found in SPECS_Filepath_Server")
            return False
        
        print(f"  -> File path: {filepath}")
        
        # Ensure volume is mounted
        if not config.ensure_volume_mounted(filepath):
            print(f"  -> ERROR: Failed to mount volume for path: {filepath}")
            return False
        
        # Check if file exists
        if not os.path.exists(filepath):
            print(f"  -> ERROR: File not found at path: {filepath}")
            return False
        
        # Extract specs using exiftool first (simpler, more reliable for basic info)
        print(f"  -> Extracting specs with exiftool...")
        
        try:
            result = subprocess.run(
                ["exiftool", "-j", "-FileType", "-SampleRate", "-Duration", filepath],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                metadata = json.loads(result.stdout)[0]
                
                file_format = metadata.get("FileType", "")
                sample_rate = metadata.get("SampleRate", "")
                duration_str = metadata.get("Duration", "")
                
                print(f"  -> File Format: {file_format}")
                print(f"  -> Sample Rate: {sample_rate}")
                print(f"  -> Duration: {duration_str}")
                
                # Parse duration if it's in "H:MM:SS" or "M:SS" format
                # exiftool returns duration as string like "0:02:59"
                duration_formatted = duration_str
                
            else:
                print(f"  -> exiftool failed, trying ffprobe...")
                # Fallback to ffprobe if exiftool fails
                result = subprocess.run(
                    [
                        "ffprobe", "-v", "quiet", "-print_format", "json",
                        "-show_format", "-show_streams", filepath
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode != 0:
                    print(f"  -> ERROR: Both exiftool and ffprobe failed")
                    return False
                
                probe_data = json.loads(result.stdout)
                format_data = probe_data.get("format", {})
                stream_data = probe_data.get("streams", [{}])[0]
                
                # Get file format
                file_format = format_data.get("format_name", "").upper().split(",")[0]
                
                # Get sample rate
                sample_rate = stream_data.get("sample_rate", "")
                
                # Get duration in seconds and format it
                duration_seconds = format_data.get("duration", "")
                duration_formatted = format_duration(duration_seconds) if duration_seconds else ""
                
                print(f"  -> File Format: {file_format}")
                print(f"  -> Sample Rate: {sample_rate}")
                print(f"  -> Duration: {duration_formatted}")
                
        except subprocess.TimeoutExpired:
            print(f"  -> ERROR: File analysis timed out")
            return False
        except Exception as e:
            print(f"  -> ERROR: Failed to extract specs: {e}")
            return False
        
        # Update FileMaker with extracted specs
        update_data = {
            FIELD_MAPPING["file_format"]: file_format or "",
            FIELD_MAPPING["sample_rate"]: str(sample_rate) if sample_rate else "",
            FIELD_MAPPING["duration"]: duration_formatted or ""
        }
        
        config.update_record(token, "Music", record_id, update_data)
        print(f"  -> FileMaker record updated with file specs")
        
        print(f"✅ Step 2 complete: File specs extracted and stored")
        return True
        
    except Exception as e:
        print(f"❌ Error in extract_file_specs: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: music_autolog_02_extract_specs.py <music_id> <token>")
        sys.exit(1)
    
    music_id = sys.argv[1]
    token = sys.argv[2]
    
    success = extract_file_specs(music_id, token)
    sys.exit(0 if success else 1)

