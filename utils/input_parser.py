#!/usr/bin/env python3
"""
Input Parser Utility

Standardized input parsing for job scripts that supports multiple ID formats:
- Single ID: "S04871"
- JSON array: '["S04871", "S04872", "S04873"]'
- Comma-separated: "S04871,S04872,S04873"
- Line-separated: "S04871\nS04872\nS04873"
- Space-separated: "S04871 S04872 S04873"
"""

import json
import sys
from typing import List, Union


def parse_input_ids(input_string: str) -> List[str]:
    """
    Parse input string into a list of IDs, supporting multiple formats.
    
    Args:
        input_string: Input string that may contain single or multiple IDs
        
    Returns:
        List of cleaned ID strings
        
    Examples:
        >>> parse_input_ids("S04871")
        ['S04871']
        
        >>> parse_input_ids('["S04871", "S04872"]')
        ['S04871', 'S04872']
        
        >>> parse_input_ids("S04871,S04872,S04873")
        ['S04871', 'S04872', 'S04873']
        
        >>> parse_input_ids("S04871\nS04872\nS04873")
        ['S04871', 'S04872', 'S04873']
    """
    if not input_string or not input_string.strip():
        return []
    
    input_string = input_string.strip()
    
    # Try JSON parsing first (most explicit format)
    try:
        parsed_ids = json.loads(input_string)
        if isinstance(parsed_ids, list):
            return [str(id).strip() for id in parsed_ids if str(id).strip()]
        else:
            return [str(parsed_ids).strip()]
    except json.JSONDecodeError:
        pass
    
    # Try comma-separated values
    if ',' in input_string:
        ids = [id.strip() for id in input_string.split(',') if id.strip()]
        if ids:
            return ids
    
    # Try line-separated values (newlines or carriage returns)
    if '\n' in input_string or '\r' in input_string:
        # Handle both \n and \r\n and \r
        cleaned_input = input_string.replace('\r\n', '\n').replace('\r', '\n')
        ids = [id.strip() for id in cleaned_input.split('\n') if id.strip()]
        if ids:
            return ids
    
    # Try space-separated values (but be careful with single IDs that might have spaces)
    if ' ' in input_string:
        # Only split on spaces if it looks like multiple IDs
        # Check if it starts with a common ID prefix or has multiple words
        words = input_string.split()
        if len(words) > 1:
            # Check if words look like IDs (start with common prefixes)
            id_prefixes = ['S', 'F', 'AF', 'FTG']  # Common ID prefixes
            if any(word.startswith(tuple(id_prefixes)) for word in words):
                ids = [word.strip() for word in words if word.strip()]
                if ids:
                    return ids
    
    # Single ID as string
    return [input_string.strip()]


def validate_ids(ids: List[str], expected_prefixes: List[str] = None) -> tuple[List[str], List[str]]:
    """
    Validate a list of IDs and return valid and invalid IDs.
    
    Args:
        ids: List of ID strings to validate
        expected_prefixes: List of expected ID prefixes (e.g., ['S', 'F', 'AF'])
        
    Returns:
        Tuple of (valid_ids, invalid_ids)
    """
    if not expected_prefixes:
        expected_prefixes = ['S', 'F', 'AF', 'FTG']  # Default prefixes
    
    valid_ids = []
    invalid_ids = []
    
    for id_str in ids:
        if not id_str:
            continue
            
        # Check if ID starts with expected prefix
        if any(id_str.startswith(prefix) for prefix in expected_prefixes):
            valid_ids.append(id_str)
        else:
            invalid_ids.append(id_str)
    
    return valid_ids, invalid_ids


def format_input_summary(ids: List[str], script_name: str = "script") -> str:
    """
    Format a summary of input IDs for logging.
    
    Args:
        ids: List of ID strings
        script_name: Name of the script for context
        
    Returns:
        Formatted summary string
    """
    if not ids:
        return f"📋 {script_name}: No IDs provided"
    
    if len(ids) == 1:
        return f"📋 {script_name}: Processing single ID: {ids[0]}"
    else:
        preview = ids[:5]
        return f"📋 {script_name}: Processing {len(ids)} IDs: {preview}{'...' if len(ids) > 5 else ''}"


def get_input_from_argv() -> List[str]:
    """
    Get input from sys.argv[1] and parse it into a list of IDs.
    
    Returns:
        List of parsed ID strings
        
    Raises:
        SystemExit: If no input is provided
    """
    if len(sys.argv) < 2:
        sys.stderr.write("ERROR: No input provided. Expected: script.py <input>\n")
        sys.exit(1)
    
    input_string = sys.argv[1]
    return parse_input_ids(input_string)


if __name__ == "__main__":
    # Test the parser
    test_cases = [
        "S04871",
        '["S04871", "S04872", "S04873"]',
        "S04871,S04872,S04873",
        "S04871\nS04872\nS04873",
        "S04871 S04872 S04873",
        "S04871, S04872 , S04873",
        "S04871\n\nS04872\n\nS04873",
        "",
        "   ",
        "S04871,invalid,F04872"
    ]
    
    print("Testing input parser:")
    for test in test_cases:
        result = parse_input_ids(test)
        print(f"Input: {repr(test)}")
        print(f"Output: {result}")
        print() 