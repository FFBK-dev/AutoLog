#!/usr/bin/env python3
import sys
import warnings
import json
from pathlib import Path
import requests

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["search_term"]

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID"
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

def parse_semantic_results(response) -> list:
    """
    Parse the semantic search results and extract record IDs sorted by similarity.
    
    Args:
        response: Response from FileMaker script (could be dict or string)
        
    Returns:
        list: Tuples of (record_id, similarity_score) sorted by similarity (highest first)
    """
    try:
        # Handle different response types
        if isinstance(response, dict):
            # If it's a dict, look for the script result
            script_result = response.get('response', {}).get('scriptResult', '')
            if script_result:
                response_str = script_result
            else:
                print("❌ No script result found in response")
                return []
        elif isinstance(response, str):
            response_str = response
        else:
            print(f"❌ Unexpected response type: {type(response)}")
            return []
        
        print(f"📋 Script result: {response_str[:200]}..." if len(response_str) > 200 else f"📋 Script result: {response_str}")
        
        # Find the JSON array in the response
        start = response_str.find('[{')
        if start == -1:
            print("❌ No JSON array found in response")
            return []
            
        end = response_str.rfind('}]') + 2
        if end == 1:
            print("❌ Could not find end of JSON array")
            return []
            
        json_str = response_str[start:end]
        print(f"📊 Parsing JSON array ({len(json_str)} characters)")
        
        # Parse the JSON
        records = json.loads(json_str)
        
        # Extract record IDs and similarity scores
        results = []
        for record in records:
            record_id = record.get('recordId')
            similarity = record.get('similarity', 0)
            if record_id:
                results.append((record_id, similarity))
        
        # Sort by similarity score (highest first)
        results.sort(key=lambda x: x[1], reverse=True)
        
        print(f"🎯 Found {len(results)} records with similarity scores")
        return results
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing error: {e}")
        return []
    except Exception as e:
        print(f"❌ Error parsing results: {e}")
        return []

def main():
    """Main function to run the semantic find workflow."""
    if len(sys.argv) != 2:
        print("❌ Error: Please provide a search term")
        print("Usage: python stills_semantic_find.py \"search term\"")
        sys.exit(1)
        
    search_term = sys.argv[1]
    print(f"🚀 Starting semantic find for: '{search_term}'")
    
    try:
        # Get authentication token
        token = config.get_token()
        
        # Execute the PSOS script
        print(f"🔍 Calling PSOS script 'Stills Semantic Find (PSOS)'...")
        response = config.execute_script(
            token=token,
            script_name="Stills Semantic Find (PSOS)",
            layout_name="Stills",
            script_parameter=search_term
        )
        
        print(f"✅ PSOS script executed successfully")
        
        # Parse the response to get record IDs
        results = parse_semantic_results(response)
        
        if not results:
            print("📭 No results found")
            return
        
        print(f"\n🎯 Converting {len(results)} record IDs to Stills IDs:")
        print("=" * 60)
        
        # Convert record IDs to Stills IDs
        for i, (record_id, similarity) in enumerate(results, 1):
            print(f"🔄 {i:2d}. Getting Stills ID for record {record_id} (similarity: {similarity:.4f})")
            stills_id = get_stills_id_from_record_id(token, record_id)
            
            if stills_id:
                print(f"    ✅ Stills ID: {stills_id}")
            else:
                print(f"    ❌ Could not retrieve Stills ID")
        
        print("=" * 60)
        print("🏁 Semantic search completed")
        
    except Exception as e:
        print(f"❌ Critical error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 