#!/usr/bin/env python3
"""
Standardize thumbnails for BOTH S00004 and S00509 using identical methodology
This ensures they're created with exactly the same settings for proper comparison
"""

import sys
import os
import warnings
from pathlib import Path
from PIL import Image

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "server_path": "SPECS_Filepath_Server",
    "thumbnail": "SPECS_Thumbnail"
}

# STANDARD THUMBNAIL SETTINGS
THUMBNAIL_MAX_SIZE = (588, 588)
THUMBNAIL_QUALITY = 85
THUMBNAIL_RESAMPLING = Image.Resampling.LANCZOS

def create_standard_thumbnail(stills_id, token):
    """
    Create a standardized thumbnail using exact workflow methodology.
    Matches stills_autolog_02_copy_to_server.py workflow.
    """
    try:
        print(f"\n{'='*80}")
        print(f"Standardizing thumbnail for {stills_id}")
        print(f"{'='*80}")
        
        # Find record
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        print(f"Record ID: {record_id}")
        
        # Get server path
        record_data = config.get_record(token, "Stills", record_id)
        server_path = record_data.get(FIELD_MAPPING["server_path"])
        
        if not server_path or not os.path.exists(server_path):
            print(f"❌ Server file not found: {server_path}")
            return False
        
        print(f"Server file: {server_path}")
        
        # Get original file info
        file_size = os.path.getsize(server_path)
        print(f"File size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
        
        # Open and process the image (matching workflow exactly)
        with Image.open(server_path) as img:
            original_size = img.size
            original_mode = img.mode
            
            print(f"\n📸 Original Image:")
            print(f"   Size: {original_size[0]}x{original_size[1]}")
            print(f"   Mode: {original_mode}")
            
            # Convert mode if needed (matching workflow)
            if img.mode not in ('RGB', 'L'):
                print(f"   Converting mode {img.mode} → RGB")
                img = img.convert('RGB')
            
            # Create a copy for thumbnailing (important!)
            thumb_img = img.copy()
            
            # Apply thumbnail (maintains aspect ratio, uses LANCZOS resampling)
            thumb_img.thumbnail(THUMBNAIL_MAX_SIZE, THUMBNAIL_RESAMPLING)
            
            thumb_size = thumb_img.size
            
            print(f"\n📐 Thumbnail Created:")
            print(f"   Size: {thumb_size[0]}x{thumb_size[1]}")
            print(f"   Max dimension: {max(thumb_size)} (target: {THUMBNAIL_MAX_SIZE[0]})")
            print(f"   Resampling: LANCZOS")
            
            # Save with exact quality settings
            temp_thumb = f"/tmp/standard_thumb_{stills_id}.jpg"
            thumb_img.save(temp_thumb, 'JPEG', quality=THUMBNAIL_QUALITY)
            
            thumb_file_size = os.path.getsize(temp_thumb)
            compression_ratio = file_size / thumb_file_size
            
            print(f"   File size: {thumb_file_size:,} bytes ({thumb_file_size/1024:.1f} KB)")
            print(f"   JPEG quality: {THUMBNAIL_QUALITY}%")
            print(f"   Compression: {compression_ratio:.1f}x smaller")
            
            # Upload to FileMaker
            print(f"\n📤 Uploading to FileMaker container field...")
            config.upload_to_container(token, "Stills", record_id, FIELD_MAPPING['thumbnail'], temp_thumb)
            
            # Clean up
            os.remove(temp_thumb)
            
            print(f"✅ Successfully standardized thumbnail")
            
            return {
                'stills_id': stills_id,
                'original_size': original_size,
                'thumb_size': thumb_size,
                'thumb_file_size': thumb_file_size,
                'compression_ratio': compression_ratio
            }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("="*80)
    print("STANDARDIZING THUMBNAILS FOR S00004 & S00509")
    print("="*80)
    print("\nThis will regenerate BOTH thumbnails using identical settings:")
    print(f"  - Max dimension: {THUMBNAIL_MAX_SIZE[0]} pixels")
    print(f"  - JPEG quality: {THUMBNAIL_QUALITY}%")
    print(f"  - Resampling: LANCZOS")
    print(f"  - Mode: RGB")
    print("\nThis ensures perfect consistency for duplicate detection.")
    
    # Get FileMaker token
    token = config.get_token()
    
    # Standardize both thumbnails
    results = []
    
    for stills_id in ["S00004", "S00509"]:
        result = create_standard_thumbnail(stills_id, token)
        if result:
            results.append(result)
    
    # Compare results
    if len(results) == 2:
        print(f"\n{'='*80}")
        print("COMPARISON")
        print(f"{'='*80}")
        
        r1, r2 = results
        
        print(f"\nOriginal Files:")
        print(f"  {r1['stills_id']}: {r1['original_size'][0]}x{r1['original_size'][1]}")
        print(f"  {r2['stills_id']}: {r2['original_size'][0]}x{r2['original_size'][1]}")
        
        if r1['original_size'] == r2['original_size']:
            print(f"  ✅ Original files have identical dimensions")
        else:
            print(f"  ⚠️  Original files have different dimensions!")
        
        print(f"\nNew Thumbnails:")
        print(f"  {r1['stills_id']}: {r1['thumb_size'][0]}x{r1['thumb_size'][1]} ({r1['thumb_file_size']:,} bytes)")
        print(f"  {r2['stills_id']}: {r2['thumb_size'][0]}x{r2['thumb_size'][1]} ({r2['thumb_file_size']:,} bytes)")
        
        # Check if thumbnails match
        size_match = r1['thumb_size'] == r2['thumb_size']
        file_size_diff = abs(r1['thumb_file_size'] - r2['thumb_file_size'])
        file_size_similar = file_size_diff < 5000  # Within 5KB
        
        if size_match:
            print(f"  ✅ Thumbnails have identical dimensions")
        else:
            print(f"  ⚠️  Thumbnails have different dimensions")
        
        if file_size_similar:
            print(f"  ✅ Thumbnails have similar file sizes (diff: {file_size_diff:,} bytes)")
        else:
            print(f"  ⚠️  Thumbnails have different file sizes (diff: {file_size_diff:,} bytes)")
        
        print(f"\n{'='*80}")
        print("NEXT STEPS")
        print(f"{'='*80}")
        print("\n1. Regenerate embeddings for BOTH S00004 and S00509")
        print("2. Run the comparison script:")
        print("   python3 temp/compare_duplicate_embeddings.py")
        print("3. Embeddings should now match at ~99%+ similarity")
        print("\nThe thumbnails are now created with IDENTICAL methodology!")
    else:
        print(f"\n❌ Failed to standardize one or both thumbnails")

