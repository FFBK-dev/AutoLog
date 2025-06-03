#!/usr/bin/env python3

import os
import json
import numpy as np
import cv2
import scenedetect
from scenedetect import detect, ContentDetector, ThresholdDetector
import openai
import whisper
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import subprocess
import tempfile
import requests
import urllib3
import warnings
import base64
import re

# Suppress SSL warnings (matching your existing script)
warnings.filterwarnings('ignore')
urllib3.disable_warnings()

# Configuration (matching your existing setup)
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
}

@dataclass
class MarkerCandidate:
    """Represents a potential marker location"""
    timecode: float
    confidence: float
    visual_description: str
    audio_transcript: str
    marker_type: str
    context: Dict

@dataclass
class FinalMarker:
    """Final marker for export"""
    timecode: str  # HH:MM:SS:FF format
    description: str  # Prompt-aware description
    
class FileMakerSession:
    """FileMaker session handler (from your existing script)"""
    
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
        all_records = []
        offset = 1
        limit = 500
        
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
            
            if len(records) < limit:
                break
                
            offset += len(records)
        
        return all_records
    
    def update_record(self, layout: str, record_id: str, field_data: Dict) -> bool:
        """Update a record in FileMaker"""
        update_url = f"https://{self.server}/fmi/data/vLatest/databases/{self.db_encoded}/layouts/{layout}/records/{record_id}"
        update_payload = {"fieldData": field_data}
        update_resp = requests.patch(update_url, headers=self.headers, json=update_payload, verify=False)
        return update_resp.status_code == 200

class SmartMarkerGenerator:
    """
    Generates intelligent markers that understand user intent
    """
    
    def __init__(self):
        self.session = None
        self.openai_client = openai.OpenAI(api_key=CONFIG['openai_api_key'])
        self.whisper_model = whisper.load_model("base")
        
        # Video timecode properties (will be populated when analyzing video)
        self.video_fps = 29.97  # Default, will be detected
        self.video_start_tc = None  # Will be extracted from video
        self.video_drop_frame = False  # Will be detected
        self.frame_rate_info = None
    
    def extract_video_timecode_info(self, video_path: str) -> Dict:
        """
        Extract timecode information from video file including start TC and frame rate
        """
        print(f"🎬 Extracting timecode information from video...")
        
        timecode_info = {
            'fps': 29.97,  # Default fallback
            'start_timecode': '00:00:00:00',
            'drop_frame': False,
            'timebase': '30000/1001'  # NTSC default
        }
        
        try:
            # Use ffprobe to get detailed video information
            ffprobe_cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', 
                '-show_format', video_path
            ]
            
            result = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                video_info = json.loads(result.stdout)
                
                # Find video stream
                video_stream = None
                for stream in video_info.get('streams', []):
                    if stream.get('codec_type') == 'video':
                        video_stream = stream
                        break
                
                if video_stream:
                    # Extract frame rate
                    r_frame_rate = video_stream.get('r_frame_rate', '30000/1001')
                    if '/' in r_frame_rate:
                        num, den = map(int, r_frame_rate.split('/'))
                        fps = num / den
                    else:
                        fps = float(r_frame_rate)
                    
                    timecode_info['fps'] = fps
                    timecode_info['timebase'] = r_frame_rate
                    
                    # Detect drop frame for 29.97fps
                    if abs(fps - 29.97) < 0.01:
                        timecode_info['drop_frame'] = True
                        timecode_info['fps'] = 29.97
                    elif abs(fps - 30.0) < 0.01:
                        timecode_info['drop_frame'] = False
                        timecode_info['fps'] = 30.0
                    elif abs(fps - 23.976) < 0.01:
                        timecode_info['fps'] = 23.976
                    elif abs(fps - 24.0) < 0.01:
                        timecode_info['fps'] = 24.0
                    elif abs(fps - 25.0) < 0.01:
                        timecode_info['fps'] = 25.0
                    
                    print(f"   📊 Frame rate: {fps:.3f} fps ({r_frame_rate})")
                    print(f"   🎭 Drop frame: {timecode_info['drop_frame']}")
                
                # Look for start timecode in metadata
                format_info = video_info.get('format', {})
                tags = format_info.get('tags', {})
                
                # Check various possible timecode fields
                start_tc_fields = ['timecode', 'creation_time', 'start_timecode', 'tc_start']
                for field in start_tc_fields:
                    if field in tags:
                        potential_tc = tags[field]
                        if self.is_valid_timecode(potential_tc):
                            timecode_info['start_timecode'] = potential_tc
                            print(f"   🕒 Start timecode: {potential_tc}")
                            break
        
        except Exception as e:
            print(f"   ⚠️ Could not extract timecode info: {e}")
        
        # Store for later use
        self.video_fps = timecode_info['fps']
        self.video_start_tc = timecode_info['start_timecode']
        self.video_drop_frame = timecode_info['drop_frame']
        self.frame_rate_info = timecode_info
        
        print(f"   ✅ Using: {timecode_info['fps']} fps, start: {timecode_info['start_timecode']}")
        return timecode_info
    
    def is_valid_timecode(self, tc_string: str) -> bool:
        """Check if string looks like a valid timecode"""
        # Match HH:MM:SS:FF or HH:MM:SS;FF patterns (both drop and non-drop frame)
        pattern = r'^\d{2}[:;]\d{2}[:;]\d{2}[:;]\d{2}$'
        return bool(re.match(pattern, tc_string))
    
    def process_marker_request(self, footage_id: str, user_prompt: str) -> Tuple[List[FinalMarker], str]:
        """
        Main entry point - returns markers and AVID file content with footage context and frame-accurate timing
        """
        print(f"🎯 Processing marker request for footage: {footage_id}")
        print(f"📝 User prompt: '{user_prompt}'")
        
        # Get footage and keyframe data
        footage_data = self.get_footage_data(footage_id)
        keyframes = self.get_keyframe_data(footage_id)
        
        if not footage_data:
            raise ValueError(f"No footage found with ID: {footage_id}")
        if not keyframes:
            raise ValueError(f"No keyframes found for footage: {footage_id}")
            
        video_path = footage_data.get("SPECS_Filepath_Server")
        if not video_path or not os.path.exists(video_path):
            raise ValueError(f"Video file not accessible: {video_path}")
        
        print(f"📁 Video path: {video_path}")
        print(f"📊 Found {len(keyframes)} keyframes to analyze")
        
        # Extract timecode information from video
        timecode_info = self.extract_video_timecode_info(video_path)
        
        # Show footage context
        title = footage_data.get("INFO_Title", "")
        description = footage_data.get("INFO_Description", "")
        if title:
            print(f"🎬 Footage title: '{title}'")
        if description:
            print(f"📄 Description: {description[:100]}{'...' if len(description) > 100 else ''}")
        
        # Step 1: Understand what the user wants
        prompt_intelligence = self.analyze_user_intent(user_prompt)
        print(f"🧠 Intent analysis: {prompt_intelligence['intent_type']}")
        
        # Step 2: Find candidate moments using analysis
        candidates = self.find_marker_candidates(
            keyframes, video_path, user_prompt, prompt_intelligence, footage_data
        )
        
        print(f"🔍 Found {len(candidates)} candidates")
        
        # Step 3: Generate intelligent descriptions for each marker
        final_markers = self.generate_intelligent_markers(
            candidates, user_prompt, prompt_intelligence, video_path, footage_data
        )
        
        print(f"✅ Generated {len(final_markers)} final markers")
        
        # Step 4: Create AVID-compatible file
        avid_content = self.create_avid_markers_file(final_markers, footage_data)
        
        # Step 5: Update FileMaker (if we have footage data)
        self.update_filemaker_markers(footage_id, final_markers, avid_content)
        
        return final_markers, avid_content
    
    def analyze_user_intent(self, user_prompt: str) -> Dict:
        """
        Analyze what the user really wants - handles both simple and complex prompts
        """
        # For now, let's use the simple analysis to avoid complexity issues
        print(f"🧠 Processing prompt analysis...")
        return self.analyze_simple_prompt(user_prompt)
    
    def analyze_simple_prompt(self, user_prompt: str) -> Dict:
        """
        Analyze simple single-requirement prompts
        """
        analysis_prompt = f"""
        Analyze this marker request to understand both WHAT to find and HOW to describe findings:
        
        User prompt: "{user_prompt}"
        
        Return ONLY a valid JSON object with these exact fields:
        {{
            "intent_type": "shot_types|speaker_changes|action_sequences|emotions|objects|locations|events|dialog_content",
            "detection_strategy": "What to look for (visual/audio/semantic cues)",
            "description_template": "How to describe markers (include the user's terminology)",
            "keywords": ["key", "terms", "for", "semantic", "matching"],
            "visual_cues": ["specific", "visual", "elements", "to", "detect"],
            "audio_cues": ["audio", "patterns", "to", "listen", "for"],
            "confidence_threshold": 0.4,
            "primary_modality": "visual|audio|both"
        }}
        
        Examples:
        - "Find all close-ups" → intent_type: "shot_types", primary_modality: "visual"
        - "Mark speaker changes" → intent_type: "speaker_changes", primary_modality: "audio"
        - "Tag emotional moments" → intent_type: "emotions", primary_modality: "both"
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an expert at understanding video analysis requests. Return ONLY valid JSON, no other text."},
                    {"role": "user", "content": analysis_prompt}
                ],
                temperature=0.1
            )
            
            response_text = response.choices[0].message.content.strip()
            print(f"🔍 Raw OpenAI response: {response_text[:200]}...")
            
            # Try to extract JSON if it's wrapped in markdown or other text
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                json_text = response_text[json_start:json_end].strip()
            elif "{" in response_text:
                json_start = response_text.find("{")
                json_end = response_text.rfind("}") + 1
                json_text = response_text[json_start:json_end]
            else:
                raise ValueError("No JSON found in response")
            
            analysis = json.loads(json_text)
            analysis['is_complex'] = False  # Mark as simple prompt
            print(f"✅ Intent analysis successful: {analysis['intent_type']}")
            
            # Generate search embedding
            search_text = f"{user_prompt} {' '.join(analysis.get('keywords', []))}"
            try:
                embedding_response = self.openai_client.embeddings.create(
                    model="text-embedding-3-small",
                    input=search_text
                )
                analysis['search_embedding'] = embedding_response.data[0].embedding
            except:
                analysis['search_embedding'] = [0.0] * 1536
            
            return analysis
            
        except Exception as e:
            print(f"⚠️ Intent analysis failed, using smart fallback: {e}")
            
            # Smart fallback based on prompt content
            prompt_lower = user_prompt.lower()
            
            if "close" in prompt_lower or "medium" in prompt_lower or "wide" in prompt_lower:
                intent_type = "shot_types"
                template = "Shot: [shot size] - [description]"
                keywords = ["close", "medium", "wide", "shot"]
                visual_cues = ["close-up", "medium shot", "wide shot"]
                audio_cues = []
                threshold = 0.3
                primary_modality = "visual"
            elif "speaker" in prompt_lower or "speech" in prompt_lower or "dialog" in prompt_lower:
                intent_type = "speaker_changes"
                template = "Dialog: [description]"
                keywords = ["speaker", "speech", "voice", "dialog"]
                visual_cues = ["person", "face", "speaking"]
                audio_cues = ["speech", "voice", "talking"]
                threshold = 0.5
                primary_modality = "audio"
            else:
                intent_type = "general"
                template = f"{user_prompt}: [description]"
                keywords = user_prompt.split()
                visual_cues = [user_prompt]
                audio_cues = [user_prompt]
                threshold = 0.4
                primary_modality = "both"
            
            try:
                embedding_response = self.openai_client.embeddings.create(
                    model="text-embedding-3-small", 
                    input=user_prompt
                )
                search_embedding = embedding_response.data[0].embedding
            except:
                print("⚠️ Embedding generation also failed, using dummy embedding")
                search_embedding = [0.0] * 1536  # Dummy embedding
            
            return {
                'intent_type': intent_type,
                'detection_strategy': user_prompt,
                'description_template': template,
                'keywords': keywords,
                'visual_cues': visual_cues,
                'audio_cues': audio_cues,
                'confidence_threshold': threshold,
                'primary_modality': primary_modality,
                'search_embedding': search_embedding,
                'is_complex': False
            }
    
    def find_marker_candidates(self, keyframes: List[Dict], video_path: str, 
                             user_prompt: str, prompt_intelligence: Dict, footage_data: Dict = None) -> List[MarkerCandidate]:
        """
        Find candidate markers using semantic analysis + scene detection + footage context + PRECISE TIMING
        """
        print(f"🧠 Using comprehensive analysis with footage context and precise timing...")
        
        candidates = []
        
        # Method 1: Semantic analysis of existing keyframes (broad candidates)
        semantic_candidates = self.find_semantic_candidates(keyframes, prompt_intelligence)
        print(f"📊 Found {len(semantic_candidates)} broad semantic candidates")
        
        # Method 2: For high-confidence semantic candidates, find precise timing
        if semantic_candidates:
            precise_candidates = self.refine_candidate_timing(
                semantic_candidates, video_path, user_prompt, prompt_intelligence
            )
            candidates.extend(precise_candidates)
        
        # Method 3: Scene detection for structural changes
        if prompt_intelligence['intent_type'] in ['shot_types', 'locations', 'speaker_changes']:
            scene_candidates = self.find_scene_candidates(video_path, prompt_intelligence)
            candidates.extend(scene_candidates)
        
        # Method 4: Audio-based detection for speech-related prompts
        if 'speaker' in user_prompt.lower() or 'speech' in user_prompt.lower() or 'mentions' in user_prompt.lower():
            audio_candidates = self.find_precise_audio_candidates(keyframes, video_path, user_prompt, prompt_intelligence)
            candidates.extend(audio_candidates)
        
        # Merge and deduplicate candidates
        merged_candidates = self.merge_candidates(candidates)
        
        # Filter by confidence threshold and also add scene detection fallback
        threshold = max(0.2, prompt_intelligence.get('confidence_threshold', 0.5) - 0.3)  # Lower threshold
        filtered_candidates = [c for c in merged_candidates if c.confidence >= threshold]
        
        # If we have very few candidates, try scene detection as fallback
        if len(filtered_candidates) < 3:
            print(f"⚠️ Only {len(filtered_candidates)} candidates found, adding scene detection...")
            scene_candidates = self.find_scene_candidates(video_path, prompt_intelligence)
            
            # Add scene candidates that meet a lower threshold
            for scene_candidate in scene_candidates:
                if scene_candidate.confidence >= 0.4:  # Lower threshold for scenes
                    filtered_candidates.append(scene_candidate)
        
        # Sort by confidence and return top candidates
        filtered_candidates.sort(key=lambda x: x.confidence, reverse=True)
        
        print(f"🎯 Final candidates after filtering: {len(filtered_candidates)}")
        return filtered_candidates[:20]  # Limit to top 20
    
    def refine_candidate_timing(self, semantic_candidates: List[MarkerCandidate], video_path: str, 
                              user_prompt: str, prompt_intelligence: Dict) -> List[MarkerCandidate]:
        """
        Refine timing of semantic candidates to frame-accurate precision
        """
        print(f"🎬 Refining timing to frame-accurate precision for {len(semantic_candidates)} candidates...")
        refined_candidates = []
        
        for candidate in semantic_candidates:
            if candidate.confidence < 0.6:  # Only refine high-confidence candidates
                # Convert to frame-accurate timecode anyway
                frame_accurate_seconds = self.find_frame_accurate_moment(
                    video_path, candidate.timecode, candidate.visual_description, 1.0
                )
                candidate.timecode = frame_accurate_seconds
                refined_candidates.append(candidate)
                continue
                
            print(f"  🎯 Refining timing around {candidate.timecode:.3f}s...")
            
            # Find frame-accurate moment for visual content
            if 'visual' in candidate.marker_type or candidate.visual_description:
                frame_accurate_seconds = self.find_frame_accurate_moment(
                    video_path, candidate.timecode, candidate.visual_description, 3.0
                )
            else:
                frame_accurate_seconds = candidate.timecode
            
            # Create refined candidate with frame-accurate timing
            refined_candidate = MarkerCandidate(
                timecode=frame_accurate_seconds,
                confidence=candidate.confidence,
                visual_description=candidate.visual_description,
                audio_transcript=candidate.audio_transcript,
                marker_type=f"{candidate.marker_type}_frame_accurate",
                context={
                    **candidate.context,
                    "original_time": candidate.timecode,
                    "frame_adjustment": frame_accurate_seconds - candidate.timecode,
                    "frame_accurate": True,
                    "frame_number": int(frame_accurate_seconds * self.video_fps)
                }
            )
            
            refined_candidates.append(refined_candidate)
        
        print(f"🎬 Frame-accurate refinement complete: {len(refined_candidates)} candidates")
        return refined_candidates
    
    def find_precise_audio_candidates(self, keyframes: List[Dict], video_path: str, 
                                    user_prompt: str, prompt_intelligence: Dict) -> List[MarkerCandidate]:
        """
        Find frame-accurate audio moments by analyzing audio with Whisper word timestamps
        """
        print(f"🎵 Searching for frame-accurate audio moments...")
        audio_candidates = []
        
        # Look for specific words or phrases in the prompt
        audio_search_terms = []
        prompt_lower = user_prompt.lower()
        
        # Extract quoted terms or specific words
        import re
        quoted_terms = re.findall(r'"([^"]*)"', user_prompt)
        if quoted_terms:
            audio_search_terms.extend(quoted_terms)
        
        # Look for "mentions of X" patterns
        mentions_match = re.search(r'mentions?\s+of\s+["\']?([^"\']+)["\']?', prompt_lower)
        if mentions_match:
            audio_search_terms.append(mentions_match.group(1))
        
        # Add audio cues from intent analysis
        audio_search_terms.extend(prompt_intelligence.get('audio_cues', []))
        
        if not audio_search_terms:
            print(f"  ⚠️ No specific audio terms to search for")
            return []
        
        print(f"  🔍 Searching for audio terms: {audio_search_terms}")
        
        # Get video duration
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = frame_count / fps if fps > 0 else 60  # Fallback to 60s
        cap.release()
        
        # Analyze audio in 10-second segments with 2-second overlap for better word detection
        segment_length = 10.0
        overlap = 2.0
        
        current_time = 0.0
        while current_time < duration - segment_length:
            try:
                # Extract audio segment
                audio_path = os.path.join(CONFIG['tmp_dir'], f"audio_segment_{current_time:.1f}.wav")
                
                ffmpeg_cmd = [
                    CONFIG['ffmpeg_path'], "-y",
                    "-ss", f"{current_time:.3f}",
                    "-i", video_path,
                    "-t", f"{segment_length:.3f}",
                    "-vn", "-acodec", "pcm_s16le",
                    "-ar", "16000", "-ac", "1",
                    audio_path,
                    "-loglevel", "quiet"
                ]
                
                result = subprocess.run(ffmpeg_cmd, capture_output=True)
                
                if result.returncode == 0 and os.path.exists(audio_path):
                    # Transcribe with word-level timestamps
                    transcription = self.whisper_model.transcribe(
                        audio_path,
                        word_timestamps=True,
                        language="en"
                    )
                    
                    # Look for search terms with frame-accurate timing
                    for search_term in audio_search_terms:
                        if hasattr(transcription, 'segments'):
                            for segment in transcription.segments:
                                if hasattr(segment, 'words'):
                                    for word in segment.words:
                                        if search_term.lower() in word.word.lower():
                                            # Calculate absolute time
                                            word_absolute_time = current_time + word.start
                                            
                                            # Convert to frame-accurate timing
                                            frame_number = int(round(word_absolute_time * self.video_fps))
                                            frame_accurate_time = frame_number / self.video_fps
                                            
                                            confidence = 0.95  # Very high confidence for word-level matches
                                            
                                            audio_candidates.append(MarkerCandidate(
                                                timecode=frame_accurate_time,
                                                confidence=confidence,
                                                visual_description=f"Audio: '{search_term}' spoken",
                                                audio_transcript=segment.text.strip(),
                                                marker_type="frame_accurate_audio",
                                                context={
                                                    "search_term": search_term,
                                                    "word_confidence": word.probability if hasattr(word, 'probability') else 1.0,
                                                    "segment_start": current_time,
                                                    "word_start": word.start,
                                                    "word_end": word.end,
                                                    "frame_number": frame_number,
                                                    "frame_accurate": True
                                                }
                                            ))
                                            
                                            print(f"  ✅ Found '{search_term}' at frame {frame_number} ({frame_accurate_time:.3f}s)")
                    
                    # Cleanup
                    os.unlink(audio_path)
                
            except Exception as e:
                print(f"  ⚠️ Audio analysis failed at {current_time:.1f}s: {e}")
            
            current_time += segment_length - overlap  # Move forward with overlap
        
        print(f"🎵 Found {len(audio_candidates)} frame-accurate audio candidates")
        return audio_candidates
    
    def seconds_to_frame_accurate_timecode(self, seconds: float) -> str:
        """
        Convert seconds to frame-accurate timecode respecting video's timecode track
        """
        # Calculate frame number from seconds
        frame_number = int(round(seconds * self.video_fps))
        
        # Convert to timecode components
        if self.video_drop_frame and abs(self.video_fps - 29.97) < 0.01:
            # Drop frame calculation for 29.97fps
            tc = self.frames_to_drop_frame_timecode(frame_number)
        else:
            # Non-drop frame calculation
            tc = self.frames_to_non_drop_timecode(frame_number)
        
        # Add start timecode offset if present
        if self.video_start_tc and self.video_start_tc != '00:00:00:00':
            tc = self.add_timecode_offset(tc, self.video_start_tc)
        
        return tc
    
    def find_frame_accurate_moment(self, video_path: str, approximate_seconds: float, 
                                 search_criteria: str, search_radius: float = 3.0) -> float:
        """
        Find frame-accurate moment within search radius
        """
        print(f"  🎯 Finding frame-accurate moment around {approximate_seconds:.2f}s...")
        
        # Convert search radius to frames
        radius_frames = int(search_radius * self.video_fps)
        center_frame = int(approximate_seconds * self.video_fps)
        
        start_frame = max(0, center_frame - radius_frames)
        end_frame = center_frame + radius_frames
        
        best_frame = center_frame
        best_confidence = 0.0
        
        # Sample every 3rd frame within radius for performance
        for frame_num in range(start_frame, end_frame, 3):
            frame_seconds = frame_num / self.video_fps
            
            # Analyze this specific frame
            confidence = self.analyze_single_frame_for_criteria(
                video_path, frame_seconds, search_criteria
            )
            
            if confidence > best_confidence:
                best_confidence = confidence
                best_frame = frame_num
        
        best_seconds = best_frame / self.video_fps
        print(f"    ✅ Best match at frame {best_frame} ({best_seconds:.3f}s, conf: {best_confidence:.3f})")
        
        return best_seconds
    
    def analyze_single_frame_for_criteria(self, video_path: str, seconds: float, criteria: str) -> float:
        """
        Analyze a single frame for specific criteria
        """
        try:
            # Extract specific frame
            cap = cv2.VideoCapture(video_path)
            cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                return 0.0
            
            # Quick visual analysis - you could enhance this with more sophisticated methods
            # For now, use simple heuristics based on criteria
            
            if 'animation' in criteria.lower() or 'graphic' in criteria.lower():
                # Look for animated content - check for high color saturation, clean lines
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                saturation = np.mean(hsv[:,:,1])
                return min(saturation / 128.0, 1.0)  # Normalize saturation
            
            elif 'blood' in criteria.lower() or 'red' in criteria.lower():
                # Look for red content
                red_channel = frame[:,:,2]  # BGR format
                red_intensity = np.mean(red_channel)
                return min(red_intensity / 128.0, 1.0)
            
            else:
                # Generic frame analysis - look for visual interest
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                edges = cv2.Canny(gray, 50, 150)
                edge_density = np.mean(edges) / 255.0
                return edge_density
                
        except Exception:
            return 0.0
    
    def find_frame_accurate_audio_moment(self, video_path: str, search_term: str, 
                                       approximate_seconds: float, search_radius: float = 2.0) -> float:
        """
        Find frame-accurate moment when specific audio occurs
        """
        print(f"  🎵 Finding frame-accurate audio moment for '{search_term}' around {approximate_seconds:.2f}s...")
        
        search_start = max(0, approximate_seconds - search_radius)
        search_end = approximate_seconds + search_radius
        search_duration = search_end - search_start
        
        try:
            # Extract audio segment with high precision
            audio_path = os.path.join(CONFIG['tmp_dir'], f"precise_audio_{approximate_seconds:.2f}.wav")
            
            ffmpeg_cmd = [
                CONFIG['ffmpeg_path'], "-y",
                "-ss", f"{search_start:.3f}",
                "-i", video_path,
                "-t", f"{search_duration:.3f}",
                "-vn", "-acodec", "pcm_s16le",
                "-ar", "16000", "-ac", "1",
                audio_path,
                "-loglevel", "quiet"
            ]
            
            result = subprocess.run(ffmpeg_cmd, capture_output=True)
            
            if result.returncode == 0 and os.path.exists(audio_path):
                # Transcribe with word-level timestamps
                transcription = self.whisper_model.transcribe(
                    audio_path, 
                    word_timestamps=True,
                    language="en"
                )
                
                # Find the specific word
                best_time = approximate_seconds
                
                if hasattr(transcription, 'segments'):
                    for segment in transcription.segments:
                        if hasattr(segment, 'words'):
                            for word in segment.words:
                                if search_term.lower() in word.word.lower():
                                    # Convert relative time to absolute time
                                    word_absolute_time = search_start + word.start
                                    
                                    # Convert to frame-accurate timing
                                    frame_number = int(round(word_absolute_time * self.video_fps))
                                    best_time = frame_number / self.video_fps
                                    
                                    print(f"    ✅ Found '{search_term}' at frame {frame_number} ({best_time:.3f}s)")
                                    break
                
                # Cleanup
                os.unlink(audio_path)
                
                return best_time
                
        except Exception as e:
            print(f"    ⚠️ Frame-accurate audio search failed: {e}")
        
        return approximate_seconds  # Fallback to approximate time
        
    def find_precise_audio_candidates(self, keyframes: List[Dict], video_path: str, 
                                    user_prompt: str, prompt_intelligence: Dict) -> List[MarkerCandidate]:
        """
        Find precise audio moments by analyzing audio segments with higher temporal resolution
        """
        print(f"🎵 Searching for precise audio moments...")
        audio_candidates = []
        
        # Look for specific words or phrases in the prompt
        audio_search_terms = []
        prompt_lower = user_prompt.lower()
        
        # Extract quoted terms or specific words
        import re
        quoted_terms = re.findall(r'"([^"]*)"', user_prompt)
        if quoted_terms:
            audio_search_terms.extend(quoted_terms)
        
        # Look for "mentions of X" patterns
        mentions_match = re.search(r'mentions?\s+of\s+["\']?([^"\']+)["\']?', prompt_lower)
        if mentions_match:
            audio_search_terms.append(mentions_match.group(1))
        
        # Add audio cues from intent analysis
        audio_search_terms.extend(prompt_intelligence.get('audio_cues', []))
        
        if not audio_search_terms:
            print(f"  ⚠️ No specific audio terms to search for")
            return []
        
        print(f"  🔍 Searching for audio terms: {audio_search_terms}")
        
        # Get video duration
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = frame_count / fps if fps > 0 else 60  # Fallback to 60s
        cap.release()
        
        # Analyze audio in 5-second segments with 1-second overlap
        segment_length = 5.0
        overlap = 1.0
        
        current_time = 0.0
        while current_time < duration - segment_length:
            try:
                # Extract audio segment
                audio_path = os.path.join(CONFIG['tmp_dir'], f"audio_segment_{current_time:.1f}.wav")
                
                ffmpeg_cmd = [
                    CONFIG['ffmpeg_path'], "-y",
                    "-ss", str(current_time),
                    "-i", video_path,
                    "-t", str(segment_length),
                    "-vn", "-acodec", "pcm_s16le",
                    "-ar", "16000", "-ac", "1",
                    audio_path,
                    "-loglevel", "quiet"
                ]
                
                result = subprocess.run(ffmpeg_cmd, capture_output=True)
                
                if result.returncode == 0 and os.path.exists(audio_path):
                    # Transcribe with Whisper
                    transcription = self.whisper_model.transcribe(audio_path)
                    transcript_text = transcription.get("text", "").strip().lower()
                    
                    if transcript_text:
                        # Check for search terms
                        for search_term in audio_search_terms:
                            if search_term.lower() in transcript_text:
                                # Found a match! Now find the precise timing within this segment
                                precise_time = self.find_precise_word_timing(
                                    transcription, search_term, current_time
                                )
                                
                                confidence = 0.9  # High confidence for direct audio matches
                                
                                audio_candidates.append(MarkerCandidate(
                                    timecode=precise_time,
                                    confidence=confidence,
                                    visual_description=f"Audio mention: '{search_term}'",
                                    audio_transcript=transcript_text,
                                    marker_type="precise_audio",
                                    context={
                                        "search_term": search_term,
                                        "full_transcript": transcript_text,
                                        "segment_start": current_time,
                                        "precise_timing": True
                                    }
                                ))
                                
                                print(f"  ✅ Found '{search_term}' at {precise_time:.1f}s")
                    
                    # Cleanup
                    os.unlink(audio_path)
                
            except Exception as e:
                print(f"  ⚠️ Audio analysis failed at {current_time:.1f}s: {e}")
            
            current_time += segment_length - overlap  # Move forward with overlap
        
        print(f"🎵 Found {len(audio_candidates)} precise audio candidates")
        return audio_candidates
    
    def find_precise_word_timing(self, transcription, search_term: str, segment_start: float) -> float:
        """
        Find the precise timing of a word within a transcription segment
        """
        # Whisper provides word-level timestamps in some cases
        if hasattr(transcription, 'segments') and transcription.segments:
            for segment in transcription.segments:
                if hasattr(segment, 'words') and segment.words:
                    for word in segment.words:
                        if search_term.lower() in word.word.lower():
                            return segment_start + word.start
                
                # Fallback: check if term is in segment text
                if search_term.lower() in segment.text.lower():
                    return segment_start + segment.start
        
        # Fallback: return middle of segment
        return segment_start + 2.5
    
    def find_semantic_candidates(self, keyframes: List[Dict], prompt_intelligence: Dict) -> List[MarkerCandidate]:
        """
        Find candidates using semantic similarity with existing keyframe data
        """
        candidates = []
        search_embedding = np.array(prompt_intelligence['search_embedding'])
        
        print(f"🔍 Analyzing {len(keyframes)} keyframes for semantic matches...")
        
        keyframes_with_embeddings = 0
        keyframes_with_content = 0
        
        for kf in keyframes:
            try:
                keyframe_id = kf.get("KeyframeID", "unknown")
                
                # Check what data we have
                has_embedding = bool(kf.get("Keyframe_Fused_Embedding"))
                has_caption = bool(kf.get("Keyframe_GPT_Caption", "").strip())
                has_transcript = bool(kf.get("Keyframe_Transcript", "").strip())
                
                if has_embedding:
                    keyframes_with_embeddings += 1
                if has_caption or has_transcript:
                    keyframes_with_content += 1
                
                print(f"  📊 {keyframe_id}: embedding={has_embedding}, caption={has_caption}, transcript={has_transcript}")
                
                # Debug: Show what content we're analyzing
                if has_caption:
                    caption_preview = kf.get("Keyframe_GPT_Caption", "")[:60] + "..." if len(kf.get("Keyframe_GPT_Caption", "")) > 60 else kf.get("Keyframe_GPT_Caption", "")
                    print(f"    💬 Caption: '{caption_preview}'")
                
                if has_transcript:
                    transcript_preview = kf.get("Keyframe_Transcript", "")[:60] + "..." if len(kf.get("Keyframe_Transcript", "")) > 60 else kf.get("Keyframe_Transcript", "")
                    print(f"    🎵 Transcript: '{transcript_preview}'")
                
                if not has_caption and not has_transcript:
                    print(f"    ❌ No text content to analyze")
                
                # Try embedding-based similarity first
                similarity = 0.0
                if has_embedding and len(search_embedding) > 100:  # Valid embedding
                    try:
                        fused_embedding_str = kf.get("Keyframe_Fused_Embedding")
                        
                        # Handle potential formatting issues with the embedding
                        if fused_embedding_str.startswith('[') and fused_embedding_str.endswith(']'):
                            kf_embedding = np.array(json.loads(fused_embedding_str))
                        else:
                            # Try to clean up the embedding string
                            cleaned_embedding = fused_embedding_str.strip()
                            if not cleaned_embedding.startswith('['):
                                cleaned_embedding = '[' + cleaned_embedding
                            if not cleaned_embedding.endswith(']'):
                                cleaned_embedding = cleaned_embedding + ']'
                            kf_embedding = np.array(json.loads(cleaned_embedding))
                        
                        # Handle dimension mismatch between CLIP (768) and OpenAI (1536) embeddings
                        if len(kf_embedding) != len(search_embedding):
                            print(f"    ⚠️ Embedding dimension mismatch: {len(kf_embedding)} vs {len(search_embedding)}")
                            
                            if len(kf_embedding) == 768 and len(search_embedding) == 1536:
                                # CLIP vs OpenAI - use only text similarity for now
                                print(f"    🔄 Using text similarity only due to CLIP/OpenAI mismatch")
                                similarity = 0.0
                            else:
                                # Try to compare compatible dimensions
                                min_dim = min(len(kf_embedding), len(search_embedding))
                                similarity = np.dot(kf_embedding[:min_dim], search_embedding[:min_dim]) / (
                                    np.linalg.norm(kf_embedding[:min_dim]) * np.linalg.norm(search_embedding[:min_dim])
                                )
                                similarity *= 0.5  # Reduce confidence for dimension mismatch
                                print(f"    🔗 Partial similarity: {similarity:.3f} (first {min_dim} dims)")
                        else:
                            # Perfect dimension match
                            similarity = np.dot(search_embedding, kf_embedding) / (
                                np.linalg.norm(search_embedding) * np.linalg.norm(kf_embedding)
                            )
                            print(f"    🔗 Semantic similarity: {similarity:.3f}")
                            
                    except Exception as e:
                        print(f"    ⚠️ Embedding calculation failed: {e}")
                        # Debug: show what the embedding looks like
                        embedding_preview = fused_embedding_str[:100] + "..." if len(fused_embedding_str) > 100 else fused_embedding_str
                        print(f"    🔍 Embedding preview: {embedding_preview}")
                else:
                    print(f"    ⚠️ No valid embedding or search embedding too short")
                
                # Text-based similarity as backup/supplement
                text_content = f"{kf.get('Keyframe_GPT_Caption', '')} {kf.get('Keyframe_Transcript', '')}"
                text_similarity = self.calculate_keyword_similarity(
                    prompt_intelligence['keywords'], text_content
                )
                print(f"    📝 Text similarity: {text_similarity:.3f}")
                
                # Combined confidence score (favor text if no embedding)
                if similarity > 0:
                    confidence = 0.4 * similarity + 0.6 * text_similarity  # Favor text more due to embedding issues
                else:
                    confidence = text_similarity  # Fall back to text only
                
                print(f"    ⭐ Combined confidence: {confidence:.3f}")
                
                # Lower threshold due to embedding dimension issues
                threshold = max(0.2, prompt_intelligence.get('confidence_threshold', 0.4) - 0.2)
                if confidence > threshold:
                    # Handle missing timecode data
                    try:
                        timecode_value = float(kf.get("TC_IN_Seconds", 0))
                    except (ValueError, TypeError):
                        # If timecode is empty or invalid, skip this keyframe
                        print(f"    ⚠️ Invalid timecode data, skipping keyframe")
                        continue
                    
                    candidates.append(MarkerCandidate(
                        timecode=timecode_value,
                        confidence=confidence,
                        visual_description=kf.get("Keyframe_GPT_Caption", ""),
                        audio_transcript=kf.get("Keyframe_Transcript", ""),
                        marker_type="semantic",
                        context={
                            "keyframe_id": keyframe_id,
                            "semantic_similarity": similarity,
                            "text_similarity": text_similarity
                        }
                    ))
                    print(f"    ✅ Added as candidate!")
                else:
                    print(f"    ❌ Below threshold ({threshold:.3f})")
                    
            except (json.JSONDecodeError, ValueError) as e:
                print(f"    ⚠️ Error processing keyframe: {e}")
                continue
        
        print(f"📈 Summary:")
        print(f"  - Keyframes with embeddings: {keyframes_with_embeddings}/{len(keyframes)}")
        print(f"  - Keyframes with content: {keyframes_with_content}/{len(keyframes)}")
        print(f"  - Candidates found: {len(candidates)}")
        
        return candidates
    
    def find_scene_candidates(self, video_path: str, prompt_intelligence: Dict) -> List[MarkerCandidate]:
        """
        Find candidates using scene detection for structural changes
        """
        candidates = []
        
        try:
            print(f"🎬 Running scene detection on: {video_path}")
            
            # Check if video file is accessible
            if not os.path.exists(video_path):
                print(f"❌ Video file not found: {video_path}")
                return candidates
            
            # Test video accessibility
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                print(f"❌ Cannot open video file: {video_path}")
                return candidates
            cap.release()
            
            # Detect scenes with more lenient threshold
            scene_list = detect(video_path, ContentDetector(threshold=20.0))
            print(f"🎭 Detected {len(scene_list)} scenes")
            
            if not scene_list:
                print("⚠️ No scenes detected, trying lower threshold...")
                scene_list = detect(video_path, ContentDetector(threshold=10.0))
                print(f"🎭 With lower threshold: {len(scene_list)} scenes")
            
            # Analyze scene transitions (limit to prevent too many API calls)
            max_scenes = min(10, len(scene_list))
            for i in range(max_scenes):
                scene = scene_list[i]
                start_time = scene[0].get_seconds()
                end_time = scene[1].get_seconds()
                
                print(f"  🎬 Scene {i+1}: {start_time:.1f}s - {end_time:.1f}s ({end_time-start_time:.1f}s duration)")
                
                # For testing, let's skip the expensive frame analysis and use simpler heuristics
                if prompt_intelligence['intent_type'] == 'shot_types':
                    # For shot type detection, scene boundaries are good candidates
                    confidence = 0.6  # Moderate confidence for scene boundaries
                    description = f"Scene transition at {start_time:.1f}s"
                    
                    candidates.append(MarkerCandidate(
                        timecode=start_time,
                        confidence=confidence,
                        visual_description=description,
                        audio_transcript="",
                        marker_type="scene_transition",
                        context={
                            "scene_index": i,
                            "scene_duration": end_time - start_time
                        }
                    ))
                    print(f"    ✅ Added scene transition candidate")
                    
        except Exception as e:
            print(f"⚠️ Scene detection failed: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"🎭 Found {len(candidates)} scene candidates")
        return candidates
    
    def find_audio_candidates(self, keyframes: List[Dict], prompt_intelligence: Dict) -> List[MarkerCandidate]:
        """
        Find candidates based on audio transitions (speaker changes, etc.)
        """
        candidates = []
        
        # Look for keyframes with audio transitions
        prev_transcript = ""
        for kf in sorted(keyframes, key=lambda x: float(x.get("TC_IN_Seconds", 0))):
            current_transcript = kf.get("Keyframe_Transcript", "").strip()
            
            # Detect potential speaker changes (simple heuristic)
            if prev_transcript and current_transcript:
                if self.detect_speaker_change(prev_transcript, current_transcript):
                    candidates.append(MarkerCandidate(
                        timecode=float(kf.get("TC_IN_Seconds", 0)),
                        confidence=0.8,  # High confidence for clear audio transitions
                        visual_description=kf.get("Keyframe_GPT_Caption", ""),
                        audio_transcript=current_transcript,
                        marker_type="audio_transition",
                        context={
                            "previous_transcript": prev_transcript,
                            "transition_type": "speaker_change"
                        }
                    ))
            
            prev_transcript = current_transcript
        
        print(f"🎵 Found {len(candidates)} audio candidates")
        return candidates
    
    def merge_candidates(self, all_candidates: List[MarkerCandidate]) -> List[MarkerCandidate]:
        """
        Merge candidates and remove duplicates within 3 seconds of each other
        """
        if not all_candidates:
            return []
        
        # Sort by timecode
        sorted_candidates = sorted(all_candidates, key=lambda x: x.timecode)
        
        merged = []
        for candidate in sorted_candidates:
            # Check if too close to existing marker
            too_close = False
            for existing in merged:
                if abs(candidate.timecode - existing.timecode) < 3.0:
                    # Keep the one with higher confidence
                    if candidate.confidence > existing.confidence:
                        merged.remove(existing)
                        merged.append(candidate)
                    too_close = True
                    break
            
            if not too_close:
                merged.append(candidate)
        
        return merged
    
    def generate_intelligent_markers(self, candidates: List[MarkerCandidate], user_prompt: str, 
                                   prompt_intelligence: Dict, video_path: str, footage_data: Dict = None) -> List[FinalMarker]:
        """
        Generate smart descriptions for each marker based on user intent
        """
        final_markers = []
        
        for candidate in candidates:
            print(f"📝 Generating marker description for {candidate.timecode}s")
            
            # Generate enhanced description
            enhanced_description = self.enhance_marker_description(
                candidate, user_prompt, prompt_intelligence, video_path
            )
            
            # Convert to timecode
            timecode_str = self.seconds_to_frame_accurate_timecode(candidate.timecode)
            
            final_markers.append(FinalMarker(
                timecode=timecode_str,
                description=enhanced_description
            ))
        
        return final_markers
    
    def enhance_marker_description(self, candidate: MarkerCandidate, user_prompt: str, 
                                 prompt_intelligence: Dict, video_path: str) -> str:
        """
        Create intelligent marker description based on user's original prompt
        """
        try:
            # Build context for description generation
            context_parts = []
            
            if candidate.visual_description:
                context_parts.append(f"Visual: {candidate.visual_description}")
            
            if candidate.audio_transcript:
                context_parts.append(f"Audio: {candidate.audio_transcript}")
            
            context = " | ".join(context_parts) if context_parts else "No context available"
            
            # Generate smart description using the template from intent analysis
            description_prompt = f"""
            Create a natural, concise marker description (max 100 chars) for this video moment.
            Focus on WHAT is happening, not the type of shot/content.
            
            Context:
            {context}
            
            Guidelines:
            1. Start with the key action/content
            2. Be specific and descriptive
            3. Don't repeat terms like "graphic" or "animation" unless crucial
            4. Prioritize unique content over shot type
            5. For audio, focus on what was said
            6. Keep under 100 characters
            
            Return just the description text, nothing else.
            """
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You write concise, natural video marker descriptions focusing on content over shot type."},
                    {"role": "user", "content": description_prompt}
                ],
                temperature=0.3
            )
            
            description = response.choices[0].message.content.strip()
            
            # Clean up and truncate if needed
            description = description.replace('"', '').replace('\n', ' ')
            if len(description) > 100:
                description = description[:97] + "..."
            
            return description
            
        except Exception as e:
            print(f"⚠️ Description generation failed: {e}")
            # Fallback description
            return candidate.visual_description[:50] + "..." if candidate.visual_description else "Marker"
    
    def create_avid_markers_file(self, markers: List[FinalMarker], footage_data: Dict) -> str:
        """
        Create AVID Media Composer compatible markers file
        """
        filename = footage_data.get("INFO_Original_FileName", "Unknown")
        
        # AVID markers format (simplified - you may need to adjust based on actual AVID requirements)
        avid_content = f"""Avid Media Composer Markers
Project: {filename}
Date: {self.get_current_date()}

"""
        
        for i, marker in enumerate(markers, 1):
            avid_content += f"Marker {i:02d}\t{marker.timecode}\t{marker.description}\n"
        
        return avid_content
    
    def update_filemaker_markers(self, footage_id: str, markers: List[FinalMarker], avid_content: str):
        """
        Update FileMaker with generated markers
        """
        try:
            # Find footage record
            footage_records = self.session.find_records(
                CONFIG['layout_footage'],
                {"INFO_FTG_ID": footage_id}
            )
            
            if not footage_records:
                print(f"⚠️ Could not find footage record for {footage_id}")
                return False
            
            record_id = footage_records[0]["recordId"]
            
            # Create markers list formatted for FileMaker text field (readable format)
            markers_text = f"Generated {len(markers)} markers:\n\n"
            for i, marker in enumerate(markers, 1):
                markers_text += f"{i:2d}. {marker.timecode} - {marker.description}\n"
            
            # Update FileMaker with correct field names
            update_data = {
                "MARKERS_List": markers_text,
                "MARKERS_File": avid_content
            }
            
            print(f"🔄 Updating FileMaker fields:")
            print(f"   - MARKERS_List: {len(markers_text)} characters")
            print(f"   - MARKERS_File: {len(avid_content)} characters")
            
            success = self.session.update_record(
                CONFIG['layout_footage'],
                record_id,
                update_data
            )
            
            if success:
                print(f"✅ Updated FileMaker with {len(markers)} markers")
            else:
                print(f"❌ Failed to update FileMaker - check field names and permissions")
                
            return success
            
        except Exception as e:
            print(f"❌ FileMaker update error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    # Utility methods
    def calculate_keyword_similarity(self, keywords: List[str], text: str) -> float:
        """Calculate text similarity based on keyword presence with enhanced matching"""
        if not keywords or not text:
            return 0.0
        
        text_lower = text.lower()
        
        # Enhanced keyword matching
        matches = 0
        total_keywords = len(keywords)
        
        for keyword in keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in text_lower:
                matches += 1
                
        # Boost for exact phrase matches
        original_phrase = " ".join(keywords).lower()
        if original_phrase in text_lower:
            matches += 1  # Bonus for phrase match
            
        # Enhanced scoring for better results
        similarity = matches / total_keywords
        
        # Additional semantic matching for common terms
        science_terms = ['science', 'scientist', 'research', 'lab', 'laboratory', 'experiment', 'study']
        men_terms = ['man', 'men', 'male', 'guy', 'gentleman']
        
        if any(term in " ".join(keywords).lower() for term in science_terms):
            science_matches = sum(1 for term in science_terms if term in text_lower)
            similarity += science_matches * 0.1  # Boost for science terms
            
        if any(term in " ".join(keywords).lower() for term in men_terms):
            men_matches = sum(1 for term in men_terms if term in text_lower)
            similarity += men_matches * 0.1  # Boost for men terms
        
        return min(similarity, 1.0)
    
    def detect_speaker_change(self, prev_text: str, current_text: str) -> bool:
        """Simple heuristic to detect speaker changes"""
        # Look for dramatic changes in speaking style, content, etc.
        if not prev_text or not current_text:
            return False
        
        # Simple checks - you could make this more sophisticated
        word_overlap = len(set(prev_text.lower().split()) & set(current_text.lower().split()))
        total_words = len(set(prev_text.lower().split()) | set(current_text.lower().split()))
        
        overlap_ratio = word_overlap / total_words if total_words > 0 else 0
        return overlap_ratio < 0.3  # Low overlap suggests different speaker
    
    def get_current_date(self) -> str:
        """Get current date for file headers"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # FileMaker data access methods
    def get_footage_data(self, footage_id: str) -> Optional[Dict]:
        """Get footage record from FileMaker"""
        try:
            records = self.session.find_records(
                CONFIG['layout_footage'],
                {"INFO_FTG_ID": footage_id}
            )
            return records[0]["fieldData"] if records else None
        except Exception as e:
            print(f"❌ Error getting footage data: {e}")
            return None
    
    def get_keyframe_data(self, footage_id: str) -> List[Dict]:
        """Get all keyframes for footage from FileMaker"""
        try:
            records = self.session.find_records(
                CONFIG['layout_keyframes'],
                {"FootageID": footage_id}
            )
            return [record["fieldData"] for record in records]
        except Exception as e:
            print(f"❌ Error getting keyframe data: {e}")
            return []
    
    def frames_to_drop_frame_timecode(self, total_frames: int) -> str:
        """
        Convert frame count to SMPTE drop-frame timecode (29.97fps)
        """
        # Drop frame timecode constants
        FRAMES_PER_MINUTE = 1798  # 30 * 60 - 2
        FRAMES_PER_10MINUTES = 17982  # (FRAMES_PER_MINUTE * 10) + 2
        
        # Calculate various parts
        ten_minute_chunks = total_frames // FRAMES_PER_10MINUTES
        remaining_frames = total_frames % FRAMES_PER_10MINUTES
        minutes_in_chunk = (remaining_frames // FRAMES_PER_MINUTE) if remaining_frames > 0 else 0
        
        # Calculate final frame count with drops
        frames_dropped = (ten_minute_chunks * 18) + (minutes_in_chunk * 2)
        adjusted_frames = total_frames + frames_dropped
        
        # Convert to time components
        frames = adjusted_frames % 30
        seconds = (adjusted_frames // 30) % 60
        minutes = (adjusted_frames // (30 * 60)) % 60
        hours = adjusted_frames // (30 * 60 * 60)
        
        # Format with drop frame delimiter
        return f"{hours:02d}:{minutes:02d}:{seconds:02d};{frames:02d}"
    
    def frames_to_non_drop_timecode(self, total_frames: int) -> str:
        """
        Convert frame count to non-drop-frame timecode
        """
        fps = round(self.video_fps)
        frames = total_frames % fps
        seconds = (total_frames // fps) % 60
        minutes = (total_frames // (fps * 60)) % 60
        hours = total_frames // (fps * 60 * 60)
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"
    
    def add_timecode_offset(self, tc: str, offset_tc: str) -> str:
        """
        Add timecode offset to a timecode string
        """
        # Parse timecodes
        tc_parts = tc.replace(';', ':').split(':')
        offset_parts = offset_tc.replace(';', ':').split(':')
        
        # Convert to frames
        fps = round(self.video_fps)
        tc_frames = (
            int(tc_parts[0]) * 3600 * fps +
            int(tc_parts[1]) * 60 * fps +
            int(tc_parts[2]) * fps +
            int(tc_parts[3])
        )
        offset_frames = (
            int(offset_parts[0]) * 3600 * fps +
            int(offset_parts[1]) * 60 * fps +
            int(offset_parts[2]) * fps +
            int(offset_parts[3])
        )
        
        # Add frames and convert back
        total_frames = tc_frames + offset_frames
        
        # Use appropriate conversion based on drop frame setting
        if self.video_drop_frame and abs(self.video_fps - 29.97) < 0.01:
            return self.frames_to_drop_frame_timecode(total_frames)
        else:
            return self.frames_to_non_drop_timecode(total_frames)

def main():
    """
    Main function for testing - takes footage ID input from user
    """
    print("🎬 Smart Marker Generator - Testing Mode")
    print("=" * 50)
    
    # Check dependencies first
    try:
        import cv2
        print("✅ OpenCV (cv2) imported successfully")
    except ImportError:
        print("❌ OpenCV not found. Install with: pip install opencv-python")
        return
    
    try:
        import scenedetect
        print("✅ SceneDetect imported successfully")
    except ImportError:
        print("❌ SceneDetect not found. Install with: pip install scenedetect[opencv]")
        return
    
    # Get user input
    try:
        footage_id = input("Enter INFO_FTG_ID: ").strip()
        if not footage_id:
            print("❌ No footage ID provided")
            return
        
        user_prompt = input("Enter marker prompt (e.g., 'Find all close-ups'): ").strip()
        if not user_prompt:
            print("❌ No prompt provided")
            return
        
        print(f"\n🚀 Starting analysis...")
        print(f"Footage ID: {footage_id}")
        print(f"Prompt: {user_prompt}")
        
        # Test OpenAI connection
        try:
            openai_client = openai.OpenAI(api_key=CONFIG['openai_api_key'])
            test_response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Say 'test'"}],
                max_tokens=5
            )
            print("✅ OpenAI connection successful")
        except Exception as e:
            print(f"❌ OpenAI connection failed: {e}")
            print("Check your API key in the CONFIG section")
            return
        
        # Initialize generator
        generator = SmartMarkerGenerator()
        
        # Connect to FileMaker
        print("🔗 Connecting to FileMaker...")
        with FileMakerSession() as session:
            generator.session = session
            print("✅ FileMaker connection successful")
            
            # Process the request
            markers, avid_content = generator.process_marker_request(footage_id, user_prompt)
            
            # Display results
            print(f"\n🎯 Results:")
            print(f"Generated {len(markers)} markers")
            
            if markers:
                print("\nMarkers:")
                for i, marker in enumerate(markers, 1):
                    print(f"{i:2d}. {marker.timecode} - {marker.description}")
                
                # Save AVID file for testing
                avid_filename = f"markers_{footage_id}_{len(markers)}.txt"
                with open(avid_filename, 'w') as f:
                    f.write(avid_content)
                
                print(f"\n💾 AVID file saved as: {avid_filename}")
            else:
                print("\n⚠️ No markers generated. This could be because:")
                print("   - No keyframes have embeddings yet")
                print("   - Confidence threshold too high")
                print("   - Prompt doesn't match available content")
                print("   - Video file issues")
            
            print(f"✅ Complete!")
            
    except KeyboardInterrupt:
        print("\n👋 Cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()