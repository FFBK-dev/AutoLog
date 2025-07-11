# jobs/stills_autolog_08_fuse_embeddings.py
import sys, os, json, time, requests
import warnings
from pathlib import Path
import numpy as np
import openai

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

# Add the parent directory to the path to import your existing config
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["stills_id"]

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "img_embedding": "AI_ImageEmbedding",
    "txt_embedding": "AI_TextEmbedding_CLIP",
    "fused_embedding": "AI_FusedEmbedding"
}

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    stills_id = sys.argv[1]
    token = config.get_token()
    
    try:
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        record_data = config.get_record(token, "Stills", record_id)
        
        img_embedding_str = record_data.get(FIELD_MAPPING['img_embedding'], "")
        txt_embedding_str = record_data.get(FIELD_MAPPING['txt_embedding'], "")
        
        if not img_embedding_str or not txt_embedding_str:
            raise ValueError("One or both embedding fields are empty. Cannot fuse.")
        
        try:
            img_embedding = json.loads(img_embedding_str)
            txt_embedding = json.loads(txt_embedding_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid embedding format: {e}")
        
        if not img_embedding or not txt_embedding:
            raise ValueError("One or both embeddings are empty arrays.")
        
        img_array = np.array(img_embedding, dtype=np.float32)
        txt_array = np.array(txt_embedding, dtype=np.float32)
        
        if img_array.shape != txt_array.shape:
            raise ValueError(f"Shape mismatch: {img_array.shape} vs {txt_array.shape}")
        
        # Fuse: average and normalize
        fused_array = 0.5 * img_array + 0.5 * txt_array
        norm = np.linalg.norm(fused_array)
        if norm == 0:
            raise ValueError("Fused embedding norm is zero.")
        fused_array /= norm
        fused_json = json.dumps(fused_array.tolist())
        
        update_payload = {FIELD_MAPPING["fused_embedding"]: fused_json}
        config.update_record(token, "Stills", record_id, update_payload)
        print(f"SUCCESS [fuse_embeddings]: {stills_id}")
        sys.exit(0)

    except Exception as e:
        sys.stderr.write(f"ERROR [fuse_embeddings] on {stills_id}: {e}\n")
        sys.exit(1)