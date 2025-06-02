import os
import json
import requests
import urllib3
import warnings
import time
import subprocess
import numpy as np
import whisper

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
ffmpeg_path = "/opt/homebrew/bin/ffmpeg"
tmp_dir = "/private/tmp"
model = whisper.load_model("base")  # Load Whisper model once

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

    # Find Keyframes with status = Embeddings Ready
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
        footage_id = field_data.get("FootageID")
        timecode = field_data.get("Timecode_IN")
        keyframe_id = field_data.get("KeyframeID")
        video_path = field_data.get("Footage::SPECS_Filepath_Server")

        if not all([footage_id, timecode, keyframe_id, video_path]):
            print(f"⚠️ Missing data for record {record_id}, skipping.")
            continue

        # Extract 5 second audio chunk
        audio_path = os.path.join(tmp_dir, f"{keyframe_id}_audio.wav")
        ffmpeg_cmd = [
            ffmpeg_path, "-y", "-ss", timecode, "-i", video_path,
            "-t", "5", "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_path
        ]

        try:
            subprocess.run(ffmpeg_cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg extraction failed: {e}")
            continue

        # Check if file has meaningful audio (basic peak detection)
        silent = False
        try:
            result = subprocess.run(
                [ffmpeg_path, "-i", audio_path, "-af", "volumedetect", "-f", "null", "-"],
                stderr=subprocess.PIPE, text=True
            )
            vol_output = result.stderr
            mean_volume_line = next((line for line in vol_output.splitlines() if "mean_volume:" in line), None)

            if mean_volume_line:
                mean_volume_db = float(mean_volume_line.split("mean_volume:")[1].split(" dB")[0].strip())
                print(f"🔊 Mean volume: {mean_volume_db} dB")

                if mean_volume_db < -50:
                    print("🧹 Detected silence. Skipping transcription.")
                    silent = True
            else:
                print("⚠️ Couldn't read volume. Proceeding anyway.")
        except Exception as e:
            print(f"❌ Audio check failed: {e}")
            continue

        transcript = ""

        if not silent:
            # Transcribe
            try:
                result = model.transcribe(audio_path, language="en")
                transcript = result.get("text", "").strip()
                print(f"📝 Transcript: {transcript}")
            except Exception as e:
                print(f"❌ Whisper transcription failed: {e}")
                continue

        # Update FileMaker regardless
        update_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/layouts/{layout_keyframes}/records/{record_id}"
        update_payload = {
            "fieldData": {
                "Keyframe_Transcript": transcript,
                "Keyframe_Status": "Audio Transcribed"
            }
        }
        update_resp = requests.patch(update_url, headers=headers, json=update_payload, verify=False)
        if update_resp.status_code == 200:
            print(f"✅ Updated transcription for {keyframe_id}")
        else:
            print(f"❌ Failed to update transcription: {update_resp.status_code}")

        os.remove(audio_path)

    # Logout
    logout_url = f"https://{server}/fmi/data/vLatest/databases/{db_encoded}/sessions/{token}"
    requests.delete(logout_url, headers={"Authorization": f"Bearer {token}"}, verify=False)

# Loop forever
while True:
    print("🔄 Starting audio check...")
    try:
        run_once()
    except Exception as e:
        print(f"❌ Loop error: {e}")
    print("⏳ Sleeping for 60 seconds...\n")
    time.sleep(60)