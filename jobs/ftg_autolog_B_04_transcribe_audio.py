#!/usr/bin/env python3
"""
Footage AutoLog B Step 4: Audio Transcription Mapping (Optional)
- Checks if transcription completed from Step 1
- Maps transcript segments to frame records
- Updates frame records with audio transcripts
- Only runs if audio was detected in Step 1
- Supports both LF (Library Footage) and AF (Archival Footage)
"""

import sys
import os
import json
import warnings
from pathlib import Path
import requests

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.audio_detector import check_transcription_status, load_transcript, map_transcript_to_frames

__ARGS__ = ["footage_id"]

FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "frame_parent_id": "FRAMES_ParentID",
    "frame_id": "FRAMES_ID",
    "frame_timecode": "FRAMES_TC_IN",
    "frame_transcript": "FRAMES_Transcript",
    "frame_status": "FRAMES_Status"
}


def update_frame_transcript(token, record_id, frame_id, transcript_text):
    """Update a frame record with transcript text."""
    try:
        field_data = {
            FIELD_MAPPING["frame_transcript"]: transcript_text,
            FIELD_MAPPING["frame_status"]: "4 - Audio Transcribed"
        }
        
        response = config.update_record(token, "FRAMES", record_id, field_data)
        
        if response.status_code == 200:
            return True
        else:
            print(f"    -> ⚠️ Failed to update {frame_id}: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"    -> ❌ Error updating {frame_id}: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    
    footage_id = sys.argv[1]
    
    # Flexible token handling
    if len(sys.argv) == 2:
        token = config.get_token()
        print(f"Direct mode: Created new FileMaker session for {footage_id}")
    elif len(sys.argv) == 3:
        token = sys.argv[2]
        print(f"Subprocess mode: Using provided token for {footage_id}")
    else:
        sys.stderr.write(f"ERROR: Invalid arguments. Expected: script.py footage_id [token]\n")
        sys.exit(1)
    
    try:
        print(f"=== Audio Transcription Mapping for {footage_id} ===")
        
        # Load assessment data (supports both LF and AF prefixes)
        output_dir = f"/private/tmp/ftg_autolog_{footage_id}"
        assessment_path = os.path.join(output_dir, "assessment.json")
        
        if not os.path.exists(assessment_path):
            raise FileNotFoundError(f"Assessment file not found: {assessment_path}")
        
        with open(assessment_path, 'r') as f:
            assessment_data = json.load(f)
        
        # Check if audio was detected
        audio_status = assessment_data.get('audio_status', 'unknown')
        
        if audio_status == 'silent':
            print(f"  -> 📵 Video is silent - no transcription needed")
            print(f"  -> Updating all frames to '4 - Audio Transcribed' status...")
            
            # Find all frames and update status (no transcript)
            try:
                query = {
                    "query": [{FIELD_MAPPING["frame_parent_id"]: footage_id}],
                    "limit": 1000
                }
                
                response = requests.post(
                    config.url("layouts/FRAMES/_find"),
                    headers=config.api_headers(token),
                    json=query,
                    verify=False,
                    timeout=30
                )
                
                if response.status_code == 200:
                    frames = response.json()['response']['data']
                    
                    updated = 0
                    for frame in frames:
                        frame_id = frame['fieldData'].get(FIELD_MAPPING["frame_id"])
                        record_id = frame['recordId']
                        
                        if update_frame_transcript(token, record_id, frame_id, ""):
                            updated += 1
                    
                    print(f"  -> ✅ Updated {updated}/{len(frames)} frames as silent")
                
            except Exception as e:
                print(f"  -> ⚠️ Error updating silent frames: {e}")
            
            print(f"✅ Silent video processing complete for {footage_id}")
            sys.exit(0)
        
        # Check transcription status
        status_file = assessment_data.get('transcription_status_path')
        
        if not status_file or not os.path.exists(status_file):
            print(f"  -> ⚠️ No transcription status file found")
            print(f"  -> This may mean transcription hasn't started or audio detection failed")
            sys.exit(0)
        
        status = check_transcription_status(status_file)
        
        print(f"  -> Transcription status: {status['status']}")
        
        if status['status'] == 'running':
            progress = status.get('progress', 0)
            print(f"  -> Transcription still in progress ({progress}%)")
            print(f"  -> Will check again later")
            sys.exit(0)
        
        elif status['status'] == 'failed':
            error = status.get('error', 'Unknown error')
            print(f"  -> ❌ Transcription failed: {error}")
            print(f"  -> Marking frames as MOS (no audio)")
            
            # Update frames without transcripts
            try:
                query = {
                    "query": [{FIELD_MAPPING["frame_parent_id"]: footage_id}],
                    "limit": 1000
                }
                
                response = requests.post(
                    config.url("layouts/FRAMES/_find"),
                    headers=config.api_headers(token),
                    json=query,
                    verify=False,
                    timeout=30
                )
                
                if response.status_code == 200:
                    frames = response.json()['response']['data']
                    
                    for frame in frames:
                        frame_id = frame['fieldData'].get(FIELD_MAPPING["frame_id"])
                        record_id = frame['recordId']
                        update_frame_transcript(token, record_id, frame_id, "")
                
            except Exception as e:
                print(f"  -> ⚠️ Error updating frames: {e}")
            
            sys.exit(1)
        
        elif status['status'] == 'completed':
            print(f"  -> ✅ Transcription completed")
            
            # Load transcript
            transcript_path = assessment_data.get('audio_transcript_path')
            
            if not transcript_path or not os.path.exists(transcript_path):
                raise FileNotFoundError(f"Transcript file not found: {transcript_path}")
            
            transcript = load_transcript(transcript_path)
            
            if not transcript:
                raise RuntimeError("Failed to load transcript")
            
            print(f"  -> Loaded transcript with {len(transcript.get('segments', []))} segments")
            
            # Get frame timestamps
            frame_timestamps = []
            for frame_data in assessment_data['frames'].values():
                frame_timestamps.append(frame_data['timestamp_seconds'])
            
            frame_timestamps.sort()
            
            # Map transcript to frames
            print(f"\n🔄 Mapping transcript to {len(frame_timestamps)} frames...")
            frame_transcripts = map_transcript_to_frames(transcript, frame_timestamps)
            
            # Update frame records
            print(f"\n📝 Updating frame records with transcripts...")
            
            # Find all frames
            query = {
                "query": [{FIELD_MAPPING["frame_parent_id"]: footage_id}],
                "limit": 1000
            }
            
            response = requests.post(
                config.url("layouts/FRAMES/_find"),
                headers=config.api_headers(token),
                json=query,
                verify=False,
                timeout=30
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"Failed to find frames: {response.status_code}")
            
            frames = response.json()['response']['data']
            
            updated = 0
            for frame in frames:
                frame_id = frame['fieldData'].get(FIELD_MAPPING["frame_id"])
                record_id = frame['recordId']
                timecode = frame['fieldData'].get(FIELD_MAPPING["frame_timecode"])
                
                # Find matching transcript by timestamp
                # Parse timecode to seconds
                try:
                    parts = timecode.split(':')
                    if len(parts) == 4:
                        h, m, s, f = map(int, parts)
                        timestamp = h * 3600 + m * 60 + s + (f / 30.0)  # Assume 30fps
                        
                        transcript_text = frame_transcripts.get(timestamp, "")
                        
                        if update_frame_transcript(token, record_id, frame_id, transcript_text):
                            updated += 1
                            if transcript_text:
                                print(f"    -> {frame_id}: {len(transcript_text)} chars")
                            else:
                                print(f"    -> {frame_id}: (no audio)")
                except Exception as e:
                    print(f"    -> ⚠️ Error processing {frame_id}: {e}")
                    continue
            
            print(f"\n  -> ✅ Updated {updated}/{len(frames)} frames with transcripts")
            
            print(f"\n=== Audio Transcription Complete ===")
            print(f"  Frames updated: {updated}")
            print(f"  Frames with audio: {len([t for t in frame_transcripts.values() if t])}")
            
            print(f"\n✅ Audio transcription mapping completed for {footage_id}")
        
        else:
            print(f"  -> Unknown transcription status: {status['status']}")
            sys.exit(1)
        
    except Exception as e:
        print(f"❌ Error in audio transcription mapping for {footage_id}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

