#!/usr/bin/env python3
"""
Footage AutoLog B Step 3: Create Frame Records from Gemini Response
- Parses Gemini JSON response
- Creates FRAMES records with captions pre-populated
- Uploads cached thumbnails
- Sets status to "3 - Caption Generated"
- Updates parent FOOTAGE record with global metadata
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

__ARGS__ = ["footage_id"]

FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "description": "INFO_Description",
    "date": "INFO_Date",
    "location": "INFO_Location",
    "audio_type": "INFO_AudioType",
    "tags_list": "TAGS_List",
    "primary_bin": "INFO_PrimaryBin",
    "video_events": "INFO_Video_Events",
    "frame_parent_id": "FRAMES_ParentID",
    "frame_status": "FRAMES_Status",
    "frame_timecode": "FRAMES_TC_IN",
    "frame_id": "FRAMES_ID",
    "frame_caption": "FRAMES_Caption",
    "frame_thumbnail": "FRAMES_Thumbnail",
    "frame_framerate": "FOOTAGE::SPECS_File_Framerate"
}


def create_frame_record_with_caption(token, footage_id, frame_data, frame_metadata, framerate):
    """Create a FRAMES record with caption pre-populated."""
    try:
        frame_num = frame_data['frame_number']
        frame_id = f"{footage_id}_{frame_num:03d}"
        timecode = frame_data['timecode']
        caption = frame_data['caption']
        
        # Create record
        payload = {
            "fieldData": {
                FIELD_MAPPING["frame_parent_id"]: footage_id,
                FIELD_MAPPING["frame_timecode"]: timecode,
                FIELD_MAPPING["frame_status"]: "3 - Caption Generated",
                FIELD_MAPPING["frame_id"]: frame_id,
                FIELD_MAPPING["frame_caption"]: caption,
                FIELD_MAPPING["frame_framerate"]: framerate
            }
        }
        
        response = requests.post(
            config.url("layouts/FRAMES/records"),
            headers=config.api_headers(token),
            json=payload,
            verify=False,
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            record_id = response.json()['response']['recordId']
            print(f"    -> Created {frame_id} at {timecode}")
            
            # Upload thumbnail if available
            frame_filename = None
            for fname, fdata in frame_metadata.items():
                if fdata['frame_number'] == frame_num:
                    frame_filename = fname
                    break
            
            if frame_filename:
                thumb_path = frame_metadata[frame_filename]['file_path']
                
                if os.path.exists(thumb_path):
                    upload_url = config.url(f"layouts/FRAMES/records/{record_id}/containers/{FIELD_MAPPING['frame_thumbnail']}/1")
                    
                    with open(thumb_path, "rb") as f:
                        files = {"upload": (frame_filename, f, "image/jpeg")}
                        upload_resp = requests.post(
                            upload_url,
                            headers={"Authorization": f"Bearer {token}"},
                            files=files,
                            verify=False,
                            timeout=30
                        )
                    
                    if upload_resp.status_code == 200:
                        print(f"    -> ✅ Thumbnail uploaded for {frame_id}")
                    else:
                        print(f"    -> ⚠️ Thumbnail upload failed for {frame_id}")
            
            return True, record_id
        else:
            print(f"    -> ❌ Failed to create {frame_id}: {response.status_code}")
            return False, None
            
    except Exception as e:
        print(f"    -> ❌ Error creating frame: {e}")
        return False, None


def build_video_events_csv(gemini_result):
    """Build CSV format video events data for INFO_Video_Events field."""
    csv_lines = ["Frame,Timecode,Visual Description,Audio Transcript"]
    
    for frame in gemini_result['frames']:
        frame_id = f"Frame {frame['frame_number']}"
        timecode = frame['timecode']
        caption = frame['caption'].replace("\n", " ").replace(",", ";")  # CSV safe
        transcript = ""  # Will be populated by step 6 if audio exists
        
        csv_lines.append(f"{frame_id},{timecode},{caption},{transcript}")
    
    return "\n".join(csv_lines)


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
        print(f"=== Creating Frame Records for {footage_id} ===")
        
        # Get the current record
        record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        footage_data = config.get_record(token, "FOOTAGE", record_id)
        
        # Load Gemini result from step 2 (supports both LF and AF prefixes)
        output_dir = f"/private/tmp/ftg_autolog_{footage_id}"
        gemini_result_path = os.path.join(output_dir, "gemini_result.json")
        
        if not os.path.exists(gemini_result_path):
            raise FileNotFoundError(f"Gemini result not found: {gemini_result_path}. Run step 4 first.")
        
        with open(gemini_result_path, 'r') as f:
            gemini_result = json.load(f)
        
        # Load assessment data for frame metadata
        assessment_path = os.path.join(output_dir, "assessment.json")
        with open(assessment_path, 'r') as f:
            assessment_data = json.load(f)
        
        framerate = assessment_data['framerate']
        
        print(f"  -> Loaded Gemini result: {len(gemini_result['frames'])} frames")
        
        # Create frame records
        print(f"\n📋 Creating FRAMES records...")
        successful = 0
        failed = 0
        
        for frame_data in gemini_result['frames']:
            success, _ = create_frame_record_with_caption(
                token,
                footage_id,
                frame_data,
                assessment_data['frames'],
                framerate
            )
            
            if success:
                successful += 1
            else:
                failed += 1
        
        print(f"  -> Created {successful}/{len(gemini_result['frames'])} frame records")
        
        if failed > 0:
            print(f"  -> ⚠️ {failed} frames failed to create")
        
        # Update parent FOOTAGE record with global metadata
        print(f"\n📝 Updating parent FOOTAGE record...")
        
        global_data = gemini_result['global']
        
        # Build video events CSV
        video_events_csv = build_video_events_csv(gemini_result)
        
        # Format tags
        tags_str = ", ".join(global_data['tags']) if global_data['tags'] else ""
        primary_tag = global_data.get('primary_tag', '')
        
        # Update fields
        field_data = {
            FIELD_MAPPING["description"]: global_data['synopsis'],
            FIELD_MAPPING["date"]: global_data['date'],
            FIELD_MAPPING["location"]: global_data['location'] if global_data['location'] else "",
            FIELD_MAPPING["audio_type"]: global_data['audio_type'],
            FIELD_MAPPING["tags_list"]: tags_str,
            FIELD_MAPPING["primary_bin"]: primary_tag,
            FIELD_MAPPING["video_events"]: video_events_csv
        }
        
        # Add title if field exists
        if "INFO_Title" in footage_data:
            field_data["INFO_Title"] = global_data['title']
        
        update_response = config.update_record(token, "FOOTAGE", record_id, field_data)
        
        if update_response.status_code == 200:
            print(f"  -> ✅ Parent record updated")
            print(f"     Title: {global_data['title']}")
            print(f"     Description: {global_data['synopsis'][:80]}...")
            print(f"     Date: {global_data['date']}")
            print(f"     Location: {global_data['location'] if global_data['location'] else 'Not specified'}")
            print(f"     Audio: {global_data['audio_type']}")
            print(f"     Tags: {tags_str if tags_str else 'None'}")
            print(f"     Primary Tag: {primary_tag if primary_tag else 'None'}")
        else:
            print(f"  -> ❌ Failed to update parent record: {update_response.status_code}")
            raise RuntimeError("Failed to update parent FOOTAGE record")
        
        print(f"\n=== Frame Creation Complete ===")
        print(f"  Frames created: {successful}")
        print(f"  Parent updated: ✅")
        
        print(f"\n✅ Frame records created for {footage_id}")
        print(f"🔄 Ready for Step 6: Audio Transcription (if audio exists)")
        
    except Exception as e:
        print(f"❌ Error creating frame records for {footage_id}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

