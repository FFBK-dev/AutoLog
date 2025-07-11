# jobs/stills_autolog_04_scrape_url.py
import sys, os, json, time, requests, base64
import warnings
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import openai

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
    "filename": "INFO_Filename",
    "source": "INFO_Source",
    "archival_id": "INFO_Archival_ID",
    "server_path": "SPECS_Filepath_Server",
    "globals_api_key": "SystemGlobals_AutoLog_OpenAI_API_Key"
}

def load_prompts():
    """Load prompts from prompts.json file."""
    prompts_path = Path(__file__).resolve().parent.parent / "prompts.json"
    with open(prompts_path, 'r') as f:
        return json.load(f)

# --- Helper Functions ---

def is_metadata_sufficient(text, client):
    """Uses OpenAI to evaluate if the scraped text contains useful metadata about a visual asset."""
    if not text or not text.strip():
        return False
    
    # Quick checks for obviously insufficient content
    text_clean = text.strip()
    if len(text_clean) < 10:
        return False
    
    try:
        # Load the metadata sufficiency prompt
        prompts = load_prompts()
        prompt_template = prompts["metadata_sufficiency"]
        
        # Format the prompt with the scraped text
        prompt_text = prompt_template.format(scraped_text=text_clean)
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": prompt_text}
            ],
            response_format={"type": "json_object"},
            max_tokens=150,
            temperature=0.1  # Low temperature for consistent evaluation
        )
        
        evaluation = json.loads(response.choices[0].message.content)
        is_useful = evaluation.get("useful", False)
        reason = evaluation.get("reason", "No reason provided")
        
        print(f"  -> Metadata evaluation: {'✅ USEFUL' if is_useful else '❌ NOT USEFUL'}")
        print(f"     Reason: {reason}")
        
        return is_useful
        
    except Exception as e:
        print(f"  -> Metadata evaluation failed: {e}")
        # Fall back to basic text check if OpenAI fails
        basic_boilerplate = ["stock photo", "search results", "©", "getty images", "download image", "cookies", "privacy policy", "log in", "free digital items", "digital collection"]
        text_lower = text_clean.lower()
        has_boilerplate = any(phrase in text_lower for phrase in basic_boilerplate)
        return len(text_clean) >= 25 and not has_boilerplate

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

def scrape_level_1_html(soup, client):
    """Tries to find metadata in common HTML tags and archival site structures."""
    print("  -> Attempting Level 1: Standard HTML Parsing...")
    
    # Try meta tags first
    selectors = [ ('meta', {'property': 'og:description'}), ('meta', {'name': 'description'}) ]
    for tag, attrs in selectors:
        element = soup.find(tag, attrs)
        if element and 'content' in element.attrs and is_metadata_sufficient(element['content'], client):
            print("  -> Success with meta tag.")
            return element['content']
    
    # Try common content selectors
    content_selectors = ['.caption', '.description', '.article-body', 'article', 'main', '#main-content', '#content']
    for selector in content_selectors:
        element = soup.select_one(selector)
        if element and is_metadata_sufficient(element.get_text(separator=" ", strip=True), client):
            print(f"  -> Success with selector: {selector}")
            return element.get_text(separator=" ", strip=True)
    
    # Try to extract structured archival metadata (new approach)
    print("  -> Trying structured metadata extraction...")
    structured_data = extract_structured_metadata(soup)
    if structured_data and is_metadata_sufficient(structured_data, client):
        print("  -> Success with structured metadata extraction.")
        return structured_data
    
    print("  -> Level 1 failed to find sufficient content.")
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

def scrape_level_2_archival_ai(soup, client):
    """Uses AI to extract structured archival metadata from the full page text."""
    print("  -> Attempting Level 2: Archival Metadata Extraction...")
    try:
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "header", "footer"]):
            script.decompose()
        
        full_text = soup.get_text(separator='\n', strip=True)
        if not full_text: return None

        # Truncate to avoid exceeding token limits
        max_chars = 15000  # Increased for better archival data extraction
        truncated_text = full_text[:max_chars]

        # Load the archival metadata extraction prompt
        prompts = load_prompts()
        prompt_template = prompts["archival_metadata_extraction"]
        
        # Format the prompt with the page content
        prompt_text = prompt_template.format(page_content=truncated_text)

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": prompt_text}
            ],
            temperature=0.1,  # Low temperature for consistent extraction
            max_tokens=500    # Increased for more comprehensive extraction
        )
        extracted_metadata = response.choices[0].message.content

        if is_metadata_sufficient(extracted_metadata, client):
            print("  -> Success with Archival Metadata Extraction.")
            return extracted_metadata
            
    except Exception as e:
        print(f"  -> Level 2 Archival Metadata Extraction failed: {e}")
        
    print("  -> Level 2 failed to produce sufficient content.")
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

                response = client.chat.completions.create(
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
                    max_tokens=400,
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
        # Fetch record and globals first
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        system_globals = config.get_system_globals(token)
        
        # Set OpenAI key
        api_key = system_globals.get(FIELD_MAPPING["globals_api_key"])
        if not api_key: raise ValueError("OpenAI API Key not found in SystemGlobals.")
        # Create OpenAI client for v1.x API
        client = openai.OpenAI(api_key=api_key)

        record_data = config.get_record(token, "Stills", record_id)
        url_to_scrape = record_data.get(FIELD_MAPPING["url"])
        existing_metadata = record_data.get(FIELD_MAPPING["metadata"], '')
        server_path = record_data.get(FIELD_MAPPING["server_path"], '')
        
        if url_to_scrape:
            print(f"  -> Found URL to scrape: {url_to_scrape}")
            # --- Begin Optimized Cascading Scraping with URL ---
            headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
            response = requests.get(url_to_scrape, timeout=15, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Level 1: Quick HTML parsing
            scraped_content = scrape_level_1_html(soup, client)

            # Level 2: Archival metadata extraction (comprehensive text analysis)
            if not scraped_content:
                scraped_content = scrape_level_2_archival_ai(soup, client)

            # Level 3: Enhanced selenium with multiple screenshots (as fallback)
            if not scraped_content:
                screenshot_path = f"/tmp/screenshot_{stills_id}.png"
                scraped_content = scrape_level_3_enhanced_selenium(url_to_scrape, screenshot_path, client)
        else:
            print("  -> No URL found, skipping URL-based scraping methods")
        
        # --- Final Update ---
        if is_metadata_sufficient(scraped_content, client):
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