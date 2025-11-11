#!/usr/bin/env python3
"""
URLs Cache - In-memory caching for archive URL roots

Reduces FileMaker API calls by caching all URL roots from the URLs table.
Thread-safe for concurrent access.
"""

import threading
import requests
import config


class URLsCache:
    """Thread-safe in-memory cache for archive URL roots."""
    
    def __init__(self):
        self._cache = None
        self._lock = threading.Lock()
    
    def load_cache(self, token):
        """
        Load all URL roots from FileMaker URLs table into cache.
        
        Args:
            token (str): FileMaker Data API token
            
        Returns:
            dict: Dictionary mapping archive names to URL roots
        """
        with self._lock:
            try:
                print(f"  -> Loading URLs cache from FileMaker...")
                
                # Query all records from URLs layout
                response = requests.get(
                    config.url("layouts/URLs/records"),
                    headers=config.api_headers(token),
                    params={"_limit": 100},  # Should be enough for all archives
                    verify=False,
                    timeout=30
                )
                
                response.raise_for_status()
                records = response.json().get('response', {}).get('data', [])
                
                # Build cache dictionary
                cache = {}
                for record in records:
                    field_data = record.get('fieldData', {})
                    archive = field_data.get('Archive', '').strip()
                    url_root = field_data.get('URL Root', '').strip()
                    
                    if archive and url_root:
                        cache[archive] = url_root
                
                self._cache = cache
                print(f"  -> Cached {len(cache)} URL roots")
                
                return cache
                
            except Exception as e:
                print(f"  -> Error loading URLs cache: {e}")
                self._cache = {}
                return {}
    
    def get_url_root(self, source, token):
        """
        Get URL root for a source, using cache or falling back to direct query.
        
        Args:
            source (str): Archive/source name
            token (str): FileMaker Data API token
            
        Returns:
            str: URL root or None if not found
        """
        if not source:
            return None
        
        source = source.strip()
        
        # Load cache on first access
        if self._cache is None:
            self.load_cache(token)
        
        # Check cache first
        if source in self._cache:
            return self._cache[source]
        
        # Not in cache - try direct query as fallback
        print(f"  -> {source} not in cache, querying FileMaker...")
        try:
            query = {"query": [{"Archive": f"=={source}"}], "limit": 1}
            response = requests.post(
                config.url("layouts/URLs/_find"),
                headers=config.api_headers(token),
                json=query,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 404:
                print(f"  -> No URL root found for: {source}")
                return None
            
            response.raise_for_status()
            records = response.json().get('response', {}).get('data', [])
            
            if records:
                url_root = records[0]['fieldData'].get('URL Root', '').strip()
                if url_root:
                    # Add to cache for future use
                    with self._lock:
                        self._cache[source] = url_root
                    print(f"  -> Found and cached: {source} -> {url_root}")
                    return url_root
            
            return None
            
        except Exception as e:
            print(f"  -> Error querying URL root for {source}: {e}")
            return None
    
    def add_to_cache(self, source, url_root):
        """
        Add a new entry to the cache (called after auto-detection succeeds).
        
        Args:
            source (str): Archive/source name
            url_root (str): URL root
        """
        if not source or not url_root:
            return
        
        with self._lock:
            if self._cache is None:
                self._cache = {}
            self._cache[source.strip()] = url_root.strip()
            print(f"  -> Added to cache: {source} -> {url_root}")
    
    def clear_cache(self):
        """Clear the cache (useful for testing or forcing reload)."""
        with self._lock:
            self._cache = None
            print(f"  -> Cache cleared")


# Global cache instance
global_urls_cache = URLsCache()

