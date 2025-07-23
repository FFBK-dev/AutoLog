#!/usr/bin/env python3
"""
Enhanced URL Scraping Utility

This utility provides comprehensive web scraping capabilities for different types of websites,
with special handling for archival sites like CONTENTdm, NYPL, LOC, and others.

Features:
- Multi-level scraping approach (HTML, JavaScript, structured data)
- Specialized handlers for different website types
- Robust error handling and retry logic
- Content cleaning and filtering
- Metadata quality evaluation
"""

import requests
import json
import re
import time
import warnings
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urlparse

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

class URLScraper:
    """Enhanced URL scraper with specialized handlers for different website types."""
    
    def __init__(self, timeout=30, max_retries=3):
        self.timeout = timeout
        self.max_retries = max_retries
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    
    def scrape_url(self, url, client=None):
        """
        Main scraping method that orchestrates different scraping approaches.
        
        Args:
            url (str): URL to scrape
            client: OpenAI client (optional, for vision analysis)
            
        Returns:
            str: Extracted content or None if failed
        """
        print(f"  -> Enhanced scraping for: {url}")
        
        try:
            # Detect website type and apply specialized handling
            website_type = self._detect_website_type(url)
            print(f"  -> Detected website type: {website_type}")
            
            # Try specialized scraper first
            if website_type == "contentdm":
                content = self._scrape_contentdm(url)
                if content:
                    print(f"  -> CONTENTdm extraction successful ({len(content)} chars)")
                    return content
            
            # Fall back to general scraping methods
            content = self._scrape_general(url)
            if content:
                print(f"  -> General extraction successful ({len(content)} chars)")
                return content
            
            # Try Selenium as last resort for JavaScript-heavy sites
            print(f"  -> Trying Selenium for JavaScript-heavy content...")
            content = self._scrape_with_selenium(url)
            if content:
                print(f"  -> Selenium extraction successful ({len(content)} chars)")
                return content
            
            print(f"  -> No content could be extracted from URL")
            return None
            
        except Exception as e:
            print(f"  -> Error in enhanced URL scraping: {e}")
            return None
    
    def _detect_website_type(self, url):
        """Detect the type of website for specialized handling."""
        domain = urlparse(url).netloc.lower()
        
        # CONTENTdm sites
        if any(pattern in domain for pattern in ['contentdm', 'digitalcollections']):
            return "contentdm"
        
        # Library of Congress
        if 'loc.gov' in domain:
            return "loc"
        
        # New York Public Library
        if 'nypl.org' in domain or 'digitalcollections.nypl.org' in domain:
            return "nypl"
        
        # Internet Archive
        if 'archive.org' in domain:
            return "archive"
        
        # HarpWeek
        if 'harpweek.com' in domain:
            return "harpweek"
        
        # Generic archival/library sites
        if any(pattern in domain for pattern in ['library', 'archive', 'museum', 'digital']):
            return "archival"
        
        return "generic"
    
    def _scrape_contentdm(self, url):
        """Specialized scraper for CONTENTdm sites."""
        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            html_content = response.text
            
            # Extract JSON data from JavaScript
            pattern = r'window\.__INITIAL_STATE__ = JSON\.parse\("(.*?)"\);'
            match = re.search(pattern, html_content, re.DOTALL)
            
            if match:
                json_str = match.group(1)
                # Unescape the JSON string
                json_str = json_str.encode('utf-8').decode('unicode_escape')
                
                data = json.loads(json_str)
                item = data['item']['item']
                
                # Extract all metadata fields
                metadata_parts = []
                metadata_parts.append(f"Title: {item['title']}")
                metadata_parts.append(f"Collection: {item['collectionName']}")
                
                for field in item['fields']:
                    if field['value'] and field['value'].strip():
                        metadata_parts.append(f"{field['label']}: {field['value']}")
                
                return "\n\n".join(metadata_parts)
            
            return None
            
        except Exception as e:
            print(f"  -> CONTENTdm scraping error: {e}")
            return None
    
    def _scrape_general(self, url):
        """General HTML scraping with enhanced content extraction."""
        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "header", "footer", "advertisement"]):
                script.decompose()
            
            # Extract structured metadata
            structured_metadata = self._extract_structured_metadata(soup)
            if structured_metadata:
                return structured_metadata
            
            # Extract basic content
            content_parts = []
            
            # Title
            title = soup.find('title')
            if title:
                content_parts.append(f"Title: {title.get_text(strip=True)}")
            
            # Meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
            if meta_desc and meta_desc.get('content'):
                content_parts.append(f"Description: {meta_desc['content'].strip()}")
            
            # Look for content areas
            content_selectors = [
                'main', 'article', '.content', '#content', '.main-content',
                '.record-view', '.item-view', '.detail-view', '.metadata-view',
                '.item-summary', '.item-details', '.item-metadata'
            ]
            
            for selector in content_selectors:
                elements = soup.select(selector)
                for element in elements:
                    text = element.get_text(separator='\n', strip=True)
                    if text and len(text) > 50:
                        content_parts.append(text[:1000])
                        break
            
            return "\n\n".join(content_parts)
            
        except Exception as e:
            print(f"  -> General scraping error: {e}")
            return None
    
    def _extract_structured_metadata(self, soup):
        """Extract structured metadata from archival sites."""
        metadata_parts = []
        
        # Look for definition lists (common in archival sites)
        dl_elements = soup.find_all('dl')
        for dl in dl_elements:
            dt_dd_pairs = []
            dts = dl.find_all('dt')
            dds = dl.find_all('dd')
            
            for i, dt in enumerate(dts):
                if i < len(dds):
                    key = dt.get_text(strip=True)
                    value = dds[i].get_text(strip=True)
                    if key and value and len(value) > 2:
                        dt_dd_pairs.append(f"{key}: {value}")
            
            if dt_dd_pairs:
                metadata_parts.extend(dt_dd_pairs)
        
        # Look for tables with metadata
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) == 2:
                    key = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if key and value and len(value) > 2:
                        metadata_parts.append(f"{key}: {value}")
        
        # Look for JSON-LD structured data
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    metadata_parts.extend(self._extract_json_ld_metadata(data))
            except:
                continue
        
        if metadata_parts:
            return "\n\n".join(metadata_parts)
        
        return None
    
    def _extract_json_ld_metadata(self, data):
        """Extract metadata from JSON-LD structured data."""
        metadata = []
        
        if 'name' in data:
            metadata.append(f"Name: {data['name']}")
        if 'description' in data:
            metadata.append(f"Description: {data['description']}")
        if 'creator' in data:
            creator = data['creator']
            if isinstance(creator, dict) and 'name' in creator:
                metadata.append(f"Creator: {creator['name']}")
            elif isinstance(creator, str):
                metadata.append(f"Creator: {creator}")
        if 'dateCreated' in data:
            metadata.append(f"Date Created: {data['dateCreated']}")
        if 'keywords' in data:
            metadata.append(f"Keywords: {data['keywords']}")
        
        return metadata
    
    def _scrape_with_selenium(self, url):
        """Scrape using Selenium for JavaScript-heavy sites."""
        driver = None
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument(f"--user-agent={self.headers['User-Agent']}")
            
            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)
            
            # Wait for page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Additional wait for dynamic content
            time.sleep(3)
            
            # Get page source and parse
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Extract content similar to general method
            content_parts = []
            
            # Title
            title = soup.find('title')
            if title:
                content_parts.append(f"Title: {title.get_text(strip=True)}")
            
            # Look for content areas
            content_selectors = [
                'main', 'article', '.content', '.description', '.about', 
                '.details', '.info', '#content', '#description'
            ]
            
            for selector in content_selectors:
                elements = soup.select(selector)
                for element in elements:
                    text = element.get_text(separator='\n', strip=True)
                    if text and len(text) > 50:
                        content_parts.append(text[:1000])
                        break
            
            return "\n\n".join(content_parts)
            
        except Exception as e:
            print(f"  -> Selenium scraping error: {e}")
            return None
        finally:
            if driver:
                driver.quit()
    
    def clean_content(self, content):
        """Clean and filter scraped content."""
        if not content:
            return None
        
        lines = content.split('\n')
        cleaned_lines = []
        navigation_count = 0
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Skip excessive navigation text
            if 'Navigate cartoons individually' in line or 'Back|Next' in line:
                navigation_count += 1
                if navigation_count <= 2:  # Keep first 2 instances, skip the rest
                    cleaned_lines.append(line)
                continue
            
            # Skip other repetitive navigation patterns
            if any(pattern in line.lower() for pattern in [
                'navigate', 'back|next', 'previous|next', 'first|last',
                'menu', 'footer', 'header', 'sidebar', 'advertisement'
            ]):
                continue
            
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    def evaluate_metadata_quality(self, content):
        """
        Evaluate the quality of scraped metadata.
        
        Returns:
            dict: Quality assessment with score, sufficient flag, and reason
        """
        if not content or not content.strip():
            return {"sufficient": False, "score": 0.0, "reason": "No content"}
        
        text_clean = content.strip()
        if len(text_clean) < 20:
            return {"sufficient": False, "score": 0.0, "reason": "Content too short"}
        
        text_lower = text_clean.lower()
        
        # Check for boilerplate/useless content
        boilerplate_phrases = [
            "stock photo", "search results", "download image", "cookies", 
            "privacy policy", "log in", "sign up", "free digital items", 
            "digital collection", "browse", "cart", "checkout", "shopping",
            "advertisement", "sponsored content", "click here", "learn more"
        ]
        
        boilerplate_count = sum(1 for phrase in boilerplate_phrases if phrase in text_lower)
        
        # Check for useful metadata indicators
        useful_indicators = [
            "date", "year", "photographer", "creator", "artist", "title", 
            "description", "location", "collection", "archive", "museum",
            "copyright", "rights", "permission", "circa", "historical",
            "dimensions", "medium", "subject", "depicts", "shows"
        ]
        
        useful_count = sum(1 for indicator in useful_indicators if indicator in text_lower)
        
        # Check for year patterns
        year_pattern = r'\b(18|19|20)\d{2}\b'
        year_matches = re.findall(year_pattern, text_clean)
        year_bonus = len(year_matches) * 2
        
        # Check for archival keywords
        archival_keywords = [
            "election", "cartoon", "political", "campaign", "vote", "president",
            "congress", "senate", "governor", "mayor", "democrat", "republican",
            "harpweek", "harpers", "weekly", "magazine", "periodical", "newspaper",
            "illustration", "drawing", "sketch", "print", "engraving", "lithograph",
            "african american", "black people", "women", "children", "schools", "teachers"
        ]
        
        archival_count = sum(1 for keyword in archival_keywords if keyword in text_lower)
        archival_bonus = min(archival_count, 3)
        
        # Calculate total score
        total_score = useful_count + year_bonus + archival_bonus
        
        # Determine if sufficient
        if boilerplate_count > 3:
            return {
                "sufficient": False, 
                "score": total_score, 
                "reason": f"Too much boilerplate content ({boilerplate_count} instances)"
            }
        elif total_score >= 2 and len(text_clean) >= 30:
            return {
                "sufficient": True, 
                "score": total_score, 
                "reason": f"Good quality metadata (score: {total_score})"
            }
        elif useful_count >= 1 and len(text_clean) >= 40 and (year_bonus > 0 or archival_bonus > 0):
            return {
                "sufficient": True, 
                "score": total_score, 
                "reason": f"Acceptable metadata with historical content (score: {total_score})"
            }
        else:
            return {
                "sufficient": False, 
                "score": total_score, 
                "reason": f"Insufficient metadata (score: {total_score})"
            }


def scrape_url_enhanced(url, client=None, timeout=30):
    """
    Enhanced URL scraping function with comprehensive metadata extraction.
    
    Args:
        url (str): URL to scrape
        client: OpenAI client (optional)
        timeout (int): Request timeout in seconds
        
    Returns:
        str: Extracted content or None if failed
    """
    scraper = URLScraper(timeout=timeout)
    content = scraper.scrape_url(url, client)
    
    if content:
        cleaned_content = scraper.clean_content(content)
        return cleaned_content
    
    return None


def evaluate_metadata_quality(content):
    """
    Evaluate the quality of scraped metadata.
    
    Args:
        content (str): Scraped content to evaluate
        
    Returns:
        dict: Quality assessment
    """
    scraper = URLScraper()
    return scraper.evaluate_metadata_quality(content) 