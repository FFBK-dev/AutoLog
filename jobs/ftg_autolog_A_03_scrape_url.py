#!/usr/bin/env python3
import sys, os, time, requests
import warnings
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.local_metadata_evaluator import evaluate_metadata_local
from utils.url_validator import validate_and_test_url
from utils.url_scraper import scrape_url_enhanced, evaluate_metadata_quality

__ARGS__ = ["footage_id"]

FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "url": "SPECS_URL",
    "metadata": "INFO_Metadata",
    "description": "INFO_Description",
    "source": "INFO_Source",
    "archival_id": "INFO_Archival_ID"
}

def scrape_url_content(url, max_retries=3):
    """Enhanced URL scraping using the new utility."""
    print(f"  -> Enhanced scraping for: {url}")
    
    try:
        # Use the enhanced URL scraper
        scraped_content = scrape_url_enhanced(url, timeout=30)
        
        if scraped_content:
            print(f"  -> Enhanced extraction successful: {len(scraped_content)} characters")
            return scraped_content
        else:
            print(f"  -> No content could be extracted from URL")
            return ""
        
    except Exception as e:
        print(f"  -> Error in enhanced URL scraping: {e}")
        return ""

def clean_scraped_content(content):
    """Clean and format scraped content."""
    if not content:
        return ""
    
    # Remove excessive whitespace
    lines = content.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        if line and len(line) > 10:  # Skip very short lines
            cleaned_lines.append(line)
    
    # Join with proper spacing
    cleaned_content = '\n'.join(cleaned_lines)
    
    # Limit total length
    if len(cleaned_content) > 3000:
        cleaned_content = cleaned_content[:3000] + "..."
    
    return cleaned_content

def combine_metadata(existing_metadata, scraped_content):
    """Combine existing metadata with scraped content."""
    combined_parts = []
    
    # Add existing metadata first
    if existing_metadata and existing_metadata.strip():
        combined_parts.append("=== EXISTING METADATA ===")
        combined_parts.append(existing_metadata.strip())
    
    # Add scraped content
    if scraped_content and scraped_content.strip():
        combined_parts.append("=== SCRAPED CONTENT ===")
        combined_parts.append(scraped_content.strip())
    
    return "\n\n".join(combined_parts)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    
    footage_id = sys.argv[1]
    
    # Flexible token handling
    if len(sys.argv) == 2:
        token = config.get_token()
        print(f"Direct mode: Created new FileMaker session for {footage_id}")
    elif len(sys.argv) == 3:
        token = sys.argv[2]
        print(f"Subprocess mode: Using provided token for {footage_id}")
    else:
        sys.stderr.write(f"ERROR: Invalid arguments. Expected: script.py footage_id [token]\n")
        sys.exit(1)
    
    try:
        print(f"Starting URL scraping for footage {footage_id}")
        
        # Get the current record
        record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        record_data = config.get_record(token, "FOOTAGE", record_id)
        
        # Get URL and existing metadata
        url = record_data.get(FIELD_MAPPING["url"], "").strip()
        existing_metadata = record_data.get(FIELD_MAPPING["metadata"], "").strip()
        
        if not url:
            print(f"⚠️ No URL found for footage {footage_id}")
            print(f"  -> Setting status to 'Awaiting User Input' - user needs to add metadata or URL")
            
            # Update status to awaiting user input
            status_update = {"fieldData": {"AutoLog_Status": "Awaiting User Input"}}
            update_response = config.update_record(token, "FOOTAGE", record_id, status_update)
            
            if update_response.status_code == 200:
                print(f"✅ Set status to 'Awaiting User Input' for {footage_id}")
                print(f"  -> User should add metadata to INFO_Metadata field and trigger workflow again")
            else:
                print(f"❌ Failed to update status: {update_response.status_code}")
            
            sys.exit(0)  # Exit successfully - this is an expected condition, not an error
        
        print(f"URL to scrape: {url}")
        print(f"Existing metadata: {len(existing_metadata)} characters")
        
        # Validate URL before scraping
        print(f"Validating URL before scraping...")
        validation_result = validate_and_test_url(url, test_accessibility=True, timeout=10)
        
        if not validation_result["valid"]:
            print(f"❌ URL validation failed: {validation_result['reason']}")
            print(f"  -> Setting status to 'Awaiting User Input' - invalid URL")
            
            # Update status to awaiting user input
            status_update = {"fieldData": {"AutoLog_Status": "Awaiting User Input"}}
            update_response = config.update_record(token, "FOOTAGE", record_id, status_update)
            
            if update_response.status_code == 200:
                print(f"✅ Set status to 'Awaiting User Input' for {footage_id}")
                print(f"  -> User should fix the URL and trigger workflow again")
            else:
                print(f"❌ Failed to update status: {update_response.status_code}")
            
            sys.exit(0)  # Exit successfully - this is an expected condition, not an error
        
        if not validation_result["accessible"]:
            print(f"⚠️ URL format is valid but not accessible: {validation_result['reason']}")
            print(f"  -> Will attempt scraping anyway - may be accessible during scraping")
        else:
            print(f"✅ URL is valid and accessible (HTTP {validation_result['status_code']})")
        
        # Scrape URL content
        scraped_content = scrape_url_content(url)
        
        if not scraped_content:
            print(f"⚠️ Failed to scrape content from URL (non-critical)")
            # Don't fail - URL scraping is optional
            scraped_content = ""
        
        # Clean scraped content
        cleaned_content = clean_scraped_content(scraped_content)
        print(f"Scraped content: {len(cleaned_content)} characters")
        
        # Combine with existing metadata
        combined_metadata = combine_metadata(existing_metadata, cleaned_content)
        print(f"Combined metadata: {len(combined_metadata)} characters")
        
        # Evaluate metadata quality using enhanced evaluator
        print(f"Evaluating combined metadata quality...")
        evaluation = evaluate_metadata_quality(combined_metadata)
        
        is_sufficient = evaluation.get("sufficient", False)
        reason = evaluation.get("reason", "No reason provided")
        score = evaluation.get("score", 0.0)
        
        print(f"Metadata evaluation:")
        print(f"  -> Sufficient: {'YES' if is_sufficient else 'NO'}")
        print(f"  -> Score: {score:.2f}")
        print(f"  -> Reason: {reason}")
        
        # Update the record with combined metadata (if any was scraped)
        field_data = {}
        
        if scraped_content:
            field_data[FIELD_MAPPING["metadata"]] = combined_metadata
        
        # Always update status to "Awaiting User Input" (Part A complete)
        field_data["AutoLog_Status"] = "Awaiting User Input"
        
        update_response = config.update_record(token, "FOOTAGE", record_id, field_data)
        
        if update_response.status_code == 200:
            if scraped_content:
                print(f"✅ Successfully updated footage {footage_id} with scraped metadata")
            else:
                print(f"✅ Successfully updated footage {footage_id} (no URL to scrape)")
            print(f"  -> Status set to: Awaiting User Input")
            
        else:
            print(f"❌ Failed to update footage record: {update_response.status_code}")
            print(f"Response: {update_response.text}")
            sys.exit(1)
        
    except Exception as e:
        print(f"❌ Error processing footage {footage_id}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 