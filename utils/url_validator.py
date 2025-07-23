#!/usr/bin/env python3
"""
URL Validation and Construction Utilities

This module provides utilities for:
- Validating URLs before use
- Cleaning archival IDs for URL construction
- Testing URL accessibility
"""

import requests
import re
from urllib.parse import urlparse
import time

def clean_archival_id_for_url(archival_id, source):
    """
    Clean archival ID by removing source-specific prefixes.
    
    Args:
        archival_id (str): The original archival ID
        source (str): The source/archive name
    
    Returns:
        str: Cleaned archival ID
    """
    if not archival_id:
        return archival_id
    
    cleaned_id = archival_id.strip()
    
    # Getty Images specific cleaning
    if source and "getty" in source.lower():
        # Remove Getty Images prefixes
        prefixes_to_remove = [
            "GettyImages-",
            "Getty Images-",
            "Getty-",
            "GI-",
            "gettyimages-"
        ]
        for prefix in prefixes_to_remove:
            if cleaned_id.lower().startswith(prefix.lower()):
                cleaned_id = cleaned_id[len(prefix):]
                break
        
        # Remove Getty Images suffixes (like -640_adpp, -640, etc.)
        # Common Getty Images suffixes
        suffixes_to_remove = [
            "-640_adpp",
            "-640",
            "-480",
            "-360",
            "-240",
            "_adpp",
            "_preview",
            "_thumbnail"
        ]
        for suffix in suffixes_to_remove:
            if cleaned_id.lower().endswith(suffix.lower()):
                cleaned_id = cleaned_id[:-len(suffix)]
                break
    
    # Shutterstock specific cleaning
    elif source and "shutterstock" in source.lower():
        # Remove Shutterstock prefixes
        prefixes_to_remove = [
            "Shutterstock-",
            "SS-",
            "ST-"
        ]
        for prefix in prefixes_to_remove:
            if cleaned_id.startswith(prefix):
                cleaned_id = cleaned_id[len(prefix):]
                break
    
    # Adobe Stock specific cleaning
    elif source and "adobe" in source.lower():
        # Remove Adobe Stock prefixes
        prefixes_to_remove = [
            "AdobeStock-",
            "AS-",
            "Adobe-"
        ]
        for prefix in prefixes_to_remove:
            if cleaned_id.startswith(prefix):
                cleaned_id = cleaned_id[len(prefix):]
                break
    
    return cleaned_id

def validate_url_format(url):
    """
    Validate URL format without making network requests.
    
    Args:
        url (str): URL to validate
        
    Returns:
        dict: Validation result with 'valid' boolean and 'reason' string
    """
    if not url or not isinstance(url, str):
        return {"valid": False, "reason": "URL is empty or not a string"}
    
    url = url.strip()
    if not url:
        return {"valid": False, "reason": "URL is empty after stripping"}
    
    # Basic URL format validation
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return {"valid": False, "reason": "URL missing scheme or domain"}
        
        # Check for valid schemes
        if parsed.scheme not in ['http', 'https']:
            return {"valid": False, "reason": f"Invalid scheme: {parsed.scheme}"}
        
        # Check for valid domain
        if len(parsed.netloc) < 3:
            return {"valid": False, "reason": "Domain too short"}
        
        # Check for common issues
        if '..' in url or '//' in url[8:]:  # After http:// or https://
            return {"valid": False, "reason": "URL contains invalid path sequences"}
        
        return {"valid": True, "reason": "URL format is valid"}
        
    except Exception as e:
        return {"valid": False, "reason": f"URL parsing error: {str(e)}"}

def test_url_accessibility(url, timeout=10, max_retries=2):
    """
    Test if a URL is accessible by making a HEAD request.
    
    Args:
        url (str): URL to test
        timeout (int): Request timeout in seconds
        max_retries (int): Maximum number of retry attempts
        
    Returns:
        dict: Test result with 'accessible' boolean, 'status_code', and 'reason'
    """
    if not url:
        return {"accessible": False, "status_code": None, "reason": "URL is empty"}
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for attempt in range(max_retries):
        try:
            print(f"  -> Testing URL accessibility (attempt {attempt + 1}/{max_retries}): {url}")
            
            response = requests.head(
                url, 
                headers=headers, 
                timeout=timeout, 
                verify=False,
                allow_redirects=True
            )
            
            if response.status_code < 400:
                return {
                    "accessible": True, 
                    "status_code": response.status_code, 
                    "reason": f"URL accessible (HTTP {response.status_code})"
                }
            else:
                return {
                    "accessible": False, 
                    "status_code": response.status_code, 
                    "reason": f"HTTP error {response.status_code}"
                }
                
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                print(f"  -> Timeout on attempt {attempt + 1}, retrying...")
                time.sleep(1)
                continue
            return {
                "accessible": False, 
                "status_code": None, 
                "reason": "Request timeout"
            }
            
        except requests.exceptions.ConnectionError:
            if attempt < max_retries - 1:
                print(f"  -> Connection error on attempt {attempt + 1}, retrying...")
                time.sleep(1)
                continue
            return {
                "accessible": False, 
                "status_code": None, 
                "reason": "Connection error"
            }
            
        except Exception as e:
            return {
                "accessible": False, 
                "status_code": None, 
                "reason": f"Request error: {str(e)}"
            }
    
    return {
        "accessible": False, 
        "status_code": None, 
        "reason": "All retry attempts failed"
    }

def validate_and_test_url(url, test_accessibility=True, timeout=10):
    """
    Comprehensive URL validation including format and accessibility testing.
    
    Args:
        url (str): URL to validate
        test_accessibility (bool): Whether to test URL accessibility
        timeout (int): Timeout for accessibility test
        
    Returns:
        dict: Complete validation result
    """
    # Step 1: Format validation
    format_result = validate_url_format(url)
    if not format_result["valid"]:
        return {
            "valid": False,
            "accessible": False,
            "status_code": None,
            "reason": format_result["reason"],
            "format_valid": False
        }
    
    # Step 2: Accessibility testing (if requested)
    if test_accessibility:
        accessibility_result = test_url_accessibility(url, timeout)
        return {
            "valid": True,
            "accessible": accessibility_result["accessible"],
            "status_code": accessibility_result["status_code"],
            "reason": accessibility_result["reason"],
            "format_valid": True
        }
    else:
        return {
            "valid": True,
            "accessible": None,  # Not tested
            "status_code": None,
            "reason": "Format valid, accessibility not tested",
            "format_valid": True
        }

def construct_url_from_source_and_id(url_root, archival_id, source=None):
    """
    Construct a URL from URL root and archival ID with proper cleaning.
    
    Args:
        url_root (str): The URL root from the URLs layout
        archival_id (str): The archival ID
        source (str): The source/archive name for cleaning
        
    Returns:
        str: Constructed URL or None if construction fails
    """
    if not url_root or not archival_id:
        return None
    
    # Clean the archival ID
    cleaned_id = clean_archival_id_for_url(archival_id, source)
    if not cleaned_id:
        print(f"  -> Warning: Archival ID became empty after cleaning")
        return None
    
    # Construct the URL
    if url_root.endswith('/'):
        constructed_url = f"{url_root}{cleaned_id}"
    else:
        constructed_url = f"{url_root}/{cleaned_id}"
    
    print(f"  -> Constructed URL: {constructed_url}")
    print(f"  -> Original ID: {archival_id}")
    print(f"  -> Cleaned ID: {cleaned_id}")
    
    return constructed_url 