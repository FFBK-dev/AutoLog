# jobs/stills_autolog_03_parse_metadata.py
import sys, subprocess, json
from pathlib import Path
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

# ... (helper functions are the same)

if __name__ == "__main__":
    stills_id = sys.argv[1]
    token = config.get_token()
    try:
        record_id, import_path = get_record_id_and_path(stills_id, token) # This helper would also use the FIELD_MAPPING
        # ... (logic to parse metadata is the same)
        
        field_data = {
            FIELD_MAPPING["description_orig"]: description,
            FIELD_MAPPING["copyright"]: copyright_final,
            FIELD_MAPPING["archival_id"]: archival_id,
            FIELD_MAPPING["url"]: url,
            FIELD_MAPPING["date"]: date_created,
            FIELD_MAPPING["metadata"]: json.dumps(metadata, indent=2)
        }
        
        requests.patch(config.url(f"layouts/Stills/records/{record_id}"), headers=config.api_headers(token), json={"fieldData": field_data}).raise_for_status()
        print(f"SUCCESS [parse_metadata]: {stills_id}")
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"ERROR [parse_metadata] on {stills_id}: {e}\n")
        sys.exit(1)