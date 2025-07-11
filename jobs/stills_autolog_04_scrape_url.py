# jobs/stills_autolog_04_scrape_url.py
import sys, requests
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["stills_id"]

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "url": "SPECS_URL",
    "metadata": "INFO_Metadata"
}

# ... (helper functions are the same)

if __name__ == "__main__":
    stills_id = sys.argv[1]
    token = config.get_token()
    
    try:
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        r = requests.get(config.url(f"layouts/Stills/records/{record_id}"), headers=config.api_headers(token))
        r.raise_for_status()
        
        record_data = r.json()['response']['data'][0]['fieldData']
        url_to_scrape = record_data.get(FIELD_MAPPING["url"])
        existing_metadata = record_data.get(FIELD_MAPPING["metadata"], '')
        
        # ... (scraping logic is the same) ...

        if is_metadata_sufficient(scraped_content):
            new_metadata = f"{existing_metadata}\n\n--- SCRAPED FROM URL ---\n{scraped_content}"
            field_data = {FIELD_MAPPING["metadata"]: new_metadata}
            requests.patch(config.url(f"layouts/Stills/records/{record_id}"), headers=config.api_headers(token), json={"fieldData": field_data}).raise_for_status()
            print(f"SUCCESS [scrape_url]: {stills_id}")
            sys.exit(0)
        else:
            raise RuntimeError("All scraping methods failed to find sufficient content.")

    except Exception as e:
        sys.stderr.write(f"ERROR [scrape_url] on {stills_id}: {e}\n")
        sys.exit(1)