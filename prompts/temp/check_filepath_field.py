#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path
import requests
import json

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "import_path": "SPECS_Filepath_Import",
    "status": "AutoLog_Status",
    "dev_console": "AI_DevConsole",
}

def check_filepath_fields(token, stills_ids):
    """Check the filepath fields for specific stills records."""
    print(f"🔍 Checking filepath fields for {len(stills_ids)} records...")
    
    for stills_id in stills_ids:
        try:
            # Find the record by stills_id
            record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
            record_data = config.get_record(token, "Stills", record_id)
            
            import_path = record_data.get(FIELD_MAPPING["import_path"])
            
            print(f"\n📋 {stills_id} (Record ID: {record_id}):")
            print(f"   SPECS_Filepath_Import: {repr(import_path)}")
            print(f"   Type: {type(import_path)}")
            
            if import_path is None:
                print(f"   ❌ Field is None/empty")
            elif isinstance(import_path, (int, float)):
                print(f"   ❌ Field contains numeric value instead of file path!")
            elif isinstance(import_path, str):
                if import_path.strip() == "":
                    print(f"   ❌ Field is empty string")
                else:
                    print(f"   ✅ Field contains string: {import_path[:100]}...")
            else:
                print(f"   ❓ Field contains unexpected type: {type(import_path)}")
            
        except Exception as e:
            print(f"❌ {stills_id}: ERROR - {e}")

if __name__ == "__main__":
    try:
        token = config.get_token()
        
        # The specific records mentioned by the user
        target_stills_ids = [
            "S07032", "S07033", "S07034", "S07035", "S07036", 
            "S07037", "S07038", "S07039", "S07040", "S07041", 
            "S07042", "S07043"
        ]
        
        print(f"=== Checking Filepath Fields ===")
        check_filepath_fields(token, target_stills_ids)
        
    except Exception as e:
        print(f"Critical error: {e}")
        sys.exit(1) 