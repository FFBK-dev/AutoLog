# jobs/stills_autolog_01_get_file_info.py
import sys, os, json, time, requests, subprocess
import warnings
from pathlib import Path
from PIL import Image

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

# Add the parent directory to the path to import your existing config
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["stills_id"]

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "import_path": "SPECS_Filepath_Import",
    "dimensions": "SPECS_File_Dimensions",
    "size": "SPECS_File_Size",
    "source": "INFO_Source",
    "archival_id": "INFO_Archival_ID",
    "url": "SPECS_URL",
    "thumbnail": "SPECS_Thumbnail",
    "file_format": "SPECS_File_Format"
}

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
            
        # Combine URL root with archival ID
        if url_root.endswith('/'):
            combined_url = f"{url_root}{archival_id}"
        else:
            combined_url = f"{url_root}/{archival_id}"
            
        print(f"  -> Generated URL: {combined_url}")
        return combined_url
        
    except Exception as e:
        print(f"  -> Error finding URL root: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    stills_id = sys.argv[1]
    token = config.get_token()
    
    try:
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        record_data = config.get_record(token, "Stills", record_id)
        import_path = record_data[FIELD_MAPPING["import_path"]]

        img = Image.open(import_path)
        dimensions = f"{img.width}x{img.height}"
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
        archival_id = filename.replace("GettyImages-", "")

        # Generate URL from source and archival ID
        generated_url = None
        if source and archival_id and source != "Unknown Archive":
            generated_url = find_url_from_source_and_archival_id(token, source, archival_id)

        thumb_path = f"/tmp/thumb_{stills_id}.jpg"
        subprocess.run(['magick', import_path, '-resize', '588x588>', thumb_path], check=True)
        
        # Upload thumbnail using config function
        config.upload_to_container(token, "Stills", record_id, FIELD_MAPPING['thumbnail'], thumb_path)
        os.remove(thumb_path)
        
        field_data = {
            FIELD_MAPPING["dimensions"]: dimensions,
            FIELD_MAPPING["size"]: file_size_mb,
            FIELD_MAPPING["source"]: source,
            FIELD_MAPPING["archival_id"]: archival_id,
            FIELD_MAPPING["file_format"]: file_format
        }
        
        # Add generated URL if we found one
        if generated_url:
            field_data[FIELD_MAPPING["url"]] = generated_url
            print(f"  -> Set generated URL: {generated_url}")
        
        config.update_record(token, "Stills", record_id, field_data)
        print(f"SUCCESS [get_file_info]: {stills_id}")
        sys.exit(0)

    except Exception as e:
        sys.stderr.write(f"ERROR [get_file_info] on {stills_id}: {e}\n")
        sys.exit(1)