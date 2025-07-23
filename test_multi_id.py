#!/usr/bin/env python3
"""
Test script to demonstrate multi-ID capabilities
"""

import json
import requests

# Test configuration
API_BASE = "http://localhost:8081"
API_KEY = "supersecret"

def test_multi_id_endpoint():
    """Test the multi-ID capabilities of individual endpoints."""
    
    print("🧪 Testing Multi-ID Endpoint Capabilities")
    print("=" * 50)
    
    # Test cases with different input formats
    test_cases = [
        {
            "name": "Single ID",
            "payload": {"stills_id": "S04871"}
        },
        {
            "name": "JSON Array",
            "payload": {"stills_id": ["S04871", "S04872", "S04873"]}
        },
        {
            "name": "Comma-separated",
            "payload": {"stills_id": "S04871,S04872,S04873"}
        },
        {
            "name": "Line-separated",
            "payload": {"stills_id": "S04871\nS04872\nS04873"}
        },
        {
            "name": "Space-separated",
            "payload": {"stills_id": "S04871 S04872 S04873"}
        }
    ]
    
    for test_case in test_cases:
        print(f"\n📋 Testing: {test_case['name']}")
        print(f"Payload: {json.dumps(test_case['payload'], indent=2)}")
        
        try:
            response = requests.post(
                f"{API_BASE}/run/stills_autolog_01_get_file_info",
                headers={
                    "x-api-key": API_KEY,
                    "Content-Type": "application/json"
                },
                json=test_case['payload'],
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Success: {result}")
            else:
                print(f"❌ Error: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"❌ Exception: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 Multi-ID testing completed!")

if __name__ == "__main__":
    test_multi_id_endpoint() 