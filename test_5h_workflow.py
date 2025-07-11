#!/usr/bin/env python3
import sys
import json
import warnings
from pathlib import Path
import requests

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent))
import config

def test_record_data(stills_id):
    """Fetch and display current record data for debugging."""
    print(f"\n=== TESTING STILLS ID: {stills_id} ===")
    
    token = config.get_token()
    
    try:
        # Find the record
        record_id = config.find_record_id(token, "Stills", {"INFO_STILLS_ID": f"=={stills_id}"})
        print(f"✅ Found record ID: {record_id}")
        
        # Get full record data
        record_data = config.get_record(token, "Stills", record_id)
        
        # Display key fields
        print(f"\n📊 CURRENT RECORD DATA:")
        print(f"  Status: {record_data.get('AutoLog_Status', 'N/A')}")
        print(f"  Metadata length: {len(record_data.get('INFO_Metadata', ''))}")
        print(f"  URL: {record_data.get('SPECS_URL', 'N/A')}")
        print(f"  Server Path: {record_data.get('SPECS_Filepath_Server', 'N/A')}")
        print(f"  Source: {record_data.get('INFO_Source', 'N/A')}")
        print(f"  Archival ID: {record_data.get('INFO_Archival_ID', 'N/A')}")
        print(f"  Filename: {record_data.get('INFO_Filename', 'N/A')}")
        
        # Show metadata content (truncated)
        metadata = record_data.get('INFO_Metadata', '')
        if metadata:
            print(f"\n📝 METADATA PREVIEW (first 200 chars):")
            print(f"  {metadata[:200]}{'...' if len(metadata) > 200 else ''}")
        else:
            print(f"\n📝 METADATA: (empty)")
            
        return record_data, record_id, token
        
    except Exception as e:
        print(f"❌ Error fetching record: {e}")
        return None, None, None

def test_agentic_lookup_directly(stills_id, record_data):
    """Test the agentic lookup function directly."""
    print(f"\n🔍 TESTING AGENTIC LOOKUP DIRECTLY...")
    
    # Import the scraping functions
    sys.path.append(str(Path(__file__).resolve().parent / "jobs"))
    from stills_autolog_04_scrape_url import scrape_level_4_agentic_lookup, load_prompts
    
    server_path = record_data.get('SPECS_Filepath_Server', '')
    
    if not server_path:
        print("❌ No server path found!")
        return None
        
    print(f"  Server path: {server_path}")
    
    # Check if file exists
    if not Path(server_path).exists():
        print(f"❌ Image file not found at: {server_path}")
        return None
    else:
        print(f"✅ Image file exists")
    
    # Test prompts loading
    try:
        prompts = load_prompts()
        print(f"✅ Prompts loaded successfully")
        if "stills_agentic_lookup" in prompts:
            print(f"✅ Agentic lookup prompt found")
        else:
            print(f"❌ Agentic lookup prompt missing from prompts.json")
            return None
    except Exception as e:
        print(f"❌ Error loading prompts: {e}")
        return None
    
    # Test the agentic lookup
    try:
        result = scrape_level_4_agentic_lookup(record_data, server_path)
        if result:
            print(f"✅ Agentic lookup succeeded!")
            print(f"📝 Result: {result}")
            return result
        else:
            print(f"❌ Agentic lookup returned no result")
            return None
    except Exception as e:
        print(f"❌ Agentic lookup failed: {e}")
        return None

def test_controller_workflow(stills_id):
    """Test the controller workflow step by step."""
    print(f"\n🔄 TESTING CONTROLLER WORKFLOW...")
    
    # Import controller functions
    sys.path.append(str(Path(__file__).resolve().parent / "controllers"))
    from stills_autolog_controller import process_single_step, FIELD_MAPPING
    
    token = config.get_token()
    
    try:
        # Get the record in the format the controller expects
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        response = requests.get(
            config.url(f"layouts/Stills/records/{record_id}"), 
            headers=config.api_headers(token), 
            verify=False
        )
        response.raise_for_status()
        record = response.json()['response']['data'][0]
        
        print(f"✅ Got record for controller")
        print(f"  Current status: {record['fieldData'].get(FIELD_MAPPING['status'], 'N/A')}")
        
        # Process the step
        print(f"\n⚙️ Processing single step...")
        result = process_single_step(record, token)
        print(f"✅ Process step result: {result}")
        
        # Check new status
        response = requests.get(
            config.url(f"layouts/Stills/records/{record_id}"), 
            headers=config.api_headers(token), 
            verify=False
        )
        response.raise_for_status()
        updated_record = response.json()['response']['data'][0]
        new_status = updated_record['fieldData'].get(FIELD_MAPPING['status'], 'N/A')
        print(f"📊 New status: {new_status}")
        
        return new_status
        
    except Exception as e:
        print(f"❌ Controller workflow failed: {e}")
        return None

def run_full_test(stills_id):
    """Run complete test suite."""
    print(f"🧪 FULL WORKFLOW TEST FOR {stills_id}")
    print("=" * 50)
    
    # 1. Check current record data
    record_data, record_id, token = test_record_data(stills_id)
    if not record_data:
        return
    
    # 2. Test agentic lookup directly
    agentic_result = test_agentic_lookup_directly(stills_id, record_data)
    
    # 3. Test controller workflow
    new_status = test_controller_workflow(stills_id)
    
    print(f"\n📋 SUMMARY:")
    print(f"  Record found: {'✅' if record_data else '❌'}")
    print(f"  Agentic lookup: {'✅' if agentic_result else '❌'}")
    print(f"  Controller workflow: {'✅' if new_status else '❌'}")
    if new_status:
        print(f"  Final status: {new_status}")

def set_status_for_testing(stills_id, status):
    """Helper to set a specific status for testing."""
    print(f"\n🔧 SETTING STATUS TO '{status}' FOR TESTING...")
    
    token = config.get_token()
    
    try:
        record_id = config.find_record_id(token, "Stills", {"INFO_STILLS_ID": f"=={stills_id}"})
        payload = {"fieldData": {"AutoLog_Status": status}}
        response = requests.patch(
            config.url(f"layouts/Stills/records/{record_id}"), 
            headers=config.api_headers(token), 
            json=payload, 
            verify=False
        )
        response.raise_for_status()
        print(f"✅ Status set to: {status}")
        return True
    except Exception as e:
        print(f"❌ Failed to set status: {e}")
        return False

if __name__ == "__main__":
    stills_id = "S04619"
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "set-status" and len(sys.argv) > 2:
            # Set status for testing
            status = sys.argv[2]
            set_status_for_testing(stills_id, status)
        elif sys.argv[1] == "agentic-only":
            # Test just the agentic lookup
            record_data, _, _ = test_record_data(stills_id)
            if record_data:
                test_agentic_lookup_directly(stills_id, record_data)
        elif sys.argv[1] == "controller-only":
            # Test just the controller
            test_controller_workflow(stills_id)
        else:
            print("Usage:")
            print("  python test_5h_workflow.py                    # Full test")
            print("  python test_5h_workflow.py set-status STATUS  # Set status")
            print("  python test_5h_workflow.py agentic-only       # Test agentic lookup only")
            print("  python test_5h_workflow.py controller-only    # Test controller only")
    else:
        # Full test
        run_full_test(stills_id) 