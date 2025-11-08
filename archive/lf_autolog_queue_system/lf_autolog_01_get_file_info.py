#!/usr/bin/env python3
import sys, os, json, subprocess, re, requests
import warnings
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.url_validator import clean_archival_id_for_url, construct_url_from_source_and_id, validate_and_test_url

__ARGS__ = ["footage_id"]

FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "filepath": "SPECS_Filepath_Server",
    "metadata": "INFO_Metadata",
    "url": "SPECS_URL",
    "status": "AutoLog_Status",
    "dev_console": "AI_DevConsole",
    "codec": "SPECS_File_Codec",
    "framerate": "SPECS_File_Framerate",
    "start_tc": "SPECS_File_startTC",
    "end_tc": "SPECS_File_endTC",
    "duration": "SPECS_File_Duration_Timecode",
    "dimensions": "SPECS_File_Dimensions",
    "frames": "SPECS_File_Frames",  # Added frame count field
    "color_mode": "INFO_ColorMode",
    "archival_id": "INFO_Archival_ID",
    "source": "INFO_Source",
    "filename": "INFO_Filename"
}

def extract_exif_metadata(file_path):
    """Extract EXIF metadata using ExifTool, focusing on QuickTime fields."""
    print(f"  -> Extracting EXIF metadata from: {file_path}")
    
    try:
        # Find exiftool
        exiftool_paths = ['/opt/homebrew/bin/exiftool', '/usr/local/bin/exiftool', 'exiftool']
        exiftool_cmd = None
        
        for path in exiftool_paths:
            if os.path.exists(path) or path == 'exiftool':
                exiftool_cmd = path
                break
        
        if not exiftool_cmd:
            raise RuntimeError("ExifTool not found in any expected location")
        
        # Run ExifTool to get QuickTime Comment and Description
        cmd = [
            exiftool_cmd,
            '-QuickTime:Comment',
            '-QuickTime:Description', 
            '-json',
            file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            print(f"  -> ExifTool warning/error: {result.stderr}")
            return ""
        
        if not result.stdout.strip():
            print(f"  -> No EXIF data found")
            return ""
        
        metadata_json = json.loads(result.stdout)[0]
        
        # Combine QuickTime fields
        metadata_parts = []
        
        comment = metadata_json.get("Comment", "")
        if comment:
            metadata_parts.append(f"Comment: {comment}")
        
        description = metadata_json.get("Description", "")
        if description:
            metadata_parts.append(f"Description: {description}")
        
        combined_metadata = "\n".join(metadata_parts)
        print(f"  -> Extracted {len(combined_metadata)} characters of EXIF metadata")
        
        return combined_metadata
        
    except subprocess.TimeoutExpired:
        print(f"  -> ExifTool timed out")
        return ""
    except Exception as e:
        print(f"  -> ExifTool error: {e}")
        return ""

def extract_url_from_metadata(metadata_text):
    """Extract URL from metadata text using regex patterns."""
    if not metadata_text:
        return None
    
    # Common URL patterns
    url_patterns = [
        r'https?://[^\s\n\r]+',
        r'www\.[^\s\n\r]+',
        r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s\n\r]*'
    ]
    
    for pattern in url_patterns:
        matches = re.findall(pattern, metadata_text, re.IGNORECASE)
        if matches:
            # Return the first URL found
            url = matches[0].strip('.,;:"\'')  # Clean up common trailing punctuation
            print(f"  -> Found URL in metadata: {url}")
            return url
    
    return None

def run_ffprobe(file_path):
    """Run FFprobe to extract video technical specifications."""
    print(f"  -> Running FFprobe analysis on: {file_path}")
    
    try:
        # Find ffprobe
        ffprobe_paths = ['/opt/homebrew/bin/ffprobe', '/usr/local/bin/ffprobe', 'ffprobe']
        ffprobe_cmd = None
        
        for path in ffprobe_paths:
            if os.path.exists(path) or path == 'ffprobe':
                ffprobe_cmd = path
                break
        
        if not ffprobe_cmd:
            raise RuntimeError("FFprobe not found in any expected location")
        
        # Comprehensive FFprobe command based on user's requirements
        cmd = [
            ffprobe_cmd,
            '-v', 'error',
            '-sexagesimal',
            '-select_streams', 'v:0',
            '-show_entries',
            'stream=id,codec_name,codec_long_name,codec_type,'
            'codec_time_base,time_base,r_frame_rate,avg_frame_rate,nb_frames,'
            'start_pts,start_time,duration_ts,duration,width,height,'
            'field_order,pix_fmt,color_space,color_transfer,color_range,'
            'sample_aspect_ratio,display_aspect_ratio,'
            'tags=timecode,'
            'side_data_list'
            ':format=start_time,duration,duration_ts,bit_rate,size,format_long_name,probe_score,'
            'tags=timecode',
            '-of', 'default=nw=1',
            file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode != 0:
            print(f"  -> FFprobe error: {result.stderr}")
            return {}
        
        # Parse FFprobe output
        specs = {}
        current_section = None
        
        for line in result.stdout.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('[STREAM]'):
                current_section = 'stream'
                continue
            elif line.startswith('[/STREAM]'):
                current_section = None
                continue
            elif line.startswith('[FORMAT]'):
                current_section = 'format'
                continue
            elif line.startswith('[/FORMAT]'):
                current_section = None
                continue
            
            if '=' in line:
                key, value = line.split('=', 1)
                specs[key] = value
        
        # Extract the specific fields we need
        extracted_specs = {}
        
        # Codec name
        if 'codec_name' in specs:
            extracted_specs['codec'] = specs['codec_name']
        
        # Frame count
        if 'nb_frames' in specs and specs['nb_frames'] != 'N/A':
            extracted_specs['frames'] = specs['nb_frames']
            print(f"  -> Found frame count: {specs['nb_frames']}")
        
        # Frame rate 
        if 'r_frame_rate' in specs:
            # Convert from fraction to decimal
            rate_str = specs['r_frame_rate']
            if '/' in rate_str:
                try:
                    num, den = rate_str.split('/')
                    rate = float(num) / float(den)
                    extracted_specs['framerate'] = f"{rate:.1f}"
                except:
                    extracted_specs['framerate'] = rate_str
            else:
                extracted_specs['framerate'] = rate_str
        
        # Timecode - try multiple sources
        timecode_found = False
        if 'TAG:timecode' in specs and specs['TAG:timecode']:
            extracted_specs['start_tc'] = specs['TAG:timecode']
            timecode_found = True
            print(f"  -> Found timecode in TAG:timecode: {specs['TAG:timecode']}")
        elif 'tags=timecode' in specs and specs['tags=timecode']:
            extracted_specs['start_tc'] = specs['tags=timecode']
            timecode_found = True
            print(f"  -> Found timecode in tags=timecode: {specs['tags=timecode']}")
        
        # If no timecode found, try format-level timecode
        if not timecode_found:
            # Check for format-level timecode
            for key, value in specs.items():
                if 'timecode' in key.lower() and value and value != 'N/A':
                    extracted_specs['start_tc'] = value
                    timecode_found = True
                    print(f"  -> Found timecode in {key}: {value}")
                    break
        
        if not timecode_found:
            print(f"  -> No timecode found in metadata - using 00:00:00:00 as default")
            extracted_specs['start_tc'] = "00:00:00:00"
        
        # Dimensions
        if 'width' in specs and 'height' in specs:
            extracted_specs['dimensions'] = f"{specs['width']}x{specs['height']}"
        
        # Pixel format for color mode detection
        if 'pix_fmt' in specs:
            extracted_specs['pix_fmt'] = specs['pix_fmt']
            print(f"  -> Found pixel format: {specs['pix_fmt']}")
        
        # Color space information (additional context)
        if 'color_space' in specs and specs['color_space'] != 'N/A':
            extracted_specs['color_space'] = specs['color_space']
        
        # Duration (from format section)
        if 'duration' in specs:
            duration_str = specs['duration']
            try:
                if ':' in duration_str:
                    # Parse sexagesimal format (H:MM:SS.ssssss)
                    parts = duration_str.split(':')
                    if len(parts) == 3:
                        hours = float(parts[0])
                        minutes = float(parts[1])
                        seconds = float(parts[2])
                        total_seconds = hours * 3600 + minutes * 60 + seconds
                        extracted_specs['duration_seconds'] = total_seconds
                    else:
                        extracted_specs['duration_seconds'] = float(duration_str)
                else:
                    extracted_specs['duration_seconds'] = float(duration_str)
            except ValueError as e:
                print(f"  -> Warning: Could not parse duration '{duration_str}': {e}")
                extracted_specs['duration_seconds'] = 0.0
        
        print(f"  -> Extracted video specs: {extracted_specs}")
        return extracted_specs
        
    except subprocess.TimeoutExpired:
        print(f"  -> FFprobe timed out")
        return {}
    except Exception as e:
        print(f"  -> FFprobe error: {e}")
        return {}

def extract_source_from_path(file_path, footage_id):
    """Extract source string from file path - different positions for AF vs LF footage."""
    try:
        path_parts = Path(file_path).parts
        
        # Determine extraction position based on footage type
        if footage_id.startswith("AF"):
            # AF footage: Extract from 5th '/' (6th part, index 5)
            required_parts = 6
            extract_index = 5
            footage_type = "AF"
        elif footage_id.startswith("LF"):
            # LF footage: Extract from 4th '/' (5th part, index 4) - one fewer parentheses
            required_parts = 5
            extract_index = 4
            footage_type = "LF"
        else:
            # Unknown footage type - default to AF behavior
            print(f"  -> Unknown footage type: {footage_id}, defaulting to AF extraction logic")
            required_parts = 6
            extract_index = 5
            footage_type = "Unknown"
        
        if len(path_parts) > extract_index:
            source_part = path_parts[extract_index]
            print(f"  -> Extracted source from path ({footage_type} footage, index {extract_index}): {source_part}")
            return source_part
        else:
            print(f"  -> Path doesn't have enough parts for {footage_type} source extraction (need {required_parts}, have {len(path_parts)})")
            return ""
    except Exception as e:
        print(f"  -> Error extracting source: {e}")
        return ""

def get_filename_with_extension(file_path):
    """Get filename with extension."""
    try:
        filename = Path(file_path).name
        print(f"  -> Filename with extension: {filename}")
        return filename
    except Exception as e:
        print(f"  -> Error getting filename: {e}")
        return ""

def clean_archival_id_for_storage(filename, source):
    """Clean archival ID for storage in FileMaker - removes extension and source prefixes."""
    if not filename:
        return ""
    
    # Remove file extension
    archival_id = Path(filename).stem  # Gets filename without extension
    
    # Apply source-specific cleaning using existing utility
    cleaned_id = clean_archival_id_for_url(archival_id, source)
    
    print(f"  -> Cleaned archival ID for storage:")
    print(f"     Original filename: {filename}")
    print(f"     Without extension: {archival_id}")
    print(f"     After prefix cleaning: {cleaned_id}")
    
    return cleaned_id

def seconds_to_timecode(seconds, framerate=24.0):
    """Convert seconds to HH:MM:SS:FF timecode format."""
    try:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        frames = int((seconds % 1) * framerate)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"
    except Exception as e:
        print(f"  -> Error converting seconds to timecode: {e}")
        return "00:00:00:00"

def timecode_to_seconds(timecode, framerate=24.0):
    """Convert HH:MM:SS:FF timecode to seconds."""
    try:
        if ':' not in timecode:
            return 0.0
        
        parts = timecode.split(':')
        if len(parts) != 4:
            return 0.0
        
        hours, minutes, secs, frames = [int(x) for x in parts]
        total_seconds = hours * 3600 + minutes * 60 + secs + (frames / framerate)
        return total_seconds
    except Exception as e:
        print(f"  -> Error converting timecode to seconds: {e}")
        return 0.0

def calculate_end_timecode(start_tc, duration_seconds, framerate=24.0):
    """Calculate end timecode based on start timecode and duration."""
    try:
        if not start_tc or start_tc == "":
            # If no start timecode, assume 00:00:00:00
            start_seconds = 0.0
        else:
            start_seconds = timecode_to_seconds(start_tc, framerate)
        
        end_seconds = start_seconds + duration_seconds
        end_tc = seconds_to_timecode(end_seconds, framerate)
        
        print(f"  -> Calculated end timecode: {start_tc} + {duration_seconds}s = {end_tc}")
        return end_tc
    except Exception as e:
        print(f"  -> Error calculating end timecode: {e}")
        return "00:00:00:00"

def determine_color_mode(pix_fmt, color_space=None):
    """Determine if video is color or black & white based on pixel format."""
    if not pix_fmt:
        print(f"  -> No pixel format available, defaulting to Color")
        return "Color"
    
    # Common grayscale/monochrome pixel formats
    grayscale_formats = {
        'gray', 'gray8', 'gray16', 'gray16le', 'gray16be',
        'monow', 'monob', 'y400a', 'ya8', 'ya16le', 'ya16be'
    }
    
    # Check if pixel format indicates grayscale
    pix_fmt_lower = pix_fmt.lower()
    
    # Direct grayscale format check
    if pix_fmt_lower in grayscale_formats:
        print(f"  -> Detected B&W based on pixel format: {pix_fmt}")
        return "B/W"
    
    # Check for grayscale indicators in format name
    grayscale_indicators = ['gray', 'mono', 'y400']
    if any(indicator in pix_fmt_lower for indicator in grayscale_indicators):
        print(f"  -> Detected B&W based on pixel format pattern: {pix_fmt}")
        return "B/W"
    
    # Additional check using color space if available
    if color_space and color_space.lower() in ['bt709', 'bt601', 'bt2020']:
        print(f"  -> Detected Color based on color space: {color_space}")
        return "Color"
    
    # Common color formats (most modern video)
    color_formats = {
        'yuv420p', 'yuv422p', 'yuv444p', 'rgb24', 'bgr24', 'rgba', 'bgra',
        'yuv420p10le', 'yuv422p10le', 'yuv444p10le', 'nv12', 'nv21'
    }
    
    if pix_fmt_lower in color_formats:
        print(f"  -> Detected Color based on pixel format: {pix_fmt}")
        return "Color"
    
    # Default assumption for unknown formats (most video is color)
    print(f"  -> Unknown pixel format '{pix_fmt}', defaulting to Color")
    return "Color"

def analyze_thumbnail_for_color(thumbnail_path):
    """Analyze a thumbnail image to determine if it's color or B&W (backup method)."""
    try:
        from PIL import Image
        import numpy as np
        
        if not os.path.exists(thumbnail_path):
            print(f"  -> Thumbnail not found: {thumbnail_path}")
            return None
        
        # Load image
        with Image.open(thumbnail_path) as img:
            # Convert to RGB if needed
            if img.mode not in ['RGB', 'RGBA']:
                img = img.convert('RGB')
            
            # Convert to numpy array
            img_array = np.array(img)
            
            # For RGB image, check if R, G, B channels are significantly different
            if len(img_array.shape) == 3 and img_array.shape[2] >= 3:
                r_channel = img_array[:, :, 0].astype(float)
                g_channel = img_array[:, :, 1].astype(float)
                b_channel = img_array[:, :, 2].astype(float)
                
                # Calculate variance between channels
                rg_diff = np.var(r_channel - g_channel)
                rb_diff = np.var(r_channel - b_channel)
                gb_diff = np.var(g_channel - b_channel)
                
                # If channels are very similar, it's likely B&W
                color_variance = (rg_diff + rb_diff + gb_diff) / 3
                
                # Threshold for determining B&W vs Color (can be tuned)
                bw_threshold = 10.0  # Lower values = more sensitive to B&W
                
                if color_variance < bw_threshold:
                    print(f"  -> Thumbnail analysis: B&W (color variance: {color_variance:.2f})")
                    return "B/W"
                else:
                    print(f"  -> Thumbnail analysis: Color (color variance: {color_variance:.2f})")
                    return "Color"
        
        return None
        
    except ImportError:
        print(f"  -> PIL/numpy not available for thumbnail analysis")
        return None
    except Exception as e:
        print(f"  -> Error analyzing thumbnail: {e}")
        return None

def find_url_from_source_and_archival_id(token, source, archival_id):
    """Find URL root from URLs layout based on source and combine with archival ID."""
    print(f"  -> Attempting to find URL root for source: {source}")
    
    try:
        # Query the URLs layout for the source
        query = {"query": [{"Archive": f"=={source}"}], "limit": 1}
        response = requests.post(
            config.url("layouts/URLs/_find"),
            headers=config.api_headers(token),
            json=query,
            verify=False
        )
        response.raise_for_status()
        
        records = response.json().get('response', {}).get('data', [])
        if not records:
            print(f"  -> No URL root found for source: {source}")
            return None
            
        url_root = records[0]['fieldData'].get('URL Root', '')
        if not url_root:
            print(f"  -> URL Root field is empty for source: {source}")
            return None
        
        # Use the new URL construction utility with cleaning
        constructed_url = construct_url_from_source_and_id(url_root, archival_id, source)
        if not constructed_url:
            print(f"  -> Failed to construct URL after cleaning archival ID")
            return None
        
        # Validate the constructed URL
        print(f"  -> Validating constructed URL...")
        validation_result = validate_and_test_url(constructed_url, test_accessibility=True, timeout=10)
        
        if validation_result["valid"] and validation_result["accessible"]:
            print(f"  -> ✅ URL is valid and accessible (HTTP {validation_result['status_code']})")
            return constructed_url
        elif validation_result["valid"]:
            print(f"  -> ⚠️ URL format is valid but not accessible: {validation_result['reason']}")
            print(f"  -> Will use URL anyway - may be accessible during scraping")
            return constructed_url
        else:
            print(f"  -> ❌ URL validation failed: {validation_result['reason']}")
            return None
        
    except Exception as e:
        print(f"  -> Error finding URL root: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    
    footage_id = sys.argv[1]
    
    # Flexible token handling
    if len(sys.argv) == 2:
        token = config.get_token()
        print(f"Direct mode: Created new FileMaker session for {footage_id}")
    elif len(sys.argv) == 3:
        token = sys.argv[2]
        print(f"Subprocess mode: Using provided token for {footage_id}")
    else:
        sys.stderr.write(f"ERROR: Invalid arguments. Expected: script.py footage_id [token]\n")
        sys.exit(1)
    
    try:
        print(f"Starting file info extraction for footage {footage_id}")
        
        # Get the current record to find the file path
        record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        record_data = config.get_record(token, "FOOTAGE", record_id)
        file_path = record_data[FIELD_MAPPING["filepath"]]
        
        print(f"Processing file: {file_path}")
        
        # Check if required volume is mounted (startup should have handled mounting)
        if "/Volumes/" in file_path:
            volume_path = "/".join(file_path.split("/")[:3])  # /Volumes/VolumeName
            if not os.path.exists(volume_path) or not os.path.ismount(volume_path):
                print(f"⚠️ Warning: Required volume not mounted: {volume_path}")
        
        # Check if file exists
        if not os.path.exists(file_path):
            error_msg = f"Footage file not found: {file_path}"
            print(f"❌ {error_msg}")
            
            # Update record with error instead of crashing
            error_data = {
                FIELD_MAPPING["status"]: "Error - File Not Found",
                FIELD_MAPPING["dev_console"]: error_msg
            }
            config.update_record(token, "FOOTAGE", record_id, error_data)
            print(f"  -> Updated record status to indicate file not found")
            sys.exit(1)  # Exit this specific job, but don't crash the whole system
        
        # Step 1: Extract EXIF metadata
        metadata = extract_exif_metadata(file_path)
        
        # Step 2: Extract URL from metadata if present
        url = extract_url_from_metadata(metadata)
        
        # Step 3: Run FFprobe analysis
        video_specs = run_ffprobe(file_path)
        
        # Step 4: Extract source from path
        source = extract_source_from_path(file_path, footage_id)
        
        # Step 5: Get filename with extension and create clean archival ID
        filename = get_filename_with_extension(file_path)
        
        # Create clean archival ID for storage (no extension, no prefixes)
        archival_id = clean_archival_id_for_storage(filename, source)
        
        # Create cleaned archival ID for URL construction (may need additional cleaning)
        cleaned_archival_id = clean_archival_id_for_url(archival_id, source)
        if cleaned_archival_id != archival_id:
            print(f"  -> Cleaned archival ID for URL construction:")
            print(f"     Original: {archival_id}")
            print(f"     Cleaned: {cleaned_archival_id}")
        
        # Step 6: Try to build URL from source and archival_id if no URL found yet
        url_source = "metadata" if url else None
        if not url and source and cleaned_archival_id and source.strip() and cleaned_archival_id.strip():
            print(f"  -> No URL found in metadata, attempting to build from source...")
            generated_url = find_url_from_source_and_archival_id(token, source, cleaned_archival_id)
            if generated_url:
                url = generated_url  # Use generated URL
                url_source = "generated"
                print(f"  -> Successfully generated URL: {url}")
            else:
                print(f"  -> Could not generate URL from source: {source}")
        elif not url and source and archival_id and source.strip() and archival_id.strip():
            print(f"  -> No URL found in metadata, attempting to build from source (using original archival ID)...")
            generated_url = find_url_from_source_and_archival_id(token, source, archival_id)
            if generated_url:
                url = generated_url  # Use generated URL
                url_source = "generated"
                print(f"  -> Successfully generated URL: {url}")
            else:
                print(f"  -> Could not generate URL from source: {source}")
        
        # Build field data for update
        field_data = {}
        
        # Always update metadata field
        field_data[FIELD_MAPPING["metadata"]] = metadata
        
        # Update URL if found (either from metadata or generated)
        if url:
            field_data[FIELD_MAPPING["url"]] = url
        
        # Update video specs
        if video_specs.get('codec'):
            field_data[FIELD_MAPPING["codec"]] = video_specs['codec']
        if video_specs.get('framerate'):
            field_data[FIELD_MAPPING["framerate"]] = video_specs['framerate']
        if video_specs.get('start_tc'):
            field_data[FIELD_MAPPING["start_tc"]] = video_specs['start_tc']
        if video_specs.get('dimensions'):
            field_data[FIELD_MAPPING["dimensions"]] = video_specs['dimensions']
        if video_specs.get('frames'):
            field_data[FIELD_MAPPING["frames"]] = video_specs['frames']
        
        # Determine color mode from pixel format
        if video_specs.get('pix_fmt'):
            color_mode = determine_color_mode(
                video_specs['pix_fmt'], 
                video_specs.get('color_space')
            )
            field_data[FIELD_MAPPING["color_mode"]] = color_mode
            print(f"  -> Color mode: {color_mode}")
        
        # Calculate duration and end timecode
        is_false_start = False
        if video_specs.get('duration_seconds'):
            duration_seconds = video_specs['duration_seconds']
            framerate = float(video_specs.get('framerate', 24.0))
            start_tc = video_specs.get('start_tc', '00:00:00:00')
            
            # Format duration as timecode
            duration_tc = seconds_to_timecode(duration_seconds, framerate)
            field_data[FIELD_MAPPING["duration"]] = duration_tc
            print(f"  -> Duration timecode: {duration_tc}")
            
            # Calculate end timecode
            end_tc = calculate_end_timecode(start_tc, duration_seconds, framerate)
            field_data[FIELD_MAPPING["end_tc"]] = end_tc
            
            # Check for false start (< 5 seconds)
            if duration_seconds < 5.0:
                is_false_start = True
                print(f"  -> ⚠️ FALSE START DETECTED (duration: {duration_seconds:.2f}s < 5s)")
                field_data[FIELD_MAPPING.get("description", "INFO_Description")] = "False start"
                field_data["INFO_AvidDescription"] = "False start"
        
        # Update archival ID, source, and filename
        if archival_id:
            field_data[FIELD_MAPPING["archival_id"]] = archival_id
        if source:
            field_data[FIELD_MAPPING["source"]] = source
        if filename:
            field_data[FIELD_MAPPING["filename"]] = filename
        
        # Update the record
        print(f"Updating footage record with extracted information...")
        update_response = config.update_record(token, "FOOTAGE", record_id, field_data)
        
        if update_response.status_code == 200:
            print(f"✅ Successfully updated footage {footage_id}")
            print(f"  -> Metadata: {len(metadata)} chars")
            print(f"  -> URL: {'Found' if url else 'Not found'}")
            print(f"  -> Video specs: {len(video_specs)} fields")
            if video_specs.get('start_tc'):
                print(f"  -> Start Timecode: {video_specs['start_tc']}")
            if video_specs.get('frames'):
                print(f"  -> Frame Count: {video_specs['frames']}")
            print(f"  -> Source: {source}")
            print(f"  -> Archival ID: {archival_id}")
            print(f"  -> Filename: {filename}")
            if field_data.get(FIELD_MAPPING["color_mode"]):
                print(f"  -> Color Mode: {field_data[FIELD_MAPPING['color_mode']]}")
            if url and url_source:
                print(f"  -> URL source: {url_source}")
        else:
            print(f"❌ Failed to update footage record: {update_response.status_code}")
            print(f"Response: {update_response.text}")
            sys.exit(1)
        
    except Exception as e:
        print(f"❌ Error processing footage {footage_id}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 