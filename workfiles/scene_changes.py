import os
import json
import requests
import urllib3
import warnings
import time
import numpy as np

# Suppress SSL and warning messages
warnings.filterwarnings('ignore')
urllib3.disable_warnings()

# Configuration
server = "10.0.222.144"
db_name = "Emancipation to Exodus"
db_encoded = db_name.replace(" ", "%20")
layout_keyframes = "Keyframes"
username = "Background"
password = "july1776"
threshold = 0.85  # Distance threshold for scene change

def run_once():
    # Get session token
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

    token = auth_response.json().get("response", {}).get("token")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Find keyframes where Keyframe_Status = Embedding Ready
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

    # Parse and sort records by timecode
    keyframes = []
    for record in records:
        record_id = record["recordId"]
        field_data = record["fieldData"]
        keyframe_id = field_data.get("KeyframeID")
        timecode = float(field_data.get("Timecode_IN"))
        embedding_str = field_data.get("Keyframe_Embedding")

        if not embedding_str:
            print(f"⚠️ Missing embedding for record {record_id}, skipping.")
            continue

        embedding = np.array(json.loads(embedding_str))
        keyframes.append({"recordId": record_id, "timecode": timecode, "embedding": embedding})

    keyframes.sort(key=lambda x: x["timecode"])

    for i in range(len(keyframes)):
        if i == 0:
            # Always mark first keyframe as scene change
            field_value = 0  # FileMaker checkbox (0 = true)
            print(f"📝 First frame {i} marked as scene change (start of clip)")
        else:
            prev_embedding = keyframes[i-1]["embedding"]
            curr_embedding = keyframes[i]["embedding"]
            distance = np.linalg.norm(curr_embedding - prev_embedding)
            is_scene_change = distance > threshold
            field_value = 0 if is_scene_change else ""

            print(f"📝 Compared frames {i-1} and {i} | Distance: {distance:.3f} | Scene Change: {is_scene_change}")

        # Update record
        update_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/layouts/{layout_keyframes}/records/{keyframes[i]['recordId']}"
        update_payload = {
            "fieldData": {
                "Keyframe_Is_SceneChange": field_value
                # "Keyframe_Status": "Embeddings Fused"  <-- You'll uncomment this later
            }
        }
        update_resp = requests.patch(update_url, headers=headers, json=update_payload, verify=False)

    # Logout
    logout_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/sessions/{token}"
    requests.delete(logout_url, headers={"Authorization": f"Bearer {token}"}, verify=False)

# Loop forever
while True:
    print("🔄 Starting scene change check...")
    try:
        run_once()
    except Exception as e:
        print(f"❌ Error in scene change loop: {e}")
    print("⏳ Sleeping for 60 seconds...\n")
    time.sleep(60)