#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path
import json
import requests

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["id"]

# ID type detection and PSOS script mapping
ID_TYPE_MAPPING = {
    "stills": {
        "prefix": "S",
        "layout": "Stills", 
        "script": "AVID - STILLS - Find Similar",
        "id_field": "stills_id",
        "description": "Find similar stills images using AI-powered matching"
    },
    "live": {
        "prefix": "LF",
        "layout": "FOOTAGE",
        "script": "AVID - LIVE - Find Similar", 
        "id_field": "footage_id",
        "description": "Find similar live footage clips using AI-powered matching"
    },
    "archival": {
        "prefix": "AF",
        "layout": "FOOTAGE",
        "script": "AVID - ARCHIVAL - Find Similar",
        "id_field": "footage_id", 
        "description": "Find similar archival footage clips using AI-powered matching"
    }
}

# Field mappings for ID conversion
FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "footage_id": "INFO_FTG_ID"
}

def clean_and_detect_id_type(input_id):
    """Clean ID and detect type based on prefix and length patterns."""
    input_id = str(input_id).strip().upper()
    
    # Clean common suffixes and separators
    # Handle cases like: LF0022.sub.01, AF1234_001, S01000.mov, etc.
    import re
    
    # Extract the core ID using regex patterns
    # For stills: S + 5 digits
    stills_match = re.match(r'^(S\d{5})', input_id)
    if stills_match:
        core_id = stills_match.group(1)
        return core_id, "stills", ID_TYPE_MAPPING["stills"]
    
    # For footage: 2 letters + 4 digits  
    footage_match = re.match(r'^([A-Z]{2}\d{4})', input_id)
    if footage_match:
        core_id = footage_match.group(1)
        prefix = core_id[:2]
        
        # Determine footage type based on prefix
        if prefix == "LF":
            return core_id, "live", ID_TYPE_MAPPING["live"]
        elif prefix == "AF": 
            return core_id, "archival", ID_TYPE_MAPPING["archival"]
        else:
            # Unknown footage prefix, but still footage format
            print(f"⚠️ Warning: Unknown footage prefix '{prefix}', treating as archival")
            return core_id, "archival", ID_TYPE_MAPPING["archival"]
    
    return None, None, None

def validate_parameters(input_id):
    """Validate input parameters."""
    if not input_id:
        return False, "ID parameter is required"
    
    core_id, id_type, _ = clean_and_detect_id_type(input_id)
    if not id_type:
        return False, f"Invalid ID format. Must be S#####, LF####, or AF####. Got: {input_id}"
    
    return True, None

def extract_ranked_ids(psos_result):
    """Extract ranked record IDs from PSOS script result."""
    if not psos_result:
        return []
    
    try:
        # Parse the JSON result from PSOS
        parsed_result = json.loads(psos_result)
        
        if isinstance(parsed_result, list):
            record_ids = []
            for item in parsed_result:
                if isinstance(item, dict) and 'recordId' in item:
                    record_ids.append(str(item['recordId']))
                elif isinstance(item, str):
                    record_ids.append(item)
                else:
                    record_ids.append(str(item))
            return record_ids
        elif isinstance(parsed_result, dict) and 'recordId' in parsed_result:
            return [str(parsed_result['recordId'])]
        else:
            return [str(parsed_result)]
            
    except json.JSONDecodeError:
        # If not JSON, treat as string and split by common delimiters
        result_str = str(psos_result).strip()
        if ',' in result_str:
            return [id.strip() for id in result_str.split(',') if id.strip()]
        elif '\n' in result_str:
            return [id.strip() for id in result_str.split('\n') if id.strip()]
        else:
            return [result_str] if result_str else []

def get_business_id_from_record_id(token, record_id, layout, id_field_key):
    """Convert FileMaker record ID to business ID."""
    try:
        response = requests.get(
            config.url(f"layouts/{layout}/records/{record_id}"),
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            field_name = FIELD_MAPPING[id_field_key]
            business_id = data['response']['data'][0]['fieldData'].get(field_name)
            return business_id
        else:
            print(f"  -> Warning: Could not fetch business ID for record {record_id} (status: {response.status_code})")
            return None
            
    except Exception as e:
        print(f"  -> Warning: Error fetching business ID for record {record_id}: {e}")
        return None

def convert_record_ids_to_business_ids(token, record_ids, layout, id_field_key):
    """Convert list of record IDs to business IDs."""
    results = []
    
    print(f"🔄 Converting {len(record_ids)} record IDs to business IDs...")
    
    for i, record_id in enumerate(record_ids, 1):
        print(f"  -> Converting {i}/{len(record_ids)}: Record ID {record_id}")
        
        business_id = get_business_id_from_record_id(token, record_id, layout, id_field_key)
        if business_id:
            results.append(business_id)
            print(f"    ✅ {record_id} -> {business_id}")
        else:
            print(f"    ⚠️ Could not convert record ID {record_id}")
    
    return results

def perform_similarity_search(input_id, token):
    """Perform similarity search using appropriate PSOS script."""
    core_id, id_type, type_config = clean_and_detect_id_type(input_id)
    
    if not id_type:
        return None, f"Invalid ID format: {input_id}"
    
    layout = type_config["layout"]
    script_name = type_config["script"] 
    id_field_key = type_config["id_field"]
    
    # Show what we cleaned/detected
    if core_id != input_id:
        print(f"🧹 Cleaned input '{input_id}' → '{core_id}'")
    
    print(f"🎯 Detected ID type: {id_type.upper()} (Core ID: {core_id})")
    print(f"📋 Using layout: {layout}")
    print(f"🔧 Calling PSOS script: {script_name}")
    
    try:
        # Execute the PSOS script with the cleaned core ID as parameter
        psos_response = config.execute_script(token, script_name, layout, core_id)
        
        if not psos_response:
            return None, "No results returned from PSOS script"
        
        print(f"✅ PSOS script executed successfully")
        print(f"📊 Raw PSOS result: {psos_response}")
        
        # Extract script result from the response
        script_result = psos_response.get('response', {}).get('scriptResult', '')
        
        if not script_result:
            return None, "No script result returned from PSOS"
        
        # Extract ranked record IDs
        record_ids = extract_ranked_ids(script_result)
        
        if not record_ids:
            print(f"📋 No similar items found for {input_id}")
            return [], None
        
        print(f"🔍 Found {len(record_ids)} similar items")
        
        # Convert record IDs to business IDs
        business_ids = convert_record_ids_to_business_ids(token, record_ids, layout, id_field_key)
        
        return business_ids, None
        
    except Exception as e:
        error_msg = f"Error executing PSOS script '{script_name}': {str(e)}"
        print(f"❌ {error_msg}")
        return None, error_msg

def main():
    if len(sys.argv) < 2:
        print("❌ Error: ID parameter is required")
        print("Usage: python avid-find-similar.py <id>")
        sys.exit(1)
    
    input_id = sys.argv[1]
    
    print(f"🚀 Starting similarity search for ID: {input_id}")
    
    # Validate parameters
    is_valid, error_msg = validate_parameters(input_id)
    if not is_valid:
        print(f"❌ Validation Error: {error_msg}")
        sys.exit(1)
    
    try:
        # Get FileMaker token
        token = config.get_token()
        print(f"🔑 FileMaker authentication successful")
        
        # Perform similarity search
        similar_ids, error = perform_similarity_search(input_id, token)
        
        if error:
            print(f"❌ Search failed: {error}")
            sys.exit(1)
        
        if not similar_ids:
            print(f"📋 No similar items found for {input_id}")
        
        # Prepare results
        core_id, id_type, type_config = clean_and_detect_id_type(input_id)
        results = {
            "input_id": input_id,
            "core_id": core_id,
            "media_type": id_type,  # stills, live, or archival
            "total_results": len(similar_ids),
            "similar_items": similar_ids
        }
        
        print(f"✅ Similarity search completed successfully")
        print(f"📊 Found {len(similar_ids)} similar items")
        print(f"📊 JSON Results:")
        print(json.dumps(results, indent=2))
        
    except Exception as e:
        print(f"❌ Critical error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 