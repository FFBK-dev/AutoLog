#!/usr/bin/env python3
"""
Compare embeddings between known duplicates S00001 and S07396
Tests if compression affects duplicate detection
"""

import sys
import os
import warnings
import json
import numpy as np
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "embedding": "AI_Embed_Image",
    "thumbnail": "SPECS_Thumbnail",
    "server_path": "SPECS_Filepath_Server"
}

def parse_embedding(embedding_data):
    """Parse embedding data from FileMaker (could be JSON, comma-separated, etc.)."""
    if not embedding_data:
        return None
    
    try:
        # Try parsing as JSON array
        if isinstance(embedding_data, str):
            # Remove any whitespace
            embedding_data = embedding_data.strip()
            
            # Try JSON
            if embedding_data.startswith('['):
                return np.array(json.loads(embedding_data))
            
            # Try comma-separated
            elif ',' in embedding_data:
                values = [float(x.strip()) for x in embedding_data.split(',')]
                return np.array(values)
            
            # Try space-separated
            elif ' ' in embedding_data:
                values = [float(x.strip()) for x in embedding_data.split()]
                return np.array(values)
        
        # If it's already a list/array
        elif isinstance(embedding_data, (list, np.ndarray)):
            return np.array(embedding_data)
        
        print(f"⚠️  Unknown embedding format: {type(embedding_data)}")
        return None
        
    except Exception as e:
        print(f"❌ Error parsing embedding: {e}")
        print(f"   Data preview: {str(embedding_data)[:200]}...")
        return None

def cosine_similarity(emb1, emb2):
    """Calculate cosine similarity between two embeddings."""
    # Normalize embeddings
    emb1_norm = emb1 / np.linalg.norm(emb1)
    emb2_norm = emb2 / np.linalg.norm(emb2)
    
    # Calculate cosine similarity
    similarity = np.dot(emb1_norm, emb2_norm)
    return float(similarity)

def get_embedding_info(stills_id, token):
    """Get embedding and related info for a stills_id."""
    try:
        print(f"\n{'='*80}")
        print(f"Retrieving {stills_id}")
        print(f"{'='*80}")
        
        # Find record
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        print(f"Record ID: {record_id}")
        
        # Get record data
        record_data = config.get_record(token, "Stills", record_id)
        
        # Get embedding
        embedding_data = record_data.get(FIELD_MAPPING["embedding"])
        
        if not embedding_data:
            print(f"⚠️  No embedding found in AI_Embed_Image field")
            return None
        
        # Show embedding preview
        if isinstance(embedding_data, str):
            print(f"Embedding data type: string")
            print(f"Embedding length: {len(embedding_data)} characters")
            print(f"Preview: {embedding_data[:100]}...")
        else:
            print(f"Embedding data type: {type(embedding_data)}")
        
        # Parse embedding
        embedding = parse_embedding(embedding_data)
        
        if embedding is None:
            print(f"❌ Failed to parse embedding")
            return None
        
        print(f"✅ Embedding parsed successfully")
        print(f"   Dimensions: {embedding.shape}")
        print(f"   First 5 values: {embedding[:5]}")
        print(f"   L2 Norm: {np.linalg.norm(embedding):.6f}")
        
        # Get thumbnail info
        server_path = record_data.get(FIELD_MAPPING["server_path"])
        if server_path and os.path.exists(server_path):
            file_size = os.path.getsize(server_path)
            print(f"\nServer file: {server_path}")
            print(f"File size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
        
        return {
            "stills_id": stills_id,
            "record_id": record_id,
            "embedding": embedding,
            "embedding_raw": embedding_data
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def compare_embeddings(info1, info2):
    """Compare two embeddings and display results."""
    print(f"\n{'='*80}")
    print(f"COMPARING EMBEDDINGS")
    print(f"{'='*80}")
    
    print(f"\n{info1['stills_id']} vs {info2['stills_id']}")
    print(f"Embedding shapes: {info1['embedding'].shape} vs {info2['embedding'].shape}")
    
    if info1['embedding'].shape != info2['embedding'].shape:
        print(f"❌ ERROR: Embeddings have different dimensions!")
        return None
    
    # Calculate similarity
    similarity = cosine_similarity(info1['embedding'], info2['embedding'])
    
    print(f"\n📊 COSINE SIMILARITY: {similarity:.6f}")
    print(f"   (1.0 = identical, 0.0 = completely different)")
    
    # Interpretation
    print(f"\n🔍 INTERPRETATION:")
    if similarity > 0.99:
        print(f"   🟢 IDENTICAL - Nearly perfect match (>0.99)")
    elif similarity > 0.95:
        print(f"   🟢 VERY HIGH - Strong duplicate match (>0.95)")
    elif similarity > 0.90:
        print(f"   🟡 HIGH - Likely duplicate (>0.90)")
    elif similarity > 0.85:
        print(f"   🟡 MODERATE - Possible duplicate (>0.85)")
    elif similarity > 0.80:
        print(f"   🟠 LOW - Unlikely duplicate (>0.80)")
    else:
        print(f"   🔴 VERY LOW - Not a duplicate (<0.80)")
    
    # For known duplicates
    print(f"\n💡 CONTEXT:")
    print(f"   These are KNOWN DUPLICATES")
    if similarity > 0.95:
        print(f"   ✅ Current embeddings successfully identify them as duplicates")
    elif similarity > 0.90:
        print(f"   ⚠️  Similarity is good but could be higher")
        print(f"   → Compression may be having a minor impact")
    else:
        print(f"   ❌ Similarity is lower than expected for duplicates")
        print(f"   → Compression may be significantly affecting detection")
    
    return similarity

if __name__ == "__main__":
    print("="*80)
    print("DUPLICATE DETECTION TEST: S00001 vs S07396")
    print("="*80)
    print("\nThese are KNOWN duplicates - testing if compression affects detection")
    
    # Get FileMaker token
    token = config.get_token()
    
    # Get embedding info for both items
    info_s00001 = get_embedding_info("S00001", token)
    info_s07396 = get_embedding_info("S07396", token)
    
    if not info_s00001 or not info_s07396:
        print("\n❌ Failed to retrieve embeddings")
        sys.exit(1)
    
    # Compare embeddings
    similarity = compare_embeddings(info_s00001, info_s07396)
    
    # Next steps
    print(f"\n{'='*80}")
    print("NEXT STEPS FOR TESTING:")
    print(f"{'='*80}")
    print(f"\n1. Current Status:")
    print(f"   - S00001: Now has FULL-RESOLUTION thumbnail ({info_s00001.get('embedding').shape[0]} dimensions)")
    print(f"   - S07396: Still has compressed 588x588 thumbnail")
    print(f"   - Current similarity: {similarity:.6f}")
    
    print(f"\n2. To Test Compression Impact:")
    print(f"   a) Regenerate S00001's embedding (using new full-res thumbnail)")
    print(f"   b) Run this script again")
    print(f"   c) Compare the NEW similarity to current: {similarity:.6f}")
    
    print(f"\n3. Expected Results:")
    print(f"   - If NEW similarity is HIGHER: Compression was reducing match quality")
    print(f"   - If NEW similarity is SIMILAR: Compression has minimal impact")
    print(f"   - If NEW similarity is LOWER: Something else is affecting embeddings")
    
    print(f"\n4. To Regenerate S00001 Embedding:")
    print(f"   - Use your FileMaker client to trigger CLIP embedding generation")
    print(f"   - It will now use the full-resolution thumbnail we uploaded")
    
    print(f"\n{'='*80}")
    print("Save this similarity score: {:.6f}".format(similarity))
    print("Run this script again after regenerating S00001's embedding")
    print(f"{'='*80}")

