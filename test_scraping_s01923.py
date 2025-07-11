#!/usr/bin/env python3
import sys
import json
import warnings
import os
from pathlib import Path

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

def test_scraping_functions(stills_id, record_data):
    """Test all scraping functions individually."""
    print(f"\n🔍 TESTING SCRAPING FUNCTIONS FOR {stills_id}...")
    
    # Import scraping functions
    sys.path.append(str(Path(__file__).resolve().parent / "jobs"))
    
    try:
        from stills_autolog_04_scrape_url import (
            scrape_level_1_html, 
            scrape_level_2_vision, 
            scrape_level_3_summary,
            is_metadata_sufficient,
            load_prompts
        )
        print(f"✅ Successfully imported scraping functions")
    except Exception as e:
        print(f"❌ Error importing scraping functions: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    # Check URL
    url_to_scrape = record_data.get('SPECS_URL', '')
    if not url_to_scrape:
        print(f"❌ No URL found in record - cannot test scraping")
        return None
    
    print(f"📁 URL to scrape: {url_to_scrape}")
    
    # Test OpenAI setup
    try:
        import openai
        token = config.get_token()
        system_globals = config.get_system_globals(token)
        api_key = system_globals.get("SystemGlobals_AutoLog_OpenAI_API_Key")
        if not api_key:
            print("❌ OpenAI API Key not found")
            return None
        client = openai.OpenAI(api_key=api_key)
        print(f"✅ OpenAI client created")
    except Exception as e:
        print(f"❌ Error setting up OpenAI: {e}")
        return None
    
    # Test basic web request
    try:
        import requests
        from bs4 import BeautifulSoup
        
        print(f"\n🌐 Testing basic web request...")
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        response = requests.get(url_to_scrape, timeout=15, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        print(f"✅ Successfully fetched webpage ({len(response.text)} chars)")
    except Exception as e:
        print(f"❌ Error fetching webpage: {e}")
        return None
    
    # Test Level 1: HTML parsing
    print(f"\n📄 TESTING LEVEL 1: HTML PARSING")
    try:
        level1_result = scrape_level_1_html(soup)
        if level1_result:
            print(f"✅ Level 1 SUCCESS")
            print(f"  Result: {level1_result[:200]}{'...' if len(level1_result) > 200 else ''}")
            print(f"  Length: {len(level1_result)} chars")
            print(f"  Sufficient: {is_metadata_sufficient(level1_result)}")
        else:
            print(f"❌ Level 1 failed to find content")
    except Exception as e:
        print(f"❌ Level 1 error: {e}")
        level1_result = None
    
    # Test Level 2: Selenium screenshot (only if Level 1 failed)
    level2_result = None
    if not level1_result:
        print(f"\n📸 TESTING LEVEL 2: SELENIUM SCREENSHOT")
        try:
            # Check if selenium is available
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            print(f"✅ Selenium imported successfully")
            
            screenshot_path = f"/tmp/test_screenshot_{stills_id}.png"
            level2_result = scrape_level_2_vision(url_to_scrape, screenshot_path, client)
            
            if level2_result:
                print(f"✅ Level 2 SUCCESS")
                print(f"  Result: {level2_result[:200]}{'...' if len(level2_result) > 200 else ''}")
                print(f"  Length: {len(level2_result)} chars")
                print(f"  Sufficient: {is_metadata_sufficient(level2_result)}")
            else:
                print(f"❌ Level 2 failed to extract content")
                
        except ImportError as e:
            print(f"⚠️ Selenium not available: {e}")
            print(f"  Install with: pip3 install selenium")
        except Exception as e:
            print(f"❌ Level 2 error: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"\n📸 SKIPPING LEVEL 2: Level 1 succeeded")
    
    # Test Level 3: AI summary (only if previous levels failed)
    level3_result = None
    if not level1_result and not level2_result:
        print(f"\n🤖 TESTING LEVEL 3: AI SUMMARY")
        try:
            level3_result = scrape_level_3_summary(soup, client)
            
            if level3_result:
                print(f"✅ Level 3 SUCCESS")
                print(f"  Result: {level3_result[:200]}{'...' if len(level3_result) > 200 else ''}")
                print(f"  Length: {len(level3_result)} chars")
                print(f"  Sufficient: {is_metadata_sufficient(level3_result)}")
            else:
                print(f"❌ Level 3 failed to extract content")
                
        except Exception as e:
            print(f"❌ Level 3 error: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"\n🤖 SKIPPING LEVEL 3: Previous level succeeded")
    
    # Return results
    return {
        'level1': level1_result,
        'level2': level2_result, 
        'level3': level3_result,
        'url': url_to_scrape
    }

def test_full_scraping_script(stills_id):
    """Test the actual scraping script as a subprocess."""
    print(f"\n⚙️ TESTING FULL SCRAPING SCRIPT...")
    
    try:
        import subprocess
        script_path = Path(__file__).resolve().parent / "jobs" / "stills_autolog_04_scrape_url.py"
        
        print(f"  Script path: {script_path}")
        print(f"  Script exists: {script_path.exists()}")
        
        if not script_path.exists():
            print(f"❌ Script not found!")
            return False
        
        # Run the script with dry-run approach (we'll catch the error before it writes)
        print(f"  Running script with stills ID: {stills_id}")
        
        result = subprocess.run(
            ["python3", str(script_path), stills_id], 
            capture_output=True, 
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        print(f"\n📊 SCRIPT EXECUTION RESULTS:")
        print(f"  Return code: {result.returncode}")
        print(f"  STDOUT:")
        if result.stdout:
            print(f"    {result.stdout}")
        else:
            print(f"    (empty)")
            
        print(f"  STDERR:")
        if result.stderr:
            print(f"    {result.stderr}")
        else:
            print(f"    (empty)")
        
        if result.returncode == 0:
            print(f"✅ Script executed successfully")
            return True
        else:
            print(f"❌ Script failed with return code {result.returncode}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"❌ Script timed out after 5 minutes")
        return False
    except Exception as e:
        print(f"❌ Error running script: {e}")
        return False

if __name__ == "__main__":
    stills_id = "S01923"
    
    print(f"🧪 COMPREHENSIVE SCRAPING TEST FOR {stills_id}")
    print("=" * 60)
    print("⚠️  NOTE: This is a READ-ONLY test - no data will be written back to the record")
    print("=" * 60)
    
    # 1. Check current record data
    record_data, record_id, token = test_record_data(stills_id)
    if not record_data:
        print(f"❌ Cannot proceed without record data")
        sys.exit(1)
    
    # 2. Test scraping functions individually
    scraping_results = test_scraping_functions(stills_id, record_data)
    
    # 3. Test full script execution (this might write to the record - be careful!)
    print(f"\n⚠️  CAUTION: The next test will run the actual script which WILL update the record!")
    print(f"   Do you want to proceed? (This is just a warning - the script will run)")
    
    # Actually, let's not run the full script since user said not to write back
    print(f"   SKIPPING full script test to avoid writing to record as requested")
    
    # Summary
    print(f"\n📋 SUMMARY:")
    print(f"  Record found: {'✅' if record_data else '❌'}")
    if scraping_results:
        print(f"  Level 1 (HTML): {'✅' if scraping_results['level1'] else '❌'}")
        print(f"  Level 2 (Selenium): {'✅' if scraping_results['level2'] else '❌'}")
        print(f"  Level 3 (AI Summary): {'✅' if scraping_results['level3'] else '❌'}")
        
        # Show what would be scraped
        best_result = scraping_results['level1'] or scraping_results['level2'] or scraping_results['level3']
        if best_result:
            print(f"\n✅ WOULD SCRAPE THIS CONTENT:")
            print(f"  {best_result}")
        else:
            print(f"\n❌ NO CONTENT WOULD BE SCRAPED")
    else:
        print(f"  Scraping functions: ❌")

    print(f"\n✅ Test completed - no data was written to the record") 