import requests
import urllib3
import warnings
import json
from typing import Dict, List

# Suppress SSL warnings
warnings.filterwarnings('ignore')
urllib3.disable_warnings()

# Config
CONFIG = {
    'server': '10.0.222.144',
    'db_name': 'Emancipation to Exodus',
    'username': 'Background',
    'password': 'july1776',
    'layout_keyframes': 'Keyframes',
    'layout_footage': 'Footage'
}

class FileMakerDiagnostic:
    def __init__(self):
        self.server = CONFIG['server']
        self.db_encoded = CONFIG['db_name'].replace(" ", "%20")
        self.username = CONFIG['username']
        self.password = CONFIG['password']
        self.token = None
        self.headers = None
    
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
        print("✅ Authenticated with FileMaker")
    
    def logout(self):
        """Logout from FileMaker"""
        if self.token:
            logout_url = f"https://{self.server}/fmi/data/vLatest/databases/{self.db_encoded}/sessions/{self.token}"
            requests.delete(logout_url, headers={"Authorization": f"Bearer {self.token}"}, verify=False)
            print("✅ Logged out from FileMaker")
    
    def find_records(self, layout: str, query: Dict) -> List[Dict]:
        """Find records in FileMaker"""
        find_url = f"https://{self.server}/fmi/data/vLatest/databases/{self.db_encoded}/layouts/{layout}/_find"
        find_response = requests.post(find_url, headers=self.headers, json={"query": [query]}, verify=False)
        
        if find_response.status_code != 200:
            print(f"❌ Find failed: {find_response.status_code} {find_response.text}")
            return []
        
        return find_response.json().get("response", {}).get("data", [])
    
    def analyze_footage(self, footage_id: str):
        """Analyze specific footage and its keyframes"""
        print(f"\n🔍 ANALYZING FOOTAGE: {footage_id}")
        print("=" * 60)
        
        # Get footage record
        footage_records = self.find_records(CONFIG['layout_footage'], {"INFO_FTG_ID": footage_id})
        
        if not footage_records:
            print(f"❌ No footage record found for {footage_id}")
            return
        
        footage_data = footage_records[0]["fieldData"]
        print(f"📁 Filename: {footage_data.get('Filename', 'N/A')}")
        print(f"📁 Original Filename: {footage_data.get('INFO_Original_FileName', 'N/A')}")
        print(f"📁 File Path: {footage_data.get('SPECS_Filepath_Server', 'N/A')}")
        print(f"📝 Current Description: {footage_data.get('INFO_Description', 'N/A')}")
        print(f"📝 Current Title: {footage_data.get('INFO_Title', 'N/A')}")
        
        # Get all keyframes for this footage
        keyframe_records = self.find_records(CONFIG['layout_keyframes'], {"FootageID": footage_id})
        
        print(f"\n🎯 KEYFRAMES ANALYSIS:")
        print(f"📊 Total keyframes found: {len(keyframe_records)}")
        
        if not keyframe_records:
            print("❌ No keyframes found!")
            return
        
        # Analyze keyframe statuses
        status_counts = {}
        for record in keyframe_records:
            status = record["fieldData"].get("Keyframe_Status", "Unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"\n📈 STATUS BREAKDOWN:")
        for status, count in status_counts.items():
            print(f"   {status}: {count} keyframes")
        
        # Analyze keyframe content
        print(f"\n📝 CONTENT ANALYSIS:")
        
        captions_with_content = 0
        transcripts_with_content = 0
        empty_captions = 0
        empty_transcripts = 0
        
        sample_data = []
        
        for i, record in enumerate(keyframe_records):
            field_data = record["fieldData"]
            keyframe_id = field_data.get("KeyframeID", f"Unknown_{i}")
            timecode = field_data.get("Timecode_IN", "N/A")
            status = field_data.get("Keyframe_Status", "Unknown")
            
            # Check captions
            caption = field_data.get("Keyframe_GPT_Caption", "")
            caption = caption.strip() if caption else ""
            
            # Check transcripts  
            transcript = field_data.get("Keyframe_Transcript", "")
            transcript = transcript.strip() if transcript else ""
            
            if caption:
                captions_with_content += 1
            else:
                empty_captions += 1
                
            if transcript:
                transcripts_with_content += 1
            else:
                empty_transcripts += 1
            
            # Collect sample data (first 3 keyframes)
            if i < 3:
                sample_data.append({
                    'id': keyframe_id,
                    'timecode': timecode,
                    'status': status,
                    'caption_length': len(caption),
                    'caption': caption[:100] + "..." if len(caption) > 100 else caption,
                    'transcript_length': len(transcript),
                    'transcript': transcript[:100] + "..." if len(transcript) > 100 else transcript
                })
        
        print(f"   📸 Captions with content: {captions_with_content}/{len(keyframe_records)}")
        print(f"   📸 Empty captions: {empty_captions}/{len(keyframe_records)}")
        print(f"   🎵 Transcripts with content: {transcripts_with_content}/{len(keyframe_records)}")
        print(f"   🎵 Empty transcripts: {empty_transcripts}/{len(keyframe_records)}")
        
        # Show sample data
        print(f"\n📋 SAMPLE KEYFRAME DATA:")
        for sample in sample_data:
            print(f"   🎯 Keyframe: {sample['id']}")
            print(f"      ⏰ Timecode: {sample['timecode']}")
            print(f"      📊 Status: {sample['status']}")
            print(f"      📸 Caption ({sample['caption_length']} chars): {repr(sample['caption'])}")
            print(f"      🎵 Transcript ({sample['transcript_length']} chars): {repr(sample['transcript'])}")
            print()
        
        # Generate the CSV that would be sent to OpenAI
        print(f"\n📄 CSV DATA THAT WOULD BE SENT TO OPENAI:")
        csv_lines = ["Frame,Visual Description,Audio Transcript"]
        
        for record in keyframe_records[:5]:  # Show first 5 for brevity
            field_data = record["fieldData"]
            keyframe_id = field_data.get("KeyframeID", "")
            caption = field_data.get("Keyframe_GPT_Caption", "").replace("\n", " ").strip()
            transcript = field_data.get("Keyframe_Transcript", "").replace("\n", " ").strip()
            csv_lines.append(f"{keyframe_id},{caption},{transcript}")
        
        csv_preview = "\n".join(csv_lines)
        print(csv_preview)
        
        if len(keyframe_records) > 5:
            print(f"... (showing first 5 of {len(keyframe_records)} keyframes)")
        
        # Analysis summary
        print(f"\n🔍 DIAGNOSIS:")
        
        if empty_captions > len(keyframe_records) * 0.8:
            print("   ⚠️  ISSUE: Most captions are empty - thumbnail generation or captioning failed")
        
        if empty_transcripts > len(keyframe_records) * 0.8:
            print("   ℹ️  INFO: Most transcripts are empty - this is normal for silent video")
        
        if captions_with_content == 0 and transcripts_with_content == 0:
            print("   🚨 CRITICAL: No meaningful content found - this explains the 'no content' AI response")
        
        if captions_with_content > 0:
            print(f"   ✅ GOOD: {captions_with_content} keyframes have visual descriptions")
        
        if transcripts_with_content > 0:
            print(f"   ✅ GOOD: {transcripts_with_content} keyframes have audio content")

def main():
    """Main diagnostic function"""
    print("🩺 FileMaker Data Diagnostic Tool")
    print("================================")
    
    # Get footage ID to analyze
    footage_id = input("Enter Footage ID to analyze (e.g., LF2755): ").strip()
    
    if not footage_id:
        print("❌ No footage ID provided")
        return
    
    diagnostic = FileMakerDiagnostic()
    
    try:
        diagnostic.authenticate()
        diagnostic.analyze_footage(footage_id)
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        diagnostic.logout()

if __name__ == "__main__":
    main()