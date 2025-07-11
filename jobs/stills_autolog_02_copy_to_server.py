# jobs/stills_autolog_02_copy_to_server.py
import sys, os, json, time, requests
import warnings
from pathlib import Path
from PIL import Image, ImageFile

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

# Add the parent directory to the path to import your existing config
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

def get_system_globals(token):
    return config.get_system_globals(token)

def calculate_destination_path(stills_id: str, globals_data: dict) -> str:
    server_drive = globals_data.get(FIELD_MAPPING["globals_drive"])
    subfolder_path = globals_data.get(FIELD_MAPPING["globals_subfolder"])
    if not server_drive or not subfolder_path:
        raise ValueError("Stills server drive or subfolder path is not set in SystemGlobals.")
    stills_root = f"/Volumes/{server_drive}/{subfolder_path}"
    
    num = int(stills_id.replace('S', ''))
    range_start = (num // 500) * 500
    range_end = range_start + 499
    folder_name = f"S{range_start:05d}-S{range_end:05d}"
    
    destination_folder = os.path.join(stills_root, folder_name)
    
    # Thread-safe directory creation
    try:
        os.makedirs(destination_folder, exist_ok=True)
    except OSError as e:
        # Another thread might have created it, check if it exists
        if not os.path.exists(destination_folder):
            raise e
    
    return os.path.join(destination_folder, f"{stills_id}.jpg")

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    stills_id = sys.argv[1]
    token = config.get_token()
    
    try:
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        record_data = config.get_record(token, "Stills", record_id)
        import_path = record_data[FIELD_MAPPING["import_path"]]
        
        system_globals = get_system_globals(token)

        with Image.open(import_path) as img:
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            if max(img.size) > AVID_MAX_DIMENSION:
                img.thumbnail((AVID_MAX_DIMENSION, AVID_MAX_DIMENSION), Image.Resampling.LANCZOS)
            
            destination_path = calculate_destination_path(stills_id, system_globals)
            img.save(destination_path, 'JPEG', quality=95)

        payload = {FIELD_MAPPING["server_path"]: destination_path}
        config.update_record(token, "Stills", record_id, payload)
        print(f"SUCCESS [copy_to_server]: {stills_id}")
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"ERROR [copy_to_server] on {stills_id}: {e}\n")
        sys.exit(1)