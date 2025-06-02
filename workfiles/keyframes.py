import os
import json
import requests
import urllib3
import subprocess
import warnings
import time
import openai
import base64

# Suppress SSL and warning messages
warnings.filterwarnings('ignore')
urllib3.disable_warnings()

# Configuration
server = "10.0.222.144"
db_name = "Emancipation to Exodus"
db_encoded = db_name.replace(" ", "%20")
layout_keyframes = "Keyframes"
layout_footage = "Footage"
username = "Background"
password = "july1776"
ffmpeg_path = "/opt/homebrew/bin/ffmpeg"
tmp_dir = "/private/tmp"
openai.api_key = "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"

# Simplified GPT system prompt
gpt_prompt = (
    "You are generating brief visual descriptions for frames pulled from historical footage. "
    "Keep it concise, under 70 tokens. Avoid unnecessary phrases like 'this image shows'. "
    "Just describe what's in the frame: people, setting, action, objects. "
    "Also include the approximate shot type (wide, medium, close)."
)

def remove_markdown(text):
    # Very simple markdown cleaner
    text = text.replace("*", "")
    text = text.replace("-", "")
    text = text.replace("_", "")
    text = text.strip()
    return text

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

    token = auth_response.json().get("response", {}).get("token")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Find records where Keyframe_Status = "Pending"
    find_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/layouts/{layout_keyframes}/_find"
    query_payload = {
        "query": [{"Keyframe_Status": "Pending"}]
    }
    find_response = requests.post(find_url, headers=headers, json=query_payload, verify=False)

    if find_response.status_code != 200:
        print("❌ Find failed:", find_response.status_code, find_response.text)
        return

    records = find_response.json().get("response", {}).get("data", [])

    for record in records:
        record_id = record["recordId"]
        field_data = record["fieldData"]
        footage_id = field_data.get("FootageID")
        timecode = field_data.get("Timecode_IN")
        keyframe_id = field_data.get("KeyframeID")
        video_path = field_data.get("Footage::SPECS_Filepath_Server")

        if not all([footage_id, timecode, keyframe_id, video_path]):
            print(f"⚠️ Missing data in record {record_id}, skipping.")
            continue

        # Generate thumbnail
        thumb_filename = f"thumbnail_{keyframe_id}.jpg"
        thumb_path = os.path.join(tmp_dir, thumb_filename)
        ffmpeg_cmd = [
            ffmpeg_path,
            "-y", "-ss", timecode,
            "-i", video_path,
            "-frames:v", "1",
            thumb_path
        ]

        try:
            subprocess.run(ffmpeg_cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg failed for {video_path}: {e}")
            continue

        # Upload thumbnail to FileMaker
        upload_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/layouts/{layout_keyframes}/records/{record_id}/containers/Thumbnail/1"
        with open(thumb_path, "rb") as f:
            files = {"upload": (thumb_filename, f, "image/jpeg")}
            upload_resp = requests.post(upload_url, headers={"Authorization": f"Bearer {token}"}, files=files, verify=False)
            print(f"✅ Uploaded thumbnail for {keyframe_id}: {upload_resp.status_code}")

        # Get additional footage context for GPT
        footage_find_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/layouts/{layout_footage}/_find"
        footage_payload = {"query": [{"INFO_FTG_ID": footage_id}]}
        footage_resp = requests.post(footage_find_url, headers=headers, json=footage_payload, verify=False)
        footage_data = footage_resp.json().get("response", {}).get("data", [])

        filename_context = ""
        description_context = ""

        if footage_data:
            footage_fields = footage_data[0]["fieldData"]
            filename_context = footage_fields.get("INFO_Original_FileName", "")
            description_context = footage_fields.get("INFO_Description", "")

        # Encode image for GPT-4o vision
        with open(thumb_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode("utf-8")

        try:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": gpt_prompt
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"""Filename: {filename_context}
Existing description: {description_context}
Generate the keyframe description:"""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ]
            )

            gpt_caption = response.choices[0].message.content
            gpt_caption_clean = remove_markdown(gpt_caption)

            print(f"📝 Caption: {gpt_caption_clean}")

            # Update FileMaker record with caption + status
            update_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/layouts/{layout_keyframes}/records/{record_id}"
            update_payload = {
                "fieldData": {
                    "Keyframe_GPT_Caption": gpt_caption_clean,
                    "Keyframe_Status": "Thumbnail Ready"
                }
            }
            update_resp = requests.patch(update_url, headers=headers, json=update_payload, verify=False)
            print(f"🔄 Updated record {record_id} with caption.")

        except Exception as e:
            print(f"❌ Error generating OpenAI caption: {e}")

    # Log out from FileMaker
    logout_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/sessions/{token}"
    requests.delete(logout_url, headers={"Authorization": f"Bearer {token}"}, verify=False)

# Loop forever
while True:
    print("🔄 Starting keyframe check...")
    try:
        run_once()
    except Exception as e:
        print(f"❌ Error in keyframe loop: {e}")
    print("⏳ Sleeping for 30 seconds...\n")
    time.sleep(30)