# controllers/stills_autolog_00_controller.py
import subprocess
import sys
import time
from pathlib import Path
import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = [] # This script is run by scheduler or with a list of IDs

JOBS_DIR = Path(__file__).resolve().parent.parent / "jobs"

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "status": "AutoLog_Status",
    "metadata": "INFO_Metadata",
    "url": "SPECS_URL",
    "dev_console": "AI_DevConsole"
}

WORKFLOW_STEPS = {
    "1 - Pending File Info":      {"script": "stills_autolog_01_get_file_info.py",      "next_status": "2 - File Info Complete"},
    "2 - File Info Complete":     {"script": "stills_autolog_02_copy_to_server.py",     "next_status": "3 - Server Copy Complete"},
    "3 - Server Copy Complete":   {"script": "stills_autolog_03_parse_metadata.py",   "next_status": "4 - Metadata Parsed"},
    "5 - Scraping URL":           {"script": "stills_autolog_04_scrape_url.py",       "next_status": "4 - Metadata Parsed"},
    "6 - Ready for AI Description": {"script": "stills_autolog_05_generate_description.py", "next_status": "7 - Ready for Embeddings"},
    "9 - Ready for Fusion":      {"script": "stills_autolog_06_fuse_embeddings.py",      "next_status": "9 - Complete"}
}

def process_single_step(record, token):
    record_id = record['recordId']
    stills_id = record['fieldData'][FIELD_MAPPING["stills_id"]]
    status = record['fieldData'].get(FIELD_MAPPING["status"], '')
    
    print(f"--- Processing {stills_id} (Status: {status}) ---")
    
    if status == "4 - Metadata Parsed":
        metadata_content = record['fieldData'].get(FIELD_MAPPING["metadata"], '')
        url_content = record['fieldData'].get(FIELD_MAPPING["url"], '')
        
        if len(metadata_content.strip()) > 50:
            next_status = "6 - Ready for AI Description"
        elif url_content:
            next_status = "5 - Scraping URL"
        else:
            next_status = "5H - Halted: Awaiting User Input"
        
        print(f"  -> State transition from '4' to '{next_status}'.")
        payload = {"fieldData": {FIELD_MAPPING["status"]: next_status}}
        requests.patch(config.url(f"layouts/Stills/records/{record_id}"), headers=config.api_headers(token), json=payload, verify=False)
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
            payload = {"fieldData": {FIELD_MAPPING["dev_console"]: error_message}}
            
        requests.patch(config.url(f"layouts/Stills/records/{record_id}"), headers=config.api_headers(token), json=payload, verify=False)
        return result.returncode == 0
            
    print(f"  -> Status '{status}' is a final or unknown state. Stopping.")
    return False

def run_batch_mode(id_list, token):
    print(f"--- Controller running in BATCH mode for {len(id_list)} IDs. ---")
    for stills_id in id_list:
        max_steps, step_count = 10, 0
        while step_count < max_steps:
            try:
                record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
                r = requests.get(config.url(f"layouts/Stills/records/{record_id}"), headers=config.api_headers(token), verify=False)
                record = r.json()['response']['data'][0]
                if not process_single_step(record, token):
                    break
            except Exception as e:
                print(f"FATAL ERROR processing {stills_id}: {e}")
                # Write error to dev console
                try:
                    record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
                    error_payload = {"fieldData": {FIELD_MAPPING["dev_console"]: f"FATAL ERROR: {e}"}}
                    requests.patch(config.url(f"layouts/Stills/records/{record_id}"), headers=config.api_headers(token), json=error_payload, verify=False)
                except:
                    pass  # Don't let error logging cause another error
                break
            step_count += 1
            time.sleep(0.5)

def run_polling_mode(token):
    print("--- Controller running in POLLING mode. ---")
    find_statuses = list(WORKFLOW_STEPS.keys()) + ["4 - Metadata Parsed"]
    query = {"query": [{"AutoLog_Status": f"=={status}"} for status in find_statuses], "limit": 50}
    
    while True:
        try:
            r = requests.post(config.url("layouts/Stills/_find"), headers=config.api_headers(token), json=query, verify=False)
            r.raise_for_status()
            records = r.json().get('response', {}).get('data', [])
            if records:
                print(f"Found {len(records)} records to process.")
                for record in records:
                    process_single_step(record, token)
            else:
                print("No records need processing.")
        except Exception as e:
            print(f"Error finding records: {e}")
        
        print("Sleeping for 15 seconds before next poll...")
        time.sleep(15)

if __name__ == "__main__":
    token = config.get_token()
    if len(sys.argv) > 1:
        stills_id_list = sys.argv[1].split(',')
        run_batch_mode(stills_id_list, token)
    else:
        run_polling_mode(token)