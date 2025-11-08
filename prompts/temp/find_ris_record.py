#!/usr/bin/env python3
"""
Find the Reverse Image Search record by import path
"""

import sys
import os
import warnings
import json
import requests
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

# Try different possible layout names for Reverse Image Search
POSSIBLE_LAYOUTS = [
    "Reverse Image Search",
    "RIS",
    "Image Search",
    "Search Log",
    "Stills_RIS",
    "STILLS_SEARCH"
]

def find_ris_record_by_path(token, partial_path="GettyImages-3302950.jpg"):
    """Find a record in Reverse Image Search log by import path."""
    
    print(f"🔍 Searching for record with import path containing: {partial_path}")
    
    for layout in POSSIBLE_LAYOUTS:
        try:
            print(f"\n  Trying layout: '{layout}'...") 
            
            # Try different possible field names for import path
            import_path_fields = [
                'SPECS_Filepath_Import',
                'Import_Path', 
                'FilePath_Import',
                'ImportPath',
                'Path',
                'File_Path'
            ]
            
            # Try to find a record with this import path
            for field_name in import_path_fields:
                try:
                    # Use wildcard search
                    query = {field_name: f"*{partial_path}*"}
                    
                    # Make raw API call to get more than just record ID
                    response = requests.post(
                        config.url(f"layouts/{layout}/_find"),
                        headers=config.api_headers(token),
                        json={"query": [query], "limit": 100},
                        verify=False
                    )
                    
                    if response.status_code == 200:
                        data = response.json()["response"]["data"]
                        if data:
                            print(f"    ✅ Found {len(data)} record(s) in '{layout}' using field '{field_name}'")
                            
                            # Get the first record
                            record = data[0]
                            record_id = record.get('recordId')
                            field_data = record.get('fieldData', {})
                            import_path = field_data.get(field_name, '')
                            
                            print(f"\n✅ Found matching record!")
                            print(f"   Layout: {layout}")
                            print(f"   Record ID: {record_id}")
                            print(f"   Import Path: {import_path}")
                            print(f"   Field Name: {field_name}")
                            
                            # Show all fields in the record
                            print(f"\n   All fields in record:")
                            for key, value in field_data.items():
                                if value and not key.startswith('_'):
                                    value_str = str(value)[:100]
                                    print(f"     {key}: {value_str}")
                            
                            return layout, record_id, field_data
                            
                except Exception as field_error:
                    # Field might not exist, try next field
                    continue
                
        except Exception as e:
            print(f"    ⚠️  Could not access layout '{layout}': {e}")
            continue
    
    print(f"\n❌ Could not find record with import path containing: {partial_path}")
    return None, None, None

if __name__ == "__main__":
    print("="*80)
    print("FINDING REVERSE IMAGE SEARCH RECORD")
    print("="*80)
    
    # Get FileMaker token
    token = config.get_token()
    
    # Search for the record
    layout, record_id, field_data = find_ris_record_by_path(token)
    
    if layout and record_id:
        print(f"\n{'='*80}")
        print(f"FOUND!")
        print(f"{'='*80}")
        print(f"\nTo analyze this record, you can:")
        print(f"1. Manually check the embedding in FileMaker")
        print(f"2. Check what thumbnail size it has")
        print(f"3. Compare to S00616's thumbnail (449x588)")
        
        # Try to get embedding info if field exists
        embedding_fields = ['AI_Embed_Image', 'Embedding', 'Image_Embedding', 'CLIP_Embedding']
        for field in embedding_fields:
            if field in field_data and field_data[field]:
                print(f"\n🧠 Found embedding in field: {field}")
                embedding_data = field_data[field]
                if isinstance(embedding_data, str):
                    print(f"   Length: {len(embedding_data)} characters")
                    print(f"   Preview: {embedding_data[:100]}...")
                break
    else:
        print(f"\n❌ Could not locate the Reverse Image Search record")
        print(f"\nPlease provide:")
        print(f"1. The exact layout/table name for Reverse Image Search")
        print(f"2. Or the full import path")

