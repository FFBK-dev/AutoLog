# jobs/stills_autolog_03_parse_metadata.py
import sys, os, json, time, requests, subprocess
import warnings
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

# Add the parent directory to the path to import your existing config
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["stills_id"]

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "import_path": "SPECS_Filepath_Import",
    "description_orig": "INFO_Description_Original",
    "copyright": "INFO_Copyright",
    "archival_id": "INFO_Archival_ID",
    "url": "SPECS_URL",
    "date": "INFO_Date",
    "metadata": "INFO_Metadata"
}

def safe_get(metadata_dict, key, default=''):
    return metadata_dict.get(key, default)

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    stills_id = sys.argv[1]
    token = config.get_token()

    try:
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        record_data = config.get_record(token, "Stills", record_id)
        import_path = record_data[FIELD_MAPPING["import_path"]]

        result = subprocess.run(['/usr/local/bin/exiftool', '-j', '-g1', '-S', import_path], capture_output=True, text=True)
        if result.returncode != 0: raise RuntimeError(f"Exiftool failed: {result.stderr}")
        
        metadata = json.loads(result.stdout)[0]
        
        description = safe_get(metadata, 'IPTC:Caption-Abstract')
        copyright_notice = safe_get(metadata, 'IPTC:CopyrightNotice')
        byline = safe_get(metadata, 'IPTC:By-line')
        exif_url = safe_get(metadata, 'XMP:CreatorAddress')
        date_created = safe_get(metadata, 'IPTC:DateCreated', '').replace(':', '/')
        copyright_final = copyright_notice if copyright_notice else byline
        filename = Path(import_path).stem
        archival_id = filename.replace("GettyImages-", "")

        # Check if URL already exists (might have been generated in previous step)
        existing_url = record_data.get(FIELD_MAPPING["url"], '')
        
        field_data = {
            FIELD_MAPPING["description_orig"]: description,
            FIELD_MAPPING["copyright"]: copyright_final,
            FIELD_MAPPING["archival_id"]: archival_id,
            FIELD_MAPPING["date"]: date_created,
            FIELD_MAPPING["metadata"]: json.dumps(metadata, indent=2)
        }
        
        # Only set URL from EXIF if we don't already have one
        if exif_url and not existing_url:
            field_data[FIELD_MAPPING["url"]] = exif_url
            print(f"  -> Set URL from EXIF: {exif_url}")
        elif existing_url:
            print(f"  -> Keeping existing URL: {existing_url}")
        elif exif_url:
            print(f"  -> Set URL from EXIF: {exif_url}")
            field_data[FIELD_MAPPING["url"]] = exif_url

        config.update_record(token, "Stills", record_id, field_data)
        print(f"SUCCESS [parse_metadata]: {stills_id}")
        sys.exit(0)

    except Exception as e:
        sys.stderr.write(f"ERROR [parse_metadata] on {stills_id}: {e}\n")
        sys.exit(1)