#!/usr/bin/env python3
"""
Archive Detector - Automatic detection and URL pattern testing for new archives

Attempts to automatically detect URL patterns for unknown archive sources
by testing common URL formats and patterns.
"""

import requests
import time
import re
from datetime import datetime
import config


# Common URL patterns to test (in order of likelihood)
URL_PATTERNS = [
    "https://www.{source}.com/video/{id}",
    "https://www.{source}.com/footage/{id}",
    "https://www.{source}.com/clip/{id}",
    "https://{source}.com/video/{id}",
    "https://{source}.com/footage/{id}",
    "https://{source}.com/clip/{id}",
    "https://{source}.io/clip/{id}",
    "https://www.{source}.io/clip/{id}",
    "https://www.{source}.com/item/{id}",
    "https://{source}.com/item/{id}",
    "https://www.{source}.com/detail/{id}",
    "https://{source}.com/detail/{id}",
]


def normalize_source_name(source):
    """
    Normalize source name for URL testing.
    Remove spaces, convert to lowercase, etc.
    
    Args:
        source (str): Source name (e.g., "Critical Past")
        
    Returns:
        str: Normalized name (e.g., "criticalpast")
    """
    if not source:
        return ""
    
    # Remove spaces and special characters
    normalized = re.sub(r'[^a-zA-Z0-9]', '', source.lower())
    return normalized


def test_url_pattern(url, timeout=10):
    """
    Test if a URL pattern is valid by making a HEAD request.
    
    Args:
        url (str): URL to test
        timeout (int): Request timeout
        
    Returns:
        tuple: (success: bool, status_code: int, reason: str)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    
    try:
        response = requests.head(
            url,
            headers=headers,
            timeout=timeout,
            verify=False,
            allow_redirects=True
        )
        
        status_code = response.status_code
        
        # Success codes
        if status_code in [200, 301, 302]:
            return True, status_code, f"Valid (HTTP {status_code})"
        
        # Auth required (likely valid but needs login)
        if status_code == 403:
            return True, status_code, "Valid (403 - auth required)"
        
        # Not found
        if status_code == 404:
            return False, status_code, "Not found"
        
        # Other codes
        return False, status_code, f"Unexpected HTTP {status_code}"
        
    except requests.exceptions.Timeout:
        return False, None, "Timeout"
    except requests.exceptions.ConnectionError:
        return False, None, "Connection failed"
    except Exception as e:
        return False, None, f"Error: {str(e)}"


def detect_archive_pattern(filename, source):
    """
    Analyze filename to detect ID pattern.
    
    Args:
        filename (str): Filename to analyze
        source (str): Source name
        
    Returns:
        dict: Pattern information with suggested cleaning rules
    """
    # Remove file extension
    name_without_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
    
    pattern_info = {
        "filename": filename,
        "name_without_ext": name_without_ext,
        "has_hyphens": "-" in name_without_ext,
        "has_underscores": "_" in name_without_ext,
        "numeric_parts": [],
        "suggested_id": None
    }
    
    # Find numeric parts
    numeric_parts = re.findall(r'\d+', name_without_ext)
    pattern_info["numeric_parts"] = numeric_parts
    
    # Suggest most likely ID (first or longest numeric sequence)
    if numeric_parts:
        # Prefer longer sequences (more likely to be IDs)
        longest = max(numeric_parts, key=len)
        pattern_info["suggested_id"] = longest
    
    return pattern_info


def test_url_patterns(archival_id, source):
    """
    Test multiple URL patterns to find one that works.
    
    Args:
        archival_id (str): The archival ID to test
        source (str): Source name
        
    Returns:
        tuple: (url_root: str or None, tested_urls: list)
    """
    if not archival_id or not source:
        return None, []
    
    normalized_source = normalize_source_name(source)
    tested_urls = []
    
    print(f"  -> Testing URL patterns for {source} (ID: {archival_id})...")
    
    for pattern_template in URL_PATTERNS:
        # Generate URL from pattern
        try:
            url = pattern_template.format(source=normalized_source, id=archival_id)
        except KeyError:
            continue
        
        # Test the URL
        success, status_code, reason = test_url_pattern(url)
        
        tested_urls.append({
            "url": url,
            "success": success,
            "status_code": status_code,
            "reason": reason
        })
        
        # If successful, extract URL root
        if success:
            # Extract everything before the ID
            url_root = url.rsplit(archival_id, 1)[0]
            print(f"  -> ✅ Found working pattern: {url_root}")
            print(f"     Status: {reason}")
            return url_root, tested_urls
        
        # Small delay to avoid rate limiting
        time.sleep(0.5)
    
    print(f"  -> ❌ No working URL pattern found for {source}")
    return None, tested_urls


def add_url_to_filemaker(token, source, url_root):
    """
    Add a new URL root to FileMaker URLs table.
    
    Args:
        token (str): FileMaker token
        source (str): Archive name
        url_root (str): URL root
        
    Returns:
        bool: Success status
    """
    try:
        field_data = {
            "Archive": source,
            "URL Root": url_root
        }
        
        response = config.create_record(token, "URLs", field_data)
        
        if response and response.status_code in [200, 201]:
            print(f"  -> ✅ Added to FileMaker URLs table: {source}")
            return True
        else:
            print(f"  -> ❌ Failed to add to FileMaker: {response.status_code if response else 'No response'}")
            return False
            
    except Exception as e:
        print(f"  -> ❌ Error adding to FileMaker: {e}")
        return False


def write_detection_failure_to_dev_console(record_id, token, source, archival_id):
    """
    Write URL construction failure to AI_DevConsole field.
    
    Args:
        record_id (str): FileMaker record ID
        token (str): FileMaker token
        source (str): Archive name
        archival_id (str): Archival ID
    """
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"[{timestamp}] URL Construction Failed\nArchive: {source}\nID: {archival_id}\nNo matching URL pattern found - manual URL or metadata required"
        
        field_data = {"AI_DevConsole": message}
        config.update_record(token, "FOOTAGE", record_id, field_data)
        
    except Exception as e:
        print(f"  -> Warning: Could not write to DevConsole: {e}")


def auto_detect_and_register(source, archival_id, token, record_id=None):
    """
    Main entry point: Attempt to automatically detect and register a new archive.
    
    Args:
        source (str): Archive/source name
        archival_id (str): Sample archival ID
        token (str): FileMaker token
        record_id (str): Optional - FileMaker record ID for DevConsole logging
        
    Returns:
        str: URL root if successful, None if failed
    """
    print(f"  -> 🔍 Auto-detecting URL pattern for new archive: {source}")
    
    # Test URL patterns
    url_root, tested_urls = test_url_patterns(archival_id, source)
    
    if url_root:
        # Success! Add to FileMaker
        if add_url_to_filemaker(token, source, url_root):
            print(f"  -> ✅ Successfully registered {source}")
            return url_root
        else:
            print(f"  -> ⚠️ Found URL pattern but failed to register in FileMaker")
            return url_root  # Still return it for immediate use
    else:
        # Failed - log it
        print(f"  -> ❌ Could not construct URL for {source}")
        print(f"     Tested {len(tested_urls)} patterns without success")
        
        # Write to DevConsole if record_id provided
        if record_id:
            write_detection_failure_to_dev_console(record_id, token, source, archival_id)
        
        return None

