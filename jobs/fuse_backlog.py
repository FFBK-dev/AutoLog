import sys, os, json, time
from pathlib import Path
import numpy as np
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
import requests

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "status": "AutoLog_Status",
    "img_embedding": "AI_ImageEmbedding",
    "txt_embedding": "AI_TextEmbedding_CLIP",
    "fused_embedding": "AI_FusedEmbedding"
}

BATCH_SIZE = 25
SLEEP_BETWEEN_BATCHES = 5  # seconds

if __name__ == "__main__":
    token = config.get_token()
    total_processed = 0
    while True:
        # Find up to BATCH_SIZE records with status '9 - Ready for Fusion'
        query = {
            "query": [{FIELD_MAPPING["status"]: "==9 - Ready for Fusion"}],
            "limit": BATCH_SIZE
        }
        r = requests.post(config.url("layouts/Stills/_find"), headers=config.api_headers(token), json=query, verify=False)
        r.raise_for_status()
        records = r.json().get('response', {}).get('data', [])
        if not records:
            print(f"No more records to process. Total processed: {total_processed}")
            break
        print(f"Processing batch of {len(records)} records...")
        for record in records:
            try:
                record_id = record['recordId']
                stills_id = record['fieldData'][FIELD_MAPPING["stills_id"]]
                record_data = config.get_record(token, "Stills", record_id)
                img_embedding_str = record_data.get(FIELD_MAPPING['img_embedding'], "")
                txt_embedding_str = record_data.get(FIELD_MAPPING['txt_embedding'], "")
                if not img_embedding_str or not txt_embedding_str:
                    print(f"[SKIP] {stills_id}: Missing embedding(s)")
                    continue
                try:
                    img_embedding = json.loads(img_embedding_str)
                    txt_embedding = json.loads(txt_embedding_str)
                except json.JSONDecodeError as e:
                    print(f"[SKIP] {stills_id}: Invalid embedding format: {e}")
                    continue
                if not img_embedding or not txt_embedding:
                    print(f"[SKIP] {stills_id}: Empty embedding array(s)")
                    continue
                img_array = np.array(img_embedding, dtype=np.float32)
                txt_array = np.array(txt_embedding, dtype=np.float32)
                if img_array.shape != txt_array.shape:
                    print(f"[SKIP] {stills_id}: Shape mismatch {img_array.shape} vs {txt_array.shape}")
                    continue
                fused_array = 0.5 * img_array + 0.5 * txt_array
                norm = np.linalg.norm(fused_array)
                if norm == 0:
                    print(f"[SKIP] {stills_id}: Fused embedding norm is zero.")
                    continue
                fused_array /= norm
                fused_json = json.dumps(fused_array.tolist())
                update_payload = {
                    FIELD_MAPPING["fused_embedding"]: fused_json,
                    FIELD_MAPPING["status"]: "10 - Complete"
                }
                config.update_record(token, "Stills", record_id, update_payload)
                print(f"[OK] {stills_id}: Fused embedding updated and status set to 10 - Complete.")
                total_processed += 1
            except Exception as e:
                print(f"[ERROR] {record.get('fieldData', {}).get(FIELD_MAPPING['stills_id'], 'UNKNOWN')}: {e}")
        print(f"Sleeping {SLEEP_BETWEEN_BATCHES}s before next batch...")
        time.sleep(SLEEP_BETWEEN_BATCHES) 