#!/usr/bin/env python3
"""
Diagnose why S00616 and Reverse Image Search have different embeddings
Both are grayscale, neither went through RGB conversion
"""

import sys
import os
import warnings
import json
import numpy as np
import hashlib
from pathlib import Path
from PIL import Image

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "embedding": "AI_Embed_Image",
    "thumbnail": "SPECS_Thumbnail",
    "server_path": "SPECS_Filepath_Server",
    "import_path": "SPECS_Filepath_Import",
    "file_format": "SPECS_File_Format",
    "width": "SPECS_Width",
    "height": "SPECS_Height",
    "status": "AutoLog_Status"
}

def get_file_hash(filepath):
    """Get MD5 hash of a file."""
    if not os.path.exists(filepath):
        return None
    
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def download_container_field(token, layout, record_id, field_name, output_path):
    """Download image from container field to analyze it."""
    try:
        import requests
        
        # Get full record to access container URL
        response = requests.get(
            config.url(f"layouts/{layout}/records/{record_id}"),
            headers=config.api_headers(token),
            verify=False
        )
        response.raise_for_status()
        
        # Navigate to the container field data
        field_data = response.json().get('response', {}).get('data', [{}])[0].get('fieldData', {})
        container_url = field_data.get(field_name)
        
        if not container_url:
            print(f"  ⚠️  No container URL found for {field_name}")
            return False
        
        # Container URL is typically a FileMaker URL that needs authentication
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
            print(f"  ⚠️  Failed to download from container: {download_response.status_code}")
            return False
            
    except Exception as e:
        print(f"  ⚠️  Error downloading container field: {e}")
        import traceback
        traceback.print_exc()
        return False

def analyze_image_file(filepath, label):
    """Analyze an image file in detail."""
    if not os.path.exists(filepath):
        print(f"  ❌ File doesn't exist")
        return None
    
    try:
        file_size = os.path.getsize(filepath)
        file_hash = get_file_hash(filepath)
        
        with Image.open(filepath) as img:
            width, height = img.size
            mode = img.mode
            format_type = img.format
            
            # Get image data for pixel analysis
            img_array = np.array(img)
            
            print(f"\n  📊 {label}:")
            print(f"     File size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
            print(f"     MD5 hash: {file_hash}")
            print(f"     Dimensions: {width}x{height}")
            print(f"     Mode: {mode}")
            print(f"     Format: {format_type}")
            print(f"     Array shape: {img_array.shape}")
            print(f"     Array dtype: {img_array.dtype}")
            
            # Check if it's truly grayscale or RGB
            if len(img_array.shape) == 3:
                # Check if all channels are identical
                if img_array.shape[2] == 3:
                    r, g, b = img_array[:,:,0], img_array[:,:,1], img_array[:,:,2]
                    channels_identical = np.array_equal(r, g) and np.array_equal(g, b)
                    print(f"     RGB channels identical: {channels_identical}")
                    if not channels_identical:
                        print(f"       R mean: {r.mean():.2f}, G mean: {g.mean():.2f}, B mean: {b.mean():.2f}")
            
            # Sample some pixel values
            if len(img_array.shape) == 2:
                sample_pixels = img_array[:5, :5].flatten()
            else:
                sample_pixels = img_array[:5, :5, 0].flatten()
            print(f"     Sample pixels (first 25): {sample_pixels.tolist()}")
            
            return {
                "file_size": file_size,
                "file_hash": file_hash,
                "width": width,
                "height": height,
                "mode": mode,
                "format": format_type,
                "array_shape": img_array.shape,
                "exists": True
            }
            
    except Exception as e:
        print(f"  ❌ Error analyzing image: {e}")
        return None

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

def diagnose_record(stills_id, token):
    """Get comprehensive diagnostic info about a record."""
    try:
        print(f"\n{'='*80}")
        print(f"DIAGNOSING: {stills_id}")
        print(f"{'='*80}")
        
        # Find record
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        print(f"Record ID: {record_id}")
        
        # Get record data
        record_data = config.get_record(token, "Stills", record_id)
        
        # Basic info
        status = record_data.get(FIELD_MAPPING["status"])
        fm_width = record_data.get(FIELD_MAPPING["width"])
        fm_height = record_data.get(FIELD_MAPPING["height"])
        file_format = record_data.get(FIELD_MAPPING["file_format"])
        
        print(f"\n📋 FileMaker Record Info:")
        print(f"   Status: {status}")
        print(f"   Width (FM): {fm_width}")
        print(f"   Height (FM): {fm_height}")
        print(f"   Format: {file_format}")
        
        # Server path
        server_path = record_data.get(FIELD_MAPPING["server_path"])
        print(f"\n📁 Server Path: {server_path}")
        if server_path:
            analyze_image_file(server_path, "SERVER FILE")
        
        # Import path
        import_path = record_data.get(FIELD_MAPPING["import_path"])
        print(f"\n📁 Import Path: {import_path}")
        if import_path:
            analyze_image_file(import_path, "IMPORT FILE")
        
        # Thumbnail from container field
        print(f"\n📦 Container Field Thumbnail:")
        temp_thumb = f"/tmp/diagnostic_thumb_{stills_id}.jpg"
        if download_container_field(token, "Stills", record_id, FIELD_MAPPING["thumbnail"], temp_thumb):
            thumb_info = analyze_image_file(temp_thumb, "CONTAINER THUMBNAIL")
            os.remove(temp_thumb)
        else:
            thumb_info = None
            print(f"  ❌ Could not download thumbnail from container")
        
        # Embedding info
        embedding_data = record_data.get(FIELD_MAPPING["embedding"])
        print(f"\n🧠 Embedding Info:")
        if embedding_data:
            embedding = parse_embedding(embedding_data)
            if embedding is not None:
                print(f"   ✅ Embedding exists")
                print(f"   Dimensions: {embedding.shape}")
                print(f"   L2 Norm: {np.linalg.norm(embedding):.6f}")
                print(f"   Mean: {embedding.mean():.6f}")
                print(f"   First 10 values: {embedding[:10]}")
            else:
                print(f"   ❌ Failed to parse embedding")
                embedding = None
        else:
            print(f"   ❌ No embedding found")
            embedding = None
        
        return {
            "stills_id": stills_id,
            "record_id": record_id,
            "status": status,
            "fm_width": fm_width,
            "fm_height": fm_height,
            "file_format": file_format,
            "server_path": server_path,
            "import_path": import_path,
            "embedding": embedding,
            "has_thumbnail": thumb_info is not None
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def compare_records(info1, info2):
    """Compare two records."""
    print(f"\n{'='*80}")
    print(f"COMPARISON")
    print(f"{'='*80}")
    
    print(f"\n📊 Status Comparison:")
    print(f"   {info1['stills_id']}: {info1['status']}")
    print(f"   {info2['stills_id']}: {info2['status']}")
    
    print(f"\n🖼️  Dimensions Comparison:")
    print(f"   {info1['stills_id']}: {info1['fm_width']}x{info1['fm_height']}")
    print(f"   {info2['stills_id']}: {info2['fm_width']}x{info2['fm_height']}")
    
    # Embedding comparison
    if info1['embedding'] is not None and info2['embedding'] is not None:
        similarity = cosine_similarity(info1['embedding'], info2['embedding'])
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
        
        return similarity
    else:
        print(f"\n❌ Cannot compare embeddings - one or both missing")
        return None

if __name__ == "__main__":
    print("="*80)
    print("EMBEDDING SOURCE DIAGNOSIS")
    print("="*80)
    print("\nComparing S00616 (older) vs Reverse Image Search import")
    print("Both should be grayscale with no RGB conversion")
    print("Looking for what causes different embeddings\n")
    
    # Get FileMaker token
    token = config.get_token()
    
    # Get S00616 info
    info_s00616 = diagnose_record("S00616", token)
    
    # Get Reverse Image Search record ID from command line or default
    if len(sys.argv) > 1:
        ris_id = sys.argv[1].strip()
        print(f"\nUsing provided STILLS_ID: {ris_id}")
    else:
        # Ask user for the Reverse Image Search record ID
        print(f"\n{'='*80}")
        print("Please provide the STILLS_ID for the Reverse Image Search import")
        print("(Look in your Reverse Image Search log for the recent import)")
        print("Usage: python diagnose_embedding_sources.py <STILLS_ID>")
        print(f"{'='*80}")
        ris_id = input("Enter STILLS_ID: ").strip()
    
    if not ris_id:
        print("❌ No ID provided, exiting")
        sys.exit(1)
    
    # Get Reverse Image Search record info
    info_ris = diagnose_record(ris_id, token)
    
    if not info_s00616 or not info_ris:
        print("\n❌ Failed to retrieve record info")
        sys.exit(1)
    
    # Compare
    similarity = compare_records(info_s00616, info_ris)
    
    # Diagnosis
    print(f"\n{'='*80}")
    print("DIAGNOSIS")
    print(f"{'='*80}")
    
    print(f"\n🔍 Key Findings:")
    print(f"\n1. Source Files:")
    print(f"   - Check if thumbnails have different sizes")
    print(f"   - Check if one is using import path vs thumbnail")
    print(f"   - Check if compression/quality differs")
    
    print(f"\n2. Likely Causes:")
    print(f"   a) Different thumbnail sizes (old: varied, new: 588x588)")
    print(f"   b) Different image source (import vs thumbnail vs server)")
    print(f"   c) Different thumbnail compression quality")
    print(f"   d) Container field storage differences")
    
    print(f"\n3. To Fix:")
    print(f"   - Ensure Reverse Image Search uses same thumbnail size (588x588)")
    print(f"   - Ensure both use same image source (container thumbnail)")
    print(f"   - Consider regenerating S00616's embedding after confirming source")
    
    print(f"\n{'='*80}")

