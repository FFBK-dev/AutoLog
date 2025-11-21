#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path
import subprocess
import json
import os
import time

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["music_id"]

FIELD_MAPPING = {
    "music_id": "INFO_MUSIC_ID",
    "filepath_server": "SPECS_Filepath_Server",
    "song_name": "INFO_Song_Name",
    "artist": "INFO_Artist",
    "album": "INFO_Album",
    "composer": "PUBLISHING_Composer",
    "genre": "INFO_Genre",
    "release_year": "INFO_Release_Year",
    "track_number": "INFO_Track_Number",
    "isrc_upc": "INFO_ISRC_UPC_Code",
    "copyright": "INFO_Copyright",
    "metadata": "INFO_Metadata",
    "status": "AutoLog_Status"
}

def extract_with_ffprobe(filepath):
    """Extract metadata using ffprobe (best for music tags)."""
    try:
        print(f"  -> Extracting with ffprobe...")
        
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", 
             "-show_format", "-show_streams", filepath],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"  -> ffprobe failed: {result.stderr}")
            return None
        
        data = json.loads(result.stdout)
        tags = data.get('format', {}).get('tags', {})
        
        print(f"  -> ffprobe found {len(tags)} tags")
        
        # Extract metadata with multiple fallback options
        metadata = {
            'title': tags.get('title', tags.get('Title', '')),
            'artist': tags.get('artist', tags.get('album_artist', tags.get('Artist', ''))),
            'album_artist': tags.get('album_artist', tags.get('AlbumArtist', '')),
            'album': tags.get('album', tags.get('Album', '')),
            'genre': tags.get('genre', tags.get('Genre', '')),
            'date': tags.get('date', tags.get('year', tags.get('Year', tags.get('DATE', '')))),
            'track': tags.get('track', tags.get('Track', tags.get('TRACKNUMBER', ''))),
            'disc': tags.get('disc', tags.get('Disc', '')),
            'composer': tags.get('composer', tags.get('Composer', '')),
            'copyright': tags.get('copyright', tags.get('Copyright', '')),
            'isrc': tags.get('isrc', tags.get('ISRC', '')),
            'upc': tags.get('upc', tags.get('UPC', '')),
            'publisher': tags.get('publisher', tags.get('Publisher', '')),
            'label': tags.get('label', tags.get('Label', '')),
            'encoder': tags.get('encoder', ''),
            'comment': tags.get('comment', tags.get('Comment', ''))
        }
        
        return metadata
        
    except subprocess.TimeoutExpired:
        print(f"  -> ffprobe timed out")
        return None
    except json.JSONDecodeError as e:
        print(f"  -> ffprobe JSON parse error: {e}")
        return None
    except Exception as e:
        print(f"  -> ffprobe error: {e}")
        return None

def extract_with_exiftool(filepath):
    """Extract metadata using exiftool (comprehensive RIFF/INFO chunks)."""
    try:
        print(f"  -> Extracting with exiftool...")
        
        result = subprocess.run(
            ["exiftool", "-j", "-a", "-G1", filepath],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"  -> exiftool failed: {result.stderr}")
            return None
        
        data = json.loads(result.stdout)[0]
        print(f"  -> exiftool found {len(data)} fields")
        
        # Extract metadata from various tag groups
        metadata = {
            'title': (
                data.get('RIFF:Title') or 
                data.get('Title') or 
                data.get('ID3:Title') or ''
            ),
            'artist': (
                data.get('RIFF:Artist') or 
                data.get('Artist') or 
                data.get('ID3:Artist') or ''
            ),
            'album': (
                data.get('RIFF:Product') or 
                data.get('Product') or
                data.get('Album') or
                data.get('ID3:Album') or ''
            ),
            'genre': (
                data.get('RIFF:Genre') or 
                data.get('Genre') or 
                data.get('ID3:Genre') or ''
            ),
            'date': (
                data.get('RIFF:DateCreated') or 
                data.get('DateCreated') or
                data.get('Year') or
                data.get('ID3:Year') or ''
            ),
            'composer': (
                data.get('RIFF:Composer') or
                data.get('Composer') or
                data.get('ID3:Composer') or ''
            ),
            'copyright': (
                data.get('RIFF:Copyright') or
                data.get('Copyright') or
                data.get('ID3:Copyright') or ''
            ),
            'comment': (
                data.get('RIFF:Comment') or
                data.get('Comment') or
                data.get('ID3:Comment') or ''
            ),
            'publisher': (
                data.get('RIFF:Publisher') or
                data.get('Publisher') or ''
            ),
            'label': (
                data.get('RIFF:Label') or
                data.get('Label') or ''
            )
        }
        
        return metadata
        
    except subprocess.TimeoutExpired:
        print(f"  -> exiftool timed out")
        return None
    except json.JSONDecodeError as e:
        print(f"  -> exiftool JSON parse error: {e}")
        return None
    except Exception as e:
        print(f"  -> exiftool error: {e}")
        return None

def merge_metadata(ffprobe_data, exiftool_data):
    """
    Intelligently merge metadata from multiple sources.
    Priority: ffprobe for music tags, exiftool for supplementary data.
    """
    merged = {}
    
    # Start with ffprobe data (better for music tags)
    if ffprobe_data:
        for key, value in ffprobe_data.items():
            if value and str(value).strip():
                merged[key] = str(value).strip()
    
    # Supplement with exiftool data (fill in gaps)
    if exiftool_data:
        for key, value in exiftool_data.items():
            # Only use exiftool if ffprobe didn't find this field
            if key not in merged or not merged.get(key):
                if value and str(value).strip():
                    merged[key] = str(value).strip()
    
    return merged

def build_comprehensive_metadata_text(ffprobe_data, exiftool_data, merged_data):
    """Build comprehensive metadata text for INFO_Metadata field."""
    lines = []
    
    lines.append("=== COMBINED METADATA ===")
    lines.append("")
    
    # Show final merged values
    if merged_data:
        for key, value in sorted(merged_data.items()):
            if value:
                lines.append(f"{key.title()}: {value}")
    
    lines.append("")
    lines.append("=== FFPROBE EXTRACTION ===")
    if ffprobe_data:
        for key, value in sorted(ffprobe_data.items()):
            if value:
                lines.append(f"{key}: {value}")
    else:
        lines.append("(ffprobe extraction failed)")
    
    lines.append("")
    lines.append("=== EXIFTOOL EXTRACTION ===")
    if exiftool_data:
        for key, value in sorted(exiftool_data.items()):
            if value:
                lines.append(f"{key}: {value}")
    else:
        lines.append("(exiftool extraction failed)")
    
    return "\n".join(lines)

def truncate_field(value, max_length=255):
    """Safely truncate a field value to FileMaker's field size limits."""
    # Always return a string, even if value is None or empty
    if value is None or value == "":
        return ""
    
    # Convert to string and strip whitespace
    value_str = str(value).strip()
    
    # Truncate if needed
    if len(value_str) > max_length:
        return value_str[:max_length-3] + "..."
    
    return value_str

def extract_metadata(music_id, token):
    """Extract metadata from audio file using multiple methods."""
    try:
        print(f"🎵 Step 3: Parse Metadata (Multi-Tool Approach)")
        print(f"  -> Music ID: {music_id}")
        
        # Get record ID
        record_id = config.find_record_id(
            token, 
            "Music", 
            {FIELD_MAPPING["music_id"]: f"=={music_id}"}
        )
        print(f"  -> Record ID: {record_id}")
        
        # Get file path with retry logic (handles race condition where FileMaker
        # hasn't finished populating the field during large batch imports)
        # Also handles cases where long filenames or special characters cause FileMaker
        # to take longer processing the import
        filepath = ""
        max_retries = 15  # Wait up to 15 seconds for file path to be populated (increased for complex filenames)
        retry_delay = 1.0  # Check every 1 second
        
        for attempt in range(max_retries):
            record_data = config.get_record(token, "Music", record_id)
            filepath = record_data.get(FIELD_MAPPING["filepath_server"], "")
            
            if filepath and filepath.strip():
                # File path found, proceed
                break
            
            if attempt < max_retries - 1:
                print(f"  -> Waiting for file path to be populated (attempt {attempt + 1}/{max_retries})...")
                time.sleep(retry_delay)
            else:
                print(f"  -> ERROR: No file path found in SPECS_Filepath_Server after {max_retries} attempts")
                print(f"  -> Possible causes:")
                print(f"     - FileMaker is still processing a large batch import")
                print(f"     - Filename is too long or contains problematic special characters")
                print(f"     - File import failed or was incomplete")
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
        
        # Extract metadata using multiple methods
        print(f"  -> Using multi-tool extraction approach...")
        
        ffprobe_data = extract_with_ffprobe(filepath)
        exiftool_data = extract_with_exiftool(filepath)
        
        # Check if at least one method succeeded
        if not ffprobe_data and not exiftool_data:
            print(f"  -> ERROR: All extraction methods failed")
            return False
        
        # Merge metadata intelligently
        print(f"  -> Merging metadata from all sources...")
        merged = merge_metadata(ffprobe_data, exiftool_data)
        
        # Extract final values with multiple fallbacks
        song_name = merged.get('title', '')
        artist = merged.get('artist', '')
        album = merged.get('album', '')
        composer = merged.get('composer', '')
        genre = merged.get('genre', '')
        release_year = merged.get('date', '')
        track_number = merged.get('track', '')
        copyright_info = merged.get('copyright', '')
        
        # Handle ISRC/UPC (could be separate or not present)
        isrc_upc = merged.get('isrc', '') or merged.get('upc', '')
        
        # FALLBACK: Extract song title from filename if metadata doesn't have title
        if not song_name or not song_name.strip():
            print(f"  -> No title in metadata, attempting to extract from filename...")
            filename = Path(filepath).name
            # Remove extension
            filename_no_ext = Path(filename).stem
            
            # Check if filename follows "EM####_Song Title" format (after renaming)
            if "_" in filename_no_ext:
                # Split on first underscore
                parts = filename_no_ext.split("_", 1)
                if len(parts) == 2:
                    # Check if first part looks like a Music ID (EM####)
                    first_part = parts[0]
                    if first_part.startswith("EM") and len(first_part) >= 5:
                        # Extract song title (everything after Music ID)
                        song_name = parts[1]
                        print(f"  -> Extracted song title from filename: {song_name}")
                    elif "__" in filename_no_ext:
                        # Check for double underscore format (original format)
                        parts_double = filename_no_ext.split("__", 1)
                        if len(parts_double) == 2:
                            song_name = parts_double[1]
                            print(f"  -> Extracted song title from filename (double underscore): {song_name}")
            else:
                # No underscore - use entire filename (minus extension) as title
                song_name = filename_no_ext
                print(f"  -> Using entire filename as song title: {song_name}")
        
        # Extract just year if date is longer
        if release_year and len(str(release_year)) > 4:
            release_year = str(release_year)[:4]
        
        # Extract track number if it contains other info (e.g., "8/12")
        if track_number and '/' in str(track_number):
            track_number = str(track_number).split('/')[0]
        
        # Print extracted values with clear indication of what was found
        print(f"  -> Song Name: {song_name or '(not found)'}")
        print(f"  -> Artist: {artist or '(not found)'}")
        print(f"  -> Album: {album or '(not found)'}")
        print(f"  -> Composer: {composer or '(not found)'}")
        print(f"  -> Genre: {genre or '(not found)'}")
        print(f"  -> Release Year: {release_year or '(not found)'}")
        print(f"  -> Track Number: {track_number or '(not found)'}")
        print(f"  -> Copyright: {copyright_info or '(not found)'}")
        print(f"  -> ISRC/UPC: {isrc_upc or '(not found)'}")
        
        # Build comprehensive metadata text
        comprehensive_metadata = build_comprehensive_metadata_text(
            ffprobe_data, exiftool_data, merged
        )
        
        print(f"  -> Comprehensive metadata: {len(comprehensive_metadata)} chars")
        
        # Truncate metadata if too long (FileMaker field size limit protection)
        MAX_METADATA_LENGTH = 10000  # Conservative limit for FileMaker text fields
        if len(comprehensive_metadata) > MAX_METADATA_LENGTH:
            comprehensive_metadata = comprehensive_metadata[:MAX_METADATA_LENGTH-50] + "\n\n... (truncated for length)"
            print(f"  -> Metadata truncated to {MAX_METADATA_LENGTH} chars to fit FileMaker field")
        
        # Update FileMaker with extracted metadata (with field truncation for safety)
        update_data = {
            FIELD_MAPPING["song_name"]: truncate_field(song_name, 255),
            FIELD_MAPPING["artist"]: truncate_field(artist, 255),
            FIELD_MAPPING["album"]: truncate_field(album, 255),
            FIELD_MAPPING["composer"]: truncate_field(composer, 255),
            FIELD_MAPPING["genre"]: truncate_field(genre, 100),
            FIELD_MAPPING["release_year"]: truncate_field(release_year, 10),
            FIELD_MAPPING["track_number"]: truncate_field(track_number, 10),
            FIELD_MAPPING["isrc_upc"]: truncate_field(isrc_upc, 50),
            FIELD_MAPPING["copyright"]: truncate_field(copyright_info, 500),
            FIELD_MAPPING["metadata"]: comprehensive_metadata
        }
        
        print(f"  -> Attempting FileMaker update with {len(update_data)} fields...")
        print(f"  -> Debug: Field lengths - Song:{len(update_data[FIELD_MAPPING['song_name']])}, "
              f"Artist:{len(update_data[FIELD_MAPPING['artist']])}, "
              f"Metadata:{len(update_data[FIELD_MAPPING['metadata']])}")
        
        config.update_record(token, "Music", record_id, update_data)
        print(f"  -> FileMaker record updated with metadata")
        
        # Count how many fields were populated
        populated_fields = sum(1 for v in update_data.values() if v)
        print(f"  -> Populated {populated_fields}/{len(update_data)} metadata fields")
        
        # Show extraction method summary
        methods_used = []
        if ffprobe_data:
            methods_used.append("ffprobe")
        if exiftool_data:
            methods_used.append("exiftool")
        print(f"  -> Extraction methods used: {', '.join(methods_used)}")
        
        print(f"✅ Step 3 complete: Metadata extracted and stored")
        return True
        
    except Exception as e:
        print(f"❌ Error in extract_metadata: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: music_autolog_03_parse_metadata.py <music_id> <token>")
        sys.exit(1)
    
    music_id = sys.argv[1]
    token = sys.argv[2]
    
    success = extract_metadata(music_id, token)
    sys.exit(0 if success else 1)
