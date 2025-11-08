#!/usr/bin/env python3
"""
Compare S00616 embedding to REVERSE_IMAGE_SEARCH embedding
Both are grayscale, so why are they different?
"""

import sys
import os
import warnings
import json
import numpy as np
import hashlib
import requests
from pathlib import Path
from PIL import Image

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

def parse_embedding(embedding_data):
    """Parse embedding data from FileMaker."""
    if not embedding_data:
        return None
    
    try:
        if isinstance(embedding_data, str):
            embedding_data = embedding_data.strip()
            if embedding_data.startswith('['):
                return np.array(json.loads(embedding_data))
            elif ',' in embedding_data:
                values = [float(x.strip()) for x in embedding_data.split(',')]
                return np.array(values)
        elif isinstance(embedding_data, (list, np.ndarray)):
            return np.array(embedding_data)
        
        return None
    except Exception as e:
        print(f"  ❌ Error parsing embedding: {e}")
        return None

def cosine_similarity(emb1, emb2):
    """Calculate cosine similarity between two embeddings."""
    emb1_norm = emb1 / np.linalg.norm(emb1)
    emb2_norm = emb2 / np.linalg.norm(emb2)
    return float(np.dot(emb1_norm, emb2_norm))

def download_container_image(token, layout, record_id, field_name, output_path):
    """Download image from container field."""
    try:
        response = requests.get(
            config.url(f"layouts/{layout}/records/{record_id}"),
            headers=config.api_headers(token),
            verify=False
        )
        response.raise_for_status()
        
        field_data = response.json()['response']['data'][0]['fieldData']
        container_url = field_data.get(field_name)
        
        if not container_url:
            print(f"  ⚠️  No container URL found")
            return False
        
        # Download the file
        download_response = requests.get(
            container_url,
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        
        if download_response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(download_response.content)
            return True
        else:
            print(f"  ⚠️  Failed to download: {download_response.status_code}")
            return False
            
    except Exception as e:
        print(f"  ⚠️  Error: {e}")
        return False

def analyze_image(filepath, label):
    """Analyze an image file."""
    if not os.path.exists(filepath):
        print(f"  ❌ File doesn't exist")
        return None
    
    try:
        file_size = os.path.getsize(filepath)
        file_hash = hashlib.md5(open(filepath, 'rb').read()).hexdigest()
        
        with Image.open(filepath) as img:
            width, height = img.size
            mode = img.mode
            format_type = img.format
            img_array = np.array(img)
            
            print(f"\n  📊 {label}:")
            print(f"     File size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
            print(f"     MD5 hash: {file_hash}")
            print(f"     Dimensions: {width}x{height}")
            print(f"     Mode: {mode}")
            print(f"     Format: {format_type}")
            print(f"     Array shape: {img_array.shape}")
            
            # Check if RGB channels are identical
            if len(img_array.shape) == 3 and img_array.shape[2] == 3:
                r, g, b = img_array[:,:,0], img_array[:,:,1], img_array[:,:,2]
                channels_identical = np.array_equal(r, g) and np.array_equal(g, b)
                print(f"     RGB channels identical: {channels_identical}")
            
            # Sample pixels
            if len(img_array.shape) == 2:
                sample_pixels = img_array[:5, :5].flatten()
            else:
                sample_pixels = img_array[:5, :5, 0].flatten()
            print(f"     Sample pixels: {sample_pixels.tolist()}")
            
            return {
                "file_size": file_size,
                "file_hash": file_hash,
                "width": width,
                "height": height,
                "mode": mode,
                "format": format_type,
                "array_shape": img_array.shape
            }
            
    except Exception as e:
        print(f"  ❌ Error analyzing image: {e}")
        return None

if __name__ == "__main__":
    print("="*80)
    print("COMPARING S00616 vs REVERSE_IMAGE_SEARCH")
    print("="*80)
    
    token = config.get_token()
    
    # Get S00616 info
    print("\n🔍 Getting S00616 from Stills layout...")
    s00616_record_id = config.find_record_id(token, "Stills", {"INFO_STILLS_ID": "==S00616"})
    s00616_data = config.get_record(token, "Stills", s00616_record_id)
    
    print(f"   Record ID: {s00616_record_id}")
    print(f"   Status: {s00616_data.get('AutoLog_Status')}")
    print(f"   Server Path: {s00616_data.get('SPECS_Filepath_Server')}")
    
    # Download S00616 thumbnail
    print("\n📦 Downloading S00616 container thumbnail...")
    s00616_thumb = "/tmp/s00616_thumb.jpg"
    if download_container_image(token, "Stills", s00616_record_id, "SPECS_Thumbnail", s00616_thumb):
        s00616_thumb_info = analyze_image(s00616_thumb, "S00616 THUMBNAIL")
    
    # Get S00616 embedding
    s00616_embedding = parse_embedding(s00616_data.get('AI_Embed_Image'))
    print(f"\n🧠 S00616 Embedding:")
    if s00616_embedding is not None:
        print(f"   Dimensions: {s00616_embedding.shape}")
        print(f"   L2 Norm: {np.linalg.norm(s00616_embedding):.6f}")
        print(f"   First 10 values: {s00616_embedding[:10]}")
    
    # Get REVERSE_IMAGE_SEARCH record
    print("\n" + "="*80)
    print("🔍 Getting REVERSE_IMAGE_SEARCH record...")
    ris_record_id = "184"  # We know it's record 184
    
    response = requests.get(
        config.url(f"layouts/REVERSE_IMAGE_SEARCH/records/{ris_record_id}"),
        headers=config.api_headers(token),
        verify=False
    )
    response.raise_for_status()
    ris_data = response.json()['response']['data'][0]['fieldData']
    
    print(f"   Record ID: {ris_record_id}")
    print(f"   Path: {ris_data.get('PATH')}")
    print(f"   Match Count: {ris_data.get('MATCH COUNT')}")
    
    # Download RIS thumbnail
    print("\n📦 Downloading REVERSE_IMAGE_SEARCH container image...")
    ris_thumb = "/tmp/ris_thumb.jpg"
    if download_container_image(token, "REVERSE_IMAGE_SEARCH", ris_record_id, "IMAGE_CONTAINER", ris_thumb):
        ris_thumb_info = analyze_image(ris_thumb, "RIS THUMBNAIL")
    
    # Get RIS embedding
    ris_embedding = parse_embedding(ris_data.get('EMBEDDING'))
    print(f"\n🧠 RIS Embedding:")
    if ris_embedding is not None:
        print(f"   Dimensions: {ris_embedding.shape}")
        print(f"   L2 Norm: {np.linalg.norm(ris_embedding):.6f}")
        print(f"   First 10 values: {ris_embedding[:10]}")
    
    # Compare embeddings
    print("\n" + "="*80)
    print("COMPARISON")
    print("="*80)
    
    if s00616_embedding is not None and ris_embedding is not None:
        similarity = cosine_similarity(s00616_embedding, ris_embedding)
        print(f"\n🧠 Embedding Similarity: {similarity:.6f}")
        
        if similarity > 0.99:
            print(f"   🟢 IDENTICAL (>0.99)")
        elif similarity > 0.95:
            print(f"   🟢 VERY HIGH (>0.95)")
        elif similarity > 0.90:
            print(f"   🟡 HIGH (>0.90)")
        elif similarity > 0.80:
            print(f"   🟠 MODERATE (>0.80)")
        else:
            print(f"   🔴 LOW (<0.80)")
    
    # Clean up
    if os.path.exists(s00616_thumb):
        os.remove(s00616_thumb)
    if os.path.exists(ris_thumb):
        os.remove(ris_thumb)
    
    print("\n" + "="*80)
    print("DIAGNOSIS")
    print("="*80)
    print("\n🔍 Key Findings:")
    print("   - Both are grayscale images")
    print("   - Check if thumbnail dimensions differ")
    print("   - Check if one uses RGB mode vs L mode")
    print("   - Check if FileMaker's embedding generation differs between layouts")

