# jobs/stills_autolog_04_scrape_url.py
import sys, os, time, requests
import warnings
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

# Add the parent directory to the path to import your existing config
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.url_validator import validate_and_test_url
from utils.url_scraper import scrape_url_enhanced, evaluate_metadata_quality

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

# --- Helper Functions ---

def is_metadata_sufficient(text, client=None):
    """Uses enhanced evaluation to determine if scraped text contains useful metadata."""
    if not text or not text.strip():
        return False
    
    # Use the enhanced metadata quality evaluator
    quality = evaluate_metadata_quality(text)
    
    # Log the evaluation results
    print(f"  -> Metadata evaluation: {'✅ USEFUL' if quality['sufficient'] else '❌ NOT USEFUL'} (score: {quality['score']}, reason: {quality['reason']})")
    
    return quality['sufficient']

def scrape_url(url, client=None):
    """Enhanced URL scraping using the new utility."""
    print(f"  -> Found URL to scrape: {url}")
    
    try:
        # Use the enhanced URL scraper
        scraped_content = scrape_url_enhanced(url, client, timeout=30)
        
        if scraped_content:
            print(f"  -> Enhanced extraction successful: {len(scraped_content)} characters")
        else:
            print(f"  -> No content could be extracted from URL")
        
        return scraped_content
        
    except Exception as e:
        print(f"  -> Error in enhanced URL scraping: {e}")
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
        
        # Validate URL before scraping
        print(f"  -> Validating URL before scraping...")
        validation_result = validate_and_test_url(url, test_accessibility=True, timeout=10)
        
        if not validation_result["valid"]:
            print(f"  -> ❌ URL validation failed: {validation_result['reason']}")
            print(f"  -> Continuing workflow - existing metadata will be evaluated in next step")
            sys.exit(0)  # Exit successfully - this is an expected condition, not an error
        
        if not validation_result["accessible"]:
            print(f"  -> ⚠️ URL format is valid but not accessible: {validation_result['reason']}")
            print(f"  -> Will attempt scraping anyway - may be accessible during scraping")
        else:
            print(f"  -> ✅ URL is valid and accessible (HTTP {validation_result['status_code']})")
        
        print(f"  -> Scraping URL: {url}")
        scraped_content = scrape_url(url, None)  # No client needed anymore
        
        # --- Always append scraped content if we have any ---
        if scraped_content:
            print(f"  -> Scraped content found ({len(scraped_content)} characters)")
            
            # Evaluate metadata quality for workflow decision (not for storage decision)
            is_useful = is_metadata_sufficient(scraped_content)
            
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
            
            if is_useful:
                print(f"SUCCESS [scrape_url]: {stills_id} - High-quality metadata found and added")
            else:
                print(f"SUCCESS [scrape_url]: {stills_id} - Scraped content added (quality evaluation: insufficient for workflow optimization)")
            sys.exit(0)
        else:
            # No content was scraped at all
            print(f"  -> No content could be scraped from URL")
            print(f"  -> Continuing workflow - existing metadata will be evaluated in next step")
            print(f"SUCCESS [scrape_url]: {stills_id} - No content scraped, but not critical")
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