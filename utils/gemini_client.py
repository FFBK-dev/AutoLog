#!/usr/bin/env python3
"""
Global Gemini client with rate limiting and retry logic.
Designed for multi-image video frame analysis with structured JSON output.
"""

import time
import threading
import warnings
import os
import base64
from datetime import datetime
from pathlib import Path
from collections import deque

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

try:
    import google.generativeai as genai
    from google.generativeai.types import HarmCategory, HarmBlockThreshold
except ImportError:
    print("⚠️ google-generativeai not installed. Run: pip install google-generativeai")
    genai = None


class GlobalGeminiClient:
    """Global Gemini client with built-in rate limiting and retry logic."""
    
    def __init__(self):
        # Gemini 2.0 rate limits (adjust based on your tier)
        self.requests_per_minute = 15  # Free tier: 15 RPM, adjust for paid tier
        self.request_window = deque()
        self.lock = threading.Lock()
        self.api_key = None
        self.model_name = "gemini-2.0-pro-exp"  # Default to Pro for quality
        self.configured = False
        
    def set_api_key(self, api_key: str, model_name: str = "gemini-2.0-pro-exp"):
        """Configure the Gemini API client."""
        if not genai:
            raise RuntimeError("google-generativeai package not installed")
            
        with self.lock:
            self.api_key = api_key
            self.model_name = model_name
            genai.configure(api_key=api_key)
            self.configured = True
            print(f"🔑 Configured Gemini API with model: {model_name}")
    
    def _clean_window(self):
        """Remove entries older than 1 minute from tracking window."""
        cutoff = time.time() - 60
        while self.request_window and self.request_window[0] < cutoff:
            self.request_window.popleft()
    
    def _current_usage(self):
        """Get current request count in the last minute."""
        self._clean_window()
        return len(self.request_window)
    
    def _can_make_request(self) -> bool:
        """Check if we can make a request without exceeding rate limits."""
        current_requests = self._current_usage()
        return current_requests < self.requests_per_minute
    
    def _record_usage(self):
        """Record a request timestamp."""
        self.request_window.append(time.time())
    
    def _wait_for_capacity(self):
        """Wait until we have capacity to make a request."""
        while not self._can_make_request():
            current_requests = self._current_usage()
            print(f"⏳ Rate limit: {current_requests}/{self.requests_per_minute} requests/min, waiting...")
            time.sleep(5)
    
    def generate_content(
        self,
        prompt: str,
        images: list = None,
        response_schema: dict = None,
        max_retries: int = 3,
        timeout: int = 120
    ):
        """
        Generate content with Gemini, supporting multi-image input and structured output.
        
        Args:
            prompt: Text prompt for the model
            images: List of image file paths or PIL Image objects
            response_schema: Optional JSON schema for structured output
            max_retries: Maximum number of retry attempts
            timeout: Request timeout in seconds
            
        Returns:
            Response object from Gemini API
        """
        if not self.configured:
            raise RuntimeError("Gemini client not configured. Call set_api_key() first.")
        
        # Wait for rate limit capacity
        with self.lock:
            self._wait_for_capacity()
            self._record_usage()
        
        # Prepare content parts
        content_parts = [prompt]
        
        # Add images if provided
        if images:
            print(f"📸 Preparing {len(images)} images for Gemini...")
            for img_path in images:
                if isinstance(img_path, (str, Path)):
                    # Load image from file
                    with open(img_path, 'rb') as f:
                        img_data = f.read()
                    
                    # Gemini expects images as PIL Image or inline data
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(img_data))
                    content_parts.append(img)
                else:
                    # Assume it's already a PIL Image
                    content_parts.append(img_path)
        
        # Configure model
        generation_config = {
            "temperature": 0.4,  # Lower temperature for more factual responses
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
        }
        
        # Add response schema if provided
        if response_schema:
            generation_config["response_mime_type"] = "application/json"
            generation_config["response_schema"] = response_schema
        
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        # Retry logic
        for attempt in range(max_retries):
            try:
                print(f"🔄 Gemini API call attempt {attempt + 1}/{max_retries}")
                
                model = genai.GenerativeModel(
                    model_name=self.model_name,
                    generation_config=generation_config,
                    safety_settings=safety_settings
                )
                
                response = model.generate_content(
                    content_parts,
                    request_options={"timeout": timeout}
                )
                
                print(f"✅ Gemini response received successfully")
                
                # Log usage if available
                if hasattr(response, 'usage_metadata'):
                    print(f"📊 Tokens: {response.usage_metadata.total_token_count}")
                
                return response
                
            except Exception as e:
                error_str = str(e).lower()
                
                # Handle rate limiting
                if "429" in error_str or "quota" in error_str or "rate" in error_str:
                    wait_time = 30 * (2 ** attempt)  # Exponential backoff
                    print(f"🚫 Rate limit hit, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                
                # Handle timeout
                elif "timeout" in error_str:
                    if attempt < max_retries - 1:
                        print(f"⏱️ Request timeout, retrying...")
                        time.sleep(5)
                        continue
                    else:
                        raise TimeoutError(f"Gemini request timed out after {max_retries} attempts")
                
                # Handle other errors
                else:
                    if attempt < max_retries - 1:
                        wait_time = 5 * (2 ** attempt)
                        print(f"❌ API error: {e}")
                        print(f"⏱️ Waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise
        
        raise Exception(f"Gemini API call failed after {max_retries} attempts")
    
    def get_usage_stats(self):
        """Get current usage statistics."""
        with self.lock:
            current_requests = self._current_usage()
            
            return {
                "requests_per_minute": self.requests_per_minute,
                "current_requests": current_requests,
                "requests_remaining": max(0, self.requests_per_minute - current_requests),
                "utilization_percent": (current_requests / self.requests_per_minute) * 100
            }


# Global client instance
global_gemini_client = GlobalGeminiClient()

