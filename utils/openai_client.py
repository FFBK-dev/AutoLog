#!/usr/bin/env python3
import time
import threading
from collections import deque
from datetime import datetime
import openai
from openai import OpenAI
import json
import warnings
import re
import random

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

class GlobalOpenAIClient:
    """Global OpenAI client with built-in rate limiting and API key rotation."""
    
    def __init__(self):
        self.tokens_per_minute = 30000  # GPT-4o limit per key
        self.requests_per_minute = 500  # GPT-4o limit per key
        self.token_windows = {}  # key -> deque of (timestamp, tokens) pairs
        self.request_windows = {}  # key -> deque of timestamps
        self.lock = threading.Lock()
        self.clients = {}  # key -> OpenAI client instance
        self.api_keys = []  # List of API keys
        self.current_key_index = 0
        self.current_key = None
        
    def set_api_keys(self, api_keys: list):
        """Set multiple API keys for rotation."""
        with self.lock:
            self.api_keys = [key for key in api_keys if key and key.strip()]
            self.clients = {}
            self.token_windows = {}
            self.request_windows = {}
            
            for key in self.api_keys:
                self.clients[key] = OpenAI(api_key=key)
                self.token_windows[key] = deque()
                self.request_windows[key] = deque()
            
            if self.api_keys:
                self.current_key = self.api_keys[0]
                self.current_key_index = 0
                print(f"🔑 Configured {len(self.api_keys)} OpenAI API keys for rotation")
            else:
                print("⚠️ No valid API keys provided")
        
    def set_api_key(self, api_key: str):
        """Set a single API key (backward compatibility)."""
        self.set_api_keys([api_key])
    
    def _clean_windows(self, api_key: str):
        """Remove entries older than 1 minute from tracking windows for specific key."""
        cutoff = time.time() - 60
        
        if api_key in self.token_windows:
            while self.token_windows[api_key] and self.token_windows[api_key][0][0] < cutoff:
                self.token_windows[api_key].popleft()
                
        if api_key in self.request_windows:
            while self.request_windows[api_key] and self.request_windows[api_key][0] < cutoff:
                self.request_windows[api_key].popleft()
    
    def _current_usage(self, api_key: str):
        """Get current token and request usage in the last minute for specific key."""
        self._clean_windows(api_key)
        
        total_tokens = 0
        if api_key in self.token_windows:
            total_tokens = sum(tokens for _, tokens in self.token_windows[api_key])
        
        total_requests = 0
        if api_key in self.request_windows:
            total_requests = len(self.request_windows[api_key])
            
        return total_tokens, total_requests
    
    def _can_make_request(self, api_key: str, estimated_tokens: int) -> bool:
        """Check if we can make a request with specific key without exceeding rate limits."""
        current_tokens, current_requests = self._current_usage(api_key)
        
        # Check if adding this request would exceed limits
        would_exceed_tokens = (current_tokens + estimated_tokens) > self.tokens_per_minute
        would_exceed_requests = (current_requests + 1) > self.requests_per_minute
        
        return not (would_exceed_tokens or would_exceed_requests)
    
    def _record_usage(self, api_key: str, tokens_used: int):
        """Record actual token and request usage for specific key."""
        timestamp = time.time()
        
        if api_key in self.token_windows:
            self.token_windows[api_key].append((timestamp, tokens_used))
        if api_key in self.request_windows:
            self.request_windows[api_key].append(timestamp)
    
    def _get_next_available_key(self, estimated_tokens: int) -> str:
        """Find the next available API key that can handle the request."""
        if not self.api_keys:
            raise ValueError("No API keys configured")
        
        # First, try the current key
        if self.current_key and self._can_make_request(self.current_key, estimated_tokens):
            return self.current_key
        
        # If current key is rate limited, try all other keys
        for i in range(len(self.api_keys)):
            key = self.api_keys[i]
            if self._can_make_request(key, estimated_tokens):
                # Switch to this key
                self.current_key = key
                self.current_key_index = i
                if key != self.api_keys[0]:  # Only log if we switched
                    print(f"🔄 Switched to API key #{i+1} due to rate limits")
                return key
        
        # If no key is available, return the "least loaded" key
        best_key = self.api_keys[0]
        best_usage = float('inf')
        
        for key in self.api_keys:
            current_tokens, current_requests = self._current_usage(key)
            usage_ratio = (current_tokens / self.tokens_per_minute) + (current_requests / self.requests_per_minute)
            if usage_ratio < best_usage:
                best_usage = usage_ratio
                best_key = key
        
        self.current_key = best_key
        self.current_key_index = self.api_keys.index(best_key)
        print(f"🚫 All keys rate limited, using least loaded key #{self.current_key_index+1}")
        return best_key
    
    def _wait_for_any_key_capacity(self, estimated_tokens: int):
        """Wait until any key has capacity to make the request."""
        while True:
            for key in self.api_keys:
                if self._can_make_request(key, estimated_tokens):
                    return key
            
            # Show current usage for all keys
            usage_info = []
            for i, key in enumerate(self.api_keys):
                current_tokens, current_requests = self._current_usage(key)
                usage_info.append(f"Key #{i+1}: {current_tokens}/{self.tokens_per_minute} tokens, {current_requests}/{self.requests_per_minute} requests")
            
            print(f"⏳ All keys rate limited, waiting... ({'; '.join(usage_info)})")
            time.sleep(5)  # Check every 5 seconds
    
    def chat_completions_create(self, model="gpt-4o", messages=None, response_format=None, max_retries=5, estimated_tokens=2500):
        """
        Create a chat completion with automatic key rotation and rate limiting.
        """
        if not self.api_keys:
            raise ValueError("No API keys configured. Call set_api_keys() first.")
        
        with self.lock:
            # Get the best available key
            try:
                selected_key = self._get_next_available_key(estimated_tokens)
            except ValueError:
                # Wait for any key to become available
                selected_key = self._wait_for_any_key_capacity(estimated_tokens)
            
            # Record the estimated usage upfront
            self._record_usage(selected_key, estimated_tokens)
        
        # Now make the actual API call with retries
        for attempt in range(max_retries):
            try:
                print(f"🔄 OpenAI API call attempt {attempt + 1}/{max_retries} (Key #{self.current_key_index+1})")
                
                response = self.clients[selected_key].chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format=response_format
                )
                
                print(f"✅ OpenAI response received successfully")
                
                # Update actual token usage if available
                if hasattr(response, 'usage') and response.usage:
                    actual_tokens = response.usage.total_tokens
                    print(f"📊 Tokens used: {actual_tokens} (estimated: {estimated_tokens}) on Key #{self.current_key_index+1}")
                    
                    # Update our tracking with actual usage
                    with self.lock:
                        # Remove the estimated usage and add actual usage
                        if selected_key in self.token_windows and self.token_windows[selected_key]:
                            self.token_windows[selected_key].pop()  # Remove last entry (our estimate)
                            self._record_usage(selected_key, actual_tokens)
                
                return response
                
            except openai.RateLimitError as e:
                print(f"🚫 Rate limit hit on Key #{self.current_key_index+1}")
                
                # Try to switch to another key immediately
                with self.lock:
                    try:
                        selected_key = self._get_next_available_key(estimated_tokens)
                        print(f"🔄 Switched to Key #{self.current_key_index+1} for retry")
                        continue  # Try again with new key
                    except ValueError:
                        pass  # No keys available, use normal retry logic
                        
            except openai.AuthenticationError as e:
                print(f"🚫 Authentication error on Key #{self.current_key_index+1} (invalid/archived key)")
                
                # Try to switch to another key immediately
                with self.lock:
                    try:
                        selected_key = self._get_next_available_key(estimated_tokens)
                        print(f"🔄 Switched to Key #{self.current_key_index+1} for retry")
                        continue  # Try again with new key
                    except ValueError:
                        pass  # No keys available, use normal retry logic
                
                if attempt < max_retries - 1:
                    # Extract wait time from error message if available
                    error_msg = str(e)
                    wait_time = 2.0 * (1.5 ** attempt)  # Base exponential backoff
                    
                    # Try to parse the suggested wait time from the error message
                    if "Please try again in" in error_msg:
                        try:
                            match = re.search(r'Please try again in (\d+\.?\d*)([ms])', error_msg)
                            if match:
                                suggested_wait = float(match.group(1))
                                unit = match.group(2)
                                if unit == 'ms':
                                    suggested_wait = suggested_wait / 1000
                                wait_time = max(wait_time, suggested_wait + 2.0)
                        except:
                            pass
                    
                    # Add random jitter
                    jitter = random.uniform(0.5, 1.5)
                    wait_time = wait_time * jitter
                    
                    print(f"⏱️ Rate limit hit, waiting {wait_time:.1f} seconds before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ Rate limit exceeded after {max_retries} attempts on all keys")
                    raise e
                    
            except openai.APIError as e:
                if attempt < max_retries - 1:
                    wait_time = 2.0 * (1.5 ** attempt)
                    print(f"🔧 API error on Key #{self.current_key_index+1}, waiting {wait_time:.1f} seconds before retry: {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    raise e
                    
            except Exception as e:
                raise e
        
        raise Exception("OpenAI API call failed after all retries")
    
    def get_usage_stats(self):
        """Get current usage statistics for all keys."""
        with self.lock:
            stats = {
                "total_keys": len(self.api_keys),
                "current_key_index": self.current_key_index,
                "keys": []
            }
            
            total_capacity = 0
            total_used = 0
            
            for i, key in enumerate(self.api_keys):
                current_tokens, current_requests = self._current_usage(key)
                key_stats = {
                    "key_index": i + 1,
                    "current_tokens_per_minute": current_tokens,
                    "current_requests_per_minute": current_requests,
                    "tokens_remaining": max(0, self.tokens_per_minute - current_tokens),
                    "requests_remaining": max(0, self.requests_per_minute - current_requests),
                    "utilization_percent": (current_tokens / self.tokens_per_minute) * 100
                }
                stats["keys"].append(key_stats)
                
                total_capacity += self.tokens_per_minute
                total_used += current_tokens
            
            stats["total_capacity"] = total_capacity
            stats["total_used"] = total_used
            stats["total_utilization_percent"] = (total_used / total_capacity) * 100 if total_capacity > 0 else 0
            
            return stats

# Global client instance
global_openai_client = GlobalOpenAIClient() 