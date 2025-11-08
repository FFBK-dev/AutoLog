#!/usr/bin/env python3
"""
Download and compare the actual thumbnails stored in FileMaker
to see what CLIP is actually seeing when generating embeddings
"""

import sys
import os
import warnings
import requests
from pathlib import Path
from PIL import Image
import numpy as np

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "thumbnail": "SPECS_Thumbnail"
}

def download_thumbnail(stills_id, token, output_path):
    """Download thumbnail from FileMaker container field."""
    try:
        print(f"\n📥 Downloading thumbnail for {stills_id}...")
        
        # Find record
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        print(f"   Record ID: {record_id}")
        
        # Use FileMaker Data API container download endpoint
        # Format: /layouts/{layout}/records/{recordId}/containers/{fieldName}/{repetition}
        download_url = config.url(f"layouts/Stills/records/{record_id}/containers/{FIELD_MAPPING['thumbnail']}/1")
        
        print(f"   Downloading from container endpoint...")
        
        thumb_response = requests.get(
            download_url,
            headers=config.api_headers(token),
            verify=False
        )
        
        # Check response
        if thumb_response.status_code == 404:
            print(f"   ⚠️  Container field appears to be empty or not found")
            return False
        
        thumb_response.raise_for_status()
        
        # Save to file
        with open(output_path, 'wb') as f:
            f.write(thumb_response.content)
        
        file_size = len(thumb_response.content)
        print(f"   ✅ Downloaded: {file_size:,} bytes ({file_size/1024:.1f} KB)")
        
        # Open and analyze the image
        with Image.open(output_path) as img:
            print(f"   Size: {img.size[0]}x{img.size[1]}")
            print(f"   Mode: {img.mode}")
            print(f"   Format: {img.format}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def compare_images(path1, path2, id1, id2):
    """Compare two images visually and statistically."""
    print(f"\n{'='*80}")
    print(f"COMPARING THUMBNAILS: {id1} vs {id2}")
    print(f"{'='*80}")
    
    try:
        img1 = Image.open(path1)
        img2 = Image.open(path2)
        
        print(f"\n📐 DIMENSIONS:")
        print(f"   {id1}: {img1.size[0]}x{img1.size[1]} ({img1.mode})")
        print(f"   {id2}: {img2.size[0]}x{img2.size[1]} ({img2.mode})")
        
        if img1.size != img2.size:
            print(f"   ⚠️  Different sizes!")
        
        if img1.mode != img2.mode:
            print(f"   ⚠️  Different modes!")
        
        # Convert to numpy arrays for comparison
        arr1 = np.array(img1)
        arr2 = np.array(img2)
        
        print(f"\n📊 PIXEL ANALYSIS:")
        print(f"   {id1} shape: {arr1.shape}")
        print(f"   {id2} shape: {arr2.shape}")
        
        # Check if images are identical
        if arr1.shape == arr2.shape:
            identical = np.array_equal(arr1, arr2)
            if identical:
                print(f"   ✅ IMAGES ARE PIXEL-FOR-PIXEL IDENTICAL")
            else:
                # Calculate differences
                diff = np.abs(arr1.astype(float) - arr2.astype(float))
                mean_diff = diff.mean()
                max_diff = diff.max()
                
                print(f"   ❌ IMAGES ARE DIFFERENT")
                print(f"   Mean pixel difference: {mean_diff:.2f}")
                print(f"   Max pixel difference: {max_diff:.0f}")
                print(f"   Pixels with difference: {(diff > 0).sum():,} / {diff.size:,}")
                
                # Check for rotation
                if arr1.shape[0] == arr2.shape[1] and arr1.shape[1] == arr2.shape[0]:
                    print(f"   🔄 POSSIBLE ROTATION: Dimensions are swapped!")
                
                # Check for color shifts
                if len(arr1.shape) == 3:
                    for i, channel in enumerate(['Red', 'Green', 'Blue']):
                        channel_diff = np.abs(arr1[:,:,i].astype(float) - arr2[:,:,i].astype(float))
                        print(f"   {channel} channel mean diff: {channel_diff.mean():.2f}")
        else:
            print(f"   ❌ CANNOT COMPARE: Different shapes")
        
        # Show some sample pixels
        print(f"\n🎨 SAMPLE PIXELS (top-left corner):")
        print(f"   {id1} [0,0]: {arr1[0,0]}")
        print(f"   {id2} [0,0]: {arr2[0,0]}")
        
    except Exception as e:
        print(f"❌ Error comparing images: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("="*80)
    print("DOWNLOADING AND COMPARING THUMBNAILS")
    print("="*80)
    
    # Get FileMaker token
    token = config.get_token()
    
    # Download thumbnails
    thumb_s00004 = "/tmp/thumb_S00004_analysis.jpg"
    thumb_s00509 = "/tmp/thumb_S00509_analysis.jpg"
    
    success1 = download_thumbnail("S00004", token, thumb_s00004)
    success2 = download_thumbnail("S00509", token, thumb_s00509)
    
    if success1 and success2:
        compare_images(thumb_s00004, thumb_s00509, "S00004", "S00509")
        
        print(f"\n{'='*80}")
        print("NEXT STEPS:")
        print(f"{'='*80}")
        print(f"\nThumbnails saved to:")
        print(f"   {thumb_s00004}")
        print(f"   {thumb_s00509}")
        print(f"\nYou can open these files to visually inspect the differences.")
        print(f"If they look different, that explains the embedding mismatch.")
    else:
        print(f"\n❌ Failed to download one or both thumbnails")

