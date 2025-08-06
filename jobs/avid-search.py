#!/usr/bin/env python3
"""
Avid Search Job - Semantic search across different FileMaker layouts

This job provides semantic search functionality across different content types:
- stills: Search within the Stills layout
- live: Search within live content (future implementation)
- archive: Search within archived content (future implementation)

Returns a ranked list of record IDs based on semantic similarity.
"""

import sys
import warnings
import json
import requests
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["type", "query"]

# Field mapping for different content types
FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "footage_id": "INFO_FTG_ID",  # Updated to match user specification
    "frames_id": "FRAMES_ID",
    "frames_tc_in": "FRAMES_TC_IN"
}

# Search type to layout/script mapping based on Avid panel payload
SEARCH_TYPE_MAPPING = {
    "stills_text": {
        "layout": "Stills",
        "script": "AVID - STILLS - Search Text",
        "id_field": "stills_id",
        "description": "Search stills using text-based semantic matching"
    },
    "stills_visual": {
        "layout": "Stills", 
        "script": "AVID - STILLS - Search Visual",
        "id_field": "stills_id",
        "description": "Search stills using visual/image-based matching"
    },
    "stills_transcript": {
        "layout": "Stills",
        "script": "AVID - STILLS - Search Transcripts",
        "id_field": "stills_id",
        "description": "Search stills using transcript/caption matching"
    },
    "stills_multimodal": {
        "layout": "Stills",
        "script": "AVID - STILLS - Search Multi-Modal",
        "id_field": "stills_id",
        "description": "Search stills using combined text, visual, and transcript matching"
    },
    "archival_clip": {
        "layout": "FOOTAGE",
        "script": "AVID - ARCHIVAL - Search Clips",
        "id_field": "footage_id",
        "description": "Search archival footage clips using AI-powered matching"
    },
    "archival_frame": {
        "layout": "FRAMES", 
        "script": "AVID - ARCHIVAL - Search Frames",
        "id_field": "frames_id",
        "description": "Search individual archival footage frames using AI analysis"
    },
    "live_clip": {
        "layout": "FOOTAGE",
        "script": "AVID - LIVE - Search Clips",
        "id_field": "footage_id",
        "description": "Search live footage clips using AI-powered matching"
    },
    "live_frame": {
        "layout": "FRAMES", 
        "script": "AVID - LIVE - Search Frames",
        "id_field": "frames_id",
        "description": "Search individual live footage frames using AI analysis"
    }
}

def get_stills_id_from_record_id(token: str, record_id: str) -> str:
    """
    Get the Stills ID from a record ID by querying FileMaker.
    
    Args:
        token: Authentication token
        record_id: FileMaker record ID
    
    Returns:
        str: Stills ID if found, None otherwise
    """
    try:
        response = requests.get(
            config.url(f"layouts/Stills/records/{record_id}"),
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            stills_id = data['response']['data'][0]['fieldData'].get(FIELD_MAPPING["stills_id"])
            return stills_id
        else:
            print(f"  ❌ Failed to get record {record_id}: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"  ❌ Error getting Stills ID for record {record_id}: {e}")
        return None

def get_footage_id_from_record_id(token: str, record_id: str) -> str:
    """
    Get the Footage ID from a record ID by querying FileMaker.
    
    Args:
        token: Authentication token
        record_id: FileMaker record ID
    
    Returns:
        str: Footage ID if found, None otherwise
    """
    try:
        response = requests.get(
            config.url(f"layouts/FOOTAGE/records/{record_id}"),
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            footage_id = data['response']['data'][0]['fieldData'].get(FIELD_MAPPING["footage_id"])
            return footage_id
        else:
            print(f"  ❌ Failed to get record {record_id}: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"  ❌ Error getting Footage ID for record {record_id}: {e}")
        return None

def get_business_id_from_record_id(token: str, record_id: str, layout: str, id_field_key: str) -> str:
    """
    Generic function to get business ID from record ID.
    
    Args:
        token: Authentication token
        record_id: FileMaker record ID
        layout: Layout name (Stills or Footage)
        id_field_key: Key for ID field in FIELD_MAPPING
        
    Returns:
        str: Business ID if found, None otherwise
    """
    try:
        response = requests.get(
            config.url(f"layouts/{layout}/records/{record_id}"),
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            business_id = data['response']['data'][0]['fieldData'].get(FIELD_MAPPING[id_field_key])
            return business_id
        else:
            print(f"  ❌ Failed to get record {record_id}: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"  ❌ Error getting {id_field_key} for record {record_id}: {e}")
        return None

def get_frame_data_from_record_id(token: str, record_id: str) -> dict:
    """
    Get both FRAMES_ID and FRAMES_TC_IN from a record ID for frame searches.
    
    Args:
        token: Authentication token
        record_id: FileMaker record ID
        
    Returns:
        dict: Frame data with 'id' and 'timecode' keys, or None if failed
    """
    try:
        response = requests.get(
            config.url(f"layouts/FRAMES/records/{record_id}"),
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            field_data = data['response']['data'][0]['fieldData']
            
            frames_id = field_data.get(FIELD_MAPPING["frames_id"])
            frames_tc_in = field_data.get(FIELD_MAPPING["frames_tc_in"])
            
            if frames_id:
                return {
                    "id": frames_id,
                    "timecode": frames_tc_in if frames_tc_in else ""
                }
            else:
                return None
        else:
            print(f"  ❌ Failed to get frame record {record_id}: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"  ❌ Error getting frame data for record {record_id}: {e}")
        return None

def convert_record_ids_to_business_ids(record_ids, search_type, token):
    """
    Convert FileMaker record IDs to business IDs (like INFO_STILLS_ID or INFO_FTG_ID).
    For frame searches, also includes timecode information.
    
    Args:
        record_ids: List of FileMaker record IDs
        search_type: Type of search (e.g., "stills_text", "archival_clip")
        token: FileMaker authentication token
        
    Returns:
        list: List of business IDs (strings) or frame data (dicts with id/timecode)
    """
    results = []
    is_frame_search = search_type.endswith('_frame')
    
    print(f"🔄 Converting {len(record_ids)} record IDs to business data...")
    
    # Get search configuration
    if search_type not in SEARCH_TYPE_MAPPING:
        print(f"  ⚠️ Unknown search type '{search_type}' - cannot convert IDs")
        return record_ids  # Return original IDs as fallback
    
    search_config = SEARCH_TYPE_MAPPING[search_type]
    layout = search_config["layout"]
    id_field_key = search_config["id_field"]
    
    for i, record_id in enumerate(record_ids):
        if is_frame_search:
            # For frame searches, get both ID and timecode
            frame_data = get_frame_data_from_record_id(token, record_id)
            if frame_data:
                results.append(frame_data)
            else:
                print(f"  ⚠️ Could not get frame data for record {record_id}")
        else:
            # For non-frame searches, just get the business ID
            business_id = get_business_id_from_record_id(token, record_id, layout, id_field_key)
            if business_id:
                results.append(business_id)
            else:
                print(f"  ⚠️ Could not get {id_field_key} for record {record_id}")
        
        # Progress indicator for large result sets
        if (i + 1) % 20 == 0:
            print(f"  📊 Processed {i + 1}/{len(record_ids)} conversions...")
    
    result_type = "frame data entries" if is_frame_search else "IDs"
    print(f"✅ Successfully converted {len(results)} {result_type}")
    return results

def validate_parameters(search_type, query):
    """Validate input parameters."""
    if not search_type:
        raise ValueError("Search type parameter is required")
    
    if search_type not in SEARCH_TYPE_MAPPING:
        available_types = list(SEARCH_TYPE_MAPPING.keys())
        raise ValueError(f"Invalid search type: {search_type}. Must be one of: {available_types}")
    
    if not query or not query.strip():
        raise ValueError("Query parameter is required and cannot be empty")
    
    return search_type, query.strip()

def extract_ranked_ids(response_data):
    """
    Extract ranked list of IDs from PSOS response.
    
    Args:
        response_data: The response from the PSOS script
        
    Returns:
        list: Ranked list of record IDs
    """
    try:
        # The structure will depend on what the PSOS script returns
        # For now, we'll handle the basic response structure
        
        if not response_data:
            print("⚠️ Empty response from PSOS script")
            return []
        
        # Check if response contains script result
        script_result = None
        if isinstance(response_data, dict):
            if 'response' in response_data and 'scriptResult' in response_data['response']:
                script_result = response_data['response']['scriptResult']
            elif 'scriptResult' in response_data:
                script_result = response_data['scriptResult']
        
        if script_result:
            # Try to parse script result as JSON
            try:
                if isinstance(script_result, str):
                    parsed_result = json.loads(script_result)
                else:
                    parsed_result = script_result
                
                # Extract IDs from parsed result
                if isinstance(parsed_result, list):
                    # Handle list of dictionaries with recordId and similarity
                    record_ids = []
                    for item in parsed_result:
                        if isinstance(item, dict) and 'recordId' in item:
                            record_ids.append(str(item['recordId']))
                        elif isinstance(item, str):
                            record_ids.append(item)
                        else:
                            record_ids.append(str(item))
                    return record_ids
                elif isinstance(parsed_result, dict) and 'ids' in parsed_result:
                    return [str(item) for item in parsed_result['ids'] if item]
                
            except json.JSONDecodeError:
                # If not JSON, treat as simple string/list
                if isinstance(script_result, str):
                    # Split by common delimiters and clean
                    ids = [id.strip() for id in script_result.replace(',', '\n').split('\n') if id.strip()]
                    return ids
        
        print("⚠️ Could not extract IDs from response format")
        return []
        
    except Exception as e:
        print(f"❌ Error extracting IDs from response: {e}")
        return []

def perform_semantic_search(search_type, query, token):
    """
    Perform semantic search using the appropriate PSOS script.
    
    Args:
        search_type: Type of search (e.g., "stills_text", "archival_clip")
        query: Search query
        token: FileMaker authentication token
        
    Returns:
        list: Ranked list of record IDs
    """
    try:
        search_config = SEARCH_TYPE_MAPPING[search_type]
        layout = search_config["layout"]
        script = search_config["script"]
        description = search_config["description"]
        
        print(f"🔍 Performing search: {search_type}")
        print(f"📝 Description: {description}")
        print(f"🎯 Query: '{query}'")
        print(f"📋 Using layout: {layout}, script: {script}")
        
        # Execute the PSOS script
        # Note: execute_script(token, script_name, layout_name, script_parameter)
        response = config.execute_script(token, script, layout, query)
        
        print(f"✅ PSOS script executed successfully")
        
        # Extract ranked IDs from response
        ranked_record_ids = extract_ranked_ids(response)
        
        print(f"📊 Found {len(ranked_record_ids)} raw record IDs")
        
        # Convert FileMaker record IDs to business data
        ranked_business_data = convert_record_ids_to_business_ids(ranked_record_ids, search_type, token)
        
        return ranked_business_data
        
    except Exception as e:
        print(f"❌ Error performing semantic search: {e}")
        return []

def main():
    """Main execution function."""
    try:
        # Validate we have the right number of arguments
        if len(sys.argv) != 3:
            print("❌ Error: Exactly 2 arguments required")
            print("Usage: avid-search.py <search_type> <query>")
            print("  search_type: One of the following:")
            for search_type in SEARCH_TYPE_MAPPING.keys():
                print(f"    - {search_type}")
            print("  query: Search query string")
            sys.exit(1)
        
        search_type = sys.argv[1]
        query = sys.argv[2]
        
        print(f"🚀 Starting Avid Search")
        print(f"🔍 Search Type: {search_type}")
        print(f"📝 Query: '{query}'")
        
        # Validate parameters
        search_type, query = validate_parameters(search_type, query)
        
        # Get authentication token
        token = config.get_token()
        print("🔑 Authentication token obtained")
        
        # Perform semantic search
        ranked_data = perform_semantic_search(search_type, query, token)
        
        if ranked_data:
            print(f"✅ Search completed successfully")
            print(f"📋 Results (ranked by relevance):")
            
            is_frame_search = search_type.endswith('_frame')
            
            for i, result in enumerate(ranked_data, 1):
                if is_frame_search:
                    # Frame searches return dict with id and timecode
                    print(f"  {i}. {result['id']} (TC: {result['timecode']})")
                else:
                    # Other searches return just the ID string
                    print(f"  {i}. {result}")
            
            # Output results as JSON for API consumption
            results = {
                "query": query,
                "search_type": search_type,
                "total_results": len(ranked_data),
                "ranked_results": ranked_data  # Changed from ranked_ids to ranked_results
            }
            
            print(f"\n📊 JSON Results:")
            print(json.dumps(results, indent=2))
            
        else:
            print(f"📭 No results found for query: '{query}'")
            # Still output empty results structure
            results = {
                "query": query,
                "search_type": search_type,
                "total_results": 0,
                "ranked_results": []
            }
            print(f"\n📊 JSON Results:")
            print(json.dumps(results, indent=2))
        
    except Exception as e:
        print(f"❌ Critical error in avid-search: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 