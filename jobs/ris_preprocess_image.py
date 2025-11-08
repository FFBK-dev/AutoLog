#!/usr/bin/env python3
"""
REVERSE_IMAGE_SEARCH - Image Preprocessing
Converts images to RGB and creates 588x588 thumbnails to match Stills workflow

This ensures embedding consistency by:
1. Converting grayscale → RGB (3 identical channels)
2. Creating 588x588 thumbnail
3. Uploading thumbnail to IMAGE_CONTAINER field

Then FileMaker can generate embeddings from the preprocessed thumbnail.
"""

import sys
import os
import warnings
from pathlib import Path
from PIL import Image, ImageFile
import requests

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

ImageFile.LOAD_TRUNCATED_IMAGES = True

__ARGS__ = ["record_id"]  # Can be "all" to process all pending

FIELD_MAPPING = {
    "path": "PATH",
    "image_container": "IMAGE_CONTAINER",
    "embedding": "EMBEDDING",
    "match_count": "MATCH COUNT"
}

def convert_to_rgb_if_needed(img):
    """Convert image to RGB, handling all color modes."""
    mode = img.mode
    print(f"  -> Image mode: {mode}")
    
    if mode == 'RGB':
        print(f"  -> Already RGB")
        return img
    
    # Grayscale → RGB
    if mode in ('L', '1'):
        print(f"  -> Converting grayscale to RGB")
        img = img.convert('RGB')
        print(f"  -> Grayscale converted to RGB")
        return img
    
    # RGBA → RGB (remove alpha)
    if mode == 'RGBA':
        print(f"  -> Converting RGBA to RGB (removing alpha)")
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
        print(f"  -> Alpha channel removed")
        return img
    
    # CMYK → RGB
    if mode == 'CMYK':
        print(f"  -> Converting CMYK to RGB")
        img = img.convert('RGB')
        print(f"  -> CMYK converted")
        return img
    
    # Palette mode → RGB
    if mode == 'P':
        print(f"  -> Converting palette mode to RGB")
        img = img.convert('RGB')
        print(f"  -> Palette converted")
        return img
    
    # Any other mode → RGB
    print(f"  -> Converting {mode} to RGB")
    img = img.convert('RGB')
    print(f"  -> Conversion complete")
    return img

def create_thumbnail(img, max_size=588, quality=85):
    """Create thumbnail matching Stills workflow: 588x588 max, JPEG quality 85."""
    print(f"  -> Creating thumbnail (max {max_size}x{max_size})...")
    
    original_size = img.size
    thumb_img = img.copy()
    
    # Create thumbnail maintaining aspect ratio
    thumb_img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    
    print(f"  -> Original: {original_size[0]}x{original_size[1]}")
    print(f"  -> Thumbnail: {thumb_img.size[0]}x{thumb_img.size[1]}")
    
    return thumb_img

def process_ris_record(record_id, token):
    """Process a single REVERSE_IMAGE_SEARCH record."""
    try:
        print(f"\n{'='*60}")
        print(f"Processing RIS Record ID: {record_id}")
        print(f"{'='*60}")
        
        # Get record data directly (not using _find since it has issues)
        response = requests.get(
            config.url(f"layouts/REVERSE_IMAGE_SEARCH/records/{record_id}"),
            headers=config.api_headers(token),
            verify=False
        )
        
        if response.status_code == 404:
            print(f"  ❌ Record {record_id} not found")
            return False
        
        response.raise_for_status()
        data = response.json()['response']['data']
        
        if not data:
            print(f"  ❌ No data returned for record {record_id}")
            return False
        
        field_data = data[0]['fieldData']
        actual_record_id = data[0]['recordId']
        
        import_path = field_data.get(FIELD_MAPPING["path"])
        has_embedding = bool(field_data.get(FIELD_MAPPING["embedding"]))
        
        print(f"  Import Path: {import_path}")
        print(f"  Has Embedding: {has_embedding}")
        
        if not import_path:
            print(f"  ❌ No import path found")
            return False
        
        if not os.path.exists(import_path):
            print(f"  ❌ File not found: {import_path}")
            return False
        
        # Check if already processed (has embedding)
        if has_embedding:
            print(f"  ⚠️  Record already has embedding - skipping preprocessing")
            print(f"     (Delete embedding first if you want to reprocess)")
            return True
        
        # Open and process image
        print(f"\n📸 Processing image...")
        with Image.open(import_path) as img:
            original_mode = img.mode
            original_size = img.size
            
            print(f"  Original: {original_size[0]}x{original_size[1]}, Mode: {original_mode}")
            
            # Step 1: Convert to RGB
            img_rgb = convert_to_rgb_if_needed(img)
            
            # Step 2: Create thumbnail
            thumb = create_thumbnail(img_rgb, max_size=588, quality=85)
            
            # Step 3: Save to temp file
            temp_path = f"/tmp/ris_thumb_{record_id}.jpg"
            thumb.save(temp_path, 'JPEG', quality=85)
            
            file_size = os.path.getsize(temp_path)
            print(f"  -> Thumbnail saved: {file_size:,} bytes ({file_size/1024:.1f} KB)")
        
        # Step 4: Upload to FileMaker container field
        print(f"\n📤 Uploading thumbnail to FileMaker...")
        config.upload_to_container(
            token,
            "REVERSE_IMAGE_SEARCH",
            actual_record_id,
            FIELD_MAPPING["image_container"],
            temp_path
        )
        
        print(f"  ✅ Thumbnail uploaded successfully")
        
        # Clean up temp file
        os.remove(temp_path)
        
        print(f"\n✅ SUCCESS: Record {record_id} preprocessed")
        print(f"   Next step: Run FileMaker script to generate embedding from thumbnail")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR processing record {record_id}: {e}")
        import traceback
        traceback.print_exc()
        return False

def find_unprocessed_records(token):
    """Find all REVERSE_IMAGE_SEARCH records without embeddings."""
    try:
        print(f"🔍 Finding unprocessed REVERSE_IMAGE_SEARCH records...")
        
        # Get all records
        response = requests.get(
            config.url("layouts/REVERSE_IMAGE_SEARCH/records?_limit=100"),
            headers=config.api_headers(token),
            verify=False
        )
        response.raise_for_status()
        
        records = response.json()['response']['data']
        
        # Filter for records without embeddings but with paths
        unprocessed = []
        for record in records:
            record_id = record['recordId']
            field_data = record['fieldData']
            
            import_path = field_data.get(FIELD_MAPPING["path"])
            has_embedding = bool(field_data.get(FIELD_MAPPING["embedding"]))
            
            if import_path and not has_embedding:
                unprocessed.append(record_id)
        
        print(f"  Found {len(unprocessed)} unprocessed record(s)")
        return unprocessed
        
    except Exception as e:
        print(f"❌ Error finding records: {e}")
        return []

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("❌ Error: Please provide a record ID or 'all'")
        print("Usage:")
        print("  python ris_preprocess_image.py <record_id>")
        print("  python ris_preprocess_image.py all")
        sys.exit(1)
    
    record_id_arg = sys.argv[1]
    
    try:
        token = config.get_token()
        
        if record_id_arg.lower() == "all":
            # Process all unprocessed records
            print("="*60)
            print("REVERSE_IMAGE_SEARCH - Batch Preprocessing")
            print("="*60)
            
            unprocessed = find_unprocessed_records(token)
            
            if not unprocessed:
                print("\n✅ No unprocessed records found")
                sys.exit(0)
            
            print(f"\n📋 Processing {len(unprocessed)} record(s)...")
            
            success_count = 0
            for rec_id in unprocessed:
                if process_ris_record(rec_id, token):
                    success_count += 1
            
            print(f"\n{'='*60}")
            print(f"SUMMARY")
            print(f"{'='*60}")
            print(f"  Total: {len(unprocessed)}")
            print(f"  Success: {success_count}")
            print(f"  Failed: {len(unprocessed) - success_count}")
            
        else:
            # Process single record
            print("="*60)
            print("REVERSE_IMAGE_SEARCH - Single Record Preprocessing")
            print("="*60)
            
            success = process_ris_record(record_id_arg, token)
            sys.exit(0 if success else 1)
        
    except Exception as e:
        print(f"\n❌ Critical error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

