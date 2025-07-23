# jobs/stills_autolog_01_get_file_info.py
import sys, os, json, time, requests, subprocess
import warnings
from pathlib import Path
from PIL import Image

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

# Set PIL's maximum image size to handle very large images (1 billion pixels)
# This prevents the "decompression bomb DOS attack" error for legitimate large images
Image.MAX_IMAGE_PIXELS = 1000000000  # 1 billion pixels

# Add the parent directory to the path to import your existing config
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.url_validator import clean_archival_id_for_url, construct_url_from_source_and_id, validate_and_test_url
from utils.input_parser import parse_input_ids, format_input_summary, validate_ids

__ARGS__ = ["stills_id"]

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "import_path": "SPECS_Filepath_Import",
    "dimensions": "SPECS_File_Dimensions",
    "size": "SPECS_File_Size",
    "source": "INFO_Source",
    "archival_id": "INFO_Archival_ID",
    "url": "SPECS_URL",
    "file_format": "SPECS_File_Format"
}

def get_image_dimensions_alternative(import_path):
    """Get image dimensions using alternative methods when PIL fails."""
    print(f"  -> Attempting alternative dimension extraction for: {import_path}")
    
    # Method 1: Try using exiftool to get dimensions
    try:
        exiftool_paths = ['/opt/homebrew/bin/exiftool', '/usr/local/bin/exiftool', 'exiftool']
        exiftool_cmd = None
        
        for path in exiftool_paths:
            if os.path.exists(path) or path == 'exiftool':
                exiftool_cmd = path
                break
        
        if exiftool_cmd:
            result = subprocess.run([exiftool_cmd, '-j', '-ImageWidth', '-ImageHeight', import_path], 
                                  capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                metadata = json.loads(result.stdout)[0]
                width = metadata.get('ImageWidth')
                height = metadata.get('ImageHeight')
                if width and height:
                    print(f"  -> Successfully extracted dimensions via exiftool: {width}x{height}")
                    return f"{width}x{height}"
    except Exception as e:
        print(f"  -> Exiftool dimension extraction failed: {e}")
    
    # Method 2: Try using sips (macOS built-in)
    try:
        result = subprocess.run(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', import_path], 
                              capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            width = None
            height = None
            for line in lines:
                if 'pixelWidth:' in line:
                    width = line.split(':')[1].strip()
                elif 'pixelHeight:' in line:
                    height = line.split(':')[1].strip()
            if width and height:
                print(f"  -> Successfully extracted dimensions via sips: {width}x{height}")
                return f"{width}x{height}"
    except Exception as e:
        print(f"  -> Sips dimension extraction failed: {e}")
    
    # Method 3: Try using identify (ImageMagick)
    try:
        result = subprocess.run(['identify', '-format', '%wx%h', import_path], 
                              capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            dimensions = result.stdout.strip()
            if 'x' in dimensions:
                print(f"  -> Successfully extracted dimensions via identify: {dimensions}")
                return dimensions
    except Exception as e:
        print(f"  -> Identify dimension extraction failed: {e}")
    
    print(f"  -> All alternative dimension extraction methods failed")
    return "Unknown"

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


def process_single_item(stills_id: str, token: str) -> bool:
    """Process a single stills item."""
    try:
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        record_data = config.get_record(token, "Stills", record_id)
        import_path = record_data[FIELD_MAPPING["import_path"]]

        # Enhanced image dimension extraction with fallback methods
        dimensions = "Unknown"
        try:
            print(f"  -> Attempting to open image with PIL: {import_path}")
            img = Image.open(import_path)
            dimensions = f"{img.width}x{img.height}"
            print(f"  -> Successfully extracted dimensions via PIL: {dimensions}")
        except Exception as e:
            print(f"  -> PIL failed to open image: {e}")
            print(f"  -> Attempting alternative dimension extraction methods...")
            dimensions = get_image_dimensions_alternative(import_path)
        
        file_size_mb = f"{os.path.getsize(import_path) / (1024*1024):.2f} Mb"
        
        # Extract file format from extension
        file_extension = Path(import_path).suffix.lower()
        file_format = file_extension.lstrip('.').upper() if file_extension else "UNKNOWN"
        
        # Extract archive name from path after "2 By Archive/"
        path_parts = Path(import_path).parts
        try:
            archive_index = path_parts.index("2 By Archive")
            if archive_index + 1 < len(path_parts):
                source = path_parts[archive_index + 1]
            else:
                source = "Unknown Archive"
        except ValueError:
            source = "Unknown Archive"

        # Extract archival ID from filename
        filename = Path(import_path).stem
        archival_id = filename  # Keep original - cleaning will be handled by utility

        # Extract XMP URL data from metadata
        xmp_url = None
        try:
            # Use exiftool to extract metadata
            exiftool_paths = ['/opt/homebrew/bin/exiftool', '/usr/local/bin/exiftool', 'exiftool']
            exiftool_cmd = None
            
            for path in exiftool_paths:
                if os.path.exists(path) or path == 'exiftool':
                    exiftool_cmd = path
                    break
            
            if exiftool_cmd:
                result = subprocess.run([exiftool_cmd, '-j', '-g1', '-S', import_path], capture_output=True, text=True, timeout=60)
                if result.returncode == 0:
                    metadata = json.loads(result.stdout)[0]
                    # Look for XMP Creator Address in the correct field
                    xmp_url = metadata.get('XMP-iptcCore:CreatorAddress', '')
                    if not xmp_url:
                        # Try alternative field names
                        xmp_url = metadata.get('XMP-iptcCore', {}).get('CreatorAddress', '')
                    if xmp_url:
                        print(f"  -> Found XMP URL: {xmp_url}")
        except Exception as e:
            print(f"  -> Warning: Could not extract XMP metadata: {e}")

        # Generate URL from source and archival ID (fallback)
        generated_url = None
        if source and archival_id and source != "Unknown Archive":
            generated_url = find_url_from_source_and_archival_id(token, source, archival_id)

        # Removed thumbnail creation - now handled in copy_to_server script for efficiency
        # (thumbnail will be created from the processed server JPEG instead of the large original)
        
        field_data = {
            FIELD_MAPPING["dimensions"]: dimensions,
            FIELD_MAPPING["size"]: file_size_mb,
            FIELD_MAPPING["source"]: source,
            FIELD_MAPPING["archival_id"]: archival_id,
            FIELD_MAPPING["file_format"]: file_format
        }
        
        # Set URL - prioritize XMP URL over generated URL
        if xmp_url:
            field_data[FIELD_MAPPING["url"]] = xmp_url
            print(f"  -> Set XMP URL: {xmp_url}")
        elif generated_url:
            field_data[FIELD_MAPPING["url"]] = generated_url
            print(f"  -> Set generated URL: {generated_url}")
        
        config.update_record(token, "Stills", record_id, field_data)
        print(f"✅ Successfully processed {stills_id}")
        return True

    except Exception as e:
        print(f"❌ Error processing {stills_id}: {e}")
        return False


def process_batch_items(stills_ids: list, token: str, max_workers: int = 8) -> dict:
    """Process multiple stills items in parallel."""
    if not stills_ids:
        return {"total": 0, "successful": 0, "failed": 0, "results": []}
    
    print(f"🔄 Starting batch processing of {len(stills_ids)} items")
    
    # Adjust max workers based on number of items
    actual_max_workers = min(max_workers, len(stills_ids))
    print(f"📋 Using {actual_max_workers} concurrent workers")
    
    results = {
        "total": len(stills_ids),
        "successful": 0,
        "failed": 0,
        "results": []
    }
    
    def process_item_wrapper(stills_id):
        """Wrapper function for parallel processing."""
        try:
            success = process_single_item(stills_id, token)
            return {
                "stills_id": stills_id,
                "success": success,
                "error": None
            }
        except Exception as e:
            return {
                "stills_id": stills_id,
                "success": False,
                "error": str(e)
            }
    
    # Process items in parallel
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=actual_max_workers) as executor:
        future_to_item = {
            executor.submit(process_item_wrapper, stills_id): stills_id 
            for stills_id in stills_ids
        }
        
        for future in concurrent.futures.as_completed(future_to_item):
            try:
                result = future.result()
                results["results"].append(result)
                
                if result["success"]:
                    results["successful"] += 1
                else:
                    results["failed"] += 1
                
                # Progress update
                completed = len(results["results"])
                print(f"📊 Progress: {completed}/{len(stills_ids)} completed ({results['successful']} successful, {results['failed']} failed)")
                
            except Exception as e:
                stills_id = future_to_item[future]
                print(f"❌ Unexpected error processing {stills_id}: {e}")
                results["results"].append({
                    "stills_id": stills_id,
                    "success": False,
                    "error": str(e)
                })
                results["failed"] += 1
    
    print(f"✅ Batch processing completed: {results['successful']} successful, {results['failed']} failed")
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2: 
        sys.exit(1)
    
    input_string = sys.argv[1]
    
    # Parse input IDs
    stills_ids = parse_input_ids(input_string)
    
    if not stills_ids:
        print("❌ No valid IDs provided")
        sys.exit(1)
    
    # Validate IDs
    valid_ids, invalid_ids = validate_ids(stills_ids, ['S', 'F', 'AF'])
    
    if invalid_ids:
        print(f"⚠️ Invalid IDs found: {invalid_ids}")
        print(f"📋 Proceeding with valid IDs: {valid_ids}")
    
    if not valid_ids:
        print("❌ No valid IDs to process")
        sys.exit(1)
    
    # Print input summary
    print(format_input_summary(valid_ids, "get_file_info"))
    
    # Flexible token handling - detect call mode
    if len(sys.argv) == 2:
        # Direct API call mode - create own token/session
        token = config.get_token()
        print(f"🔄 Direct mode: Created new FileMaker session")
    elif len(sys.argv) == 3:
        # Subprocess mode - use provided token from parent process
        token = sys.argv[2]
        print(f"📋 Subprocess mode: Using provided token")
    else:
        sys.stderr.write(f"ERROR: Invalid arguments. Expected: script.py <input> [token]\n")
        sys.exit(1)
    
    try:
        # Process items
        if len(valid_ids) == 1:
            # Single item processing
            success = process_single_item(valid_ids[0], token)
            sys.exit(0 if success else 1)
        else:
            # Batch processing
            results = process_batch_items(valid_ids, token)
            
            # Output results as JSON for easy parsing
            import json
            print(f"BATCH_RESULTS: {json.dumps(results, indent=2)}")
            
            # Exit with success if all items succeeded
            sys.exit(0 if results["failed"] == 0 else 1)
            
    except Exception as e:
        print(f"❌ Critical error: {e}")
        sys.exit(1)