import os
import json
import requests
import urllib3
import warnings
import time
import openai
import math

# Suppress SSL warnings
warnings.filterwarnings('ignore')
urllib3.disable_warnings()

# Config
server = "10.0.222.144"
db_name = "Emancipation to Exodus"
db_encoded = db_name.replace(" ", "%20")
layout_keyframes = "Keyframes"
layout_footage = "Footage"
username = "Background"
password = "july1776"
openai_api_key = "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"
chunk_size = 120  # 10 minutes worth of keyframes (5 sec intervals)

client = openai.OpenAI(api_key=openai_api_key)

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

    # Find all Keyframes where status is Audio Transcribed
    find_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/layouts/{layout_keyframes}/_find"
    query_payload = {"query": [{"Keyframe_Status": "Audio Transcribed"}]}
    find_response = requests.post(find_url, headers=headers, json=query_payload, verify=False)

    if find_response.status_code != 200:
        print("❌ Find failed:", find_response.status_code, find_response.text)
        return

    records = find_response.json().get("response", {}).get("data", [])
    if not records:
        print("✅ No keyframes ready.")
        return

    # Group records by FootageID
    footage_map = {}
    for record in records:
        field_data = record["fieldData"]
        footage_id = field_data.get("FootageID")
        if not footage_id:
            continue
        footage_map.setdefault(footage_id, []).append(field_data)

    for footage_id, keyframes in footage_map.items():
        # Check if ALL keyframes for this FootageID have reached Audio Transcribed
        count_all_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/layouts/{layout_keyframes}/_find"
        all_query = {"query": [{"FootageID": footage_id}]}
        all_response = requests.post(count_all_url, headers=headers, json=all_query, verify=False)
        all_records = all_response.json().get("response", {}).get("data", [])
        total_count = len(all_records)
        transcribed_count = len(keyframes)

        if transcribed_count != total_count:
            print(f"⏩ Skipping {footage_id}, not all keyframes transcribed yet.")
            continue

        # Pull corresponding footage record
        get_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/layouts/{layout_footage}/_find"
        payload = {"query": [{"INFO_FTG_ID": footage_id}]}
        get_response = requests.post(get_url, headers=headers, json=payload, verify=False)
        footage_records = get_response.json().get("response", {}).get("data", [])
        if not footage_records:
            print(f"⚠️ No footage record found for {footage_id}")
            continue

        footage_record = footage_records[0]
        footage_record_id = footage_record["recordId"]
        footage_field_data = footage_record["fieldData"]
        existing_description = footage_field_data.get("INFO_Description", "")
        filename = footage_field_data.get("Filename", "")

        # Sort keyframes
        keyframes_sorted = sorted(keyframes, key=lambda x: x.get("KeyframeID", ""))

        chunk_summaries = []
        full_csv_lines = []

        # Process chunks
        for i in range(0, len(keyframes_sorted), chunk_size):
            chunk = keyframes_sorted[i:i + chunk_size]
            csv_lines = ["Frame,Visual Description,Audio Transcript"]
            for kf in chunk:
                desc = kf.get("Keyframe_Description", "").replace("\n", " ").strip()
                trans = kf.get("Keyframe_Transcript", "").replace("\n", " ").strip()
                frame_id = kf.get("KeyframeID", "")
                csv_lines.append(f"{frame_id},{desc},{trans}")
                full_csv_lines.append(f"{frame_id},{desc},{trans}")

            combined_csv = "\n".join(csv_lines)

            system_prompt = (
                "You are generating a concise but thorough description of a video chunk for archival purposes. "
                "The input provides frame-level visual descriptions and transcripts. "
                "Do not use phrases like 'this video shows...' or 'the clip contains...'. "
                "Just provide a clean, direct summary as if writing catalog metadata. "
                "Length: ~2-3 sentences."
            )

            user_prompt = f"""Filename: {filename}
Existing description: {existing_description}
Frame-level data:
{combined_csv}"""

            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3
                )

                chunk_summary = response.choices[0].message.content.strip()
                print(f"📝 Chunk {i//chunk_size + 1} summary: {chunk_summary}")
                chunk_summaries.append(chunk_summary)

            except Exception as e:
                print(f"❌ OpenAI error (chunk {i//chunk_size + 1}): {e}")

        # Combine chunk summaries into master description
        combined_summaries_text = "\n".join(chunk_summaries)

        system_prompt_final = (
            "You are generating a master description of a video file for archival purposes. "
            "You are given summaries of individual chunks of the video. "
            "Write a concise and thorough catalog description, without introductory phrases, just clean catalog metadata."
        )

        user_prompt_final = f"""Filename: {filename}
Existing description: {existing_description}
Chunk summaries:
{combined_summaries_text}"""

        try:
            response_final = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt_final},
                    {"role": "user", "content": user_prompt_final}
                ],
                temperature=0.3
            )

            final_summary = response_final.choices[0].message.content.strip()
            print(f"📝 Final Summary for {footage_id}: {final_summary}")

            # Update footage record
            update_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/layouts/{layout_footage}/records/{footage_record_id}"
            update_payload = {
                "fieldData": {
                    "INFO_Description": final_summary,
                    "INFO_Video_Events": "\n".join(["Frame,Visual Description,Audio Transcript"] + full_csv_lines)
                }
            }
            update_resp = requests.patch(update_url, headers=headers, json=update_payload, verify=False)
            if update_resp.status_code == 200:
                print(f"✅ Updated footage record {footage_id}")

                # Update child keyframes to Fully Processed
                update_keyframes_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/layouts/{layout_keyframes}/_find"
                child_query = {"query": [{"FootageID": footage_id}]}
                child_resp = requests.post(update_keyframes_url, headers=headers, json=child_query, verify=False)

                if child_resp.status_code == 200:
                    child_records = child_resp.json().get("response", {}).get("data", [])
                    for child in child_records:
                        child_record_id = child["recordId"]
                        update_child_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/layouts/{layout_keyframes}/records/{child_record_id}"
                        update_child_payload = {"fieldData": {"Keyframe_Status": "Fully Processed"}}
                        child_update_resp = requests.patch(update_child_url, headers=headers, json=update_child_payload, verify=False)
                        if child_update_resp.status_code == 200:
                            print(f"✅ Marked keyframe {child_record_id} as Fully Processed")
                        else:
                            print(f"❌ Failed to update keyframe {child_record_id}: {child_update_resp.status_code}")
                else:
                    print(f"❌ Failed to find child keyframes for {footage_id}")

            else:
                print(f"❌ Failed to update footage: {update_resp.status_code}")

        except Exception as e:
            print(f"❌ OpenAI error (final synthesis): {e}")

    # Logout
    logout_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/sessions/{token}"
    requests.delete(logout_url, headers={"Authorization": f"Bearer {token}"}, verify=False)


# Loop forever
while True:
    print("🔄 Starting footage summarization check...")
    try:
        run_once()
    except Exception as e:
        print(f"❌ Loop error: {e}")
    print("⏳ Sleeping for 60 seconds...\n")
    time.sleep(60)