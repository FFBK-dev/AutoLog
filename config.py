# config.py
"""Central FileMaker Data-API helpers."""

import os, requests, warnings, urllib3
from pathlib import Path

warnings.filterwarnings("ignore")
urllib3.disable_warnings()

# ── connection details (no changes here) ───────────────────────────────────
SERVER   = os.getenv("FILEMAKER_SERVER",  "10.0.222.144")
DB_NAME  = "Emancipation to Exodus"
USERNAME = os.getenv("FILEMAKER_USERNAME", "Background")
PASSWORD = os.getenv("FILEMAKER_PASSWORD", "july1776")
# ───────────────────────────────────────────────────────────────────────────

# ── SMB Volume Configuration ───────────────────────────────────────────────
SMB_SERVER = "10.0.222.138"
SMB_USERNAME = "admin"
SMB_PASSWORD = "july1776"
VOLUMES = {
    "stills": "6 E2E",
    "footage": "FTG_E2E"
}
# ───────────────────────────────────────────────────────────────────────────

import subprocess
import time

def mount_volume(volume_type="footage"):
    """Mount SMB volume if not already mounted."""
    volume_name = VOLUMES.get(volume_type)
    if not volume_name:
        print(f"❌ Unknown volume type: {volume_type}")
        return False
    
    mount_point = f"/Volumes/{volume_name}"
    
    # Check if already mounted
    if os.path.exists(mount_point) and os.path.ismount(mount_point):
        print(f"✅ Volume already mounted: {mount_point}")
        return True
    
    # Mount the SMB volume using Finder's "Connect to Server" approach
    smb_path = f"smb://{SMB_USERNAME}:{SMB_PASSWORD}@{SMB_SERVER}/{volume_name.replace(' ', '%20')}"
    
    try:
        print(f"🔧 Connecting to {volume_name} via Finder (Connect to Server)...")
        
        # Use 'open' command to trigger the same connection as Finder's "Connect to Server"
        result = subprocess.run([
            "open", smb_path
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print(f"✅ Connection initiated for: {volume_name}")
            
            # Wait a moment for the mount to complete
            time.sleep(3)
            
            # Verify mount worked by checking if it's actually mounted
            if os.path.exists(mount_point) and os.path.ismount(mount_point):
                print(f"✅ Successfully mounted: {mount_point}")
                return True
            else:
                print(f"⚠️ Connection initiated but volume not yet mounted at {mount_point}")
                # Wait a bit longer and try again
                time.sleep(2)
                if os.path.exists(mount_point) and os.path.ismount(mount_point):
                    print(f"✅ Successfully mounted after delay: {mount_point}")
                    return True
                else:
                    print(f"❌ Volume still not mounted after connection")
                    return False
        else:
            print(f"❌ Connection failed with return code {result.returncode}")
            print(f"❌ Connection stderr: {result.stderr}")
            print(f"❌ Connection stdout: {result.stdout}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"❌ Mount operation timed out for volume: {volume_name}")
        return False
    except Exception as e:
        print(f"❌ Error mounting volume {volume_name}: {e}")
        return False

def ensure_volume_mounted(file_path):
    """Ensure the appropriate volume is mounted for a given file path."""
    if not file_path or not isinstance(file_path, str):
        return False
    
    # Determine volume type from path
    if "/Volumes/6 E2E/" in file_path:
        return mount_volume("stills")
    elif "/Volumes/FTG_E2E/" in file_path:
        return mount_volume("footage")
    elif "/Volumes/" in file_path:
        # Generic volume check - see if it exists
        volume_path = "/".join(file_path.split("/")[:3])  # /Volumes/VolumeName
        if os.path.exists(volume_path) and os.path.ismount(volume_path):
            return True
        else:
            print(f"⚠️ Unknown volume in path: {file_path}")
            return False
    else:
        # Local file path, no mounting needed
        return True

# --- EXISTING FUNCTIONS (Unchanged) ---

def url(path: str) -> str:
    db_enc = DB_NAME.replace(" ", "%20")
    return f"https://{SERVER}/fmi/data/vLatest/databases/{db_enc}/{path}"

def get_token() -> str:
    r = requests.post(
        url("sessions"),
        auth=(USERNAME, PASSWORD),
        headers={"Content-Type": "application/json"},
        data="{}",
        verify=False,
    )
    r.raise_for_status()
    return r.json()["response"]["token"]

def api_headers(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

def find_record_id(tok: str, layout: str, query: dict) -> str:
    r = requests.post(
        url(f"layouts/{layout}/_find"),
        headers=api_headers(tok),
        json={"query": [query], "limit": 1},
        verify=False,
    )
    r.raise_for_status()
    data = r.json()["response"]["data"]
    if not data:
        raise RuntimeError(f"No match on {layout} for {query}")
    return data[0]["recordId"]

# --- ENHANCED FUNCTION (Added Error Checking) ---

def update_record(tok: str, layout: str, rec_id: str, field_data: dict):
    """Updates a record and raises an error if the API call fails."""
    r = requests.patch(
        url(f"layouts/{layout}/records/{rec_id}"),
        headers=api_headers(tok),
        json={"fieldData": field_data},
        verify=False,
    )
    r.raise_for_status() # <-- This is the enhancement. It will stop a script if the update fails.
    return r

# --- NEW HELPER FUNCTIONS (Additive) ---

def execute_script(token: str, script_name: str, layout_name: str = "Stills", script_parameter: str = "") -> dict:
    """
    Execute a FileMaker script on the server (PSOS).
    
    Args:
        token: Authentication token
        script_name: Name of the script to execute
        layout_name: Layout to use as context for script execution (default: "Stills")
        script_parameter: Optional parameter to pass to the script
    
    Returns:
        dict: Response from the script execution
    """
    # Build the URL with layout context
    script_url = f"layouts/{layout_name}/script/{script_name}"
    
    # Add script parameter if provided
    params = {}
    if script_parameter:
        params["script.param"] = script_parameter
    
    r = requests.get(
        url(script_url),
        headers=api_headers(token),
        params=params,
        verify=False
    )
    r.raise_for_status()
    return r.json()

def get_system_globals(token: str) -> dict:
    """
    Fetches the single record from the Settings table.
    Assumes there is only one record and its internal record ID is 1.
    """
    r = requests.get(
        url("layouts/Settings/records/1"),
        headers=api_headers(token),
        verify=False
    )
    r.raise_for_status()
    return r.json()['response']['data'][0]['fieldData']

def get_record(token: str, layout: str, record_id: str) -> dict:
    """Fetches a single record by its internal FileMaker record ID."""
    r = requests.get(
        url(f"layouts/{layout}/records/{record_id}"),
        headers=api_headers(token),
        verify=False
    )
    r.raise_for_status()
    return r.json()['response']['data'][0]['fieldData']
    
def upload_to_container(token: str, layout: str, record_id: str, field_name: str, file_path: str):
    """Uploads a file to a specified container field."""
    with open(file_path, 'rb') as f:
        # Note: We don't send a Content-Type header here; `requests` handles the multipart/form-data header.
        upload_headers = {"Authorization": f"Bearer {token}"}
        
        r = requests.post(
            url(f"layouts/{layout}/records/{record_id}/containers/{field_name}/1"),
            headers=upload_headers,
            files={'upload': f},
            verify=False
        )
        r.raise_for_status()
    return r