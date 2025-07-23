#!/usr/bin/env python3
import sys
import warnings
import json
import requests
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent))
import config

def list_available_layouts():
    """List all available layouts in the FileMaker database."""
    try:
        print("🔍 Getting list of available layouts...")
        token = config.get_token()
        
        response = requests.get(
            config.url("layouts"),
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        
        if response.status_code == 200:
            layouts_data = response.json()['response']['layouts']
            print("📊 Available layouts:")
            for layout in layouts_data:
                print(f"  - {layout['name']}")
            return [layout['name'] for layout in layouts_data]
        else:
            print(f"❌ Error getting layouts: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"❌ Error listing layouts: {e}")
        return []

def check_specific_record():
    """Try to get a specific record using the patterns from working scripts."""
    try:
        print("\n🔍 Checking AI_Prompt field in FOOTAGE records...")
        token = config.get_token()
        
        # First, let's look specifically for LF0001 to see all its fields
        print(f"\n🔍 Searching specifically for LF0001...")
        search_response = requests.post(
            config.url("layouts/FOOTAGE/_find"),
            headers=config.api_headers(token),
            json={
                "query": [{"INFO_FTG_ID": "LF0001"}],
                "limit": 1
            },
            verify=False,
            timeout=30
        )
        
        if search_response.status_code == 200:
            search_records = search_response.json()['response']['data']
            if search_records:
                lf_record = search_records[0]['fieldData']
                print(f"🎯 Found LF0001!")
                print(f"  Record ID: {search_records[0]['recordId']}")
                
                # Show ALL field names to find the correct AI field
                all_fields = list(lf_record.keys())
                print(f"  Total fields: {len(all_fields)}")
                
                # Look for AI-related fields
                ai_fields = []
                prompt_fields = []
                global_fields = []
                
                for field in all_fields:
                    field_upper = field.upper()
                    if 'AI' in field_upper:
                        ai_fields.append(field)
                    if 'PROMPT' in field_upper:
                        prompt_fields.append(field)
                    if 'GLOBAL' in field_upper:
                        global_fields.append(field)
                
                print(f"\n📋 AI-related fields: {ai_fields}")
                print(f"📋 Prompt-related fields: {prompt_fields}")
                print(f"📋 Global-related fields: {global_fields}")
                
                # Check the exact field the script is looking for
                ai_prompt_value = lf_record.get('AI_Prompt', '[NOT FOUND]')
                print(f"\n🔍 Field 'AI_Prompt': {ai_prompt_value}")
                
                # Check if any AI/Prompt fields have values
                if ai_fields:
                    print(f"\n📝 AI field values:")
                    for field in ai_fields:
                        value = lf_record.get(field, '')
                        if value:
                            print(f"  {field}: {value}")
                        else:
                            print(f"  {field}: [Empty]")
                
                if prompt_fields:
                    print(f"\n📝 Prompt field values:")
                    for field in prompt_fields:
                        value = lf_record.get(field, '')
                        if value:
                            print(f"  {field}: {value}")
                        else:
                            print(f"  {field}: [Empty]")
                
                # Show first 20 fields alphabetically to see the structure
                print(f"\n📋 First 20 fields (alphabetical):")
                for i, field in enumerate(sorted(all_fields)[:20]):
                    value = lf_record.get(field, '')
                    value_preview = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                    print(f"  {i+1:2d}. {field}: {value_preview}")
                
            else:
                print(f"❌ LF0001 not found")
        elif search_response.status_code == 404:
            print(f"❌ LF0001 not found (404)")
        else:
            print(f"❌ Error searching for LF0001: {search_response.status_code}")
            try:
                error_data = search_response.json()
                print(f"   Error details: {error_data}")
            except:
                print(f"   Raw response: {search_response.text}")
        
        return True
            
    except Exception as e:
        print(f"❌ Error checking AI_Prompt field: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_ai_prompt_field():
    """Check what's currently in the AI_Prompt field for Footage records."""
    try:
        print("🔍 Checking AI_Prompt field in Footage layout...")
        
        # First, list available layouts
        layouts = list_available_layouts()
        
        # Look for footage-related layouts
        footage_layouts = [layout for layout in layouts if 'footage' in layout.lower() or 'ftg' in layout.lower()]
        if footage_layouts:
            print(f"\n📋 Found footage-related layouts: {footage_layouts}")
        
        # Try to get records using the working script approach
        success = check_specific_record()
        
        if not success:
            print("\n🔍 Trying alternative layout names...")
            for layout_name in ["Footage", "footage", "FTG", "Archival_Footage", "Live_Footage"]:
                if layout_name in layouts:
                    print(f"  -> Found layout: {layout_name}")
                    # Try with this layout
                    # ... could implement layout-specific checks here
        
    except Exception as e:
        print(f"❌ Error checking AI_Prompt field: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_ai_prompt_field() 