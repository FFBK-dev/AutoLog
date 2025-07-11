#!/usr/bin/env python3
import sys
import time
import warnings
import requests
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent))
import config

def test_psos_script_standalone(stills_id, script_name):
    """Test running a PSOS script standalone."""
    print(f"\n=== Testing PSOS Script: {script_name} ===")
    
    try:
        token = config.get_token()
        print(f"✅ Token obtained successfully")
        
        # Get record ID
        record_id = config.find_record_id(token, "Stills", {"INFO_STILLS_ID": f"=={stills_id}"})
        print(f"✅ Record ID found: {record_id}")
        
        # Get current status before running script
        response = requests.get(
            config.url(f"layouts/Stills/records/{record_id}"), 
            headers=config.api_headers(token), 
            verify=False
        )
        response.raise_for_status()
        current_status = response.json()['response']['data'][0]['fieldData']['AutoLog_Status']
        print(f"📊 Current status: {current_status}")
        
        # Execute the PSOS script
        print(f"🔄 Executing PSOS script...")
        start_time = time.time()
        result = config.execute_script(token, script_name, "Stills", stills_id)
        end_time = time.time()
        
        print(f"⏱️  Script execution took {end_time - start_time:.2f} seconds")
        print(f"📝 Script result: {result}")
        
        # Check if the script executed successfully
        script_error = result.get('response', {}).get('scriptError', '0')
        script_result = result.get('response', {}).get('scriptResult', '')
        
        print(f"🔍 Script error code: {script_error}")
        print(f"🔍 Script result: {script_result}")
        
        if script_error == '0':
            print(f"✅ PSOS script executed successfully")
            return True, record_id
        else:
            print(f"❌ PSOS script failed with error {script_error}: {script_result}")
            return False, record_id
            
    except Exception as e:
        print(f"❌ Error testing PSOS script: {e}")
        return False, None

def test_status_update_with_delays(record_id, token, new_status, delays=[0, 1, 2, 5]):
    """Test status updates with different delays after PSOS execution."""
    print(f"\n=== Testing Status Updates with Delays ===")
    
    for delay in delays:
        print(f"\n🔄 Trying status update with {delay}s delay...")
        
        if delay > 0:
            time.sleep(delay)
        
        try:
            payload = {"fieldData": {"AutoLog_Status": new_status}}
            response = requests.patch(
                config.url(f"layouts/Stills/records/{record_id}"), 
                headers=config.api_headers(token), 
                json=payload, 
                verify=False
            )
            
            print(f"📊 Status update response code: {response.status_code}")
            if response.status_code == 200:
                print(f"✅ Status update successful with {delay}s delay")
                return True
            else:
                print(f"❌ Status update failed: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"❌ Status update exception: {e}")
    
    return False

def test_record_access_patterns(record_id, token):
    """Test various record access patterns to understand locking."""
    print(f"\n=== Testing Record Access Patterns ===")
    
    # Test 1: Simple GET
    print(f"🔄 Test 1: Simple GET request...")
    try:
        response = requests.get(
            config.url(f"layouts/Stills/records/{record_id}"), 
            headers=config.api_headers(token), 
            verify=False
        )
        print(f"  GET response: {response.status_code}")
    except Exception as e:
        print(f"  GET error: {e}")
    
    # Test 2: GET with different layout
    print(f"🔄 Test 2: GET with different layout...")
    try:
        response = requests.get(
            config.url(f"layouts/Stills_API/records/{record_id}"), 
            headers=config.api_headers(token), 
            verify=False
        )
        print(f"  GET (different layout) response: {response.status_code}")
    except Exception as e:
        print(f"  GET (different layout) error: {e}")
    
    # Test 3: PATCH with minimal data
    print(f"🔄 Test 3: PATCH with minimal data...")
    try:
        payload = {"fieldData": {"AI_DevConsole": "Test update"}}
        response = requests.patch(
            config.url(f"layouts/Stills/records/{record_id}"), 
            headers=config.api_headers(token), 
            json=payload, 
            verify=False
        )
        print(f"  PATCH response: {response.status_code}")
        if response.status_code != 200:
            print(f"  PATCH error details: {response.text}")
    except Exception as e:
        print(f"  PATCH error: {e}")

def run_full_test(stills_id):
    """Run the full test suite."""
    print(f"🎯 Starting PSOS diagnostics for stills_id: {stills_id}")
    
    # Test 1: Generate Embeddings PSOS
    print(f"\n" + "="*50)
    success1, record_id = test_psos_script_standalone(stills_id, "STILLS - AutoLog - 06B - Generate Embeddings (PSOS)")
    
    if success1 and record_id:
        # Test status update after PSOS execution
        token = config.get_token()
        test_status_update_with_delays(record_id, token, "6 - Generating Embeddings")
        
        # Test record access patterns
        test_record_access_patterns(record_id, token)
    
    # Test 2: Apply Tags PSOS
    print(f"\n" + "="*50)
    success2, record_id = test_psos_script_standalone(stills_id, "STILLS - AutoLog - 07B - Apply Tags (PSOS)")
    
    if success2 and record_id:
        # Test status update after PSOS execution
        token = config.get_token()
        test_status_update_with_delays(record_id, token, "7 - Applying Tags")
    
    print(f"\n" + "="*50)
    print(f"🎯 Test Summary:")
    print(f"  Generate Embeddings PSOS: {'✅ PASS' if success1 else '❌ FAIL'}")
    print(f"  Apply Tags PSOS: {'✅ PASS' if success2 else '❌ FAIL'}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_psos_scripts.py <stills_id>")
        sys.exit(1)
    
    stills_id = sys.argv[1]
    run_full_test(stills_id) 