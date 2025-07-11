# jobs/stills_autolog_02_copy_to_server.py
import sys, os
from pathlib import Path
from PIL import Image, ImageFile
import requests
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

ImageFile.LOAD_TRUNCATED_IMAGES = True
__ARGS__ = ["stills_id"]
AVID_MAX_DIMENSION = 12000

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "import_path": "SPECS_Filepath_Import",
    "server_path": "SPECS_Filepath_Server",
    "globals_drive": "SystemGlobals_Stills_ServerDrive",
    "globals_subfolder": "SystemGlobals_Stills_Subfolderpath"
}

def get_system_globals(fm_session):
    # ... (same as before)

def calculate_destination_path(stills_id: str, globals_data: dict) -> str:
    server_drive = globals_data.get(FIELD_MAPPING["globals_drive"])
    subfolder_path = globals_data.get(FIELD_MAPPING["globals_subfolder"])
    # ... (rest of the function is the same, no field names used)

if __name__ == "__main__":
    stills_id = sys.argv[1]
    token = config.get_token()
    
    try:
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        fm_session = requests.Session()
        fm_session.headers.update(config.api_headers(token))
        
        r = fm_session.get(config.url(f"layouts/Stills/records/{record_id}"))
        import_path = r.json()['response']['data'][0]['fieldData'][FIELD_MAPPING["import_path"]]
        
        system_globals = get_system_globals(fm_session)

        with Image.open(import_path) as img:
            if img.mode not in ('RGB', 'L'): img = img.convert('RGB')
            if max(img.size) > AVID_MAX_DIMENSION: img.thumbnail((AVID_MAX_DIMENSION, AVID_MAX_DIMENSION), Image.Resampling.LANCZOS)
            
            destination_path = calculate_destination_path(stills_id, system_globals)
            img.save(destination_path, 'JPEG', quality=95)

        payload = {"fieldData": {FIELD_MAPPING["server_path"]: destination_path}}
        requests.patch(config.url(f"layouts/Stills/records/{record_id}"), json=payload).raise_for_status()
        print(f"SUCCESS [copy_to_server]: {stills_id}")
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"ERROR [copy_to_server] on {stills_id}: {e}\n")
        sys.exit(1)