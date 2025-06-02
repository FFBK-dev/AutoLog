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
from typing import Dict, List, Optional, Tuple

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
    'loop_interval': 30  # seconds between processing cycles
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

# Initialize OpenAI and Whisper
openai.api_key = CONFIG['openai_api_key']
whisper_model = whisper.load_model("base")

class FileMakerSession:
    """Handles FileMaker authentication and API calls"""
    
    def __init__(self):
        self.server = CONFIG['server']
        self.db_encoded = CONFIG['db_name'].replace(" ", "%20")
        self.username = CONFIG['username']
        self.password = CONFIG['password']
        self.token = None
        self.headers = None
    
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
        """Find records in FileMaker"""
        find_url = f"https://{self.server}/fmi/data/vLatest/databases/{self.db_encoded}/layouts/{layout}/_find"
        find_response = requests.post(find_url, headers=self.headers, json={"query": [query]}, verify=False)
        
        if find_response.status_code != 200:
            print(f"❌ Find failed: {find_response.status_code} {find_response.text}")
            return []
        
        return find_response.json().get("response", {}).get("data", [])
    
    def update_record(self, layout: str, record_id: str, field_data: Dict) -> bool:
        """Update a record in FileMaker"""
        update_url = f"https://{self.server}/fmi/data/vLatest/databases/{self.db_encoded}/layouts/{layout}/records/{record_id}"
        update_payload = {"fieldData": field_data}
        update_resp = requests.patch(update_url, headers=self.headers, json=update_payload, verify=False)
        return update_resp.status_code == 200
    
    def upload_container(self, layout: str, record_id: str, field_name: str, file_path: str, filename: str) -> bool:
        """Upload file to container field"""
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

class KeyframeProcessor:
    """Main processor for keyframe pipeline"""
    
    def __init__(self):
        self.session = None
    
    def debug_records(self):
        """Debug function to see what records exist"""
        print("🔍 DEBUG: Checking all keyframe records...")
        
        # Find ALL keyframes by searching for any non-empty KeyframeID
        query_payload = {"query": [{"KeyframeID": "*"}]}
        find_response = requests.post(
            f"https://{self.session.server}/fmi/data/vLatest/databases/{self.session.db_encoded}/layouts/{CONFIG['layout_keyframes']}/_find",
            headers=self.session.headers, 
            json=query_payload,
            verify=False
        )
        
        if find_response.status_code != 200:
            print(f"❌ Debug find failed: {find_response.status_code} {find_response.text}")
            return
        
        records = find_response.json().get("response", {}).get("data", [])
        print(f"📊 Total keyframe records found: {len(records)}")
        
        status_counts = {}
        for record in records[:10]:  # Show first 10 records
            field_data = record["fieldData"]
            status = field_data.get("Keyframe_Status", "NO_STATUS")
            keyframe_id = field_data.get("KeyframeID", "NO_ID")
            
            status_counts[status] = status_counts.get(status, 0) + 1
            
            print(f"  Record {record['recordId']}: {keyframe_id} - Status: '{status}'")
            print(f"    Fields available: {list(field_data.keys())}")
        
        print(f"\n📈 Status summary:")
        for status, count in status_counts.items():
            print(f"  '{status}': {count} records")
    
    def process_all_stages(self):
        """Process all keyframe stages in sequence"""
        with FileMakerSession() as session:
            self.session = session
            
            # Add debug info
            self.debug_records()
            
            # Process each stage in order
            self.process_thumbnails()
            self.process_captions()
            # Skip embeddings - handled by FileMaker PSOS
            self.process_embedding_fusion()
            self.process_audio_transcription()
            self.process_video_descriptions()
    
    def process_thumbnails(self):
        """Stage 1->2: Generate thumbnails for pending keyframes"""
        print("🖼️ Processing thumbnails...")
        records = self.session.find_records(
            CONFIG['layout_keyframes'], 
            {"Keyframe_Status": STATUSES['PENDING']}
        )
        
        if not records:
            print("✅ No pending keyframes found for thumbnail generation")
            return
        
        print(f"📋 Found {len(records)} pending keyframes")
        
        for record in records:
            try:
                record_id = record["recordId"]
                field_data = record["fieldData"]
                keyframe_id = field_data.get("KeyframeID")
                timecode = field_data.get("Timecode_IN")
                video_path = field_data.get("Footage::SPECS_Filepath_Server")
                
                print(f"🔍 Processing keyframe {keyframe_id}")
                print(f"   Timecode: {timecode}")
                print(f"   Video path: {video_path}")
                
                if not all([keyframe_id, timecode, video_path]):
                    print(f"⚠️ Missing thumbnail data for record {record_id}")
                    print(f"   KeyframeID: {keyframe_id}")
                    print(f"   Timecode: {timecode}")
                    print(f"   Video path: {video_path}")
                    continue
                
                # Generate thumbnail
                thumb_filename = f"thumbnail_{keyframe_id}.jpg"
                thumb_path = os.path.join(CONFIG['tmp_dir'], thumb_filename)
                
                ffmpeg_cmd = [
                    CONFIG['ffmpeg_path'], "-y", "-ss", timecode,
                    "-i", video_path, "-frames:v", "1", thumb_path
                ]
                
                print(f"🎬 Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
                result = subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
                print(f"✅ FFmpeg completed successfully")
                
                # Check if thumbnail was created
                if not os.path.exists(thumb_path):
                    print(f"❌ Thumbnail file not created at {thumb_path}")
                    continue
                
                print(f"📁 Thumbnail created at {thumb_path}")
                
                # Upload thumbnail
                success = self.session.upload_container(
                    CONFIG['layout_keyframes'], record_id, "Thumbnail", thumb_path, thumb_filename
                )
                
                if success:
                    print(f"📤 Thumbnail uploaded successfully")
                    # Update status
                    update_success = self.session.update_record(
                        CONFIG['layout_keyframes'], record_id,
                        {"Keyframe_Status": STATUSES['THUMBNAIL_CREATED']}
                    )
                    if update_success:
                        print(f"✅ Thumbnail created and status updated for {keyframe_id}")
                    else:
                        print(f"❌ Failed to update status for {keyframe_id}")
                else:
                    print(f"❌ Failed to upload thumbnail for {keyframe_id}")
                
                # Cleanup
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
                    print(f"🗑️ Cleaned up temporary file")
                    
            except subprocess.CalledProcessError as e:
                print(f"❌ FFmpeg error for {keyframe_id}: {e}")
                print(f"   stdout: {e.stdout}")
                print(f"   stderr: {e.stderr}")
            except Exception as e:
                print(f"❌ Thumbnail error for {record_id}: {e}")
                import traceback
                print(f"   Full traceback: {traceback.format_exc()}")
    
    def process_captions(self):
        """Stage 2->3: Generate captions for thumbnails"""
        print("📝 Processing captions...")
        records = self.session.find_records(
            CONFIG['layout_keyframes'], 
            {"Keyframe_Status": STATUSES['THUMBNAIL_CREATED']}
        )
        
        gpt_prompt = (
            "You are generating brief visual descriptions for frames from historical footage. "
            "Keep it concise, under 70 tokens. Avoid phrases like 'this image shows'. "
            "Just describe: people, setting, action, objects, and approximate shot type."
        )
        
        for record in records:
            try:
                record_id = record["recordId"]
                field_data = record["fieldData"]
                keyframe_id = field_data.get("KeyframeID")
                footage_id = field_data.get("FootageID")
                timecode = field_data.get("Timecode_IN")
                video_path = field_data.get("Footage::SPECS_Filepath_Server")
                
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
                    "-i", video_path, "-frames:v", "1", thumb_path
                ]
                subprocess.run(ffmpeg_cmd, check=True)
                
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
                
                if success:
                    print(f"✅ Caption generated for {keyframe_id}: {caption_clean}")
                
                # Cleanup
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
                    
            except Exception as e:
                print(f"❌ Caption error for {record_id}: {e}")
    
    def process_embedding_fusion(self):
        """Stage 4->5: Fuse embeddings (after FileMaker generates them)"""
        print("🔗 Processing embedding fusion...")
        records = self.session.find_records(
            CONFIG['layout_keyframes'], 
            {"Keyframe_Status": STATUSES['EMBEDDINGS_READY']}
        )
        
        for record in records:
            try:
                record_id = record["recordId"]
                field_data = record["fieldData"]
                keyframe_id = field_data.get("KeyframeID")
                
                # Parse embeddings
                text_embedding = json.loads(field_data.get("Keyframe_Text_Embedding", "[]"))
                image_embedding = json.loads(field_data.get("Keyframe_Image_Embedding", "[]"))
                
                if not text_embedding or not image_embedding:
                    print(f"⚠️ Missing embeddings for {keyframe_id}")
                    continue
                
                text_array = np.array(text_embedding, dtype=np.float32)
                image_array = np.array(image_embedding, dtype=np.float32)
                
                if text_array.shape != image_array.shape:
                    print(f"⚠️ Shape mismatch for {keyframe_id}")
                    continue
                
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
                    print(f"✅ Embeddings fused for {keyframe_id}")
                    
            except Exception as e:
                print(f"❌ Fusion error for {record_id}: {e}")
    
    def process_audio_transcription(self):
        """Stage 5->6: Transcribe audio for keyframes"""
        print("🎵 Processing audio transcription...")
        records = self.session.find_records(
            CONFIG['layout_keyframes'], 
            {"Keyframe_Status": STATUSES['EMBEDDINGS_FUSED']}
        )
        
        for record in records:
            try:
                record_id = record["recordId"]
                field_data = record["fieldData"]
                keyframe_id = field_data.get("KeyframeID")
                timecode = field_data.get("Timecode_IN")
                video_path = field_data.get("Footage::SPECS_Filepath_Server")
                
                if not all([keyframe_id, timecode, video_path]):
                    print(f"⚠️ Missing audio data for {keyframe_id}")
                    continue
                
                # Extract audio segment
                audio_path = os.path.join(CONFIG['tmp_dir'], f"{keyframe_id}_audio.wav")
                ffmpeg_cmd = [
                    CONFIG['ffmpeg_path'], "-y", "-ss", timecode, "-i", video_path,
                    "-t", "5", "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_path
                ]
                subprocess.run(ffmpeg_cmd, check=True)
                
                # Check for silence
                silent = self.check_audio_silence(audio_path)
                transcript = ""
                
                if not silent:
                    # Transcribe with Whisper
                    result = whisper_model.transcribe(audio_path, language="en")
                    transcript = result.get("text", "").strip()
                    print(f"📝 Transcript for {keyframe_id}: {transcript}")
                else:
                    print(f"🔇 Silent audio detected for {keyframe_id}")
                
                # Update record
                success = self.session.update_record(
                    CONFIG['layout_keyframes'], record_id,
                    {
                        "Keyframe_Transcript": transcript,
                        "Keyframe_Status": STATUSES['AUDIO_TRANSCRIBED']
                    }
                )
                
                if success:
                    print(f"✅ Audio transcribed for {keyframe_id}")
                
                # Cleanup
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                    
            except Exception as e:
                print(f"❌ Audio transcription error for {record_id}: {e}")
    
    def process_video_descriptions(self):
        """Stage 6->7: Generate video descriptions when all keyframes are transcribed"""
        print("📄 Processing video descriptions...")
        
        try:
            # Find all footage with transcribed keyframes
            print("🔍 Step 1: Finding transcribed keyframes...")
            transcribed_records = self.session.find_records(
                CONFIG['layout_keyframes'], 
                {"Keyframe_Status": STATUSES['AUDIO_TRANSCRIBED']}
            )
            print(f"📊 Found {len(transcribed_records)} transcribed keyframes")
            
            # Group by FootageID
            print("🔍 Step 2: Grouping by FootageID...")
            footage_map = {}
            for record in transcribed_records:
                field_data = record["fieldData"]
                footage_id = field_data.get("FootageID")
                if footage_id:
                    footage_map.setdefault(footage_id, []).append(field_data)
            
            print(f"📊 Found footage IDs: {list(footage_map.keys())}")
            
            for footage_id, keyframes in footage_map.items():
                print(f"\n🎯 Processing footage: {footage_id}")
                try:
                    # Check if ALL keyframes for this footage are transcribed
                    print(f"🔍 Step 3: Checking if all keyframes are transcribed for {footage_id}...")
                    all_keyframes = self.session.find_records(
                        CONFIG['layout_keyframes'], 
                        {"FootageID": footage_id}
                    )
                    
                    total_count = len(all_keyframes)
                    transcribed_count = len(keyframes)
                    print(f"📊 Keyframes for {footage_id}: {transcribed_count}/{total_count} transcribed")
                    
                    if transcribed_count != total_count:
                        print(f"⏩ Skipping {footage_id}, not all keyframes transcribed yet ({transcribed_count}/{total_count})")
                        continue
                    
                    # Get footage record
                    print(f"🔍 Step 4: Getting footage record for {footage_id}...")
                    footage_records = self.session.find_records(
                        CONFIG['layout_footage'], 
                        {"INFO_FTG_ID": footage_id}
                    )
                    
                    if not footage_records:
                        print(f"⚠️ No footage record found for {footage_id}")
                        continue
                    
                    footage_record = footage_records[0]
                    footage_record_id = footage_record["recordId"]
                    footage_field_data = footage_record["fieldData"]
                    filename = footage_field_data.get("Filename", "")
                    existing_description = footage_field_data.get("INFO_Description", "")
                    
                    print(f"📁 Footage details for {footage_id}:")
                    print(f"   Filename: {filename}")
                    print(f"   Existing description: {existing_description[:50]}...")
                    
                    # Generate description
                    print(f"🔍 Step 5: Generating description for {footage_id}...")
                    title, description, csv_data = self.generate_video_description(
                        keyframes, filename, existing_description
                    )
                    
                    print(f"✅ Description generated for {footage_id}")
                    print(f"   Title: {title}")
                    print(f"   Description length: {len(description)} chars")
                    
                    if title and description:
                        print(f"🔍 Step 6: Updating footage record for {footage_id}...")
                        # Update footage record with separate title and description
                        success = self.session.update_record(
                            CONFIG['layout_footage'], footage_record_id,
                            {
                                "INFO_Title": title,
                                "INFO_Description": description,
                                "INFO_Video_Events": csv_data
                            }
                        )
                        
                        if success:
                            print(f"✅ Video title and description updated for {footage_id}")
                            print(f"   Title: {title}")
                            print(f"   Description: {description[:100]}...")
                            
                            print(f"🔍 Step 7: Updating keyframe statuses for {footage_id}...")
                            # Update all keyframes to final status
                            updated_count = 0
                            for keyframe_record in all_keyframes:
                                update_success = self.session.update_record(
                                    CONFIG['layout_keyframes'], keyframe_record["recordId"],
                                    {"Keyframe_Status": STATUSES['FULLY_PROCESSED']}
                                )
                                if update_success:
                                    updated_count += 1
                            
                            print(f"✅ Marked {updated_count}/{len(all_keyframes)} keyframes for {footage_id} as fully processed")
                        else:
                            print(f"❌ Failed to update footage record for {footage_id}")
                    else:
                        print(f"⚠️ No title/description generated for {footage_id}")
                
                except Exception as footage_error:
                    print(f"❌ Error processing footage {footage_id}: {footage_error}")
                    import traceback
                    print(f"   Full traceback: {traceback.format_exc()}")
                    
        except Exception as e:
            print(f"❌ Video description processing error: {e}")
            import traceback
            print(f"   Full traceback: {traceback.format_exc()}")
    
    def generate_video_description(self, keyframes: List[Dict], filename: str, existing_description: str) -> Tuple[str, str, str]:
        """Generate comprehensive video description from keyframes - NO CHUNKING VERSION"""
        print("🔍 GENERATE_VIDEO_DESCRIPTION: Starting...")
        try:
            # Sort keyframes
            print("🔍 GENERATE_VIDEO_DESCRIPTION: Sorting keyframes...")
            keyframes_sorted = sorted(keyframes, key=lambda x: x.get("KeyframeID", ""))
            print(f"📊 Sorted {len(keyframes_sorted)} keyframes")
            
            # Analyze content
            print("🔍 GENERATE_VIDEO_DESCRIPTION: Analyzing content...")
            total_keyframes = len(keyframes_sorted)
            keyframes_with_audio = sum(1 for kf in keyframes_sorted if kf.get("Keyframe_Transcript", "").strip())
            keyframes_with_visuals = sum(1 for kf in keyframes_sorted if kf.get("Keyframe_GPT_Caption", "").strip())
            
            print(f"📊 Content analysis: {keyframes_with_visuals}/{total_keyframes} visual, {keyframes_with_audio}/{total_keyframes} audio")
            
            if keyframes_with_visuals == 0:
                print("⚠️ No visual content found - skipping description generation")
                return "No Visual Content", "This video appears to lack visual content data.", ""
            
            # Build CSV data
            print("🔍 GENERATE_VIDEO_DESCRIPTION: Building CSV data...")
            full_csv_lines = ["Frame,Visual Description,Audio Transcript"]
            for i, kf in enumerate(keyframes_sorted):
                desc = kf.get("Keyframe_GPT_Caption", "").replace("\n", " ").strip()
                trans = kf.get("Keyframe_Transcript", "").replace("\n", " ").strip()
                frame_id = kf.get("KeyframeID", "")
                full_csv_lines.append(f"{frame_id},{desc},{trans}")
                print(f"   Keyframe {i+1}: {frame_id} - Visual: {len(desc)} chars, Audio: {len(trans)} chars")
            
            csv_data = "\n".join(full_csv_lines)
            print(f"📊 CSV data built: {len(csv_data)} total characters")
            
            # Check if it's a silent video
            is_silent = keyframes_with_audio == 0
            
            # Prepare the OpenAI request
            print("🔍 GENERATE_VIDEO_DESCRIPTION: Preparing OpenAI request...")
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
            print(f"📊 Silent video status: {silent_note}")
            
            user_prompt = f"""Filename: {filename}
Existing description: {existing_description}
{silent_note}

Frame-level data:
{csv_data}"""
            
            print(f"📊 User prompt length: {len(user_prompt)} characters")
            print("📝 Calling OpenAI API...")
            
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            print("✅ OpenAI response received")
            final_response = response.choices[0].message.content.strip()
            print(f"📝 Raw response: {final_response[:200]}...")
            
            # Parse title and description
            print("🔍 GENERATE_VIDEO_DESCRIPTION: Parsing title and description...")
            title, description = self.parse_title_description(final_response)
            
            print(f"✅ GENERATE_VIDEO_DESCRIPTION: Complete!")
            print(f"   Title: {title}")
            print(f"   Description: {description[:100]}...")
            
            return title, description, csv_data
            
        except Exception as e:
            print(f"❌ GENERATE_VIDEO_DESCRIPTION: Exception occurred: {e}")
            import traceback
            print(f"   Full traceback: {traceback.format_exc()}")
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
                    title = line[6:].strip()  # Remove "Title:" prefix
                elif line.lower().startswith('description:'):
                    description = line[12:].strip()  # Remove "Description:" prefix
                elif not title and not line.lower().startswith('description:'):
                    # If no "Title:" prefix found, assume first line is title
                    title = line
                elif title and not description:
                    # If we have title but no "Description:" prefix, assume this is description
                    description = line
            
            # Fallback: if parsing fails, try to split on first line break
            if not title and not description:
                parts = response_text.strip().split('\n', 1)
                if len(parts) >= 2:
                    title = parts[0].strip()
                    description = parts[1].strip()
                else:
                    # Last resort: use entire response as description
                    description = response_text.strip()
                    title = "Untitled Video"
            
            # Clean up any remaining prefixes that might have been missed
            title = title.replace('Title:', '').replace('title:', '').strip()
            description = description.replace('Description:', '').replace('description:', '').strip()
            
            # Ensure we have something
            if not title:
                title = "Untitled Video"
            if not description:
                description = "No description available"
                
        except Exception as e:
            print(f"⚠️ Title/description parsing error: {e}")
            title = "Untitled Video"
            description = response_text.strip() if response_text.strip() else "No description available"
        
        print(f"📝 Parsed - Title: '{title}'")
        print(f"📝 Parsed - Description: '{description}'")
        
        return title, description
    
    def check_audio_silence(self, audio_path: str) -> bool:
        """Check if audio file is mostly silent"""
        try:
            result = subprocess.run(
                [CONFIG['ffmpeg_path'], "-i", audio_path, "-af", "volumedetect", "-f", "null", "-"],
                stderr=subprocess.PIPE, text=True
            )
            
            vol_output = result.stderr
            mean_volume_line = next((line for line in vol_output.splitlines() if "mean_volume:" in line), None)
            
            if mean_volume_line:
                mean_volume_db = float(mean_volume_line.split("mean_volume:")[1].split(" dB")[0].strip())
                return mean_volume_db < -50  # Consider silence if below -50dB
            
        except Exception as e:
            print(f"❌ Audio silence check failed: {e}")
        
        return False
    
    def remove_markdown(self, text: str) -> str:
        """Remove simple markdown formatting"""
        return text.replace("*", "").replace("-", "").replace("_", "").strip()

def main():
    """Main processing loop"""
    processor = KeyframeProcessor()
    
    print("🚀 Starting Keyframe Processor")
    print(f"📊 Status sequence: {' → '.join(STATUSES.values())}")
    
    while True:
        print(f"\n🔄 Starting processing cycle at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            processor.process_all_stages()
            print("✅ Processing cycle completed")
            
        except Exception as e:
            print(f"❌ Processing cycle error: {e}")
        
        print(f"⏳ Sleeping for {CONFIG['loop_interval']} seconds...")
        time.sleep(CONFIG['loop_interval'])

if __name__ == "__main__":
    main()