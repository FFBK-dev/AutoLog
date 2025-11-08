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
    "status": "AutoLog_Status",
    "metadata": "INFO_Metadata",
    "url": "SPECS_URL",
    "dev_console": "AI_DevConsole",
    "description_orig": "INFO_Description_Original",
    "copyright": "INFO_Copyright",
    "source": "INFO_Source",
    "archival_id": "INFO_Archival_ID",
    "reviewed_checkbox": "INFO_Reviewed_Checkbox",
}

def check_specific_records(token, stills_ids):
    """Check the current status and details of specific stills records."""
    print(f"🔍 Checking status of {len(stills_ids)} specific stills records...")
    
    results = []
    
    for stills_id in stills_ids:
        try:
            # Find the record by stills_id
            query = {
                "query": [{FIELD_MAPPING["stills_id"]: stills_id}],
                "limit": 1
            }
            
            response = requests.post(
                config.url("layouts/Stills/_find"),
                headers=config.api_headers(token),
                json=query,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 404:
                print(f"❌ {stills_id}: NOT FOUND")
                results.append({
                    "stills_id": stills_id,
                    "status": "NOT FOUND",
                    "error": "Record not found"
                })
                continue
            
            response.raise_for_status()
            records = response.json()['response']['data']
            
            if not records:
                print(f"❌ {stills_id}: NO RECORDS RETURNED")
                results.append({
                    "stills_id": stills_id,
                    "status": "NO RECORDS",
                    "error": "No records returned from query"
                })
                continue
            
            record = records[0]
            field_data = record['fieldData']
            record_id = record['recordId']
            
            current_status = field_data.get(FIELD_MAPPING["status"], "Unknown")
            dev_console = field_data.get(FIELD_MAPPING["dev_console"], "")
            url = field_data.get(FIELD_MAPPING["url"], "")
            metadata = field_data.get(FIELD_MAPPING["metadata"], "")
            
            print(f"📋 {stills_id}:")
            print(f"   Record ID: {record_id}")
            print(f"   Status: {current_status}")
            print(f"   Has URL: {'Yes' if url else 'No'}")
            print(f"   Has Metadata: {'Yes' if metadata else 'No'}")
            if dev_console:
                print(f"   Dev Console: {dev_console[:100]}{'...' if len(dev_console) > 100 else ''}")
            print()
            
            results.append({
                "stills_id": stills_id,
                "record_id": record_id,
                "status": current_status,
                "has_url": bool(url),
                "has_metadata": bool(metadata),
                "dev_console": dev_console,
                "url": url[:100] if url else None,
                "metadata_length": len(metadata) if metadata else 0
            })
            
        except Exception as e:
            print(f"❌ {stills_id}: ERROR - {e}")
            results.append({
                "stills_id": stills_id,
                "status": "ERROR",
                "error": str(e)
            })
    
    return results

def analyze_workflow_position(status):
    """Analyze where in the workflow a record is stuck."""
    workflow_positions = {
        "0 - Pending File Info": "Step 1 - Ready to start workflow",
        "1 - File Info Complete": "Step 2 - Ready for server copy",
        "2 - Server Copy Complete": "Step 3 - Ready for metadata parsing",
        "3 - Metadata Parsed": "Step 4 - Ready for URL scraping (conditional)",
        "4 - Scraping URL": "Step 5 - Ready for description generation",
        "5 - Generating Description": "Step 5 - Currently generating description",
        "6 - Generating Embeddings": "Workflow complete - final status",
        "Awaiting User Input": "Stopped - metadata quality insufficient",
        "Error - File Not Found": "Error state - file not accessible",
    }
    
    return workflow_positions.get(status, f"Unknown status: {status}")

if __name__ == "__main__":
    try:
        token = config.get_token()
        
        # The specific records mentioned by the user
        target_stills_ids = [
            "S07032", "S07033", "S07034", "S07035", "S07036", 
            "S07037", "S07038", "S07039", "S07040", "S07041", 
            "S07042", "S07043"
        ]
        
        print(f"=== Investigating Stuck Records ===")
        print(f"Target records: {', '.join(target_stills_ids)}")
        print()
        
        results = check_specific_records(token, target_stills_ids)
        
        print(f"=== ANALYSIS ===")
        
        # Group by status
        status_groups = {}
        for result in results:
            status = result.get("status", "Unknown")
            if status not in status_groups:
                status_groups[status] = []
            status_groups[status].append(result)
        
        for status, records in status_groups.items():
            print(f"\n📊 Status: {status} ({len(records)} records)")
            print(f"   Workflow Position: {analyze_workflow_position(status)}")
            
            for record in records:
                stills_id = record["stills_id"]
                if record.get("error"):
                    print(f"   - {stills_id}: {record['error']}")
                else:
                    print(f"   - {stills_id}")
                    if record.get("dev_console"):
                        print(f"     Last console message: {record['dev_console'][:200]}...")
        
        print(f"\n=== RECOMMENDATIONS ===")
        
        # Check for common issues
        pending_count = len(status_groups.get("0 - Pending File Info", []))
        if pending_count > 0:
            print(f"• {pending_count} records are in pending state - they should be picked up by autolog")
        
        error_count = len([r for r in results if "error" in r.get("status", "").lower()])
        if error_count > 0:
            print(f"• {error_count} records have errors - check dev console messages")
        
        awaiting_input_count = len(status_groups.get("Awaiting User Input", []))
        if awaiting_input_count > 0:
            print(f"• {awaiting_input_count} records stopped due to insufficient metadata")
        
        # Output full results as JSON for detailed analysis
        print(f"\n=== FULL RESULTS (JSON) ===")
        print(json.dumps(results, indent=2))
        
    except Exception as e:
        print(f"Critical error: {e}")
        sys.exit(1) 