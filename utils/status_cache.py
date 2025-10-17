#!/usr/bin/env python3
"""
Status Cache Utility for Footage AutoLog

This utility minimizes FileMaker API calls by:
1. Caching status information for a polling cycle
2. Batching status requests when possible
3. Providing intelligent cache invalidation
4. Tracking which records need fresh status checks

Key benefits:
- Reduces API calls from O(n*frames) to O(n*unique_parents)
- Provides consistent status across a single polling cycle
- Handles cache expiration and invalidation
"""

import time
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

class StatusCache:
    """Intelligent status cache for footage/frame processing."""
    
    def __init__(self, cache_duration_seconds: int = 30):
        """
        Initialize status cache.
        
        Args:
            cache_duration_seconds: How long to keep cached statuses valid
        """
        self.cache_duration = cache_duration_seconds
        self.footage_status_cache: Dict[str, Dict] = {}  # footage_id -> {status, timestamp, record_id}
        self.frame_status_cache: Dict[str, Dict] = {}    # frame_id -> {status, timestamp, record_id, parent_id}
        self.parent_child_map: Dict[str, Set[str]] = defaultdict(set)  # parent_id -> set of child frame_ids
        self.pending_status_checks: Set[str] = set()     # footage_ids that need fresh status checks
        self.api_call_count = 0
        self.cache_hit_count = 0
        
        # Performance tracking
        self.stats = {
            "api_calls_saved": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "last_reset": time.time()
        }
    
    def add_footage_records(self, footage_records: List[Dict]) -> None:
        """
        Bulk add footage records to cache.
        
        Args:
            footage_records: List of footage record data from FileMaker
        """
        current_time = time.time()
        
        for record in footage_records:
            footage_id = record['fieldData'].get('INFO_FTG_ID')
            status = record['fieldData'].get('AutoLog_Status', 'Unknown')
            
            if footage_id:
                self.footage_status_cache[footage_id] = {
                    'status': status,
                    'timestamp': current_time,
                    'record_id': record['recordId'],
                    'record_data': record['fieldData']
                }
        
        logging.info(f"🗄️ Status cache: Added {len(footage_records)} footage records")
    
    def add_frame_records(self, frame_records: List[Dict]) -> None:
        """
        Bulk add frame records to cache and build parent-child mapping.
        
        Args:
            frame_records: List of frame record data from FileMaker
        """
        current_time = time.time()
        
        for record in frame_records:
            frame_id = record['fieldData'].get('INFO_FR_ID')
            parent_id = record['fieldData'].get('INFO_FTG_ID')  # Parent footage ID
            status = record['fieldData'].get('AutoLog_Status', 'Unknown')
            
            if frame_id:
                self.frame_status_cache[frame_id] = {
                    'status': status,
                    'timestamp': current_time,
                    'record_id': record['recordId'],
                    'parent_id': parent_id,
                    'record_data': record['fieldData']
                }
                
                # Build parent-child mapping
                if parent_id:
                    self.parent_child_map[parent_id].add(frame_id)
        
        logging.info(f"🗄️ Status cache: Added {len(frame_records)} frame records")
        logging.info(f"🗄️ Status cache: Tracking {len(self.parent_child_map)} parent-child relationships")
    
    def get_footage_status(self, footage_id: str) -> Optional[Dict]:
        """
        Get cached footage status, checking if still valid.
        
        Args:
            footage_id: The footage ID to check
            
        Returns:
            Dict with status info if valid, None if expired/missing
        """
        if footage_id not in self.footage_status_cache:
            self.stats["cache_misses"] += 1
            return None
        
        cached_data = self.footage_status_cache[footage_id]
        current_time = time.time()
        
        # Check if cache is still valid
        if current_time - cached_data['timestamp'] > self.cache_duration:
            # Cache expired
            self.stats["cache_misses"] += 1
            return None
        
        self.stats["cache_hits"] += 1
        return cached_data
    
    def is_parent_ready_for_frames(self, parent_footage_id: str) -> Tuple[bool, str]:
        """
        Check if a parent footage record is ready for frame processing.
        
        Args:
            parent_footage_id: The parent footage ID to check
            
        Returns:
            Tuple of (is_ready: bool, status: str)
        """
        cached_status = self.get_footage_status(parent_footage_id)
        
        if not cached_status:
            # Cache miss - need fresh API call
            return False, "CACHE_MISS"
        
        parent_status = cached_status['status']
        
        # Define parent ready statuses (same as original logic)
        parent_ready_statuses = [
            "4 - Scraping URL",
            "5 - Processing Frame Info", 
            "6 - Generating Description",
            "7 - Avid Description",
            "8 - Generating Embeddings",
            "Force Resume"
        ]
        
        # Check for terminal success states
        parent_terminal_success_statuses = [
            "9 - Applying Tags",
            "10 - Complete"
        ]
        
        if parent_status in parent_terminal_success_statuses:
            return True, f"TERMINAL_SUCCESS:{parent_status}"
        
        if parent_status in parent_ready_statuses:
            return True, parent_status
        
        return False, parent_status
    
    def get_frames_needing_parent_check(self) -> List[Tuple[str, str]]:
        """
        Get list of (frame_id, parent_id) pairs that need parent status checks.
        
        Returns:
            List of tuples (frame_id, parent_id) that need checking
        """
        needs_check = []
        
        for frame_id, frame_data in self.frame_status_cache.items():
            parent_id = frame_data.get('parent_id')
            if parent_id:
                # Check if we have valid cached status for parent
                parent_status = self.get_footage_status(parent_id)
                if not parent_status:
                    # Need to check this parent
                    needs_check.append((frame_id, parent_id))
        
        return needs_check
    
    def invalidate_footage_status(self, footage_id: str) -> None:
        """Mark a footage status as needing refresh."""
        if footage_id in self.footage_status_cache:
            # Mark as expired by setting old timestamp
            self.footage_status_cache[footage_id]['timestamp'] = 0
        
        self.pending_status_checks.add(footage_id)
    
    def get_unique_parents_needing_check(self) -> Set[str]:
        """Get unique parent footage IDs that need status checks."""
        unique_parents = set()
        
        for frame_id, frame_data in self.frame_status_cache.items():
            parent_id = frame_data.get('parent_id')
            if parent_id:
                parent_status = self.get_footage_status(parent_id)
                if not parent_status:  # Cache miss
                    unique_parents.add(parent_id)
        
        return unique_parents
    
    def batch_update_footage_statuses(self, footage_updates: Dict[str, Dict]) -> None:
        """
        Batch update multiple footage statuses.
        
        Args:
            footage_updates: Dict of footage_id -> status_data
        """
        current_time = time.time()
        
        for footage_id, status_data in footage_updates.items():
            self.footage_status_cache[footage_id] = {
                **status_data,
                'timestamp': current_time
            }
            
            # Remove from pending checks
            self.pending_status_checks.discard(footage_id)
        
        logging.info(f"🗄️ Status cache: Batch updated {len(footage_updates)} footage statuses")
    
    def clear_expired_cache(self) -> None:
        """Remove expired entries from cache."""
        current_time = time.time()
        
        # Clear expired footage statuses
        expired_footage = [
            footage_id for footage_id, data in self.footage_status_cache.items()
            if current_time - data['timestamp'] > self.cache_duration
        ]
        
        for footage_id in expired_footage:
            del self.footage_status_cache[footage_id]
        
        # Clear expired frame statuses  
        expired_frames = [
            frame_id for frame_id, data in self.frame_status_cache.items()
            if current_time - data['timestamp'] > self.cache_duration
        ]
        
        for frame_id in expired_frames:
            del self.frame_status_cache[frame_id]
        
        if expired_footage or expired_frames:
            logging.info(f"🗄️ Status cache: Cleared {len(expired_footage)} footage, {len(expired_frames)} frame expired entries")
    
    def get_stats(self) -> Dict:
        """Get cache performance statistics."""
        current_time = time.time()
        duration = current_time - self.stats["last_reset"]
        
        return {
            **self.stats,
            "footage_cached": len(self.footage_status_cache),
            "frames_cached": len(self.frame_status_cache),
            "parent_child_relationships": len(self.parent_child_map),
            "pending_checks": len(self.pending_status_checks),
            "cache_duration": duration,
            "hit_rate": self.stats["cache_hits"] / max(1, self.stats["cache_hits"] + self.stats["cache_misses"])
        }
    
    def reset_stats(self) -> None:
        """Reset performance statistics."""
        self.stats = {
            "api_calls_saved": 0,
            "cache_hits": 0, 
            "cache_misses": 0,
            "last_reset": time.time()
        }
    
    def reset_cache(self) -> None:
        """Clear all cached data for new polling cycle."""
        self.footage_status_cache.clear()
        self.frame_status_cache.clear()
        self.parent_child_map.clear()
        self.pending_status_checks.clear()
        
        logging.info("🗄️ Status cache: Reset for new polling cycle") 