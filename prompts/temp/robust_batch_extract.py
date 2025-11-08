#!/usr/bin/env python3
"""
Robust batch script to extract IPTC descriptions from INFO_Metadata fields.
Handles JSON with appended content and extracts descriptions from multiple sources.
"""

import sys
import time
import json
import sqlite3
import re
import warnings
from pathlib import Path
from datetime import datetime

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "metadata": "INFO_Metadata",
    "description_orig": "INFO_Description_Original"
}

def robust_json_parse(metadata_text):
    """
    Robustly parse JSON that might have extra content appended.
    """
    if not metadata_text or not metadata_text.strip():
        return None
    
    # First, try parsing as-is
    try:
        return json.loads(metadata_text)
    except json.JSONDecodeError as e:
        # If that fails, try to extract just the JSON part
        try:
            # Find the end of the JSON by looking for the closing brace
            # that matches the opening brace
            brace_count = 0
            json_end = -1
            
            for i, char in enumerate(metadata_text):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break
            
            if json_end > 0:
                json_part = metadata_text[:json_end]
                return json.loads(json_part)
                
        except:
            pass
    
    return None

def extract_from_scraped_content(metadata_text):
    """
    Extract description information from scraped URL content that might be appended.
    """
    descriptions = []
    
    if "--- SCRAPED FROM URL ---" in metadata_text:
        scraped_section = metadata_text.split("--- SCRAPED FROM URL ---", 1)[1]
        
        # Look for Title and Description in scraped content
        title_match = re.search(r'Title:\s*([^\n]+)', scraped_section)
        if title_match:
            title = title_match.group(1).strip()
            if title and title != "Page Not Found" and len(title) > 10:
                descriptions.append(title)
        
        desc_match = re.search(r'Description:\s*([^\n]+)', scraped_section)
        if desc_match:
            desc = desc_match.group(1).strip()
            if desc and len(desc) > 10:
                descriptions.append(desc)
    
    return descriptions

def extract_comprehensive_description(metadata_text):
    """Extract description from multiple sources including JSON and scraped content."""
    if not metadata_text:
        return ""
    
    all_descriptions = []
    
    # Try to parse JSON metadata
    metadata = robust_json_parse(metadata_text)
    
    if metadata:
        # Description fields in nested structure (group, field) with priority order
        description_fields = [
            ('IPTC', 'Caption-Abstract'),        # Primary IPTC description field
            ('IPTC', 'Headline'),                # IPTC headline  
            ('XMP-dc', 'Description'),           # Dublin Core description
            ('XMP-iptcCore', 'Caption'),         # XMP IPTC caption
            ('EXIF', 'ImageDescription'),        # EXIF image description
            ('IPTC', 'ObjectName'),              # IPTC object name
            ('XMP-dc', 'Title'),                 # Dublin Core title
            ('IPTC', 'SpecialInstructions'),     # IPTC special instructions
            ('XMP-iptcCore', 'Headline'),        # XMP IPTC headline
            ('XMP-photoshop', 'Headline'),       # Photoshop headline
            ('XMP-photoshop', 'Instructions')   # Photoshop instructions
        ]
        
        # Extract all available description fields from nested structure
        for group, field in description_fields:
            group_data = metadata.get(group, {})
            if isinstance(group_data, dict):
                value = group_data.get(field, '')
                if value and str(value).strip():
                    # Clean up the value and convert to string if needed
                    cleaned_value = str(value).strip()
                    # Only add if it's not a duplicate and has meaningful content
                    if cleaned_value and cleaned_value not in all_descriptions and len(cleaned_value) > 3:
                        all_descriptions.append(cleaned_value)
    
    # Also try to extract from scraped URL content
    scraped_descriptions = extract_from_scraped_content(metadata_text)
    for desc in scraped_descriptions:
        if desc and desc not in all_descriptions and len(desc) > 3:
            all_descriptions.append(desc)
    
    if not all_descriptions:
        return ""
    
    # If we have multiple descriptions, combine them intelligently
    if len(all_descriptions) == 1:
        final_description = all_descriptions[0]
    else:
        # Combine multiple descriptions, with the primary one first
        final_description = all_descriptions[0]
        
        # Add additional descriptions that aren't just duplicates or substrings
        additional_info = []
        for desc in all_descriptions[1:]:
            # Only add if it's not a substring of the main description and adds value
            if desc.lower() not in final_description.lower() and final_description.lower() not in desc.lower():
                additional_info.append(desc)
        
        if additional_info:
            final_description += " | " + " | ".join(additional_info)
    
    return final_description

def fetch_records_in_batches(token):
    """Fetch all records with metadata from FileMaker in batches."""
    print(f"🔍 Fetching all stills records with metadata from FileMaker...")
    
    try:
        import requests
        
        all_records = []
        batch_size = 1000
        offset = 1
        
        while True:
            print(f"  📦 Fetching batch starting at record {offset}...")
            
            response = requests.get(
                config.url("layouts/Stills/records"),
                headers=config.api_headers(token),
                params={'_limit': batch_size, '_offset': offset},
                verify=False
            )
            
            if response.status_code == 404:
                break
                
            response.raise_for_status()
            batch_records = response.json()['response']['data']
            
            if not batch_records:
                break
            
            all_records.extend(batch_records)
            print(f"    Got {len(batch_records)} records (total so far: {len(all_records)})")
            
            if len(batch_records) < batch_size:
                break
            
            offset += batch_size
            time.sleep(0.5)
        
        print(f"📋 Found {len(all_records)} total stills records")
        return all_records
        
    except Exception as e:
        print(f"❌ Error fetching records: {e}")
        return []

def process_all_records(records):
    """Process all records to extract descriptions."""
    print(f"🔄 Processing {len(records)} records to extract descriptions...")
    
    stats = {
        "total": len(records),
        "processed": 0,
        "extracted": 0,
        "already_has_description": 0,
        "no_metadata": 0,
        "parse_errors": 0,
        "no_description_found": 0
    }
    
    results = []
    
    for i, record in enumerate(records):
        record_id = record['recordId']
        field_data = record['fieldData']
        stills_id = field_data.get(FIELD_MAPPING["stills_id"], '')
        metadata_text = field_data.get(FIELD_MAPPING["metadata"], '')
        current_description = field_data.get(FIELD_MAPPING["description_orig"], '')
        
        stats["processed"] += 1
        
        # Skip if already has description
        if current_description and current_description.strip():
            stats["already_has_description"] += 1
            if i % 100 == 0:  # Only show some of these
                print(f"  ⏭️ {stills_id}: Already has description")
            continue
        
        # Skip if no metadata
        if not metadata_text:
            stats["no_metadata"] += 1
            continue
        
        try:
            # Extract description using robust parsing
            description = extract_comprehensive_description(metadata_text)
            
            if description:
                results.append({
                    "record_id": record_id,
                    "stills_id": stills_id,
                    "description": description
                })
                stats["extracted"] += 1
                print(f"  ✅ {stills_id}: {description[:80]}...")
            else:
                stats["no_description_found"] += 1
                
        except Exception as e:
            stats["parse_errors"] += 1
            print(f"  ❌ {stills_id}: Error - {e}")
        
        # Progress update every 500 records
        if (i + 1) % 500 == 0:
            progress = ((i + 1) / len(records)) * 100
            print(f"  📊 Progress: {progress:.1f}% ({i + 1}/{len(records)}) - Extracted: {stats['extracted']}")
    
    print(f"\n🎯 Processing complete!")
    print(f"📊 Statistics:")
    print(f"  Total processed: {stats['total']}")
    print(f"  Successfully extracted: {stats['extracted']}")
    print(f"  Already had descriptions: {stats['already_has_description']}")
    print(f"  No metadata: {stats['no_metadata']}")
    print(f"  Parse errors: {stats['parse_errors']}")
    print(f"  No description found: {stats['no_description_found']}")
    
    return results, stats

def batch_update_filemaker(updates, token):
    """Update FileMaker with extracted descriptions."""
    print(f"💾 Updating FileMaker with {len(updates)} extracted descriptions...")
    
    if not updates:
        print(f"  Nothing to update")
        return 0
    
    success_count = 0
    
    # Process in batches of 50
    batch_size = 50
    for i in range(0, len(updates), batch_size):
        batch = updates[i:i+batch_size]
        
        print(f"  📦 Updating batch {i//batch_size + 1}/{(len(updates)-1)//batch_size + 1} ({len(batch)} records)")
        
        for record_id, stills_id, description in [(u["record_id"], u["stills_id"], u["description"]) for u in batch]:
            try:
                # Update FileMaker record
                field_data = {FIELD_MAPPING["description_orig"]: description}
                config.update_record(token, "Stills", record_id, field_data)
                success_count += 1
                
                # Small delay between updates
                time.sleep(0.1)
                
            except Exception as e:
                print(f"    ❌ Failed to update {stills_id}: {e}")
        
        # Progress update
        progress = ((i + batch_size) / len(updates)) * 100
        print(f"    📊 Progress: {min(progress, 100):.1f}% ({min(i + batch_size, len(updates))}/{len(updates)})")
        
        # Rate limiting between batches
        if i + batch_size < len(updates):
            time.sleep(2)
    
    print(f"  ✅ Successfully updated {success_count}/{len(updates)} records")
    return success_count

def main():
    """Main processing function."""
    print(f"🚀 Starting robust batch IPTC description extraction")
    print(f"📅 Started at: {datetime.now()}")
    
    try:
        # Get FileMaker token
        token = config.get_token()
        print(f"✅ Got FileMaker token")
        
        # Fetch all records
        records = fetch_records_in_batches(token)
        if not records:
            return 1
        
        # Process all records to extract descriptions
        updates, stats = process_all_records(records)
        
        if not updates:
            print(f"  No new descriptions to update")
            return 0
        
        # Update FileMaker with results
        updated_count = batch_update_filemaker(updates, token)
        
        # Final summary
        print(f"\n🎯 Robust batch processing complete!")
        print(f"📅 Finished at: {datetime.now()}")
        print(f"📈 Final Results:")
        print(f"  Descriptions extracted: {len(updates)}")
        print(f"  Records updated in FileMaker: {updated_count}")
        print(f"  Success rate: {(updated_count / len(updates) * 100):.1f}%")
        
        return 0
        
    except Exception as e:
        print(f"💥 Critical error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main()) 