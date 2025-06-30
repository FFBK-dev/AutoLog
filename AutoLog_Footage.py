#!/usr/bin/env python3

import os
import json
import requests
import urllib3
import subprocess
import warnings
import time
import openai
import base64
import numpy as np
import whisper
import concurrent.futures
import threading
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

# Suppress SSL warnings
warnings.filterwarnings('ignore')
urllib3.disable_warnings()

# Configuration
CONFIG = {
    'server': os.getenv('FILEMAKER_SERVER', '10.0.222.144'),
    'db_name': 'Emancipation to Exodus',
    'username': os.getenv('FILEMAKER_USERNAME', 'Background'),
    'password': os.getenv('FILEMAKER_PASSWORD', 'july1776'),
    'openai_api_key': os.getenv('OPENAI_API_KEY', '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'),
    'ffmpeg_path': '/opt/homebrew/bin/ffmpeg',
    'tmp_dir': '/private/tmp',
    'layout_keyframes': 'Keyframes',
    'layout_footage': 'Footage',
    'chunk_size': 120,  # For video description processing
    'loop_interval': 30,  # seconds between processing cycles
    'max_workers_thumbnails': 4,  # Parallel thumbnail generation
    'max_workers_captions': 3,    # Parallel caption generation (API rate limited)
    'max_workers_audio': 2,       # Parallel audio transcription (CPU intensive)
    'max_workers_api': 2,         # General API calls
}

# Status definitions
STATUSES = {
    'PENDING': '1 - Pending',
    'THUMBNAIL_CREATED': '2 - Thumbnail Created',
    'CAPTION_GENERATED': '3 - Caption Generated',
    'EMBEDDINGS_READY': '4 - Embeddings Ready',
    'EMBEDDINGS_FUSED': '5 - Embeddings Fused',
    'AUDIO_TRANSCRIBED': '6 - Audio Transcribed',
    'VIDEO_DESCRIPTION_GENERATED': '7 - Video Description Generated',
    'FULLY_PROCESSED': '8 - Fully Processed'
}

# Initialize OpenAI
openai.api_key = CONFIG['openai_api_key']

@dataclass
class ProcessingTask:
    """Data class for processing tasks"""
    record_id: str
    record_data: Dict
    task_type: str

class FileMakerSession:
    """Handles FileMaker authentication and API calls"""
    
    def __init__(self):
        self.server = CONFIG['server']
        self.db_encoded = CONFIG['db_name'].replace(" ", "%20")
        self.username = CONFIG['username']
        self.password = CONFIG['password']
        self.token = None
        self.headers = None
        self._lock = threading.Lock()  # Thread safety for session management
    
    def __enter__(self):
        self.authenticate()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logout()
    
    def authenticate(self):
        """Authenticate with FileMaker"""
        session_url = f"https://{self.server}/fmi/data/vLatest/databases/{self.db_encoded}/sessions"
        auth_response = requests.post(
            session_url,
            auth=(self.username, self.password),
            headers={"Content-Type": "application/json"},
            data="{}",
            verify=False
        )
        
        if auth_response.status_code != 200:
            raise Exception(f"Authentication failed: {auth_response.status_code} {auth_response.text}")
        
        self.token = auth_response.json()["response"]["token"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def logout(self):
        """Logout from FileMaker"""
        if self.token:
            logout_url = f"https://{self.server}/fmi/data/vLatest/databases/{self.db_encoded}/sessions/{self.token}"
            requests.delete(logout_url, headers={"Authorization": f"Bearer {self.token}"}, verify=False)
    
    def find_records(self, layout: str, query: Dict) -> List[Dict]:
        """Find records in FileMaker - Thread safe"""
        with self._lock:
            all_records = []
            offset = 1
            limit = 500  # Process in chunks of 500
            
            while True:
                find_url = f"https://{self.server}/fmi/data/vLatest/databases/{self.db_encoded}/layouts/{layout}/_find"
                find_payload = {
                    "query": [query],
                    "offset": offset,
                    "limit": limit
                }
                
                find_response = requests.post(find_url, headers=self.headers, json=find_payload, verify=False)
                
                if find_response.status_code != 200:
                    break
                
                response_data = find_response.json()
                records = response_data.get("response", {}).get("data", [])
                
                if not records:
                    break
                    
                all_records.extend(records)
                
                # Check if we got less than the limit (meaning no more records)
                if len(records) < limit:
                    break
                    
                offset += len(records)
            
            return all_records
    
    def update_record(self, layout: str, record_id: str, field_data: Dict) -> bool:
        """Update a record in FileMaker - Thread safe"""
        with self._lock:
            update_url = f"https://{self.server}/fmi/data/vLatest/databases/{self.db_encoded}/layouts/{layout}/records/{record_id}"
            update_payload = {"fieldData": field_data}
            update_resp = requests.patch(update_url, headers=self.headers, json=update_payload, verify=False)
            return update_resp.status_code == 200
    
    def upload_container(self, layout: str, record_id: str, field_name: str, file_path: str, filename: str) -> bool:
        """Upload file to container field - Thread safe"""
        with self._lock:
            upload_url = f"https://{self.server}/fmi/data/vLatest/databases/{self.db_encoded}/layouts/{layout}/records/{record_id}/containers/{field_name}/1"
            with open(file_path, "rb") as f:
                files = {"upload": (filename, f, "image/jpeg")}
                upload_resp = requests.post(
                    upload_url, 
                    headers={"Authorization": f"Bearer {self.token}"}, 
                    files=files, 
                    verify=False
                )
            return upload_resp.status_code == 200

class MultiThreadedKeyframeProcessor:
    """Main processor for keyframe pipeline with multithreading"""
    
    def __init__(self):
        self.session = None
        self.whisper_model = None
        self._whisper_lock = threading.Lock()  # Whisper model might not be thread-safe
        
        # Load Whisper model once
        self.whisper_model = whisper.load_model("base")
    
    def debug_records(self):
        """Debug function to see what records exist in each status"""
        # Use our paginated find_records method to get ALL records
        records = self.session.find_records(
            CONFIG['layout_keyframes'],
            {"KeyframeID": "*"}
        )
        
        if not records:
            print("❌ No records found")
            return
        
        # Count records in each status
        status_counts = {status: 0 for status in STATUSES.values()}
        status_counts["NO_STATUS"] = 0
        
        # Track records by status with their IDs
        status_details = {status: [] for status in STATUSES.values()}
        status_details["NO_STATUS"] = []
        
        for record in records:
            field_data = record["fieldData"]
            status = field_data.get("Keyframe_Status", "NO_STATUS")
            keyframe_id = field_data.get("KeyframeID", "UNKNOWN")
            footage_id = field_data.get("FootageID", "UNKNOWN")
            status_counts[status] += 1
            status_details[status].append(f"{keyframe_id} ({footage_id})")
        
        # Print status breakdown
        print("\n📊 Status Breakdown:")
        print(f"Total Records: {len(records)}")
        print("-" * 80)
        
        # Show all statuses in order, even if 0
        for status_key in ["NO_STATUS"] + list(STATUSES.values()):
            count = status_counts[status_key]
            print(f"{status_key}: {count} records")
            
            # For non-zero counts in interesting statuses, show details
            if count > 0 and status_key in [
                STATUSES['PENDING'],
                STATUSES['THUMBNAIL_CREATED'],
                STATUSES['CAPTION_GENERATED'],
                STATUSES['EMBEDDINGS_READY'],
                STATUSES['EMBEDDINGS_FUSED'],
                STATUSES['AUDIO_TRANSCRIBED']
            ]:
                print(f"   🔍 Sample records: {', '.join(status_details[status_key][:5])}")
                if len(status_details[status_key]) > 5:
                    print(f"   ... and {len(status_details[status_key]) - 5} more")
        
        print("-" * 80)
        
        # Alert about potentially stuck records
        for status in [
            STATUSES['PENDING'],
            STATUSES['THUMBNAIL_CREATED'],
            STATUSES['CAPTION_GENERATED'],
            STATUSES['EMBEDDINGS_READY'],
            STATUSES['EMBEDDINGS_FUSED'],
            STATUSES['AUDIO_TRANSCRIBED']
        ]:
            if status_counts[status] > 0:
                print(f"⚠️  Found {status_counts[status]} records potentially stuck in {status}")
                print(f"   First few records: {', '.join(status_details[status][:3])}")
    
    def process_all_stages(self):
        """Process all keyframe stages in sequence based purely on status fields"""
        with FileMakerSession() as session:
            self.session = session
            
            # Quick status overview for monitoring
            self.debug_records()
            
            # Process each stage in order with threading
            self.process_thumbnails_parallel()
            self.process_captions_parallel()
            # Skip embeddings - handled by FileMaker PSOS
            self.process_embedding_fusion_parallel()
            self.process_audio_transcription_parallel()
            self.process_video_descriptions()  # Keep serial for complex logic

    def check_footage_readiness_for_description(self, footage_id: str) -> bool:
        """Check if ALL keyframes for a footage are ready for description generation"""
        try:
            # Get ALL keyframes for this footage
            all_keyframes = self.session.find_records(
                CONFIG['layout_keyframes'],
                {"FootageID": footage_id}
            )
            
            if not all_keyframes:
                return False
            
            # Check if ALL keyframes are at AUDIO_TRANSCRIBED status
            for keyframe in all_keyframes:
                status = keyframe["fieldData"].get("Keyframe_Status")
                if status != STATUSES['AUDIO_TRANSCRIBED']:
                    return False
            
            return True
        except Exception as e:
            print(f"❌ Error checking footage readiness: {e}")
            return False

    def process_video_descriptions(self):
        """Stage 6->7: Generate video descriptions when ALL keyframes are transcribed"""
        try:
            # Get keyframes ready for description processing
            transcribed_records = self.session.find_records(
                CONFIG['layout_keyframes'], 
                {"Keyframe_Status": STATUSES['AUDIO_TRANSCRIBED']}
            )
            
            if not transcribed_records:
                return
            
            # Group by FootageID
            footage_groups = {}
            for record in transcribed_records:
                footage_id = record["fieldData"].get("FootageID")
                if footage_id:
                    if footage_id not in footage_groups:
                        footage_groups[footage_id] = []
                    footage_groups[footage_id].append(record)
            
            # Only process footages where ALL keyframes are ready
            ready_footages = []
            for footage_id, keyframes in footage_groups.items():
                if self.check_footage_readiness_for_description(footage_id):
                    ready_footages.append((footage_id, keyframes))
            
            if not ready_footages:
                print("ℹ️ No footages have all keyframes ready for description generation")
                return
            
            print(f"🎥 Found {len(ready_footages)} footages ready for description generation")
            
            # Process each ready footage
            for footage_id, keyframes in ready_footages:
                try:
                    # Get footage record
                    footage_records = self.session.find_records(
                        CONFIG['layout_footage'],
                        {"INFO_FTG_ID": footage_id}
                    )
                    
                    if not footage_records:
                        continue
                    
                    footage_record = footage_records[0]
                    footage_record_id = footage_record["recordId"]
                    footage_field_data = footage_record["fieldData"]
                    filename = footage_field_data.get("Filename", "")
                    existing_description = footage_field_data.get("INFO_Description", "")
                    
                    print(f"📝 Generating description for {footage_id} ({len(keyframes)} keyframes)")
                    
                    # Generate description
                    title, description, csv_data = self.generate_video_description(
                        [kf["fieldData"] for kf in keyframes],
                        filename,
                        existing_description
                    )
                    
                    if title and description:
                        # Update footage record
                        success = self.session.update_record(
                            CONFIG['layout_footage'],
                            footage_record_id,
                            {
                                "INFO_Title": title,
                                "INFO_Description": description,
                                "INFO_Video_Events": csv_data
                            }
                        )
                        
                        if success:
                            print(f"✅ Description generated for {footage_id}: '{title}'")
                            
                            # Update ALL keyframes to VIDEO_DESCRIPTION_GENERATED
                            updated = 0
                            for keyframe in keyframes:
                                if self.session.update_record(
                                    CONFIG['layout_keyframes'],
                                    keyframe["recordId"],
                                    {"Keyframe_Status": STATUSES['VIDEO_DESCRIPTION_GENERATED']}
                                ):
                                    updated += 1
                            
                            print(f"✅ Updated status for {updated}/{len(keyframes)} keyframes")
                
                except Exception as e:
                    print(f"❌ Error processing {footage_id}: {e}")
                
        except Exception as e:
            print(f"❌ Video description processing error: {e}")

    def manual_sync_footage_keyframes(self, footage_id: str, target_status: str):
        """
        Manual synchronization function that users can trigger from FileMaker
        This could be called via a script parameter if needed
        """
        try:
            keyframes = self.session.find_records(
                CONFIG['layout_keyframes'],
                {"FootageID": footage_id}
            )
            
            updated = 0
            for keyframe in keyframes:
                if self.session.update_record(
                    CONFIG['layout_keyframes'],
                    keyframe["recordId"],
                    {"Keyframe_Status": target_status}
                ):
                    updated += 1
            
            print(f"✅ Manually synchronized {updated} keyframes for {footage_id} to {target_status}")
            return updated
            
        except Exception as e:
            print(f"❌ Manual sync error: {e}")
            return 0

    def process_thumbnails_parallel(self):
        """Stage 1->2: Generate thumbnails for pending keyframes in parallel"""
        records = self.session.find_records(
            CONFIG['layout_keyframes'], 
            {"Keyframe_Status": STATUSES['PENDING']}
        )
        
        if not records:
            return
        
        # Add debug logging
        if records:
            print("\n🔍 DEBUG: First keyframe record data:")
            print(json.dumps(records[0], indent=2))
            print("\n")
        
        # Create tasks for parallel processing
        tasks = []
        for record in records:
            field_data = record["fieldData"]
            keyframe_id = field_data.get("KeyframeID")
            timecode = field_data.get("TC_IN_Seconds")
            footage_id = field_data.get("FootageID")
            
            if not all([keyframe_id, timecode, footage_id]):
                print(f"⚠️ Skipping {keyframe_id} - Missing required fields:")
                if not keyframe_id: print("   - Missing KeyframeID")
                if not timecode: print("   - Missing TC_IN_Seconds")
                if not footage_id: print("   - Missing footage ID")
                continue
                
            tasks.append(ProcessingTask(
                record_id=record["recordId"],
                record_data={
                    'keyframe_id': keyframe_id,
                    'timecode': timecode,
                    'footage_id': footage_id
                },
                task_type='thumbnail'
            ))
        
        if not tasks:
            return
        
        # Process thumbnails in parallel
        print(f"🎬 Processing {len(tasks)} thumbnails...")
        successful = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG['max_workers_thumbnails']) as executor:
            future_to_task = {executor.submit(self.process_single_thumbnail, task): task for task in tasks}
            
            for future in concurrent.futures.as_completed(future_to_task):
                try:
                    result = future.result()
                    if result['success']:
                        successful += 1
                except Exception:
                    pass  # Silently handle errors
        
        print(f"✅ Thumbnails: {successful}/{len(tasks)} completed")
    
    def process_single_thumbnail(self, task: ProcessingTask) -> Dict:
        """Process a single thumbnail generation task"""
        try:
            record_id = task.record_id
            keyframe_id = task.record_data['keyframe_id']
            timecode = task.record_data['timecode']
            footage_id = task.record_data['footage_id']
            
            # Look up footage record to get filepath
            footage_records = self.session.find_records(
                CONFIG['layout_footage'],
                {"INFO_FTG_ID": footage_id}
            )
            
            if not footage_records:
                return {'success': False, 'error': f'Could not find footage record for {footage_id}'}
                
            video_path = footage_records[0]["fieldData"].get("SPECS_Filepath_Server")
            
            if not video_path:
                return {'success': False, 'error': f'No filepath found for footage {footage_id}'}
            
            # Check if video file exists and is accessible
            if not os.path.exists(video_path):
                return {'success': False, 'error': f'Video file not found: {video_path}'}
            
            try:
                with open(video_path, 'rb') as f:
                    f.read(1)  # Try to read one byte
            except (OSError, IOError) as e:
                return {'success': False, 'error': f'Video file not accessible: {e}'}
            
            # Generate thumbnail
            thumb_filename = f"thumbnail_{keyframe_id}.jpg"
            thumb_path = os.path.join(CONFIG['tmp_dir'], thumb_filename)
            
            ffmpeg_cmd = [
                CONFIG['ffmpeg_path'], "-y", "-ss", timecode,
                "-i", video_path, "-frames:v", "1", thumb_path,
                "-loglevel", "quiet"  # Suppress FFmpeg output
            ]
            
            result = subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
            
            # Check if thumbnail was created
            if not os.path.exists(thumb_path):
                return {'success': False, 'error': f'Thumbnail file not created at {thumb_path}'}
            
            # Upload thumbnail
            success = self.session.upload_container(
                CONFIG['layout_keyframes'], record_id, "Thumbnail", thumb_path, thumb_filename
            )
            
            if success:
                # Update status
                update_success = self.session.update_record(
                    CONFIG['layout_keyframes'], record_id,
                    {"Keyframe_Status": STATUSES['THUMBNAIL_CREATED']}
                )
                
                # Cleanup
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
                
                if update_success:
                    return {'success': True}
                else:
                    return {'success': False, 'error': 'Failed to update status'}
            else:
                # Cleanup on failure
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
                return {'success': False, 'error': 'Failed to upload thumbnail'}
                
        except subprocess.CalledProcessError as e:
            return {'success': False, 'error': f'FFmpeg error'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def process_captions_parallel(self):
        """Stage 2->3: Generate captions for thumbnails in parallel"""
        records = self.session.find_records(
            CONFIG['layout_keyframes'], 
            {"Keyframe_Status": STATUSES['THUMBNAIL_CREATED']}
        )
        
        if not records:
            return
        
        # Create tasks
        tasks = []
        for record in records:
            field_data = record["fieldData"]
            keyframe_id = field_data.get("KeyframeID")
            footage_id = field_data.get("FootageID")
            timecode = field_data.get("TC_IN_Seconds")
            video_path = field_data.get("Footage::SPECS_Filepath_Server")
            
            if not all([keyframe_id, timecode, video_path]):
                print(f"⚠️ Skipping {keyframe_id} - Missing required fields:")
                if not keyframe_id: print("   - Missing KeyframeID")
                if not timecode: print("   - Missing TC_IN_Seconds")
                if not video_path: print("   - Missing video path")
                continue
                
            tasks.append(ProcessingTask(
                record_id=record["recordId"],
                record_data={
                    'keyframe_id': keyframe_id,
                    'footage_id': footage_id,
                    'timecode': timecode,
                    'video_path': video_path
                },
                task_type='caption'
            ))
        
        if not tasks:
            return
        
        # Process captions in parallel
        print(f"📝 Processing {len(tasks)} captions...")
        successful = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG['max_workers_captions']) as executor:
            future_to_task = {executor.submit(self.process_single_caption, task): task for task in tasks}
            
            for future in concurrent.futures.as_completed(future_to_task):
                try:
                    result = future.result()
                    if result['success']:
                        successful += 1
                except Exception:
                    pass
        
        print(f"✅ Captions: {successful}/{len(tasks)} completed")
    
    def process_single_caption(self, task: ProcessingTask) -> Dict:
        """Process a single caption generation task"""
        try:
            record_id = task.record_id
            keyframe_id = task.record_data['keyframe_id']
            footage_id = task.record_data['footage_id']
            timecode = task.record_data['timecode']
            video_path = task.record_data['video_path']
            
            gpt_prompt = (
                "You are generating brief visual descriptions for frames from historical footage. "
                "Keep it concise, under 65 tokens is crucial for further embedding gneeration. "
                " Avoid phrases like 'this image shows'. "
                "Just describe: people, setting, action, objects, and approximate shot type."
            )
            
            # Get footage context
            footage_records = self.session.find_records(
                CONFIG['layout_footage'], 
                {"INFO_FTG_ID": footage_id}
            )
            
            filename_context = ""
            description_context = ""
            if footage_records:
                footage_fields = footage_records[0]["fieldData"]
                filename_context = footage_fields.get("INFO_Original_FileName", "")
                description_context = footage_fields.get("INFO_Description", "")
            
            # Generate thumbnail for captioning
            thumb_path = os.path.join(CONFIG['tmp_dir'], f"caption_{keyframe_id}.jpg")
            ffmpeg_cmd = [
                CONFIG['ffmpeg_path'], "-y", "-ss", timecode,
                "-i", video_path, "-frames:v", "1", thumb_path,
                "-loglevel", "quiet"  # Suppress FFmpeg output
            ]
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
            
            # Get caption from OpenAI
            with open(thumb_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")
            
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": gpt_prompt},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"""Filename: {filename_context}
Existing description: {description_context}
Generate keyframe description:"""
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                            }
                        ]
                    }
                ]
            )
            
            caption = response.choices[0].message.content.strip()
            caption_clean = self.remove_markdown(caption)
            
            # Update record
            success = self.session.update_record(
                CONFIG['layout_keyframes'], record_id,
                {
                    "Keyframe_GPT_Caption": caption_clean,
                    "Keyframe_Status": STATUSES['CAPTION_GENERATED']
                }
            )
            
            # Cleanup
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
            
            if success:
                return {'success': True, 'caption': caption_clean}
            else:
                return {'success': False, 'error': 'Failed to update record'}
                
        except Exception as e:
            # Cleanup on error
            thumb_path = os.path.join(CONFIG['tmp_dir'], f"caption_{task.record_data['keyframe_id']}.jpg")
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
            return {'success': False, 'error': str(e)}
    
    def process_embedding_fusion_parallel(self):
        """Stage 4->5: Fuse embeddings (after FileMaker generates them) in parallel"""
        records = self.session.find_records(
            CONFIG['layout_keyframes'], 
            {"Keyframe_Status": STATUSES['EMBEDDINGS_READY']}
        )
        
        if not records:
            return
        
        # Create tasks
        tasks = []
        for record in records:
            tasks.append(ProcessingTask(
                record_id=record["recordId"],
                record_data=record["fieldData"],
                task_type='fusion'
            ))
        
        if not tasks:
            return
            
        # Process fusion in parallel
        print(f"🔗 Processing {len(tasks)} new fusions...")
        successful = 0
        failed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG['max_workers_api']) as executor:
            futures = [executor.submit(self.process_single_fusion, task) for task in tasks]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    if result['success']:
                        successful += 1
                    else:
                        failed += 1
                        print(f"❌ Fusion failed: {result.get('error', 'Unknown error')}")
                except Exception as e:
                    failed += 1
                    print(f"❌ Fusion error: {str(e)}")
        
        print(f"✅ Fusions: {successful}/{len(tasks)} completed, {failed} failed")
    
    def process_single_fusion(self, task: ProcessingTask) -> Dict:
        """Process a single embedding fusion task"""
        try:
            record_id = task.record_id
            field_data = task.record_data
            keyframe_id = field_data.get("KeyframeID")
            
            # Get raw embedding strings
            text_embedding_str = field_data.get("Keyframe_Text_Embedding", "")
            image_embedding_str = field_data.get("Keyframe_Image_Embedding", "")
            
            # Validate embeddings exist
            if not text_embedding_str or not image_embedding_str:
                print(f"⚠️ Missing embeddings for keyframe {keyframe_id}")
                return {'success': False, 'error': f'Missing embeddings for {keyframe_id}'}
            
            # Try to parse embeddings
            try:
                text_embedding = json.loads(text_embedding_str)
                image_embedding = json.loads(image_embedding_str)
            except json.JSONDecodeError as e:
                print(f"⚠️ Invalid embedding format for keyframe {keyframe_id}: {str(e)}")
                return {'success': False, 'error': f'Invalid embedding format: {str(e)}'}
            
            if not text_embedding or not image_embedding:
                return {'success': False, 'error': f'Empty embeddings for {keyframe_id}'}
            
            text_array = np.array(text_embedding, dtype=np.float32)
            image_array = np.array(image_embedding, dtype=np.float32)
            
            if text_array.shape != image_array.shape:
                return {'success': False, 'error': f'Shape mismatch for {keyframe_id}'}
            
            # Fuse embeddings (simple average)
            fused_array = 0.5 * text_array + 0.5 * image_array
            fused_array /= np.linalg.norm(fused_array)
            fused_json = json.dumps(fused_array.tolist())
            
            # Update record
            success = self.session.update_record(
                CONFIG['layout_keyframes'], record_id,
                {
                    "Keyframe_Fused_Embedding": fused_json,
                    "Keyframe_Status": STATUSES['EMBEDDINGS_FUSED']
                }
            )
            
            if success:
                print(f"✅ Fusion completed for keyframe {keyframe_id}")
                return {'success': True}
            else:
                return {'success': False, 'error': 'Failed to update record'}
                
        except Exception as e:
            print(f"❌ Unexpected error in fusion for keyframe {keyframe_id}: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def process_audio_transcription_parallel(self):
        """Stage 5->6: Transcribe audio for keyframes in parallel"""
        records = self.session.find_records(
            CONFIG['layout_keyframes'], 
            {"Keyframe_Status": STATUSES['EMBEDDINGS_FUSED']}
        )
        
        if not records:
            return
        
        # Create tasks
        tasks = []
        for record in records:
            field_data = record["fieldData"]
            keyframe_id = field_data.get("KeyframeID")
            timecode = field_data.get("TC_IN_Seconds")
            footage_id = field_data.get("FootageID")
            
            if not all([keyframe_id, timecode, footage_id]):
                print(f"⚠️ Skipping {keyframe_id} - Missing required fields:")
                if not keyframe_id: print("   - Missing KeyframeID")
                if not timecode: print("   - Missing TC_IN_Seconds")
                if not footage_id: print("   - Missing footage ID")
                continue
                
            tasks.append(ProcessingTask(
                record_id=record["recordId"],
                record_data={
                    'keyframe_id': keyframe_id,
                    'timecode': timecode,
                    'footage_id': footage_id
                },
                task_type='audio'
            ))
        
        if not tasks:
            return
        
        # Process audio in parallel
        print(f"🎵 Processing {len(tasks)} new audio transcriptions...")
        successful = 0
        failed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG['max_workers_audio']) as executor:
            futures = [executor.submit(self.process_single_audio, task) for task in tasks]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    if result['success']:
                        successful += 1
                    else:
                        failed += 1
                        print(f"❌ Audio failed: {result.get('error', 'Unknown error')}")
                except Exception as e:
                    failed += 1
                    print(f"❌ Audio error: {str(e)}")
        
        print(f"✅ Audio: {successful}/{len(tasks)} completed, {failed} failed")
    
    def process_single_audio(self, task: ProcessingTask) -> Dict:
        """Process a single audio transcription task"""
        audio_path = None
        try:
            record_id = task.record_id
            keyframe_id = task.record_data['keyframe_id']
            timecode = task.record_data['timecode']
            footage_id = task.record_data['footage_id']
            
            # Look up footage record to get filepath
            footage_records = self.session.find_records(
                CONFIG['layout_footage'],
                {"INFO_FTG_ID": footage_id}
            )
            
            if not footage_records:
                print(f"⚠️ Could not find footage record for keyframe {keyframe_id}")
                return {'success': False, 'error': f'Could not find footage record for {footage_id}'}
                
            video_path = footage_records[0]["fieldData"].get("SPECS_Filepath_Server")
            
            if not video_path:
                print(f"⚠️ No filepath found for footage {footage_id}")
                return {'success': False, 'error': f'No filepath found for footage {footage_id}'}
            
            # Check if video file exists and is accessible
            if not os.path.exists(video_path):
                print(f"⚠️ Video file not found for keyframe {keyframe_id}: {video_path}")
                return {'success': False, 'error': 'Video file not found'}
            
            try:
                with open(video_path, 'rb') as f:
                    f.read(1)  # Try to read one byte to verify access
            except (OSError, IOError) as e:
                print(f"⚠️ Cannot access video file for keyframe {keyframe_id}: {str(e)}")
                return {'success': False, 'error': f'Cannot access video file: {str(e)}'}
            
            # First check if video has audio streams
            probe_cmd = [
                CONFIG['ffmpeg_path'],
                "-i", video_path
            ]
            
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
            has_audio = "Audio:" in probe_result.stderr
            
            if not has_audio:
                print(f"ℹ️ No audio stream found in video for keyframe {keyframe_id}")
                # Update record to mark as processed since there's no audio to process
                success = self.session.update_record(
                    CONFIG['layout_keyframes'], record_id,
                    {
                        "Keyframe_Transcript": "",
                        "Keyframe_Status": STATUSES['AUDIO_TRANSCRIBED']
                    }
                )
                return {'success': True, 'transcript': ""}
            
            # Extract audio segment
            audio_path = os.path.join(CONFIG['tmp_dir'], f"{keyframe_id}_audio.wav")
            
            # Add error output to ffmpeg for debugging
            ffmpeg_cmd = [
                CONFIG['ffmpeg_path'], "-y", 
                "-ss", timecode, 
                "-i", video_path,
                "-t", "5", 
                "-vn", 
                "-acodec", "pcm_s16le", 
                "-ar", "16000", 
                "-ac", "1", 
                audio_path
            ]
            
            try:
                result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
            except subprocess.CalledProcessError as e:
                print(f"⚠️ FFmpeg error for keyframe {keyframe_id}:")
                print(f"Command: {' '.join(ffmpeg_cmd)}")
                print(f"Error output: {e.stderr}")
                return {'success': False, 'error': f'FFmpeg error: {e.stderr}'}
            
            # Check if audio was extracted
            if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                print(f"⚠️ No audio extracted for keyframe {keyframe_id}")
                return {'success': False, 'error': 'No audio extracted'}
            
            # Check for silence
            silent = self.check_audio_silence(audio_path)
            transcript = ""
            
            if not silent:
                # Transcribe with Whisper (thread-safe)
                with self._whisper_lock:
                    result = self.whisper_model.transcribe(audio_path, language="en")
                    transcript = result.get("text", "").strip()
            
            # Update record
            success = self.session.update_record(
                CONFIG['layout_keyframes'], record_id,
                {
                    "Keyframe_Transcript": transcript,
                    "Keyframe_Status": STATUSES['AUDIO_TRANSCRIBED']
                }
            )
            
            # Cleanup
            if os.path.exists(audio_path):
                os.remove(audio_path)
            
            if success:
                print(f"✅ Audio transcribed for keyframe {keyframe_id}")
                return {'success': True, 'transcript': transcript}
            else:
                return {'success': False, 'error': 'Failed to update record'}
                
        except Exception as e:
            print(f"❌ Unexpected error in audio processing for keyframe {task.record_data['keyframe_id']}: {str(e)}")
            # Cleanup on error
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
            return {'success': False, 'error': str(e)}
    
    def generate_video_description(self, keyframes: List[Dict], filename: str, existing_description: str) -> Tuple[str, str, str]:
        """Generate comprehensive video description from keyframes"""
        try:
            # Sort keyframes
            keyframes_sorted = sorted(keyframes, key=lambda x: x.get("KeyframeID", ""))
            
            # Analyze content
            total_keyframes = len(keyframes_sorted)
            keyframes_with_audio = sum(1 for kf in keyframes_sorted if kf.get("Keyframe_Transcript", "").strip())
            keyframes_with_visuals = sum(1 for kf in keyframes_sorted if kf.get("Keyframe_GPT_Caption", "").strip())
            
            if keyframes_with_visuals == 0:
                return "No Visual Content", "This video appears to lack visual content data.", ""
            
            # Build CSV data
            full_csv_lines = ["Frame,Visual Description,Audio Transcript"]
            for kf in keyframes_sorted:
                desc = kf.get("Keyframe_GPT_Caption", "").replace("\n", " ").strip()
                trans = kf.get("Keyframe_Transcript", "").replace("\n", " ").strip()
                frame_id = kf.get("KeyframeID", "")
                full_csv_lines.append(f"{frame_id},{desc},{trans}")
            
            csv_data = "\n".join(full_csv_lines)
            
            # Check if it's a silent video
            is_silent = keyframes_with_audio == 0
            
            # Prepare the OpenAI request
            system_prompt = (
                "You are generating catalog metadata for a video file. "
                "The input provides frame-level visual descriptions and audio transcripts. "
                "Empty audio transcripts indicate silent video - this is normal. "
                "Focus on the visual content to create meaningful catalog metadata. "
                "Provide your response in exactly this format:\n"
                "Title: [A concise, descriptive title for the video]\n"
                "Description: [A thorough catalog description of the video content]\n\n"
                "Do not include any other text, prefixes, or formatting. "
                "Do not mention 'missing content' or 'file integrity issues' for silent videos. "
                "The title should be 3-8 words. The description should be 2-4 sentences."
            )
            
            # Prepare context note
            silent_note = "[SILENT VIDEO - NO AUDIO]" if is_silent else ""
            
            user_prompt = f"""Filename: {filename}
Existing description: {existing_description}
{silent_note}

Frame-level data:
{csv_data}"""
            
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            final_response = response.choices[0].message.content.strip()
            
            # Parse title and description
            title, description = self.parse_title_description(final_response)
            
            return title, description, csv_data
            
        except Exception as e:
            print(f"❌ Description generation error: {e}")
            return "", "", ""
    
    def parse_title_description(self, response_text: str) -> Tuple[str, str]:
        """Parse title and description from API response"""
        title = ""
        description = ""
        
        try:
            lines = response_text.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if line.lower().startswith('title:'):
                    title = line[6:].strip()
                elif line.lower().startswith('description:'):
                    description = line[12:].strip()
                elif not title and not line.lower().startswith('description:'):
                    title = line
                elif title and not description:
                    description = line
            
            # Fallback parsing
            if not title and not description:
                parts = response_text.strip().split('\n', 1)
                if len(parts) >= 2:
                    title = parts[0].strip()
                    description = parts[1].strip()
                else:
                    description = response_text.strip()
                    title = "Untitled Video"
            
            # Clean up prefixes
            title = title.replace('Title:', '').replace('title:', '').strip()
            description = description.replace('Description:', '').replace('description:', '').strip()
            
            # Ensure we have something
            if not title:
                title = "Untitled Video"
            if not description:
                description = "No description available"
                
        except Exception:
            title = "Untitled Video"
            description = response_text.strip() if response_text.strip() else "No description available"
        
        return title, description
    
    def check_audio_silence(self, audio_path: str) -> bool:
        """Check if audio file is mostly silent"""
        try:
            result = subprocess.run(
                [CONFIG['ffmpeg_path'], "-i", audio_path, "-af", "volumedetect", 
                 "-f", "null", "-", "-loglevel", "quiet"],
                stderr=subprocess.PIPE, text=True, capture_output=True
            )
            
            vol_output = result.stderr
            mean_volume_line = next((line for line in vol_output.splitlines() if "mean_volume:" in line), None)
            
            if mean_volume_line:
                mean_volume_db = float(mean_volume_line.split("mean_volume:")[1].split(" dB")[0].strip())
                return mean_volume_db < -50  # Consider silence if below -50dB
            
        except Exception:
            pass  # Silently handle errors
        
        return False
    
    def remove_markdown(self, text: str) -> str:
        """Remove simple markdown formatting"""
        return text.replace("*", "").replace("-", "").replace("_", "").strip()

def main():
    """Main processing loop"""
    processor = MultiThreadedKeyframeProcessor()
    
    print("🚀 Starting Multithreaded Keyframe Processor")
    print(f"🧵 Thread config: {CONFIG['max_workers_thumbnails']} thumb | {CONFIG['max_workers_captions']} caption | {CONFIG['max_workers_audio']} audio")
    
    while True:
        print(f"\n🔄 Processing cycle: {time.strftime('%H:%M:%S')}")
        
        try:
            processor.process_all_stages()
            print("✅ Cycle completed")
            
        except Exception as e:
            print(f"❌ Cycle error: {e}")
        
        print(f"⏳ Sleeping {CONFIG['loop_interval']}s...")
        time.sleep(CONFIG['loop_interval'])

if __name__ == "__main__":
    main()