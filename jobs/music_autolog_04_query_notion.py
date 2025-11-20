#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path
import requests
import os

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["music_id"]

FIELD_MAPPING = {
    "music_id": "INFO_MUSIC_ID",
    "song_name": "INFO_Song_Name",
    "artist": "INFO_Artist",
    "album": "INFO_Album",
    "isrc_upc": "INFO_ISRC_UPC_Code",
    "cue_type": "INFO_Cue_Type",
    "url": "SPECS_URL",
    "performed_by": "INFO_PerformedBy",
    "composer": "PUBLISHING_Composer",
    "mood": "INFO_MOOD",
    "status": "AutoLog_Status"
}

# Notion API credentials
NOTION_KEY = os.getenv('NOTION_KEY')
NOTION_DB_ID = os.getenv('NOTION_DB_ID')
NOTION_VERSION = "2022-06-28"

# Validate required credentials
if not NOTION_KEY:
    raise ValueError("NOTION_KEY environment variable is required")
if not NOTION_DB_ID:
    raise ValueError("NOTION_DB_ID environment variable is required")

def query_notion_database(title, artist=None, album=None):
    """
    Query Notion database for a song by title, with optional artist/album confirmation.
    Returns ISRC/UPC if found, None otherwise.
    """
    try:
        print(f"  -> Querying Notion database...")
        print(f"     Title: {title}")
        if artist:
            print(f"     Artist: {artist}")
        if album:
            print(f"     Album: {album}")
        
        # Build Notion API query
        url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
        
        headers = {
            "Authorization": f"Bearer {NOTION_KEY}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json"
        }
        
        # Query by title (Notion uses filter syntax)
        query_body = {
            "filter": {
                "property": "Track Title",  # Notion database uses "Track Title" as title property
                "title": {
                    "contains": title
                }
            }
        }
        
        response = requests.post(
            url,
            headers=headers,
            json=query_body,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"  -> Notion API error: {response.status_code}")
            print(f"     Response: {response.text}")
            return None, None
        
        data = response.json()
        results = data.get('results', [])
        
        print(f"  -> Found {len(results)} potential matches in Notion")
        
        if not results:
            print(f"  -> No matches found for title: {title}")
            return None, "No matches found"
        
        # Process results to find best match with tiebreakers
        best_match = None
        match_confidence = 0
        all_matches = []
        
        for result in results:
            properties = result.get('properties', {})
            
            # Extract fields from Notion (using actual property names from database)
            notion_title = extract_notion_text(properties.get('Track Title', {}))
            notion_artist = extract_notion_text(properties.get('Artist', {}))
            notion_album = extract_notion_text(properties.get('Album', {}))
            notion_isrc_upc = extract_notion_text(properties.get('ISRC/UPC', {}))
            notion_type = extract_notion_text(properties.get('Type', {}))
            notion_url = extract_notion_text(properties.get('URL', {}))
            notion_performed_by = extract_notion_text(properties.get('Performed By', {}))
            notion_composer = extract_notion_text(properties.get('Composer', {}))
            notion_mood = extract_notion_text(properties.get('Mood/Keywords', {}))
            
            # Extract additional fields for tiebreaking
            notion_release_date = properties.get('Release Date', {}).get('number', '')
            notion_track_number = properties.get('Track Number', {}).get('number', '')
            
            print(f"  -> Checking match:")
            print(f"     Notion Title: {notion_title}")
            print(f"     Notion Artist: {notion_artist}")
            print(f"     Notion Album: {notion_album}")
            print(f"     Notion ISRC/UPC: {notion_isrc_upc}")
            print(f"     Notion Type: {notion_type}")
            print(f"     Notion URL: {notion_url}")
            print(f"     Notion Performed By: {notion_performed_by}")
            print(f"     Notion Composer: {notion_composer}")
            print(f"     Notion Mood/Keywords: {notion_mood}")
            
            # Calculate match confidence
            confidence = 0
            is_exact_title = False
            
            # Title match (required)
            if notion_title and title:
                if notion_title.lower() == title.lower():
                    confidence += 50  # Exact match
                    is_exact_title = True
                elif title.lower() in notion_title.lower() or notion_title.lower() in title.lower():
                    confidence += 30  # Partial match
            
            # Artist match (strong confirmation)
            if artist and notion_artist:
                if artist.lower() in notion_artist.lower() or notion_artist.lower() in artist.lower():
                    confidence += 30
            
            # Album match (additional confirmation)
            if album and notion_album:
                if album.lower() in notion_album.lower() or notion_album.lower() in album.lower():
                    confidence += 20
            
            print(f"     Match confidence: {confidence}%")
            
            # Calculate tiebreaker score (used when confidence is equal)
            tiebreaker_score = 0
            
            # Tiebreaker 1: Exact title match is better than partial (priority: 1000)
            if is_exact_title:
                tiebreaker_score += 1000
            
            # Tiebreaker 2: Has ISRC/UPC data (priority: 100)
            if notion_isrc_upc and notion_isrc_upc.strip():
                tiebreaker_score += 100
            
            # Tiebreaker 3: Data completeness (priority: 1 per field)
            if notion_artist and notion_artist.strip():
                tiebreaker_score += 1
            if notion_album and notion_album.strip():
                tiebreaker_score += 1
            if notion_release_date:
                tiebreaker_score += 1
            if notion_track_number:
                tiebreaker_score += 1
            
            # Store match with all metadata (including page ID for Notion updates)
            match_data = {
                'title': notion_title,
                'artist': notion_artist,
                'album': notion_album,
                'isrc_upc': notion_isrc_upc,
                'cue_type': notion_type,
                'url': notion_url,
                'performed_by': notion_performed_by,
                'composer': notion_composer,
                'mood': notion_mood,
                'confidence': confidence,
                'tiebreaker_score': tiebreaker_score,
                'is_exact_title': is_exact_title,
                'release_date': notion_release_date,
                'track_number': notion_track_number,
                'page_id': result.get('id', '')  # Store Notion page ID for updates
            }
            all_matches.append(match_data)
            
            # Keep best match (now with tiebreaker)
            if confidence > match_confidence:
                match_confidence = confidence
                best_match = match_data
            elif confidence == match_confidence and confidence > 0:
                # Same confidence - use tiebreaker
                if tiebreaker_score > best_match['tiebreaker_score']:
                    print(f"     -> Tiebreaker: {tiebreaker_score} > {best_match['tiebreaker_score']} (replacing)")
                    best_match = match_data
                else:
                    print(f"     -> Tiebreaker: {tiebreaker_score} <= {best_match['tiebreaker_score']} (keeping current)")
        
        # Check for remaining ties (same confidence AND tiebreaker)
        tied_matches = [m for m in all_matches 
                       if m['confidence'] == match_confidence 
                       and m['tiebreaker_score'] == best_match['tiebreaker_score']
                       and match_confidence > 0]
        
        if len(tied_matches) > 1:
            print(f"  -> ⚠️  WARNING: {len(tied_matches)} matches remain tied after tiebreakers")
            print(f"     Confidence: {match_confidence}%, Tiebreaker: {best_match['tiebreaker_score']}")
            for i, m in enumerate(tied_matches, 1):
                print(f"     #{i}: {m['title']} by {m['artist']}")
            print(f"     Using first match, but manual verification recommended")
        
        # Decide if match is good enough
        if best_match and match_confidence >= 50:  # At least 50% confidence
            print(f"  -> ✅ MATCH FOUND (confidence: {match_confidence}%, tiebreaker: {best_match['tiebreaker_score']})")
            print(f"     Title: {best_match['title']}")
            print(f"     Artist: {best_match['artist']}")
            print(f"     Album: {best_match['album']}")
            print(f"     ISRC/UPC: {best_match['isrc_upc']}")
            print(f"     Type: {best_match['cue_type']}")
            print(f"     URL: {best_match['url']}")
            print(f"     Performed By: {best_match['performed_by']}")
            print(f"     Composer: {best_match['composer']}")
            print(f"     Mood/Keywords: {best_match['mood']}")
            print(f"     Exact title match: {'Yes' if best_match['is_exact_title'] else 'No'}")
            
            return best_match, f"Match found (confidence: {match_confidence}%)"
        else:
            print(f"  -> ❌ No confident match (best confidence: {match_confidence}%)")
            return None, f"No confident match (best: {match_confidence}%)"
        
    except requests.exceptions.Timeout:
        print(f"  -> Notion API timeout")
        return None, "API timeout"
    except requests.exceptions.ConnectionError as e:
        print(f"  -> Notion API connection error: {e}")
        return None, "Connection error"
    except Exception as e:
        print(f"  -> Error querying Notion: {e}")
        import traceback
        traceback.print_exc()
        return None, f"Error: {str(e)}"

def update_notion_imported_status(page_id):
    """Update Notion page to mark as imported to FileMaker."""
    try:
        if not page_id:
            print(f"  -> No Notion page ID available, skipping import status update")
            return False
        
        print(f"  -> Updating Notion: Checking 'Imported to FM' checkbox...")
        
        # Notion API endpoint for updating a page
        url = f"https://api.notion.com/v1/pages/{page_id}"
        
        headers = {
            "Authorization": f"Bearer {NOTION_KEY}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION
        }
        
        # Update the "Imported to FM" checkbox property
        payload = {
            "properties": {
                "Imported to FM": {
                    "checkbox": True
                }
            }
        }
        
        response = requests.patch(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 200:
            print(f"  -> ✅ Notion page updated: 'Imported to FM' checked")
            return True
        else:
            print(f"  -> ⚠️  Failed to update Notion page: {response.status_code}")
            print(f"     Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"  -> ⚠️  Notion API timeout while updating import status")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"  -> ⚠️  Notion API connection error: {e}")
        return False
    except Exception as e:
        print(f"  -> ⚠️  Error updating Notion import status: {e}")
        return False

def extract_notion_text(property_obj):
    """Extract text from various Notion property types."""
    try:
        prop_type = property_obj.get('type')
        
        if prop_type == 'title':
            title_array = property_obj.get('title', [])
            if title_array:
                return title_array[0].get('plain_text', '')
        
        elif prop_type == 'rich_text':
            rich_text_array = property_obj.get('rich_text', [])
            if rich_text_array:
                return rich_text_array[0].get('plain_text', '')
        
        elif prop_type == 'select':
            select_obj = property_obj.get('select', {})
            if select_obj:
                return select_obj.get('name', '')
        
        elif prop_type == 'multi_select':
            multi_select_array = property_obj.get('multi_select', [])
            if multi_select_array:
                # Join multiple selections with comma
                return ', '.join([item.get('name', '') for item in multi_select_array])
        
        elif prop_type == 'number':
            num_val = property_obj.get('number', '')
            return str(num_val) if num_val is not None else ''
        
        elif prop_type == 'url':
            return property_obj.get('url', '')
        
        elif prop_type == 'email':
            return property_obj.get('email', '')
        
        elif prop_type == 'phone_number':
            return property_obj.get('phone_number', '')
        
        return ''
        
    except Exception as e:
        print(f"  -> Error extracting Notion text: {e}")
        return ''

def query_notion_for_isrc(music_id, token):
    """Query Notion database for ISRC/UPC code based on song metadata."""
    try:
        print(f"🔍 Step 4: Query Notion Database")
        print(f"  -> Music ID: {music_id}")
        
        # Get record ID
        record_id = config.find_record_id(
            token, 
            "Music", 
            {FIELD_MAPPING["music_id"]: f"=={music_id}"}
        )
        print(f"  -> Record ID: {record_id}")
        
        # Get current metadata from FileMaker
        record_data = config.get_record(token, "Music", record_id)
        
        song_name = record_data.get(FIELD_MAPPING["song_name"], "")
        artist = record_data.get(FIELD_MAPPING["artist"], "")
        album = record_data.get(FIELD_MAPPING["album"], "")
        current_isrc = record_data.get(FIELD_MAPPING["isrc_upc"], "")
        current_cue_type = record_data.get(FIELD_MAPPING["cue_type"], "")
        current_url = record_data.get(FIELD_MAPPING["url"], "")
        current_performed_by = record_data.get(FIELD_MAPPING["performed_by"], "")
        current_composer = record_data.get(FIELD_MAPPING["composer"], "")
        current_mood = record_data.get(FIELD_MAPPING["mood"], "")
        
        print(f"  -> Song: {song_name}")
        print(f"  -> Artist: {artist}")
        print(f"  -> Album: {album}")
        print(f"  -> Current ISRC/UPC: {current_isrc or '(empty)'}")
        print(f"  -> Current Cue Type: {current_cue_type or '(empty)'}")
        print(f"  -> Current URL: {current_url or '(empty)'}")
        print(f"  -> Current Performed By: {current_performed_by or '(empty)'}")
        print(f"  -> Current Composer: {current_composer or '(empty)'}")
        print(f"  -> Current Mood/Keywords: {current_mood or '(empty)'}")
        
        # Check if we should skip (all fields already populated)
        has_isrc = current_isrc and current_isrc.strip()
        has_type = current_cue_type and current_cue_type.strip()
        has_url = current_url and current_url.strip()
        has_performed_by = current_performed_by and current_performed_by.strip()
        has_composer = current_composer and current_composer.strip()
        has_mood = current_mood and current_mood.strip()
        
        if has_isrc and has_type and has_url and has_performed_by and has_composer and has_mood:
            print(f"  -> All Notion fields already populated in FileMaker, skipping query")
            print(f"✅ Step 4 complete: Notion data already populated")
            return True
        
        if not song_name or not song_name.strip():
            print(f"  -> No song name available, cannot query Notion")
            print(f"⚠️  Step 4 skipped: No song name to search")
            return True  # Not a failure, just skip
        
        # Query Notion database
        notion_match, match_info = query_notion_database(song_name, artist, album)
        
        # Update FileMaker if we found a match
        if notion_match:
            print(f"  -> Updating FileMaker with Notion data...")
            
            update_data = {}
            
            # Only update fields that are currently empty in FileMaker
            if not has_isrc and notion_match.get('isrc_upc'):
                update_data[FIELD_MAPPING["isrc_upc"]] = notion_match['isrc_upc'].strip()
                print(f"     ISRC/UPC: {notion_match['isrc_upc']}")
            
            if not has_type and notion_match.get('cue_type'):
                update_data[FIELD_MAPPING["cue_type"]] = notion_match['cue_type'].strip()
                print(f"     Cue Type: {notion_match['cue_type']}")
            
            if not has_url and notion_match.get('url'):
                update_data[FIELD_MAPPING["url"]] = notion_match['url'].strip()
                print(f"     URL: {notion_match['url']}")
            
            if not has_performed_by and notion_match.get('performed_by'):
                update_data[FIELD_MAPPING["performed_by"]] = notion_match['performed_by'].strip()
                print(f"     Performed By: {notion_match['performed_by']}")
            
            if not has_composer and notion_match.get('composer'):
                update_data[FIELD_MAPPING["composer"]] = notion_match['composer'].strip()
                print(f"     Composer: {notion_match['composer']}")
            
            if not has_mood and notion_match.get('mood'):
                update_data[FIELD_MAPPING["mood"]] = notion_match['mood'].strip()
                print(f"     Mood/Keywords: {notion_match['mood']}")
            
            if update_data:
                config.update_record(token, "Music", record_id, update_data)
                print(f"  -> FileMaker record updated with {len(update_data)} field(s) from Notion")
                
                # Update Notion to mark as imported to FileMaker
                notion_page_id = notion_match.get('page_id', '')
                if notion_page_id:
                    update_notion_imported_status(notion_page_id)
                else:
                    print(f"  -> ⚠️  No Notion page ID available to update import status")
                
                print(f"✅ Step 4 complete: Data retrieved from Notion ({match_info})")
            else:
                print(f"  -> No new data to update (all fields already populated)")
                
                # Still update Notion if we have a match (data was already synced previously)
                notion_page_id = notion_match.get('page_id', '')
                if notion_page_id:
                    update_notion_imported_status(notion_page_id)
                
                print(f"✅ Step 4 complete: Notion match found but no updates needed")
            
            return True
        else:
            print(f"  -> No match found in Notion ({match_info})")
            print(f"⚠️  Step 4 complete: No matching data in Notion")
            return True  # Not a failure, just no match found
        
    except Exception as e:
        print(f"❌ Error in query_notion_for_isrc: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: music_autolog_04_query_notion.py <music_id> <token>")
        sys.exit(1)
    
    music_id = sys.argv[1]
    token = sys.argv[2]
    
    success = query_notion_for_isrc(music_id, token)
    sys.exit(0 if success else 1)

