#!/usr/bin/env python3
"""
REVERSE_IMAGE_SEARCH - Batch Thumbnail Generation

Automatically finds REVERSE_IMAGE_SEARCH records with STATUS = "Imported"
and generates 588x588 RGB thumbnails matching the Stills workflow preprocessing.

This ensures embedding consistency by:
1. Converting all color modes to RGB (grayscale, CMYK, LAB, etc.)
2. Flattening multi-layered images (PSD, TIFF)
3. Creating 588x588 thumbnails with LANCZOS resampling
4. Uploading thumbnails to IMAGE_CONTAINER field
5. Updating STATUS to "Thumbnail Created"
"""

import sys
import os
import warnings
import time
import concurrent.futures
from pathlib import Path
from PIL import Image, ImageFile
import numpy as np
import requests

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

# Set PIL's maximum image size to handle very large images (1 billion pixels)
Image.MAX_IMAGE_PIXELS = 1000000000
ImageFile.LOAD_TRUNCATED_IMAGES = True

__ARGS__ = []  # No arguments - automatically discovers pending items

# Layout name has spaces, not underscores
LAYOUT_NAME = "REVERSE IMAGE SEARCH"

FIELD_MAPPING = {
    "path": "PATH",
    "image_container": "IMAGE_CONTAINER",
    "status": "STATUS"
}

def flatten_and_convert_to_rgb(img):
    """
    Comprehensive image processing to ensure flattened RGB output.
    Handles: PSDs, layered TIFs, CMYK, LAB, grayscale, 16-bit, RGBA, etc.
    """
    print(f"  -> Image mode: {img.mode}, Format: {img.format}, Size: {img.size}")
    
    # Handle multi-layered images (PSD, layered TIFF)
    layers = getattr(img, 'layers', [])
    # Ensure layers is a list/tuple before calling len()
    if hasattr(layers, '__len__') and not isinstance(layers, (str, bytes)) and len(layers) > 1:
        print(f"  -> Detected multi-layered image with {len(layers)} layers - flattening")
        # Flatten by converting to RGB which automatically composites layers
        img = img.convert('RGB')
        print(f"  -> Layers flattened successfully")
        return img
    
    # If image has seek method, try to composite all frames/layers
    if hasattr(img, 'seek'):
        try:
            # Check if there are multiple frames/layers
            img.seek(1)
            print(f"  -> Multiple frames/layers detected - compositing")
            img.seek(0)
            # Create composite by converting to RGB
            img = img.convert('RGB')
            print(f"  -> Frames composited successfully")
            return img
        except EOFError:
            # Only one frame/layer, continue normal processing
            img.seek(0)
    
    # Handle 16-bit images (both grayscale and color)
    if img.mode in ('I;16', 'I;16L', 'I;16B'):
        print(f"  -> Detected 16-bit image - converting to 8-bit RGB")
        # Convert 16-bit to 8-bit by scaling
        img_array = np.array(img)
        img_8bit = (img_array / 256).astype(np.uint8)
        # Convert to RGB
        img = Image.fromarray(img_8bit, mode='L').convert('RGB')
        print(f"  -> 16-bit conversion complete")
        return img
    
    # Handle CMYK images (common in print-ready files)
    if img.mode == 'CMYK':
        print(f"  -> Converting CMYK to RGB")
        img = img.convert('RGB')
        print(f"  -> CMYK conversion complete")
        return img
    
    # Handle LAB color space
    if img.mode == 'LAB':
        print(f"  -> Converting LAB to RGB")
        img = img.convert('RGB')
        print(f"  -> LAB conversion complete")
        return img
    
    # Handle RGBA (with alpha channel) - flatten alpha
    if img.mode == 'RGBA':
        print(f"  -> Converting RGBA to RGB (removing alpha channel)")
        # Create white background
        background = Image.new('RGB', img.size, (255, 255, 255))
        # Paste image on white background using alpha channel as mask
        background.paste(img, mask=img.split()[3])  # 3 is the alpha channel
        img = background
        print(f"  -> Alpha channel removed, image flattened on white background")
        return img
    
    # Handle palette mode images
    if img.mode == 'P':
        print(f"  -> Converting palette mode to RGB")
        img = img.convert('RGB')
        print(f"  -> Palette conversion complete")
        return img
    
    # Handle grayscale images
    if img.mode in ('L', '1'):
        print(f"  -> Converting grayscale to RGB")
        img = img.convert('RGB')
        print(f"  -> Grayscale conversion complete")
        return img
    
    # Handle any other exotic modes
    if img.mode != 'RGB':
        print(f"  -> Converting {img.mode} to RGB")
        try:
            img = img.convert('RGB')
            print(f"  -> Conversion to RGB complete")
        except Exception as e:
            print(f"  -> Warning: Standard conversion failed ({e}), attempting forced conversion")
            # Force conversion by going through numpy array
            img_array = np.array(img)
            if len(img_array.shape) == 2:
                # Single channel - convert to RGB by repeating
                img_rgb = np.stack([img_array, img_array, img_array], axis=2)
                img = Image.fromarray(img_rgb.astype(np.uint8), mode='RGB')
            else:
                # Multi-channel - take first 3 channels or pad to 3
                if img_array.shape[2] >= 3:
                    img = Image.fromarray(img_array[:,:,:3].astype(np.uint8), mode='RGB')
                else:
                    # Pad to 3 channels
                    img_rgb = np.zeros((*img_array.shape[:2], 3), dtype=np.uint8)
                    img_rgb[:,:,:img_array.shape[2]] = img_array
                    img = Image.fromarray(img_rgb, mode='RGB')
            print(f"  -> Forced conversion successful")
        return img
    
    print(f"  -> Image already in RGB mode")
    return img

def update_status(record_id, token, new_status, max_retries=3):
    """Update status with retry logic and error handling."""
    current_token = token
    
    for attempt in range(max_retries):
        try:
            payload = {"fieldData": {FIELD_MAPPING["status"]: new_status}}
            response = requests.patch(
                config.url(f"layouts/{LAYOUT_NAME}/records/{record_id}"),
                headers=config.api_headers(current_token),
                json=payload,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 401:
                print(f"  -> Token expired, refreshing...")
                current_token = config.get_token()
                continue
            
            response.raise_for_status()
            return True, current_token
            
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt < max_retries - 1:
                print(f"  -> Network error, retrying... ({attempt + 1}/{max_retries})")
                time.sleep(2 ** attempt)
                continue
            else:
                print(f"  -> Failed to update status after {max_retries} attempts: {e}")
                return False, current_token
        except Exception as e:
            print(f"  -> Error updating status: {e}")
            return False, current_token
    
    return False, current_token

def process_ris_record(record_id, token):
    """Process a single REVERSE_IMAGE_SEARCH record."""
    temp_path = None
    current_token = token
    
    try:
        print(f"\n{'='*60}")
        print(f"📋 Processing RIS Record ID: {record_id}")
        print(f"{'='*60}")
        
        # Get record data
        response = requests.get(
            config.url(f"layouts/{LAYOUT_NAME}/records/{record_id}"),
            headers=config.api_headers(current_token),
            verify=False,
            timeout=30
        )
        
        if response.status_code == 401:
            print(f"  -> Token expired, refreshing...")
            current_token = config.get_token()
            response = requests.get(
                config.url(f"layouts/{LAYOUT_NAME}/records/{record_id}"),
                headers=config.api_headers(current_token),
                verify=False,
                timeout=30
            )
        
        if response.status_code == 404:
            print(f"  ❌ Record {record_id} not found")
            return False, current_token
        
        response.raise_for_status()
        data = response.json()['response']['data']
        
        if not data:
            print(f"  ❌ No data returned for record {record_id}")
            return False, current_token
        
        field_data = data[0]['fieldData']
        actual_record_id = data[0]['recordId']
        
        import_path = field_data.get(FIELD_MAPPING["path"])
        current_status = field_data.get(FIELD_MAPPING["status"])
        
        print(f"  Import Path: {import_path}")
        print(f"  Current Status: {current_status}")
        
        if not import_path:
            print(f"  ❌ No import path found")
            success, current_token = update_status(actual_record_id, current_token, "Error - No Path")
            return False, current_token
        
        if not os.path.exists(import_path):
            print(f"  ❌ File not found: {import_path}")
            success, current_token = update_status(actual_record_id, current_token, "Error - File Not Found")
            return False, current_token
        
        # Process image through EXACT same workflow as Stills
        print(f"\n🔄 Processing image through Stills workflow")
        with Image.open(import_path) as img:
            original_mode = img.mode
            original_size = img.size
            
            print(f"  Original: {original_size[0]}x{original_size[1]}, Mode: {original_mode}")
            
            # Step 1: Flatten and convert to RGB
            img_rgb = flatten_and_convert_to_rgb(img)
            
            # Step 2: Save as intermediate JPEG (quality 95) - matches Stills workflow
            # This intermediate compression step is CRITICAL for embedding consistency
            intermediate_path = f"/tmp/ris_intermediate_{record_id}_{int(time.time())}.jpg"
            img_rgb.save(intermediate_path, 'JPEG', quality=95)
            print(f"  -> Saved intermediate JPEG (quality 95)")
        
        # Step 3: Re-open the intermediate JPEG and create thumbnail from it
        # This EXACTLY matches the Stills workflow which creates thumbnails from saved JPEGs
        try:
            with Image.open(intermediate_path) as final_img:
                print(f"  -> Creating thumbnail from intermediate JPEG (max 588x588)...")
                thumb_img = final_img.copy()
                thumb_img.thumbnail((588, 588), Image.Resampling.LANCZOS)
                print(f"  -> Thumbnail: {thumb_img.size[0]}x{thumb_img.size[1]}")
                
                # Step 4: Save thumbnail with JPEG quality 85
                temp_path = f"/tmp/ris_thumb_{record_id}_{int(time.time())}.jpg"
                thumb_img.save(temp_path, 'JPEG', quality=85)
                
                file_size = os.path.getsize(temp_path)
                print(f"  -> Thumbnail saved: {file_size:,} bytes ({file_size/1024:.1f} KB)")
        finally:
            # Clean up intermediate file
            if os.path.exists(intermediate_path):
                os.remove(intermediate_path)
        
        # Step 4: Upload to FileMaker container field
        print(f"\n📤 Uploading thumbnail to FileMaker...")
        config.upload_to_container(
            current_token,
            LAYOUT_NAME,
            actual_record_id,
            FIELD_MAPPING["image_container"],
            temp_path
        )
        
        print(f"  ✅ Thumbnail uploaded successfully")
        
        # Step 5: Update status to "Thumbnail Ready"
        print(f"\n🔄 Updating status...")
        success, current_token = update_status(actual_record_id, current_token, "Thumbnail Ready")
        
        if success:
            print(f"  ✅ Status updated to 'Thumbnail Ready'")
        else:
            print(f"  ⚠️  Thumbnail uploaded but status update failed")
        
        print(f"\n✅ SUCCESS: Record {record_id} processed")
        return True, current_token
        
    except Exception as e:
        print(f"\n❌ ERROR processing record {record_id}: {e}")
        import traceback
        traceback.print_exc()
        
        # Try to update status to error
        try:
            error_msg = f"Error - {str(e)[:50]}"
            update_status(record_id, current_token, error_msg)
        except:
            pass
        
        return False, current_token
        
    finally:
        # Clean up temp files
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                print(f"  🗑️  Cleaned up temp thumbnail: {temp_path}")
            except Exception as e:
                print(f"  ⚠️  Could not remove temp file {temp_path}: {e}")
        
        # Clean up intermediate file if it exists
        if 'intermediate_path' in locals() and os.path.exists(intermediate_path):
            try:
                os.remove(intermediate_path)
                print(f"  🗑️  Cleaned up intermediate JPEG: {intermediate_path}")
            except Exception as e:
                print(f"  ⚠️  Could not remove intermediate file {intermediate_path}: {e}")

def find_imported_records(token):
    """Find all REVERSE_IMAGE_SEARCH records with STATUS = 'Imported'."""
    try:
        print(f"🔍 Searching for records with STATUS = 'Imported'...")
        
        # Get all records from layout (more reliable than _find)
        response = requests.get(
            config.url(f"layouts/{LAYOUT_NAME}/records?_limit=100"),
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        
        if response.status_code == 401:
            print(f"  -> Token expired, refreshing...")
            token = config.get_token()
            response = requests.get(
                config.url(f"layouts/{LAYOUT_NAME}/records?_limit=100"),
                headers=config.api_headers(token),
                verify=False,
                timeout=30
            )
        
        response.raise_for_status()
        all_records = response.json()['response']['data']
        
        # Filter for records with STATUS = "Imported" and valid PATH
        record_ids = []
        skipped_records = []
        
        for record in all_records:
            record_id = record['recordId']
            field_data = record['fieldData']
            
            status = field_data.get(FIELD_MAPPING["status"], "")
            path = field_data.get(FIELD_MAPPING["path"], "")
            
            # Debug: Show why records are included/excluded
            if status == "Imported":
                if path:
                    record_ids.append(record_id)
                    print(f"  ✅ Including Record {record_id}: Has Imported status and valid path")
                else:
                    skipped_records.append((record_id, "Missing PATH"))
                    print(f"  ⚠️  Skipping Record {record_id}: Has Imported status but no PATH")
            elif status:
                print(f"  ℹ️  Skipping Record {record_id}: STATUS = '{status}' (not Imported)")
        
        print(f"\n  📊 Summary: Found {len(record_ids)} record(s) with STATUS = 'Imported' and valid PATH")
        if skipped_records:
            print(f"  ⚠️  Skipped {len(skipped_records)} record(s):")
            for rec_id, reason in skipped_records:
                print(f"      - Record {rec_id}: {reason}")
        
        return record_ids
        
    except Exception as e:
        print(f"❌ Error finding records: {e}")
        import traceback
        traceback.print_exc()
        return []

def run_batch_workflow(record_ids, token, max_workers=10):
    """Run workflow for multiple records in parallel."""
    if not record_ids:
        print(f"📋 No records to process")
        return []
    
    print(f"\n{'='*60}")
    print(f"🚀 Starting batch processing for {len(record_ids)} record(s)")
    print(f"{'='*60}")
    
    actual_max_workers = min(max_workers, len(record_ids))
    results = []
    
    # For thread safety with token, we'll process sequentially but could parallelize later
    # if we implement thread-safe token management
    for record_id in record_ids:
        success, token = process_ris_record(record_id, token)
        results.append({
            'record_id': record_id,
            'success': success
        })
    
    # Summary
    print(f"\n{'='*60}")
    print(f"📊 BATCH PROCESSING SUMMARY")
    print(f"{'='*60}")
    
    success_count = sum(1 for r in results if r['success'])
    failed_count = len(results) - success_count
    
    print(f"  Total Records: {len(results)}")
    print(f"  ✅ Successful: {success_count}")
    print(f"  ❌ Failed: {failed_count}")
    
    if failed_count > 0:
        print(f"\n  Failed Record IDs:")
        for r in results:
            if not r['success']:
                print(f"    - {r['record_id']}")
    
    return results

if __name__ == "__main__":
    try:
        print("="*60)
        print("REVERSE_IMAGE_SEARCH - Batch Thumbnail Generation")
        print("="*60)
        
        token = config.get_token()
        
        # Find all records with STATUS = "Imported"
        record_ids = find_imported_records(token)
        
        if not record_ids:
            print(f"\n✅ No records with STATUS = 'Imported' found - nothing to process")
            sys.exit(0)
        
        # Process records in batch
        results = run_batch_workflow(record_ids, token)
        
        # Count successful records
        success_count = sum(1 for r in results if r['success'])
        
        # Notify user to trigger PSOS script manually in FileMaker
        if success_count > 0:
            print(f"\n{'='*60}")
            print(f"📋 NEXT STEP: Trigger Embedding Generation")
            print(f"{'='*60}")
            print(f"  {success_count} record(s) ready with STATUS = 'Thumbnail Ready'")
            print(f"  ")
            print(f"  Run this in FileMaker to generate embeddings:")
            print(f"  → Script: 'STILLS - Reverse Search - 03A - Embeddings (PSOS)'")
            print(f"  ")
            print(f"  Note: PSOS scripts triggered via Data API run in limited context")
            print(f"        and may not find records reliably. Manual trigger from")
            print(f"        FileMaker client ensures proper execution.")
        
        # Exit with appropriate code
        if success_count == len(results):
            print(f"\n✅ All records processed successfully")
            sys.exit(0)
        elif success_count > 0:
            print(f"\n⚠️  Partial success: {success_count}/{len(results)} records processed")
            sys.exit(0)  # Still exit 0 since some succeeded
        else:
            print(f"\n❌ All records failed to process")
            sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Critical error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

