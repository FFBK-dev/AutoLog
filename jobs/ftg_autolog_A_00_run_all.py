#!/usr/bin/env python3
"""
Footage Import Flow - Part A (Fast & Simple)

Discovers footage at "0 - Pending Import" and processes:
1. Extract file info (specs, duration, codec, etc.)
2. Generate parent thumbnail
3. Scrape URL metadata (if available)

Ends at "Awaiting User Input" - user must add prompt before AI processing.
"""

import sys
import warnings
import subprocess
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = []  # No arguments - finds pending items automatically

def find_pending_imports(token):
    """Find all footage records at '0 - Pending Import' status."""
    import requests
    
    print("🔍 Searching for pending imports...")
    
    query = {
        "query": [{
            "AutoLog_Status": "0 - Pending Import"
        }],
        "limit": 100
    }
    
    try:
        response = requests.post(
            config.url("layouts/FOOTAGE/_find"),
            headers=config.api_headers(token),
            json=query,
            verify=False,
            timeout=30
        )
        
        if response.status_code == 404:
            return []
        
        response.raise_for_status()
        records = response.json()['response']['data']
        
        # Extract footage IDs
        footage_ids = []
        for record in records:
            footage_id = record['fieldData'].get('INFO_FTG_ID', '')
            if footage_id:
                footage_ids.append(footage_id)
        
        if footage_ids:
            print(f"✅ Found {len(footage_ids)} pending imports: {', '.join(footage_ids[:10])}")
            if len(footage_ids) > 10:
                print(f"   ... and {len(footage_ids) - 10} more")
        
        return footage_ids
        
    except Exception as e:
        print(f"❌ Error finding pending imports: {e}")
        return []


def process_import(footage_id, token):
    """
    Process import flow for a single footage item.
    Returns True if successful, False otherwise.
    """
    print(f"\n{'='*60}")
    print(f"🎬 Starting import: {footage_id}")
    print(f"{'='*60}\n")
    
    scripts_dir = Path(__file__).resolve().parent
    
    # Step 1: Get File Info
    print(f"📋 Step 1/3: Extracting file info...")
    step1 = subprocess.run(
        ["python3", str(scripts_dir / "ftg_autolog_A_01_get_file_info.py"), footage_id],
        capture_output=True,
        text=True,
        timeout=120
    )
    
    if step1.returncode != 0:
        print(f"❌ Step 1 failed: {step1.stderr[:200]}")
        return False
    
    print(step1.stdout)
    
    # Check if false start (script sets status to "False Start")
    if "FALSE START" in step1.stdout:
        print(f"⚠️  False start detected - skipping remaining steps")
        return True
    
    # Step 2: Generate Thumbnail
    print(f"🖼️  Step 2/3: Generating thumbnail...")
    step2 = subprocess.run(
        ["python3", str(scripts_dir / "ftg_autolog_A_02_generate_thumbnail.py"), footage_id],
        capture_output=True,
        text=True,
        timeout=120
    )
    
    if step2.returncode != 0:
        print(f"❌ Step 2 failed: {step2.stderr[:200]}")
        return False
    
    print(step2.stdout)
    
    # Step 3: Scrape URL
    print(f"🌐 Step 3/3: Scraping URL metadata...")
    step3 = subprocess.run(
        ["python3", str(scripts_dir / "ftg_autolog_A_03_scrape_url.py"), footage_id],
        capture_output=True,
        text=True,
        timeout=120
    )
    
    if step3.returncode != 0:
        print(f"⚠️  Step 3 warning (non-critical): {step3.stderr[:200]}")
        # URL scraping is optional, continue anyway
    
    print(step3.stdout)
    
    print(f"\n✅ Import complete: {footage_id} → Awaiting User Input\n")
    return True


if __name__ == "__main__":
    try:
        print("🚀 Footage Import Flow - Part A\n")
        
        # Get FileMaker token
        token = config.get_token()
        
        # Find pending imports
        footage_ids = find_pending_imports(token)
        
        if not footage_ids:
            print("\n✅ No pending imports found\n")
            sys.exit(0)
        
        print(f"\n📦 Processing {len(footage_ids)} items...\n")
        
        # Process each item sequentially (fast steps, no queue needed)
        success_count = 0
        for footage_id in footage_ids:
            try:
                if process_import(footage_id, token):
                    success_count += 1
            except subprocess.TimeoutExpired:
                print(f"⏱️  Timeout processing {footage_id}")
            except Exception as e:
                print(f"❌ Error processing {footage_id}: {e}")
        
        print(f"\n{'='*60}")
        print(f"✅ Import complete: {success_count}/{len(footage_ids)} items successful")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"❌ Critical error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

