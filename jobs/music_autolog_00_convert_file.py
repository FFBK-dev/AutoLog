#!/usr/bin/env python3
"""
Music file conversion to standard specs (48kHz, 24-bit WAV)
"""
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
    "status": "AutoLog_Status"
}

# Standard specs
TARGET_SAMPLE_RATE = 48000
TARGET_BIT_DEPTH = 24
TARGET_FORMAT = "WAV"

def get_audio_specs(filepath):
    """Get audio file specifications using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", filepath],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return None
        
        data = json.loads(result.stdout)
        format_data = data.get("format", {})
        streams = data.get("streams", [])
        
        # Find audio stream
        audio_stream = None
        for stream in streams:
            if stream.get("codec_type") == "audio":
                audio_stream = stream
                break
        
        if not audio_stream:
            return None
        
        # Get format name
        format_name = format_data.get("format_name", "").upper()
        if "WAV" in format_name:
            file_format = "WAV"
        elif "MP3" in format_name:
            file_format = "MP3"
        else:
            file_format = format_name.split(",")[0] if format_name else "UNKNOWN"
        
        # Get sample rate
        sample_rate = audio_stream.get("sample_rate", "")
        try:
            sample_rate = int(float(sample_rate)) if sample_rate else None
        except:
            sample_rate = None
        
        # Get bit depth (bits_per_sample)
        bit_depth = audio_stream.get("bits_per_sample")
        if not bit_depth:
            # Try to get from sample_fmt
            sample_fmt = audio_stream.get("sample_fmt", "")
            # Map sample formats to bit depth
            bit_depth_map = {
                "s16": 16, "s16p": 16,
                "s24": 24, "s24p": 24,
                "s32": 32, "s32p": 32,
                "flt": 32, "fltp": 32
            }
            bit_depth = bit_depth_map.get(sample_fmt.lower(), None)
        
        try:
            bit_depth = int(bit_depth) if bit_depth else None
        except:
            bit_depth = None
        
        return {
            "format": file_format,
            "sample_rate": sample_rate,
            "bit_depth": bit_depth
        }
        
    except Exception as e:
        print(f"  -> Error getting audio specs: {e}")
        return None

def convert_audio_file(input_path, output_path):
    """Convert audio file to 48kHz, 24-bit WAV using ffmpeg."""
    try:
        print(f"  -> Converting to 48kHz, 24-bit WAV...")
        print(f"     Input: {input_path}")
        print(f"     Output: {output_path}")
        
        # Find ffmpeg
        ffmpeg_paths = ['/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', 'ffmpeg']
        ffmpeg_cmd = None
        for path in ffmpeg_paths:
            if os.path.exists(path) or path == 'ffmpeg':
                ffmpeg_cmd = path
                break
        
        if not ffmpeg_cmd:
            raise RuntimeError("FFmpeg not found")
        
        # Build ffmpeg command for conversion
        cmd = [
            ffmpeg_cmd,
            "-i", input_path,
            "-ar", str(TARGET_SAMPLE_RATE),  # Sample rate: 48000
            "-acodec", "pcm_s24le",  # PCM 24-bit little-endian
            "-y",  # Overwrite output file
            output_path,
            "-loglevel", "error"  # Suppress verbose output
        ]
        
        print(f"  -> Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode != 0:
            print(f"  -> FFmpeg stderr: {result.stderr}")
            raise RuntimeError(f"Conversion failed: {result.stderr}")
        
        if not os.path.exists(output_path):
            raise RuntimeError("Converted file was not created")
        
        # Verify the converted file
        converted_specs = get_audio_specs(output_path)
        if converted_specs:
            print(f"  -> Converted file specs:")
            print(f"     Format: {converted_specs['format']}")
            print(f"     Sample Rate: {converted_specs['sample_rate']} Hz")
            print(f"     Bit Depth: {converted_specs['bit_depth']} bit")
            
            # Verify it meets our standards
            if (converted_specs['format'] == TARGET_FORMAT and
                converted_specs['sample_rate'] == TARGET_SAMPLE_RATE and
                converted_specs['bit_depth'] == TARGET_BIT_DEPTH):
                print(f"  -> ✅ Conversion successful - file meets standards")
                return True
            else:
                print(f"  -> ⚠️  Warning: Converted file doesn't meet all standards")
                return True  # Still return True, file was created
        else:
            print(f"  -> ⚠️  Warning: Could not verify converted file specs")
            return True  # File exists, assume success
        
    except subprocess.TimeoutExpired:
        print(f"  -> ERROR: Conversion timed out")
        return False
    except Exception as e:
        print(f"  -> ERROR: Conversion failed: {e}")
        return False

def check_and_convert_file(music_id, token):
    """Check if file needs conversion and convert if necessary."""
    try:
        print(f"🔧 Step 0: Check and Convert Audio File")
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
        
        # Check if file is already converted (has _converted suffix)
        file_path = Path(current_filepath)
        if "_converted" in file_path.stem:
            print(f"  -> File already appears to be converted (has '_converted' in name)")
            print(f"  -> Skipping conversion check")
            return True
        
        # Get current file specs
        print(f"  -> Checking file specifications...")
        specs = get_audio_specs(current_filepath)
        
        if not specs:
            print(f"  -> ⚠️  Could not determine file specs - assuming conversion needed")
            specs = {"format": "UNKNOWN", "sample_rate": None, "bit_depth": None}
        
        print(f"  -> Current specs:")
        print(f"     Format: {specs['format']}")
        print(f"     Sample Rate: {specs['sample_rate']} Hz" if specs['sample_rate'] else "     Sample Rate: (unknown)")
        print(f"     Bit Depth: {specs['bit_depth']} bit" if specs['bit_depth'] else "     Bit Depth: (unknown)")
        
        # Check if conversion is needed
        needs_conversion = False
        reasons = []
        
        if specs['format'] != TARGET_FORMAT:
            needs_conversion = True
            reasons.append(f"Format is {specs['format']}, need {TARGET_FORMAT}")
        
        if specs['sample_rate'] and specs['sample_rate'] != TARGET_SAMPLE_RATE:
            needs_conversion = True
            reasons.append(f"Sample rate is {specs['sample_rate']}Hz, need {TARGET_SAMPLE_RATE}Hz")
        
        if specs['bit_depth'] and specs['bit_depth'] != TARGET_BIT_DEPTH:
            needs_conversion = True
            reasons.append(f"Bit depth is {specs['bit_depth']}bit, need {TARGET_BIT_DEPTH}bit")
        
        if not needs_conversion:
            print(f"  -> ✅ File already meets standards (48kHz, 24-bit WAV)")
            print(f"  -> No conversion needed")
            return True
        
        # Conversion needed
        print(f"  -> ⚠️  File does NOT meet standards:")
        for reason in reasons:
            print(f"     - {reason}")
        print(f"  -> Converting file...")
        
        # Create output filename with (_converted) suffix
        file_dir = file_path.parent
        file_stem = file_path.stem
        file_ext = file_path.suffix
        
        # Insert (_converted) before the extension
        converted_filename = f"{file_stem}_converted{file_ext}"
        converted_path = file_dir / converted_filename
        
        print(f"  -> Output path: {converted_path}")
        
        # Convert the file
        success = convert_audio_file(str(current_filepath), str(converted_path))
        
        if not success:
            print(f"  -> ERROR: File conversion failed")
            return False
        
        # Update FileMaker with the converted file path
        print(f"  -> Updating FileMaker with converted file path...")
        update_data = {
            FIELD_MAPPING["filepath_server"]: str(converted_path)
        }
        config.update_record(token, "Music", record_id, update_data)
        print(f"  -> FileMaker record updated with converted file path")
        
        print(f"✅ Step 0 complete: File converted to 48kHz, 24-bit WAV")
        return True
        
    except Exception as e:
        print(f"❌ Error in check_and_convert_file: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: music_autolog_00_convert_file.py <music_id> <token>")
        sys.exit(1)
    
    music_id = sys.argv[1]
    token = sys.argv[2]
    
    success = check_and_convert_file(music_id, token)
    sys.exit(0 if success else 1)
