# controllers/stills_autolog_00_controller.py
import subprocess
import sys
import time
from pathlib import Path
import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

JOBS_DIR = Path(__file__).resolve().parent.parent / "jobs"

# --- Field Name Constants ---
# This dictionary maps our internal variable names to actual FileMaker field names.
FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "status": "AutoLog_Status",
    "metadata": "INFO_Metadata",
    "url": "SPECS_URL"
}

# Maps a record's status to the script and the next status
WORKFLOW_STEPS = {
    "1 - Pending File Info":      {"script": "stills_autolog_01_get_file_info.py",      "next_status": "2 - File Info Complete"},
    "2 - File Info Complete":     {"script": "stills_autolog_02_copy_to_server.py",     "next_status": "3 - Server Copy Complete"},
    "3 - Server Copy Complete":   {"script": "stills_autolog_03_parse_metadata.py",   "next_status": "4 - Metadata Parsed"},
    "5 - Scraping URL":           {"script": "stills_autolog_04_scrape_url.py",       "next_status": "4 - Metadata Parsed"},
    "6 - Ready for AI Description": {"script": "stills_autolog_05_generate_description.py", "next_status": "7 - Ready for Embeddings"},
    "8a - Ready for Fusion":      {"script": "stills_autolog_06_fuse_embeddings.py",      "next_status": "9 - Complete"}
}

def process_single_step(record, token):
    record_id = record['recordId']
    stills_id = record['fieldData'][FIELD_MAPPING["stills_id"]]
    status = record['fieldData'].get(FIELD_MAPPING["status"], '')
    
    print(f"--- Processing {stills_id} (Status: {status}) ---")
    
    if status == "4 - Metadata Parsed":
        metadata_content = record['fieldData'].get(FIELD_MAPPING["metadata"], '')
        url_content = record['fieldData'].get(FIELD_MAPPING["url"], '')
        
        if len(metadata_content.strip()) > 50: next_status = "6 - Ready for AI Description"
        elif url_content: next_status = "5 - Scraping URL"
        else: next_status = "5H - Halted: Awaiting User Input"
        
        print(f"  -> State transition from '4' to '{next_status}'.")
        payload = {"fieldData": {FIELD_MAPPING["status"]: next_status}}
        requests.patch(config.url(f"layouts/Stills/records/{record_id}"), headers=config.api_headers(token), json=payload)
        return next_status != "5H - Halted: Awaiting User Input"

    if status in WORKFLOW_STEPS:
        step = WORKFLOW_STEPS[status]
        script_path = JOBS_DIR / step["script"]
        result = subprocess.run(["python3", str(script_path), stills_id], capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"  -> SUCCESS: {script_path.name}. Updating status to: {step['next_status']}")
            payload = {"fieldData": {FIELD_MAPPING["status"]: step['next_status']}}
        else:
            error_message = f"Error during {status}: {result.stderr.strip()}"
            print(f"  -> FAILURE. Halting with error: {error_message}")
            payload = {"fieldData": {FIELD_MAPPING["status"]: error_message}}
            
        requests.patch(config.url(f"layouts/Stills/records/{record_id}"), headers=config.api_headers(token), json=payload)
        return result.returncode == 0
            
    print(f"  -> Status '{status}' is a final or unknown state. Stopping.")
    return False

# ... The polling/batch logic in the main execution block remains the same ...