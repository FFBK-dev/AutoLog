# jobs/stills_autolog_04_scrape_url.py
import sys, os, json, time, requests, base64
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import openai

# Add the parent directory to the path to import your existing config
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["stills_id"]

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "url": "SPECS_URL",
    "metadata": "INFO_Metadata",
    "globals_api_key": "SystemGlobals_AutoLog_OpenAI_API_Key"
}

# --- Helper Functions ---

def is_metadata_sufficient(text):
    """Checks if the scraped text is useful."""
    if not text: return False
    text = text.strip().lower()
    if len(text) < 25: return False # Increased minimum length for better quality
    boilerplate = ["stock photo", "search results", "©", "getty images", "download image", "cookies", "privacy policy", "log in"]
    return not any(phrase in text for phrase in boilerplate)

# --- Scraping Methods ---

def scrape_level_1_html(soup):
    """Tries to find metadata in common HTML tags."""
    print("  -> Attempting Level 1: Standard HTML Parsing...")
    selectors = [ ('meta', {'property': 'og:description'}), ('meta', {'name': 'description'}) ]
    for tag, attrs in selectors:
        element = soup.find(tag, attrs)
        if element and 'content' in element.attrs and is_metadata_sufficient(element['content']):
            print("  -> Success with meta tag.")
            return element['content']
            
    for selector in ['.caption', '.description', '.article-body', 'article', 'main', '#main-content', '#content']:
        element = soup.select_one(selector)
        if element and is_metadata_sufficient(element.get_text(separator=" ", strip=True)):
            print(f"  -> Success with selector: {selector}")
            return element.get_text(separator=" ", strip=True)
    
    print("  -> Level 1 failed to find sufficient content.")
    return None

def scrape_level_2_vision(url, screenshot_path):
    """Takes a screenshot and sends it to GPT-4o Vision for analysis."""
    print("  -> Attempting Level 2: Vision API Screenshot Analysis...")
    try:
        # Setup headless browser
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--window-size=1280,1080")
        driver = webdriver.Chrome(options=chrome_options)
        
        driver.get(url)
        time.sleep(3) # Wait for JavaScript to render
        driver.save_screenshot(screenshot_path)
        driver.quit()
        
        # Send to OpenAI
        with open(screenshot_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this webpage screenshot. Find the primary archival image and extract its title, caption, or description. Return ONLY the descriptive text for the image itself. Ignore all site navigation, ads, and cookie banners."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                    ]
                }
            ],
            max_tokens=300,
        )
        vision_text = response.choices[0].message.content
        
        if is_metadata_sufficient(vision_text):
            print("  -> Success with Vision API.")
            return vision_text
            
    except Exception as e:
        print(f"  -> Level 2 Vision API failed: {e}")
    finally:
        # Clean up screenshot
        if os.path.exists(screenshot_path):
            os.remove(screenshot_path)
            
    print("  -> Level 2 failed to produce sufficient content.")
    return None

def scrape_level_3_summary(soup):
    """Sends all page text to GPT-4o for summarization."""
    print("  -> Attempting Level 3: Full-Text AI Summary...")
    try:
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "header", "footer"]):
            script.decompose()
        
        full_text = soup.get_text(separator='\n', strip=True)
        if not full_text: return None

        # Truncate to avoid exceeding token limits
        max_chars = 12000
        truncated_text = full_text[:max_chars]

        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert at finding a needle in a haystack. Your task is to find the single most relevant paragraph or sentence that describes an archival asset from the raw text of a webpage provided below."},
                {"role": "user", "content": f"Please extract the specific description for the main archival image from the following text dump:\n\n---\n{truncated_text}\n---"}
            ],
            temperature=0.2,
            max_tokens=300
        )
        summary_text = response.choices[0].message.content

        if is_metadata_sufficient(summary_text):
            print("  -> Success with Full-Text Summary.")
            return summary_text
            
    except Exception as e:
        print(f"  -> Level 3 AI Summary failed: {e}")
        
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
        openai.api_key = api_key

        record_data = config.get_record(token, "Stills", record_id)
        url_to_scrape = record_data.get(FIELD_MAPPING["url"])
        existing_metadata = record_data.get(FIELD_MAPPING["metadata"], '')
        
        if not url_to_scrape: raise ValueError("No URL found in record to scrape.")

        # --- Begin Cascading Scraping ---
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        response = requests.get(url_to_scrape, timeout=15, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Level 1
        scraped_content = scrape_level_1_html(soup)

        # Level 2
        if not scraped_content:
            screenshot_path = f"/tmp/screenshot_{stills_id}.png"
            scraped_content = scrape_level_2_vision(url_to_scrape, screenshot_path)

        # Level 3
        if not scraped_content:
            scraped_content = scrape_level_3_summary(soup)
        
        # --- Final Update ---
        if is_metadata_sufficient(scraped_content):
            print(f"  -> Successfully scraped content for {stills_id}.")
            new_metadata = f"{existing_metadata}\n\n--- SCRAPED FROM URL ---\n{scraped_content}"
            config.update_record(token, "Stills", record_id, {FIELD_MAPPING["metadata"]: new_metadata})
            sys.exit(0)
        else:
            raise RuntimeError("All scraping methods failed to find sufficient content.")

    except Exception as e:
        sys.stderr.write(f"ERROR [scrape_url] on {stills_id}: {e}\n")
        sys.exit(1)