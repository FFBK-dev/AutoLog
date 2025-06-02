import os
import json
import requests
import urllib3
import warnings
import time
import numpy as np

# Suppress SSL warnings
warnings.filterwarnings('ignore')
urllib3.disable_warnings()

# Config
server = "10.0.222.144"
db_name = "Emancipation to Exodus"
db_encoded = db_name.replace(" ", "%20")
layout_keyframes = "Keyframes"
username = "Background"
password = "july1776"

def run_once():
    # Authenticate
    session_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/sessions"
    auth_response = requests.post(
        session_url,
        auth=(username, password),
        headers={"Content-Type": "application/json"},
        data="{}",
        verify=False
    )
    if auth_response.status_code != 200:
        print("❌ Authentication failed:", auth_response.status_code, auth_response.text)
        return

    token = auth_response.json()["response"]["token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Find Keyframes where status is Embeddings Ready
    find_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/layouts/{layout_keyframes}/_find"
    query_payload = {"query": [{"Keyframe_Status": "Embeddings Ready"}]}
    find_response = requests.post(find_url, headers=headers, json=query_payload, verify=False)

    if find_response.status_code != 200:
        print("❌ Find failed:", find_response.status_code, find_response.text)
        return

    records = find_response.json().get("response", {}).get("data", [])
    if not records:
        print("✅ No records to process.")
        return

    for record in records:
        record_id = record["recordId"]
        field_data = record["fieldData"]
        keyframe_id = field_data.get("KeyframeID")

        try:
            # Parse embeddings directly from text fields
            text_embedding = json.loads(field_data.get("Keyframe_Text_Embedding", "[]"))
            image_embedding = json.loads(field_data.get("Keyframe_Image_Embedding", "[]"))

            # Safety checks
            if not text_embedding or not image_embedding:
                print(f"⚠️ Missing embeddings for {keyframe_id}. Skipping.")
                continue

            text_array = np.array(text_embedding, dtype=np.float32)
            image_array = np.array(image_embedding, dtype=np.float32)

            if text_array.shape != image_array.shape:
                print(f"⚠️ Shape mismatch for {keyframe_id}. Skipping.")
                continue

            # Fuse (simple average)
            fused_array = 0.5 * text_array + 0.5 * image_array
            fused_array /= np.linalg.norm(fused_array)

            # Store back as JSON list
            fused_json = json.dumps(fused_array.tolist())

            # Update FileMaker record
            update_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/layouts/{layout_keyframes}/records/{record_id}"
            update_payload = {
                "fieldData": {
                    "Keyframe_Fused_Embedding": fused_json,
                    "Keyframe_Status": "Embeddings Fused
            }
            update_resp = requests.patch(update_url, headers=headers, json=update_payload, verify=False)
            if update_resp.status_code == 200:
                print(f"✅ Fused embeddings for {keyframe_id}")
            else:
                print(f"❌ Failed to update record {keyframe_id}: {update_resp.status_code}")

        except Exception as e:
            print(f"❌ Processing error for {keyframe_id}: {e}")

    # Logout
    logout_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/sessions/{token}"
    requests.delete(logout_url, headers={"Authorization": f"Bearer {token}"}, verify=False)


# Loop forever
while True:
    print("🔄 Starting embedding fusion check...")
    try:
        run_once()
    except Exception as e:
        print(f"❌ Loop error: {e}")
    print("⏳ Sleeping for 60 seconds...\n")
    time.sleep(60)