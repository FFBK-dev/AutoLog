#!/usr/bin/env python3
import sys
import time
import requests
import warnings
from pathlib import Path
from bs4 import BeautifulSoup
import json
import openai

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent))
import config

def test_url_accessibility(url):
    """Test if the URL is accessible and what content we get."""
    print(f"🔍 Testing URL accessibility: {url}")
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        response = requests.get(url, timeout=15, headers=headers)
        
        print(f"  Status Code: {response.status_code}")
        print(f"  Response Size: {len(response.text)} characters")
        print(f"  Content Type: {response.headers.get('Content-Type', 'Unknown')}")
        
        if response.status_code != 200:
            print(f"  Response Text Preview: {response.text[:500]}...")
            return False, response.text
        
        # Check if it's actually HTML content
        content_type = response.headers.get('Content-Type', '')
        if 'html' not in content_type.lower():
            print(f"  ❌ Content is not HTML: {content_type}")
            return False, response.text
        
        # Parse with BeautifulSoup to check structure
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.find('title')
        print(f"  Page Title: {title.text if title else 'No title found'}")
        
        # Check for common blocking patterns
        if is_blocking_page(response.text, title.text if title else ""):
            print(f"  🚫 Detected blocking/verification page")
            return False, response.text
        
        # Check meta description
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            print(f"  Meta Description: {meta_desc['content'][:100]}...")
        
        # Check for main content areas
        main_content = soup.find('main') or soup.find('article') or soup.find('#main-content')
        if main_content:
            content_text = main_content.get_text(strip=True)
            print(f"  Main Content Length: {len(content_text)} characters")
            print(f"  Main Content Preview: {content_text[:200]}...")
        else:
            print(f"  ❌ No main content area found")
        
        return True, response.text
        
    except Exception as e:
        print(f"  ❌ Error accessing URL: {e}")
        return False, str(e)

def is_blocking_page(page_source, title=""):
    """Check if the page is a blocking/verification page."""
    blocking_indicators = [
        "human verification",
        "captcha",
        "cloudflare",
        "aws waf",
        "bot detection",
        "please verify",
        "security check",
        "403 forbidden",
        "access denied",
        "blocked",
        "not available",
        "404 not found"
    ]
    
    content_lower = (page_source + " " + title).lower()
    found_indicators = [indicator for indicator in blocking_indicators if indicator in content_lower]
    
    if found_indicators:
        print(f"  🚫 Blocking indicators found: {found_indicators}")
        return True
    
    return False

def test_metadata_extraction(html_content, stills_id):
    """Test the metadata extraction process."""
    print(f"\n🔍 Testing metadata extraction for {stills_id}")
    
    try:
        # Get OpenAI API key
        token = config.get_token()
        system_globals = config.get_system_globals(token)
        api_key = system_globals.get("SystemGlobals_AutoLog_OpenAI_API_Key")
        
        if not api_key:
            print(f"  ❌ OpenAI API Key not found")
            return False
        
        client = openai.OpenAI(api_key=api_key)
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Test Level 1: HTML parsing
        print(f"  🔍 Testing Level 1: HTML parsing...")
        level1_result = test_level1_parsing(soup, client)
        
        # Test Level 2: AI text extraction  
        print(f"  🔍 Testing Level 2: AI text extraction...")
        level2_result = test_level2_ai_extraction(soup, client)
        
        print(f"\n📊 Extraction Results:")
        print(f"  Level 1 (HTML): {'✅ SUCCESS' if level1_result else '❌ FAILED'}")
        print(f"  Level 2 (AI): {'✅ SUCCESS' if level2_result else '❌ FAILED'}")
        
        return level1_result or level2_result
        
    except Exception as e:
        print(f"  ❌ Error in metadata extraction: {e}")
        return False

def test_level1_parsing(soup, client):
    """Test Level 1 HTML parsing."""
    try:
        # Try meta tags first
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            content = meta_desc['content']
            print(f"    Meta description found: {content[:100]}...")
            if is_content_sufficient(content, client):
                print(f"    ✅ Meta description is sufficient")
                return True
            else:
                print(f"    ❌ Meta description not sufficient")
        
        # Try OG description
        og_desc = soup.find('meta', {'property': 'og:description'})
        if og_desc and og_desc.get('content'):
            content = og_desc['content']
            print(f"    OG description found: {content[:100]}...")
            if is_content_sufficient(content, client):
                print(f"    ✅ OG description is sufficient")
                return True
            else:
                print(f"    ❌ OG description not sufficient")
        
        # Try content selectors
        selectors = ['.caption', '.description', '.article-body', 'article', 'main']
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                content = element.get_text(separator=" ", strip=True)
                print(f"    Found content with {selector}: {len(content)} chars")
                if len(content) > 20:
                    print(f"    Content preview: {content[:100]}...")
                    if is_content_sufficient(content, client):
                        print(f"    ✅ Content from {selector} is sufficient")
                        return True
                    else:
                        print(f"    ❌ Content from {selector} not sufficient")
        
        return False
        
    except Exception as e:
        print(f"    ❌ Error in Level 1 parsing: {e}")
        return False

def test_level2_ai_extraction(soup, client):
    """Test Level 2 AI text extraction."""
    try:
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "header", "footer"]):
            script.decompose()
        
        full_text = soup.get_text(separator='\n', strip=True)
        if not full_text:
            print(f"    ❌ No text content found")
            return False
        
        # Truncate to avoid token limits
        max_chars = 5000  # Smaller for testing
        truncated_text = full_text[:max_chars]
        
        print(f"    Full text length: {len(full_text)} chars")
        print(f"    Truncated text length: {len(truncated_text)} chars")
        print(f"    Text preview: {truncated_text[:200]}...")
        
        # Simple AI extraction test
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": f"Extract any metadata, descriptions, or archival information from this webpage text. Focus on historical details, dates, names, locations, or image descriptions. Return only the relevant information:\n\n{truncated_text}"}
            ],
            temperature=0.1,
            max_tokens=300
        )
        
        extracted = response.choices[0].message.content
        print(f"    AI extracted: {extracted[:200]}...")
        
        if is_content_sufficient(extracted, client):
            print(f"    ✅ AI extraction is sufficient")
            return True
        else:
            print(f"    ❌ AI extraction not sufficient")
            return False
        
    except Exception as e:
        print(f"    ❌ Error in Level 2 AI extraction: {e}")
        return False

def is_content_sufficient(content, client):
    """Test if content is sufficient using OpenAI evaluation."""
    if not content or len(content.strip()) < 10:
        return False
    
    try:
        # Simple sufficiency check
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": f"Is this text useful metadata about a historical image or archival document? Answer with JSON containing 'useful' (true/false) and 'reason':\n\n{content[:1000]}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=100
        )
        
        evaluation = json.loads(response.choices[0].message.content)
        is_useful = evaluation.get("useful", False)
        reason = evaluation.get("reason", "No reason provided")
        
        print(f"      AI evaluation: {'USEFUL' if is_useful else 'NOT USEFUL'} - {reason}")
        return is_useful
        
    except Exception as e:
        print(f"      ❌ Error in AI evaluation: {e}")
        return False

def test_failed_url():
    """Test the specific URL that failed."""
    failed_url = "https://www.gettyimages.com/detail/3304131"
    stills_id = "S04968"
    
    print(f"🎯 Testing failed URL: {failed_url}")
    print(f"🎯 Stills ID: {stills_id}")
    
    # Test URL accessibility
    accessible, content = test_url_accessibility(failed_url)
    
    if accessible:
        # Test metadata extraction
        success = test_metadata_extraction(content, stills_id)
        print(f"\n🎯 Final Result: {'✅ SUCCESS' if success else '❌ FAILED'}")
    else:
        print(f"\n🎯 Final Result: ❌ URL NOT ACCESSIBLE")

if __name__ == "__main__":
    test_failed_url() 