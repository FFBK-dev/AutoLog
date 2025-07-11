#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["stills_id"]

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "status": "AutoLog_Status"
}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write("Error: stills_id argument required\n")
        sys.exit(1)
    
    stills_id = sys.argv[1]
    
    try:
        token = config.get_token()
        
        # Execute the PSOS script for applying tags
        psos_script = "STILLS - AutoLog - 07B - Apply Tags (PSOS)"
        result = config.execute_script(token, psos_script, "Stills", stills_id)
        
        # Check if the script executed successfully
        script_error = result.get('response', {}).get('scriptError', '0')
        
        if script_error == '0':
            print(f"SUCCESS [apply_tags]: {stills_id}")
            sys.exit(0)
        else:
            # PSOS script returned an error
            script_result = result.get('response', {}).get('scriptResult', 'Unknown error')
            sys.stderr.write(f"Error: PSOS script error {script_error}: {script_result}\n")
            sys.exit(1)
            
    except Exception as e:
        sys.stderr.write(f"Error [apply_tags] on {stills_id}: {e}\n")
        sys.exit(1) 