#!/usr/bin/env python3
import sys
import requests
from pathlib import Path
import warnings

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent))
import config

def test_url_access(url):
    """Test different ways of accessing the URL to see what's going wrong."""
    print(f"🔍 DETAILED URL TESTING: {url}")
    print("=" * 80)
    
    # Test 1: Basic request
    print(f"\n1️⃣ BASIC REQUEST TEST")
    try:
        response = requests.get(url, timeout=15)
        print(f"  Status code: {response.status_code}")
        print(f"  Content length: {len(response.text)}")
        print(f"  Content type: {response.headers.get('content-type', 'N/A')}")
        print(f"  Response headers: {dict(list(response.headers.items())[:5])}")
        
        if len(response.text) > 0:
            print(f"  Content preview (first 200 chars):")
            print(f"    {response.text[:200]}...")
        else:
            print(f"  ⚠️ Empty response!")
            
    except Exception as e:
        print(f"  ❌ Basic request failed: {e}")
    
    # Test 2: Request with user agent
    print(f"\n2️⃣ REQUEST WITH USER AGENT")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        print(f"  Status code: {response.status_code}")
        print(f"  Content length: {len(response.text)}")
        
        if len(response.text) > 0:
            print(f"  Content preview (first 200 chars):")
            print(f"    {response.text[:200]}...")
        else:
            print(f"  ⚠️ Still empty response!")
            
    except Exception as e:
        print(f"  ❌ User agent request failed: {e}")
    
    # Test 3: Check if it's a redirect
    print(f"\n3️⃣ REDIRECT ANALYSIS")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=False)
        print(f"  Initial status: {response.status_code}")
        
        if 300 <= response.status_code < 400:
            redirect_url = response.headers.get('location')
            print(f"  Redirect to: {redirect_url}")
            
            # Follow the redirect manually
            if redirect_url:
                final_response = requests.get(redirect_url, headers=headers, timeout=15)
                print(f"  Final status: {final_response.status_code}")
                print(f"  Final content length: {len(final_response.text)}")
        else:
            print(f"  No redirect detected")
            
    except Exception as e:
        print(f"  ❌ Redirect test failed: {e}")
    
    # Test 4: Test with session (cookies)
    print(f"\n4️⃣ SESSION WITH COOKIES TEST")
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'})
        
        response = session.get(url, timeout=15)
        print(f"  Status code: {response.status_code}")
        print(f"  Content length: {len(response.text)}")
        print(f"  Cookies received: {len(session.cookies)}")
        
        if len(response.text) > 0:
            print(f"  Content preview (first 200 chars):")
            print(f"    {response.text[:200]}...")
        else:
            print(f"  ⚠️ Still empty with session!")
            
    except Exception as e:
        print(f"  ❌ Session request failed: {e}")

def test_selenium_screenshot(url, stills_id):
    """Test what selenium actually captures."""
    print(f"\n5️⃣ SELENIUM DETAILED TEST")
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        import time
        import os
        
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--window-size=1280,1080")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        print(f"  Creating Chrome driver...")
        driver = webdriver.Chrome(options=chrome_options)
        
        print(f"  Navigating to URL...")
        driver.get(url)
        
        print(f"  Waiting for page load...")
        time.sleep(5)  # Give more time for JavaScript
        
        # Get page info
        title = driver.title
        current_url = driver.current_url
        page_source_length = len(driver.page_source)
        
        print(f"  Page title: {title}")
        print(f"  Current URL: {current_url}")
        print(f"  Page source length: {page_source_length}")
        
        # Take screenshot
        screenshot_path = f"/tmp/debug_screenshot_{stills_id}.png"
        driver.save_screenshot(screenshot_path)
        
        if os.path.exists(screenshot_path):
            screenshot_size = os.path.getsize(screenshot_path)
            print(f"  Screenshot saved: {screenshot_path} ({screenshot_size} bytes)")
        else:
            print(f"  ❌ Screenshot not created!")
        
        # Get some text content
        if page_source_length > 0:
            print(f"  Page source preview (first 300 chars):")
            print(f"    {driver.page_source[:300]}...")
        
        driver.quit()
        return screenshot_path if os.path.exists(screenshot_path) else None
        
    except ImportError:
        print(f"  ❌ Selenium not installed")
        return None
    except Exception as e:
        print(f"  ❌ Selenium test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    # Get S01923's URL
    print(f"🔍 GETTING S01923 URL...")
    
    token = config.get_token()
    try:
        record_id = config.find_record_id(token, "Stills", {"INFO_STILLS_ID": "==S01923"})
        record_data = config.get_record(token, "Stills", record_id)
        url = record_data.get('SPECS_URL', '')
        
        if not url:
            print(f"❌ No URL found for S01923")
            sys.exit(1)
            
        print(f"✅ Found URL: {url}")
        
    except Exception as e:
        print(f"❌ Error getting record: {e}")
        sys.exit(1)
    
    # Run all tests
    test_url_access(url)
    screenshot_path = test_selenium_screenshot(url, "S01923")
    
    print(f"\n🎯 SUMMARY:")
    print(f"  URL: {url}")
    print(f"  Screenshot created: {'✅' if screenshot_path else '❌'}")
    if screenshot_path:
        print(f"  Screenshot path: {screenshot_path}")
        print(f"  You can manually view this to see what Selenium captured") 