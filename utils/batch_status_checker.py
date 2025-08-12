#!/usr/bin/env python3
"""
Batch Status Checker for Footage AutoLog

This utility provides efficient batch checking of footage statuses
to minimize FileMaker API calls when checking parent dependencies.
"""

import requests
import logging
import time
from typing import Dict, List, Set, Optional
import sys
from pathlib import Path

# Add parent directory to path for config import
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

class BatchStatusChecker:
    """Efficiently batch check footage statuses."""
    
    def __init__(self, token: str):
        """
        Initialize batch status checker.
        
        Args:
            token: FileMaker authentication token
        """
        self.token = token
        self.field_mapping = {
            "footage_id": "INFO_FTG_ID",
            "status": "AutoLog_Status"
        }
    
    def batch_check_footage_statuses(self, footage_ids: Set[str], max_retries: int = 3) -> Dict[str, Dict]:
        """
        Batch check multiple footage statuses with a single API call.
        
        Args:
            footage_ids: Set of footage IDs to check
            max_retries: Maximum number of retry attempts
            
        Returns:
            Dict mapping footage_id -> status_data
        """
        if not footage_ids:
            return {}
        
        current_token = self.token
        
        # Convert set to list for query building
        footage_id_list = list(footage_ids)
        
        # Build OR query for multiple footage IDs
        # FileMaker find syntax: [{"field": "value1"}, {"field": "value2"}] creates OR
        query_conditions = [{self.field_mapping["footage_id"]: footage_id} for footage_id in footage_id_list]
        
        find_payload = {
            "query": query_conditions,
            "limit": str(len(footage_id_list) + 10)  # Buffer for safety
        }
        
        for attempt in range(max_retries):
            try:
                logging.info(f"🔍 Batch checking {len(footage_ids)} footage statuses...")
                
                response = requests.post(
                    config.url("layouts/FOOTAGE/_find"),
                    headers=config.api_headers(current_token),
                    json=find_payload,
                    verify=False,
                    timeout=30
                )
                
                if response.status_code == 401:
                    # Token expired, refresh and retry
                    current_token = config.get_token()
                    continue
                
                # Handle no records found (404 is normal)
                if response.status_code == 404:
                    logging.warning(f"⚠️ No footage records found for batch status check")
                    return {}
                
                response.raise_for_status()
                
                # Process results
                result_data = response.json()['response']['data']
                status_map = {}
                
                for record in result_data:
                    footage_id = record['fieldData'].get(self.field_mapping["footage_id"])
                    status = record['fieldData'].get(self.field_mapping["status"], "Unknown")
                    
                    if footage_id:
                        status_map[footage_id] = {
                            'status': status,
                            'record_id': record['recordId'],
                            'record_data': record['fieldData']
                        }
                
                logging.info(f"✅ Batch status check: Found {len(status_map)} out of {len(footage_ids)} requested records")
                
                # Log any missing footage IDs
                missing_ids = footage_ids - set(status_map.keys())
                if missing_ids:
                    logging.warning(f"⚠️ Missing footage records: {list(missing_ids)[:5]}{'...' if len(missing_ids) > 5 else ''}")
                
                return status_map
                
            except requests.exceptions.Timeout:
                logging.warning(f"⏱️ Timeout on batch status check attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                    
            except requests.exceptions.ConnectionError as e:
                logging.warning(f"🌐 Connection error on batch status check attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                    
            except Exception as e:
                logging.error(f"❌ Error in batch status check attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
        
        logging.error(f"❌ Failed to batch check footage statuses after {max_retries} attempts")
        return {}
    
    def batch_check_single_status_type(self, status_to_check: str, max_retries: int = 3) -> List[Dict]:
        """
        Find all footage records with a specific status.
        
        Args:
            status_to_check: The status to search for
            max_retries: Maximum number of retry attempts
            
        Returns:
            List of footage records with the specified status
        """
        current_token = self.token
        
        find_payload = {
            "query": [{self.field_mapping["status"]: status_to_check}],
            "limit": "1000"  # Large limit for batch processing
        }
        
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    config.url("layouts/FOOTAGE/_find"),
                    headers=config.api_headers(current_token),
                    json=find_payload,
                    verify=False,
                    timeout=30
                )
                
                if response.status_code == 401:
                    current_token = config.get_token()
                    continue
                
                if response.status_code == 404:
                    # No records found with this status
                    return []
                
                response.raise_for_status()
                
                records = response.json()['response']['data']
                logging.info(f"🔍 Found {len(records)} footage records with status '{status_to_check}'")
                
                return records
                
            except Exception as e:
                logging.warning(f"⚠️ Error checking status '{status_to_check}' attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
        
        logging.error(f"❌ Failed to check status '{status_to_check}' after {max_retries} attempts")
        return []
    
    def refresh_token(self) -> str:
        """Refresh FileMaker token and return new token."""
        self.token = config.get_token()
        return self.token 