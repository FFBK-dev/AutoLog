# jobs/stills_autolog_06_fuse_embeddings.py
import sys, os, subprocess
from pathlib import Path
import requests
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
    stills_id = sys.argv[1]
    token = config.get_token()
    
    try:
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        
        # Request Base64 encoded container data
        container_url = config.url(f"layouts/Stills/records/{record_id}?fieldData.{FIELD_MAPPING['img_embedding']}.encoding=base64&fieldData.{FIELD_MAPPING['txt_embedding']}.encoding=base64")
        r = requests.get(container_url, headers=config.api_headers(token))
        r.raise_for_status()
        
        field_data_fm = r.json()['response']['data'][0]['fieldData']
        img_embedding_b64 = field_data_fm.get(FIELD_MAPPING['img_embedding'])
        txt_embedding_b64 = field_data_fm.get(FIELD_MAPPING['txt_embedding'])
        
        if not img_embedding_b64 or not txt_embedding_b64:
            raise ValueError("One or both embedding fields are empty.")
            
        # ... (logic to write temp files and run fuse-embeddings is the same) ...
        
        update_payload = {"fieldData": {FIELD_MAPPING["fused_embedding"]: fused_embedding_str}}
        requests.patch(config.url(f"layouts/Stills/records/{record_id}"), headers=config.api_headers(token), json=update_payload).raise_for_status()
        print(f"SUCCESS [fuse_embeddings]: {stills_id}")
        sys.exit(0)

    except Exception as e:
        sys.stderr.write(f"ERROR [fuse_embeddings] on {stills_id}: {e}\n")
        sys.exit(1)