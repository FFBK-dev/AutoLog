#!/usr/bin/env python3
"""
Investigate why S00004 and S00509 (same file) have different embeddings
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
    "height": "SPECS_Height"
}

def get_file_hash(filepath):
    """Get MD5 hash of a file to verify if files are truly identical."""
    if not os.path.exists(filepath):
        return None
    
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

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
        print(f"❌ Error parsing embedding: {e}")
        return None

def cosine_similarity(emb1, emb2):
    """Calculate cosine similarity between two embeddings."""
    emb1_norm = emb1 / np.linalg.norm(emb1)
    emb2_norm = emb2 / np.linalg.norm(emb2)
    return float(np.dot(emb1_norm, emb2_norm))

def get_detailed_info(stills_id, token):
    """Get comprehensive information about a record."""
    try:
        print(f"\n{'='*80}")
        print(f"ANALYZING {stills_id}")
        print(f"{'='*80}")
        
        # Find record
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        print(f"Record ID: {record_id}")
        
        # Get record data
        record_data = config.get_record(token, "Stills", record_id)
        
        # Server file info
        server_path = record_data.get(FIELD_MAPPING["server_path"])
        print(f"\n📁 SERVER FILE:")
        print(f"   Path: {server_path}")
        
        server_exists = os.path.exists(server_path) if server_path else False
        if server_exists:
            server_size = os.path.getsize(server_path)
            server_hash = get_file_hash(server_path)
            print(f"   ✅ Exists: Yes")
            print(f"   Size: {server_size:,} bytes ({server_size/1024/1024:.2f} MB)")
            print(f"   MD5 Hash: {server_hash}")
            
            # Get image dimensions
            try:
                with Image.open(server_path) as img:
                    print(f"   Dimensions: {img.size[0]}x{img.size[1]}")
                    print(f"   Mode: {img.mode}")
            except Exception as e:
                print(f"   ⚠️  Could not read image: {e}")
        else:
            print(f"   ❌ Exists: No")
            server_size = None
            server_hash = None
        
        # FileMaker dimensions
        width = record_data.get(FIELD_MAPPING["width"])
        height = record_data.get(FIELD_MAPPING["height"])
        file_format = record_data.get(FIELD_MAPPING["file_format"])
        print(f"\n📊 FILEMAKER SPECS:")
        print(f"   Width: {width}")
        print(f"   Height: {height}")
        print(f"   Format: {file_format}")
        
        # Embedding info
        embedding_data = record_data.get(FIELD_MAPPING["embedding"])
        print(f"\n🧠 EMBEDDING:")
        
        if not embedding_data:
            print(f"   ❌ No embedding found")
            embedding = None
        else:
            print(f"   Type: {type(embedding_data)}")
            if isinstance(embedding_data, str):
                print(f"   Length: {len(embedding_data)} characters")
                print(f"   Preview: {embedding_data[:100]}...")
            
            embedding = parse_embedding(embedding_data)
            
            if embedding is not None:
                print(f"   ✅ Parsed successfully")
                print(f"   Dimensions: {embedding.shape}")
                print(f"   First 10 values: {embedding[:10]}")
                print(f"   L2 Norm: {np.linalg.norm(embedding):.6f}")
                print(f"   Min value: {embedding.min():.6f}")
                print(f"   Max value: {embedding.max():.6f}")
                print(f"   Mean: {embedding.mean():.6f}")
                print(f"   Std Dev: {embedding.std():.6f}")
            else:
                print(f"   ❌ Failed to parse")
        
        return {
            "stills_id": stills_id,
            "record_id": record_id,
            "server_path": server_path,
            "server_exists": server_exists,
            "server_size": server_size,
            "server_hash": server_hash,
            "width": width,
            "height": height,
            "file_format": file_format,
            "embedding": embedding,
            "embedding_raw": embedding_data
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def compare_records(info1, info2):
    """Compare two records in detail."""
    print(f"\n{'='*80}")
    print(f"COMPARISON: {info1['stills_id']} vs {info2['stills_id']}")
    print(f"{'='*80}")
    
    # File comparison
    print(f"\n📁 FILE COMPARISON:")
    if info1['server_hash'] and info2['server_hash']:
        if info1['server_hash'] == info2['server_hash']:
            print(f"   ✅ FILES ARE IDENTICAL (same MD5 hash)")
            print(f"   Hash: {info1['server_hash']}")
        else:
            print(f"   ❌ FILES ARE DIFFERENT")
            print(f"   {info1['stills_id']}: {info1['server_hash']}")
            print(f"   {info2['stills_id']}: {info2['server_hash']}")
    else:
        print(f"   ⚠️  Cannot compare - one or both files missing")
    
    # Size comparison
    print(f"\n📊 SIZE COMPARISON:")
    print(f"   {info1['stills_id']}: {info1['server_size']:,} bytes" if info1['server_size'] else f"   {info1['stills_id']}: N/A")
    print(f"   {info2['stills_id']}: {info2['server_size']:,} bytes" if info2['server_size'] else f"   {info2['stills_id']}: N/A")
    
    if info1['server_size'] and info2['server_size']:
        if info1['server_size'] == info2['server_size']:
            print(f"   ✅ Same file size")
        else:
            print(f"   ❌ Different file sizes")
    
    # Dimension comparison
    print(f"\n📐 DIMENSIONS:")
    print(f"   {info1['stills_id']}: {info1['width']}x{info1['height']}")
    print(f"   {info2['stills_id']}: {info2['width']}x{info2['height']}")
    
    # Embedding comparison
    print(f"\n🧠 EMBEDDING COMPARISON:")
    
    if info1['embedding'] is None or info2['embedding'] is None:
        print(f"   ❌ Cannot compare - one or both embeddings missing")
        if info1['embedding'] is None:
            print(f"      {info1['stills_id']}: No embedding")
        if info2['embedding'] is None:
            print(f"      {info2['stills_id']}: No embedding")
        return None
    
    print(f"   Shapes: {info1['embedding'].shape} vs {info2['embedding'].shape}")
    
    if info1['embedding'].shape != info2['embedding'].shape:
        print(f"   ❌ Different embedding dimensions!")
        return None
    
    # Calculate similarity
    similarity = cosine_similarity(info1['embedding'], info2['embedding'])
    
    print(f"\n   📊 COSINE SIMILARITY: {similarity:.6f}")
    
    if similarity > 0.99:
        print(f"   🟢 IDENTICAL (>0.99) - Expected for duplicates ✅")
    elif similarity > 0.95:
        print(f"   🟢 VERY HIGH (>0.95) - Good for duplicates ✅")
    elif similarity > 0.90:
        print(f"   🟡 HIGH (>0.90) - Acceptable for duplicates ⚠️")
    elif similarity > 0.80:
        print(f"   🟠 MODERATE (>0.80) - Low for duplicates ⚠️")
    else:
        print(f"   🔴 LOW (<0.80) - NOT matching as duplicates ❌")
    
    # Element-wise comparison
    diff = np.abs(info1['embedding'] - info2['embedding'])
    print(f"\n   📈 ELEMENT-WISE DIFFERENCES:")
    print(f"      Mean difference: {diff.mean():.6f}")
    print(f"      Max difference: {diff.max():.6f}")
    print(f"      Std dev of differences: {diff.std():.6f}")
    print(f"      Elements with >0.1 difference: {(diff > 0.1).sum()} / {len(diff)}")
    
    return similarity

if __name__ == "__main__":
    print("="*80)
    print("INVESTIGATING EMBEDDING MISMATCH: S00004 vs S00509")
    print("="*80)
    print("\nThese should be the SAME file but have different embeddings")
    
    # Get FileMaker token
    token = config.get_token()
    
    # Get detailed info
    info_s00004 = get_detailed_info("S00004", token)
    info_s00509 = get_detailed_info("S00509", token)
    
    if not info_s00004 or not info_s00509:
        print("\n❌ Failed to retrieve record info")
        sys.exit(1)
    
    # Compare records
    similarity = compare_records(info_s00004, info_s00509)
    
    # Diagnosis
    print(f"\n{'='*80}")
    print("DIAGNOSIS")
    print(f"{'='*80}")
    
    if similarity is not None:
        if similarity < 0.90:
            print(f"\n🔍 POSSIBLE CAUSES OF LOW SIMILARITY:")
            print(f"   1. Files are NOT actually identical (different content)")
            print(f"   2. Different image preprocessing/cropping")
            print(f"   3. Different CLIP model versions used")
            print(f"   4. Image orientation/rotation differences")
            print(f"   5. One embedding generated from corrupted thumbnail")
            print(f"   6. Different color spaces (RGB vs grayscale)")
        else:
            print(f"\n✅ Embeddings are similar enough for duplicate detection")

