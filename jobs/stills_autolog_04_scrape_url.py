# jobs/stills_autolog_04_scrape_url.py
import sys, os, time, requests, base64
import warnings
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

# Add the parent directory to the path to import your existing config
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["stills_id"]

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "url": "SPECS_URL",
    "metadata": "INFO_Metadata",
    "description_orig": "INFO_Description_Original",
    "copyright": "INFO_Copyright",
    "source": "INFO_Source",
    "archival_id": "INFO_Archival_ID",
    "globals_api_key_1": "SystemGlobals_AutoLog_OpenAI_API_Key_1",
    "globals_api_key_2": "SystemGlobals_AutoLog_OpenAI_API_Key_2",
    "globals_api_key_3": "SystemGlobals_AutoLog_OpenAI_API_Key_3",
    "globals_api_key_4": "SystemGlobals_AutoLog_OpenAI_API_Key_4",
    "globals_api_key_5": "SystemGlobals_AutoLog_OpenAI_API_Key_5"
}

def load_prompts():
    """Load prompts from prompts.json file."""
    # No longer needed since we're not using OpenAI
    pass

def call_openai_with_retry(client, messages, max_retries=3, base_delay=1.0, **kwargs):
    """Call OpenAI API with retry logic for rate limiting and other transient errors."""
    # No longer needed since we're not using OpenAI
    pass

# --- Helper Functions ---

def is_metadata_sufficient(text, client=None):
    """Uses simple heuristics to evaluate if the scraped text contains useful metadata."""
    if not text or not text.strip():
        return False
    
    # Quick checks for obviously insufficient content
    text_clean = text.strip()
    if len(text_clean) < 20:
        return False
    
    # Simple heuristic-based evaluation (no OpenAI calls)
    text_lower = text_clean.lower()
    
    # Check for obvious boilerplate/useless content
    boilerplate_phrases = [
        "stock photo", "search results", "download image", "cookies", 
        "privacy policy", "log in", "sign up", "free digital items", 
        "digital collection", "browse", "cart", "checkout", "shopping",
        "advertisement", "sponsored content", "click here", "learn more"
    ]
    
    boilerplate_count = sum(1 for phrase in boilerplate_phrases if phrase in text_lower)
    
    # Check for useful metadata indicators
    useful_indicators = [
        "date", "year", "photographer", "creator", "artist", "title", 
        "description", "location", "collection", "archive", "museum",
        "copyright", "rights", "permission", "circa", "historical",
        "dimensions", "medium", "subject", "depicts", "shows"
    ]
    
    useful_count = sum(1 for indicator in useful_indicators if indicator in text_lower)
    
    # Simple scoring
    if boilerplate_count > 3:
        print(f"  -> Metadata evaluation: ❌ NOT USEFUL (too much boilerplate: {boilerplate_count})")
        return False
    elif useful_count >= 2 and len(text_clean) >= 50:
        print(f"  -> Metadata evaluation: ✅ USEFUL (indicators: {useful_count}, length: {len(text_clean)})")
        return True
    else:
        print(f"  -> Metadata evaluation: ❌ NOT USEFUL (indicators: {useful_count}, length: {len(text_clean)})")
        return False

def scrape_url(url, client=None):
    """Orchestrates the different scraping methods to extract metadata from a URL."""
    print(f"  -> Found URL to scrape: {url}")
    
    try:
        # --- Begin Optimized Cascading Scraping with URL ---
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        response = requests.get(url, timeout=15, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Always run both Level 1 and Level 2 (both are fast and free)
        print("  -> Running comprehensive HTML extraction (Level 1 + 2)")
        
        # Level 1: Basic meta tags and structured data
        level1_content = scrape_level_1_html(soup)
        
        # Level 2: Enhanced content parsing
        level2_content = scrape_level_2_archival_ai(soup)
        
        # Combine results from both levels
        combined_content = []
        if level1_content:
            combined_content.append("=== META TAGS & STRUCTURED DATA ===")
            combined_content.append(level1_content)
        if level2_content:
            combined_content.append("=== PAGE CONTENT ===")
            combined_content.append(level2_content)
        
        if combined_content:
            scraped_content = "\n\n".join(combined_content)
            print(f"  -> Combined extraction: {len(scraped_content)} characters")
        else:
            scraped_content = None
            print(f"  -> No content extracted from either level")

        # Level 3: Disabled to avoid expensive OpenAI Vision API calls
        # if not scraped_content:
        #     screenshot_path = f"/tmp/screenshot_{int(time.time())}.png"
        #     scraped_content = scrape_level_3_enhanced_selenium(url, screenshot_path, client)
        
        return scraped_content
        
    except Exception as e:
        print(f"  -> Error in URL scraping: {e}")
        return None

def is_verification_page(page_source, title=""):
    """Check if the page is a verification/CAPTCHA page."""
    verification_indicators = [
        "human verification",
        "captcha",
        "cloudflare",
        "aws waf",
        "bot detection",
        "please verify",
        "security check",
        "403 forbidden",
        "access denied"
    ]
    
    content_lower = (page_source + " " + title).lower()
    return any(indicator in content_lower for indicator in verification_indicators)

# --- Scraping Methods ---

def scrape_level_1_html(soup):
    """Basic HTML parsing to extract metadata."""
    print("  -> Level 1: Extracting meta tags and structured data...")
    try:
        # Extract title, description, and other metadata
        title = soup.find('title')
        meta_description = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
        
        extracted_text = ""
        if title:
            extracted_text += f"Title: {title.get_text(strip=True)}\n"
        if meta_description:
            extracted_text += f"Description: {meta_description.get('content', '')}\n"
        
        # Look for specific metadata patterns
        for meta in soup.find_all('meta'):
            name = meta.get('name', '').lower()
            property_name = meta.get('property', '').lower()
            content = meta.get('content', '')
            
            if any(keyword in name or keyword in property_name for keyword in ['keywords', 'subject', 'creator', 'date', 'rights']):
                extracted_text += f"{name or property_name}: {content}\n"
        
        if extracted_text.strip():
            print(f"  -> Level 1: Found {len(extracted_text)} characters of meta data")
            return extracted_text.strip()
        else:
            print("  -> Level 1: No useful meta tags found")
            return None
            
    except Exception as e:
        print(f"  -> Level 1 failed: {e}")
        return None

def extract_structured_metadata(soup):
    """Extract structured metadata from archival sites like NYPL, LOC, etc."""
    metadata_parts = []
    
    # Look for common archival metadata patterns
    metadata_selectors = [
        # NYPL patterns
        '.item-summary', '.item-details', '.item-metadata',
        # Generic patterns  
        '.metadata', '.record-data', '.catalog-data', '.item-info',
        '.details', '.description', '.summary', '.about',
        # Dublin Core / schema.org patterns
        '[itemprop="description"]', '[itemprop="about"]', '[itemprop="keywords"]',
        # Archive-specific
        '.archival-description', '.finding-aid', '.catalog-record'
    ]
    
    for selector in metadata_selectors:
        elements = soup.select(selector)
        for element in elements:
            text = element.get_text(separator=" ", strip=True)
            if text and len(text) > 20:  # Basic length check
                metadata_parts.append(text)
    
    # Look for definition lists (common in archival sites)
    dl_elements = soup.find_all('dl')
    for dl in dl_elements:
        dt_dd_pairs = []
        dts = dl.find_all('dt')
        dds = dl.find_all('dd')
        
        for i, dt in enumerate(dts):
            if i < len(dds):
                key = dt.get_text(strip=True)
                value = dds[i].get_text(strip=True)
                if key and value and len(value) > 2:
                    dt_dd_pairs.append(f"{key}: {value}")
        
        if dt_dd_pairs:
            metadata_parts.extend(dt_dd_pairs)
    
    # Look for tables with metadata
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) == 2:
                key = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if key and value and len(value) > 2:
                    metadata_parts.append(f"{key}: {value}")
    
    if metadata_parts:
        # Join all found metadata
        combined = " | ".join(metadata_parts[:10])  # Limit to prevent too much text
        return combined
    
    return None

def scrape_level_2_archival_ai(soup):
    """Enhanced HTML parsing to extract structured archival metadata."""
    print("  -> Level 2: Extracting page content and structured data...")
    try:
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "header", "footer", "advertisement"]):
            script.decompose()
        
        # Try structured metadata extraction first
        structured_metadata = extract_structured_metadata(soup)
        if structured_metadata:
            print(f"  -> Level 2: Found structured metadata ({len(structured_metadata)} chars)")
            return structured_metadata
        
        # If structured extraction didn't work, try comprehensive text extraction
        # Focus on content-rich areas
        content_selectors = [
            'main', 'article', '.content', '#content', '.main-content',
            '.record-view', '.item-view', '.detail-view', '.metadata-view'
        ]
        
        extracted_content = []
        
        for selector in content_selectors:
            elements = soup.select(selector)
            for element in elements:
                # Get text but preserve some structure
                text = element.get_text(separator='\n', strip=True)
                if text and len(text) > 50:  # Only meaningful content
                    extracted_content.append(text)
        
        # If no content areas found, get body text but filter out common noise
        if not extracted_content:
            body = soup.find('body')
            if body:
                full_text = body.get_text(separator='\n', strip=True)
                # Filter out navigation, ads, etc.
                lines = full_text.split('\n')
                filtered_lines = []
                
                noise_keywords = [
                    'navigation', 'menu', 'footer', 'header', 'sidebar',
                    'advertisement', 'sponsored', 'cookie', 'privacy',
                    'terms of service', 'help', 'contact', 'about us',
                    'social media', 'follow us', 'newsletter', 'subscribe'
                ]
                
                for line in lines:
                    line = line.strip()
                    if len(line) > 10 and not any(keyword in line.lower() for keyword in noise_keywords):
                        filtered_lines.append(line)
                
                if filtered_lines:
                    extracted_content = ['\n'.join(filtered_lines)]
        
        # Combine and truncate
        if extracted_content:
            combined_text = '\n\n'.join(extracted_content)
            # Truncate to manageable size
            if len(combined_text) > 2000:
                combined_text = combined_text[:2000] + "..."
            
            print(f"  -> Level 2: Found page content ({len(combined_text)} chars)")
            return combined_text
        else:
            print("  -> Level 2: No useful page content found")
            return None
            
    except Exception as e:
        print(f"  -> Level 2 failed: {e}")
        return None

def scrape_level_3_enhanced_selenium(url, screenshot_path, client):
    """Takes multiple screenshots and sends them to GPT-4o Vision for comprehensive analysis."""
    print("  -> Attempting Level 3: Enhanced Selenium Screenshot Analysis...")
    try:
        # Setup headless browser
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--window-size=1280,1080")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        driver = webdriver.Chrome(options=chrome_options)
        
        # Add stealth measures
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        driver.get(url)
        time.sleep(5) # Wait for JavaScript to render
        
        # Check if we got a verification page
        page_title = driver.title
        page_source = driver.page_source
        
        if is_verification_page(page_source, page_title):
            print(f"  -> Detected verification/bot detection page (title: {page_title})")
            driver.quit()
            return None
        
        # Take multiple screenshots for comprehensive coverage
        screenshots = []
        
        # Screenshot 1: Full page overview
        full_screenshot_path = screenshot_path.replace('.png', '_full.png')
        driver.save_screenshot(full_screenshot_path)
        screenshots.append(('Full Page', full_screenshot_path))
        
        # Screenshot 2: Scroll down to capture middle content
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(2)
        mid_screenshot_path = screenshot_path.replace('.png', '_mid.png')
        driver.save_screenshot(mid_screenshot_path)
        screenshots.append(('Mid Page', mid_screenshot_path))
        
        # Screenshot 3: Scroll to bottom to capture footer/additional metadata
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        bottom_screenshot_path = screenshot_path.replace('.png', '_bottom.png')
        driver.save_screenshot(bottom_screenshot_path)
        screenshots.append(('Bottom Page', bottom_screenshot_path))
        
        driver.quit()
        
        # Analyze each screenshot and combine results
        all_results = []
        for section_name, screenshot_file in screenshots:
            try:
                print(f"    -> Analyzing {section_name} screenshot...")
                
                with open(screenshot_file, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode('utf-8')

                response = client.chat_completions_create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"Analyze this {section_name.lower()} screenshot from an archival website. Extract any metadata, descriptions, dates, historical context, or other information about the archival image/document. Focus on factual details that would be useful for cataloging. Return only the relevant metadata, ignore navigation and website elements."},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                            ]
                        }
                    ],
                    estimated_tokens=400
                )
                vision_text = response.choices[0].message.content.strip()
                
                if vision_text and len(vision_text) > 10:
                    all_results.append(f"{section_name}: {vision_text}")
                    print(f"      -> Found: {vision_text[:100]}{'...' if len(vision_text) > 100 else ''}")
                else:
                    print(f"      -> No useful content in {section_name}")
                    
            except Exception as e:
                print(f"      -> Error analyzing {section_name}: {e}")
            finally:
                # Clean up screenshot
                if os.path.exists(screenshot_file):
                    os.remove(screenshot_file)
        
        # Combine all results
        if all_results:
            combined_result = " | ".join(all_results)
            if is_metadata_sufficient(combined_result, client):
                print("  -> Success with Enhanced Selenium Screenshot Analysis.")
                return combined_result
        
    except Exception as e:
        print(f"  -> Level 3 Enhanced Selenium Screenshot Analysis failed: {e}")
    finally:
        # Clean up any remaining screenshots
        for ext in ['_full.png', '_mid.png', '_bottom.png']:
            cleanup_path = screenshot_path.replace('.png', ext)
            if os.path.exists(cleanup_path):
                os.remove(cleanup_path)
            
    print("  -> Level 3 failed to produce sufficient content.")
    return None

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    stills_id = sys.argv[1]
    token = config.get_token()
    
    try:
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        record_data = config.get_record(token, "Stills", record_id)
        
        url = record_data.get(FIELD_MAPPING["url"], '')
        if not url:
            print(f"  -> No URL found for {stills_id}")
            sys.exit(0)
        
        existing_metadata = record_data.get(FIELD_MAPPING["metadata"], '')
        
        print(f"  -> Scraping URL: {url}")
        scraped_content = scrape_url(url, None)  # No client needed anymore
        
        # --- Final Update ---
        if is_metadata_sufficient(scraped_content):
            print(f"  -> Successfully scraped content for {stills_id}.")
            
            # Ensure we're appending, not overwriting
            existing_metadata = existing_metadata or ""  # Handle None case explicitly
            
            # Check if URL content was already scraped to avoid duplicates
            if "--- SCRAPED FROM URL ---" in existing_metadata:
                print(f"  -> URL content already exists in metadata, appending with timestamp...")
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                new_metadata = f"{existing_metadata}\n\n--- SCRAPED FROM URL ({timestamp}) ---\n{scraped_content}"
            else:
                new_metadata = f"{existing_metadata}\n\n--- SCRAPED FROM URL ---\n{scraped_content}"
            
            # Double-check that we're not losing existing content
            if existing_metadata and existing_metadata.strip() and existing_metadata.strip() not in new_metadata:
                print(f"  -> WARNING: Existing metadata may be lost! Existing: {len(existing_metadata)} chars")
                print(f"  -> New metadata: {len(new_metadata)} chars")
                # Force append to be safe
                new_metadata = f"{existing_metadata}\n\n--- SCRAPED FROM URL ---\n{scraped_content}"
            
            print(f"  -> Updating metadata field (existing: {len(existing_metadata)} chars, new total: {len(new_metadata)} chars)")
            config.update_record(token, "Stills", record_id, {FIELD_MAPPING["metadata"]: new_metadata})
            print(f"SUCCESS [scrape_url]: {stills_id} - Additional metadata found and added")
            sys.exit(0)
        else:
            # URL scraping failed to find additional content, but this is not a critical error
            # The workflow should continue as existing EXIF data might be sufficient
            print(f"  -> URL scraping did not find additional useful content")
            print(f"  -> Continuing workflow - existing metadata will be evaluated in next step")
            print(f"SUCCESS [scrape_url]: {stills_id} - No additional metadata found, but not critical")
            sys.exit(0)

    except Exception as e:
        # Only fail on critical errors (network issues, API key missing, etc.)
        # Content extraction failures should not stop the workflow
        error_msg = str(e)
        
        # Check if this is a critical error that should stop the workflow
        critical_errors = [
            "API Key not found",
            "Connection", 
            "Timeout",
            "Authentication",
            "Permission denied",
            "Network unreachable"
        ]
        
        is_critical = any(critical_error.lower() in error_msg.lower() for critical_error in critical_errors)
        
        if is_critical:
            print(f"  -> CRITICAL ERROR in URL scraping: {e}")
            sys.stderr.write(f"ERROR [scrape_url] on {stills_id}: {e}\n")
            sys.exit(1)
        else:
            # Non-critical error (content extraction failure, parsing issues, etc.)
            print(f"  -> Non-critical error in URL scraping: {e}")
            print(f"  -> Continuing workflow - existing metadata will be evaluated in next step")
            print(f"SUCCESS [scrape_url]: {stills_id} - URL scraping encountered issues but workflow continues")
            sys.exit(0)