# jobs/stills_autolog_06_fuse_embeddings.py
import sys, os, subprocess, requests
from pathlib import Path
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
        
        img_field = FIELD_MAPPING['img_embedding']
        txt_field = FIELD_MAPPING['txt_embedding']
        
        # Get record with base64 encoded fields
        r = requests.get(
            config.url(f"layouts/Stills/records/{record_id}?fieldData.{img_field}.encoding=base64&fieldData.{txt_field}.encoding=base64"),
            headers=config.api_headers(token),
            verify=False
        )
        r.raise_for_status()
        
        field_data_fm = r.json()['response']['data'][0]['fieldData']
        img_embedding_b64 = field_data_fm.get(img_field)
        txt_embedding_b64 = field_data_fm.get(txt_field)
        
        if not img_embedding_b64 or not txt_embedding_b64:
            raise ValueError("One or both embedding fields are empty. Cannot fuse.")
            
        img_path = f"/tmp/{stills_id}_img_embedding.b64"
        txt_path = f"/tmp/{stills_id}_txt_embedding.b64"
        with open(img_path, "w") as f: f.write(img_embedding_b64)
        with open(txt_path, "w") as f: f.write(txt_embedding_b64)
        
        result = subprocess.run(['/usr/local/bin/fuse-embeddings', img_path, txt_path], capture_output=True, text=True, check=True)
        fused_embedding_str = result.stdout.strip()
        
        os.remove(img_path)
        os.remove(txt_path)
        
        update_payload = {FIELD_MAPPING["fused_embedding"]: fused_embedding_str}
        config.update_record(token, "Stills", record_id, update_payload)
        print(f"SUCCESS [fuse_embeddings]: {stills_id}")
        sys.exit(0)

    except Exception as e:
        sys.stderr.write(f"ERROR [fuse_embeddings] on {stills_id}: {e}\n")
        if 'img_path' in locals() and os.path.exists(img_path): os.remove(img_path)
        if 'txt_path' in locals() and os.path.exists(txt_path): os.remove(txt_path)
        sys.exit(1)