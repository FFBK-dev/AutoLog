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
from datetime import datetime
from astral import LocationInfo
from astral.sun import sun

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
    "date_created": "SPECS_DateCreated",
    "time_of_day": "SPECS_TimeOfDay",
    "frame_parent_id": "FRAMES_ParentID",
    "frame_status": "FRAMES_Status",
    "frame_timecode": "FRAMES_TC_IN",
    "frame_id": "FRAMES_ID",
    "frame_caption": "FRAMES_Caption",
    "frame_thumbnail": "FRAMES_Thumbnail",
    "frame_framerate": "FOOTAGE::SPECS_File_Framerate"
}


def get_timezone_offset_from_coordinates(lat, lon):
    """
    Estimate UTC offset based on longitude.
    Approximation for US locations.
    
    Returns:
        Integer UTC offset (e.g., -5 for Eastern Time)
    """
    # Rough timezone estimation based on longitude
    # US timezones: Eastern (-5), Central (-6), Mountain (-7), Pacific (-8)
    if lon > -85:  # Eastern
        return -5
    elif lon > -100:  # Central
        return -6
    elif lon > -115:  # Mountain
        return -7
    else:  # Pacific
        return -8


def calculate_time_of_day(date_created_str, location_str):
    """
    Calculate time-of-day category based on location and timestamp.
    
    Categories based on sunrise/sunset with twilight buffers:
    - Morning: 1 hour before sunrise to 2 hours after sunrise (captures pre-dawn light)
    - Midday: 2 hours after sunrise to 2 hours before sunset
    - Evening: 2 hours before sunset to 1 hour after sunset (captures twilight/blue hour)
    - Night: more than 1 hour after sunset or more than 1 hour before sunrise
    
    Args:
        date_created_str: Timestamp string like "251105 - 06:22" (YYMMDD - HH:MM)
        location_str: Location string from Gemini (e.g., "Savannah, Georgia")
        
    Returns:
        String: "Morning", "Midday", "Evening", or "Night"
    """
    if not date_created_str or not location_str:
        return None
    
    try:
        # Parse the date and time from YYMMDD - HH:MM format
        date_part, time_part = date_created_str.split(' - ')
        
        # Parse date: YYMMDD
        year = int('20' + date_part[0:2])  # 25 -> 2025
        month = int(date_part[2:4])
        day = int(date_part[4:6])
        
        # Parse time: HH:MM (this is in LOCAL time from the camera)
        hour = int(time_part.split(':')[0])
        minute = int(time_part.split(':')[1])
        
        # Create datetime object
        recording_time = datetime(year, month, day, hour, minute)
        recording_hour = hour + (minute / 60.0)  # Local time
        
        # Get coordinates for location
        lat, lon = get_coordinates_from_location(location_str)
        
        # Estimate timezone offset from coordinates
        utc_offset = get_timezone_offset_from_coordinates(lat, lon)
        
        # Create LocationInfo for astral
        location = LocationInfo(
            name=location_str,
            region='',
            timezone='UTC',  # Doesn't matter, we'll handle offset manually
            latitude=lat,
            longitude=lon
        )
        
        # Calculate sun times (returns UTC times)
        s = sun(location.observer, date=recording_time.date())
        sunrise_utc = s['sunrise']
        sunset_utc = s['sunset']
        
        # Convert UTC to local time by applying timezone offset
        sunrise_local_hour = (sunrise_utc.hour + utc_offset) + (sunrise_utc.minute / 60.0)
        sunset_local_hour = (sunset_utc.hour + utc_offset) + (sunset_utc.minute / 60.0)
        
        # Handle day wraparound (e.g., if offset makes it negative or >= 24)
        if sunrise_local_hour < 0:
            sunrise_local_hour += 24
        if sunrise_local_hour >= 24:
            sunrise_local_hour -= 24
        if sunset_local_hour < 0:
            sunset_local_hour += 24
        if sunset_local_hour >= 24:
            sunset_local_hour -= 24
        
        # Calculate the time boundaries with twilight buffers
        morning_start = sunrise_local_hour - 1  # 1 hour before sunrise (pre-dawn)
        morning_end = sunrise_local_hour + 2    # 2 hours after sunrise
        evening_start = sunset_local_hour - 2   # 2 hours before sunset
        evening_end = sunset_local_hour + 1     # 1 hour after sunset (twilight/blue hour)
        
        # Determine category
        if recording_hour < morning_start or recording_hour >= evening_end:
            category = "Night"
        elif recording_hour < morning_end:
            category = "Morning"
        elif recording_hour >= evening_start:
            category = "Evening"
        else:
            category = "Midday"
        
        print(f"  -> Time of day calculation:")
        print(f"     Location: {location_str} (lat: {lat:.2f}, lon: {lon:.2f})")
        print(f"     Timezone: UTC{utc_offset:+d}")
        print(f"     Recording: {hour:02d}:{minute:02d} (local)")
        print(f"     Sunrise: {int(sunrise_local_hour):02d}:{int((sunrise_local_hour % 1) * 60):02d}")
        print(f"     Sunset: {int(sunset_local_hour):02d}:{int((sunset_local_hour % 1) * 60):02d}")
        print(f"     Morning: {int(morning_start):02d}:{int((morning_start % 1) * 60):02d} to {int(morning_end):02d}:{int((morning_end % 1) * 60):02d}")
        print(f"     Evening: {int(evening_start):02d}:{int((evening_start % 1) * 60):02d} to {int(evening_end):02d}:{int((evening_end % 1) * 60):02d}")
        print(f"     Category: {category}")
        
        return category
        
    except Exception as e:
        print(f"  -> Warning: Could not calculate time of day: {e}")
        return None


def get_coordinates_from_location(location_str):
    """
    Extract approximate coordinates from location string.
    Uses simple lookup for common locations, falls back to US mid-latitude.
    
    Returns:
        Tuple of (latitude, longitude)
    """
    if not location_str:
        return (36.0, -86.0)  # Default: Nashville area
    
    location_lower = location_str.lower()
    
    # Simple lookup for common US cities/states
    location_coords = {
        'savannah': (32.08, -81.09),
        'georgia': (32.16, -82.90),
        'nashville': (36.16, -86.78),
        'tennessee': (35.86, -86.66),
        'new york': (40.71, -74.01),
        'los angeles': (34.05, -118.24),
        'chicago': (41.88, -87.63),
        'houston': (29.76, -95.37),
        'philadelphia': (39.95, -75.17),
        'louisiana': (30.98, -91.96),
        'new orleans': (29.95, -90.07),
        'atlanta': (33.75, -84.39),
        'miami': (25.76, -80.19),
        'dallas': (32.78, -96.80),
        'san francisco': (37.77, -122.42),
        'boston': (42.36, -71.06),
        'washington': (38.91, -77.04),
        'seattle': (47.61, -122.33),
        'denver': (39.74, -104.99),
        'mississippi': (32.32, -90.21),
        'alabama': (32.32, -86.90),
        'south carolina': (33.84, -81.16),
        'north carolina': (35.63, -79.81),
        'florida': (27.66, -81.52),
        'texas': (31.05, -97.56),
        'california': (36.12, -119.68),
    }
    
    # Check for matches
    for place, coords in location_coords.items():
        if place in location_lower:
            return coords
    
    # Default to mid-US
    return (36.0, -86.0)  # Nashville area


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
        primary_bin = global_data.get('primary_bin', '')
        
        # Calculate time of day using SPECS_DateCreated and location from Gemini
        time_of_day = None
        date_created = footage_data.get(FIELD_MAPPING["date_created"])
        location = global_data['location'] if global_data['location'] else ""
        
        if date_created and location:
            print(f"\n⏰ Calculating time of day...")
            time_of_day = calculate_time_of_day(date_created, location)
        
        # Update fields
        field_data = {
            FIELD_MAPPING["description"]: global_data['synopsis'],
            FIELD_MAPPING["date"]: global_data['date'],
            FIELD_MAPPING["location"]: location,
            FIELD_MAPPING["audio_type"]: global_data['audio_type'],
            FIELD_MAPPING["tags_list"]: tags_str,
            FIELD_MAPPING["primary_bin"]: primary_bin,
            FIELD_MAPPING["video_events"]: video_events_csv
        }
        
        # Add time of day if calculated
        if time_of_day:
            field_data[FIELD_MAPPING["time_of_day"]] = time_of_day
        
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
            print(f"     Primary Bin: {primary_bin if primary_bin else 'None'}")
            if time_of_day:
                print(f"     Time of Day: {time_of_day}")
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

