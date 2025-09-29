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

def extract_comprehensive_description(metadata):
    """Extract description from multiple IPTC/EXIF fields and combine intelligently."""
    # Description fields in nested structure (group, field) with priority order
    description_fields = [
        ('IPTC', 'Caption-Abstract'),        # Primary IPTC description field
        ('IPTC', 'Headline'),                # IPTC headline  
        ('XMP-dc', 'Description'),           # Dublin Core description
        ('XMP-iptcCore', 'Caption'),         # XMP IPTC caption
        ('EXIF', 'ImageDescription'),        # EXIF image description
        ('IPTC', 'ObjectName'),              # IPTC object name
        ('XMP-dc', 'Title'),                 # Dublin Core title
        ('IPTC', 'SpecialInstructions'),     # IPTC special instructions
        ('XMP-iptcCore', 'Headline'),        # XMP IPTC headline
        ('XMP-photoshop', 'Headline'),       # Photoshop headline
        ('XMP-photoshop', 'Instructions')   # Photoshop instructions
    ]
    
    descriptions = []
    found_fields = []
    
    # Extract all available description fields from nested structure
    for group, field in description_fields:
        group_data = metadata.get(group, {})
        if isinstance(group_data, dict):
            value = group_data.get(field, '')
            if value and str(value).strip():
                # Clean up the value and convert to string if needed
                cleaned_value = str(value).strip()
                # Only add if it's not a duplicate and has meaningful content
                if cleaned_value and cleaned_value not in descriptions and len(cleaned_value) > 3:
                    descriptions.append(cleaned_value)
                    found_fields.append(f"{group}:{field}")
    
    if not descriptions:
        print(f"  -> No description found in any IPTC/EXIF fields")
        return ""
    
    print(f"  -> Found description fields: {', '.join(found_fields)}")
    
    # If we have multiple descriptions, combine them intelligently
    if len(descriptions) == 1:
        final_description = descriptions[0]
        print(f"  -> Found single description from IPTC/EXIF: {final_description[:100]}...")
    else:
        # Combine multiple descriptions, with the primary one first
        final_description = descriptions[0]
        
        # Add additional descriptions that aren't just duplicates or substrings
        additional_info = []
        for desc in descriptions[1:]:
            # Only add if it's not a substring of the main description and adds value
            if desc.lower() not in final_description.lower() and final_description.lower() not in desc.lower():
                additional_info.append(desc)
        
        if additional_info:
            final_description += " | " + " | ".join(additional_info)
        
        print(f"  -> Combined {len(descriptions)} description fields from IPTC/EXIF: {final_description[:100]}...")
    
    return final_description

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    stills_id = sys.argv[1]
    
    print(f"DEBUG: Starting parse_metadata for {stills_id}")
    
    try:
        token = config.get_token()
        print(f"DEBUG: Got FileMaker token")

        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        print(f"DEBUG: Found record ID: {record_id}")
        
        record_data = config.get_record(token, "Stills", record_id)
        import_path = record_data[FIELD_MAPPING["import_path"]]
        print(f"DEBUG: Import path: {import_path}")
        
        # Check if file exists
        if not os.path.exists(import_path):
            raise FileNotFoundError(f"Import file not found: {import_path}")
        
        # Use correct exiftool path - try multiple locations
        exiftool_paths = ['/opt/homebrew/bin/exiftool', '/usr/local/bin/exiftool', 'exiftool']
        exiftool_cmd = None
        
        for path in exiftool_paths:
            if os.path.exists(path) or path == 'exiftool':
                exiftool_cmd = path
                break
        
        if not exiftool_cmd:
            raise RuntimeError("Exiftool not found in any expected location")
        
        print(f"DEBUG: Using exiftool at: {exiftool_cmd}")
        
        result = subprocess.run([exiftool_cmd, '-j', '-g1', '-S', import_path], capture_output=True, text=True)
        if result.returncode != 0: 
            print(f"DEBUG: Exiftool stderr: {result.stderr}")
            raise RuntimeError(f"Exiftool failed: {result.stderr}")
        
        print(f"DEBUG: Exiftool output length: {len(result.stdout)} characters")
        
        metadata = json.loads(result.stdout)[0]
        print(f"DEBUG: Parsed metadata with {len(metadata)} keys")
        
        description = extract_comprehensive_description(metadata)
        copyright_notice = safe_get(metadata, 'IPTC:CopyrightNotice')
        byline = safe_get(metadata, 'IPTC:By-line')
        exif_url = safe_get(metadata, 'XMP-iptcCore:CreatorAddress')
        if not exif_url:
            # Try alternative field names
            exif_url = safe_get(metadata, 'XMP-iptcCore', {}).get('CreatorAddress', '')
        date_created = safe_get(metadata, 'IPTC:DateCreated', '').replace(':', '/')
        copyright_final = copyright_notice if copyright_notice else byline
        filename = Path(import_path).stem
        archival_id = filename.replace("GettyImages-", "")

        print(f"DEBUG: Enhanced description extraction complete: {description[:100] if description else 'None'}...")
        print(f"DEBUG: Extracted copyright: {copyright_final[:100] if copyright_final else 'None'}...")
        print(f"DEBUG: Extracted archival_id: {archival_id}")
        print(f"DEBUG: Extracted date: {date_created}")

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
            print(f"DEBUG: Set URL from EXIF: {exif_url}")
        elif existing_url:
            print(f"DEBUG: Keeping existing URL: {existing_url}")
        elif exif_url:
            print(f"DEBUG: Set URL from EXIF: {exif_url}")
            field_data[FIELD_MAPPING["url"]] = exif_url

        print(f"DEBUG: Updating record with {len(field_data)} fields")
        config.update_record(token, "Stills", record_id, field_data)
        print(f"SUCCESS [parse_metadata]: {stills_id}")
        sys.exit(0)

    except Exception as e:
        print(f"DEBUG: Error in parse_metadata: {e}")
        import traceback
        traceback.print_exc()
        sys.stderr.write(f"ERROR [parse_metadata] on {stills_id}: {e}\n")
        sys.exit(1)