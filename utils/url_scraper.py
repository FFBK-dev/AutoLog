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
            if website_type == "valentine":
                content = self._scrape_valentine(url)
                if content:
                    print(f"  -> Valentine Museum extraction successful ({len(content)} chars)")
                    return content
            elif website_type == "temple":
                content = self._scrape_temple(url)
                if content:
                    print(f"  -> Temple University extraction successful ({len(content)} chars)")
                    return content
            elif website_type == "contentdm":
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
        
        # The Valentine Museum (Re:discovery software)
        if 'valentine.rediscoverysoftware.com' in domain or 'thevalentine.org' in domain:
            return "valentine"
        
        # Temple University Digital Library
        if 'digital.library.temple.edu' in domain:
            return "temple"
        
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
    
    def _scrape_valentine(self, url):
        """Specialized scraper for The Valentine Museum (Re:discovery software)."""
        try:
            # Valentine Museum uses JavaScript to load content, so we need Selenium
            driver = None
            try:
                print(f"  -> Valentine Museum requires JavaScript rendering...")
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
                
                # Additional wait for Re:discovery's dynamic content to load
                time.sleep(5)
                
                # Parse the rendered page
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                
                metadata_parts = []
                
                # Extract title from #redtitle
                title_elem = soup.find(id='redtitle')
                if title_elem:
                    title_text = title_elem.get_text(strip=True)
                    if title_text:
                        metadata_parts.append(f"Title: {title_text}")
                
                # Extract collection hierarchy from #redboxARH
                hierarchy_elem = soup.find(id='redboxARH')
                if hierarchy_elem:
                    hierarchy_text = hierarchy_elem.get_text(separator=' | ', strip=True)
                    # Clean up the hierarchy text
                    hierarchy_text = hierarchy_text.replace('Record Hierarchy - Item', '').strip()
                    if hierarchy_text:
                        metadata_parts.append(f"Collection Hierarchy: {hierarchy_text}")
                
                # Extract main metadata from table in #robjres
                robjres_elem = soup.find(id='robjres')
                if robjres_elem:
                    # Look for the metadata table
                    table = robjres_elem.find('table')
                    if table:
                        rows = table.find_all('tr')
                        for row in rows:
                            cells = row.find_all(['td', 'th'])
                            if len(cells) >= 2:
                                key = cells[0].get_text(strip=True).rstrip(':')
                                value = cells[1].get_text(strip=True)
                                if key and value and len(value) > 1:
                                    # Clean up common formatting issues
                                    if key == "Summary Note":
                                        # This is often the most important field
                                        metadata_parts.append(f"Description: {value}")
                                    else:
                                        metadata_parts.append(f"{key}: {value}")
                
                # If we didn't get a table, try extracting from the #robjres div directly
                if len(metadata_parts) <= 2 and robjres_elem:
                    text = robjres_elem.get_text(separator='\n', strip=True)
                    # Parse key-value pairs from the text
                    lines = text.split('\n')
                    i = 0
                    while i < len(lines):
                        line = lines[i].strip()
                        # Look for lines ending with colon (field labels)
                        if line.endswith(':') and i + 1 < len(lines):
                            key = line.rstrip(':')
                            value = lines[i + 1].strip()
                            if key and value and len(key) < 100 and len(value) > 1:
                                if key == "Summary Note":
                                    metadata_parts.append(f"Description: {value}")
                                else:
                                    metadata_parts.append(f"{key}: {value}")
                            i += 2
                        else:
                            i += 1
                
                # Extract archive number if available
                archive_no_elem = soup.find(string=re.compile(r'Archive No:', re.I))
                if archive_no_elem:
                    parent_text = archive_no_elem.parent.get_text(strip=True) if archive_no_elem.parent else ""
                    if parent_text:
                        # Extract just the archive number
                        match = re.search(r'Archive No:\s*([^\s]+)', parent_text)
                        if match:
                            metadata_parts.append(f"Archive Number: {match.group(1)}")
                
                if metadata_parts:
                    return "\n\n".join(metadata_parts)
                
                return None
                
            finally:
                if driver:
                    driver.quit()
                    
        except Exception as e:
            print(f"  -> Valentine Museum scraping error: {e}")
            return None
    
    def _scrape_temple(self, url):
        """Specialized scraper for Temple University Digital Library."""
        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            html_content = response.text
            soup = BeautifulSoup(html_content, 'html.parser')
            
            metadata_parts = []
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "header", "footer"]):
                script.decompose()
            
            # Extract title
            title = soup.find('title')
            if title:
                title_text = title.get_text(strip=True)
                # Clean up common Temple University title patterns
                title_text = re.sub(r'\s*\|\s*Temple University Libraries.*$', '', title_text)
                title_text = re.sub(r'\s*\|\s*Digital Collections.*$', '', title_text)
                if title_text and title_text != "CONTENTdm":
                    metadata_parts.append(f"Title: {title_text}")
            
            # Look for metadata tables (common in digital library systems)
            tables = soup.find_all('table')
            for table in tables:
                # Check if this looks like a metadata table
                if any(keyword in table.get_text().lower() for keyword in ['title', 'creator', 'date', 'subject', 'description']):
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 2:
                            key = cells[0].get_text(strip=True).rstrip(':')
                            value = cells[1].get_text(strip=True)
                            if key and value and len(value) > 2 and len(key) < 50:
                                # Skip navigation and boilerplate
                                if not any(skip_word in key.lower() for skip_word in ['navigate', 'zoom', 'download', 'print']):
                                    metadata_parts.append(f"{key}: {value}")
            
            # Look for definition lists (dl/dt/dd structure)
            dl_elements = soup.find_all('dl')
            for dl in dl_elements:
                dt_elements = dl.find_all('dt')
                dd_elements = dl.find_all('dd')
                for i, dt in enumerate(dt_elements):
                    if i < len(dd_elements):
                        key = dt.get_text(strip=True).rstrip(':')
                        value = dd_elements[i].get_text(strip=True)
                        if key and value and len(value) > 2 and len(key) < 50:
                            metadata_parts.append(f"{key}: {value}")
            
            # Look for specific Temple University digital library patterns
            # Check for item details sections
            detail_sections = soup.find_all(['div', 'section'], class_=re.compile(r'(item|detail|metadata|info)', re.I))
            for section in detail_sections:
                # Look for key-value pairs within these sections
                strong_elements = section.find_all('strong')
                for strong in strong_elements:
                    key = strong.get_text(strip=True).rstrip(':')
                    # Try to find the value after the strong element
                    next_text = strong.next_sibling
                    if next_text and hasattr(next_text, 'strip'):
                        value = next_text.strip().lstrip(':').strip()
                        if value and len(value) > 2 and len(key) < 50:
                            metadata_parts.append(f"{key}: {value}")
                    elif strong.parent:
                        # Try to get text from parent and extract after the key
                        parent_text = strong.parent.get_text()
                        if key in parent_text:
                            value_part = parent_text.split(key, 1)[-1].strip().lstrip(':').strip()
                            if value_part and len(value_part) > 2 and '\n' not in value_part[:100]:
                                metadata_parts.append(f"{key}: {value_part}")
            
            # Look for any CONTENTdm-style JSON data (Temple might use CONTENTdm backend)
            contentdm_patterns = [
                r'window\.__INITIAL_STATE__ = JSON\.parse\("(.*?)"\);',
                r'var itemData = ({.*?});',
                r'var metadata = ({.*?});'
            ]
            
            for pattern in contentdm_patterns:
                match = re.search(pattern, html_content, re.DOTALL)
                if match:
                    try:
                        json_str = match.group(1)
                        if pattern.startswith('window'):
                            # Unescape the JSON string for __INITIAL_STATE__
                            json_str = json_str.encode('utf-8').decode('unicode_escape')
                        
                        data = json.loads(json_str)
                        
                        # Extract metadata from JSON structure
                        if isinstance(data, dict):
                            if 'item' in data and 'item' in data['item']:
                                item = data['item']['item']
                                if 'title' in item:
                                    metadata_parts.append(f"Title: {item['title']}")
                                if 'collectionName' in item:
                                    metadata_parts.append(f"Collection: {item['collectionName']}")
                                if 'fields' in item:
                                    for field in item['fields']:
                                        if field.get('value') and field.get('value').strip():
                                            metadata_parts.append(f"{field['label']}: {field['value']}")
                            else:
                                # Direct metadata structure
                                for key, value in data.items():
                                    if isinstance(value, str) and value.strip() and len(value) > 2:
                                        clean_key = key.replace('_', ' ').title()
                                        metadata_parts.append(f"{clean_key}: {value}")
                        break
                    except (json.JSONDecodeError, KeyError, TypeError):
                        continue
            
            # Look for meta tags
            meta_tags = soup.find_all('meta')
            for meta in meta_tags:
                name = meta.get('name') or meta.get('property', '')
                content = meta.get('content', '')
                if name and content and len(content) > 10:
                    if any(keyword in name.lower() for keyword in ['description', 'subject', 'creator', 'date', 'title']):
                        clean_name = name.replace('_', ' ').replace('-', ' ').title()
                        metadata_parts.append(f"{clean_name}: {content}")
            
            # If we have metadata, return it
            if metadata_parts:
                return "\n\n".join(metadata_parts)
            
            # Fallback: extract general content from likely content areas
            content_selectors = [
                '.item-view', '.record-view', '.detail-view', '.metadata-view',
                '.item-details', '.item-info', '.record-details', '.content-area',
                '#main-content', '#content', 'main', 'article'
            ]
            
            for selector in content_selectors:
                elements = soup.select(selector)
                for element in elements:
                    text = element.get_text(separator='\n', strip=True)
                    if text and len(text) > 100:
                        # Clean up the text
                        lines = text.split('\n')
                        clean_lines = []
                        for line in lines:
                            line = line.strip()
                            if line and len(line) > 3:
                                # Skip navigation and boilerplate
                                if not any(skip_word in line.lower() for skip_word in [
                                    'navigate', 'zoom in', 'zoom out', 'download', 'print', 
                                    'back to results', 'previous', 'next', 'home', 'search'
                                ]):
                                    clean_lines.append(line)
                        
                        if clean_lines:
                            return '\n'.join(clean_lines[:20])  # Limit to first 20 lines
                        break
            
            return None
            
        except Exception as e:
            print(f"  -> Temple University scraping error: {e}")
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
        
        # Check for Temple University and academic keywords
        temple_keywords = [
            "temple university", "temple libraries", "blockson", "afro-american",
            "philadelphia", "pennsylvania", "delaware valley", "scrc",
            "special collections", "research center", "manuscript", "oral history",
            "digital collections", "finding aid", "archival", "university archives"
        ]
        
        temple_count = sum(1 for keyword in temple_keywords if keyword in text_lower)
        temple_bonus = min(temple_count * 2, 6)  # Higher bonus for Temple content
        
        # Check for Valentine Museum keywords
        valentine_keywords = [
            "valentine museum", "the valentine", "richmond", "virginia",
            "phil flournoy", "flournoy", "richmond chamber of commerce",
            "photograph collection", "tobacco", "archive no", "item nbr",
            "collection nbr", "phys desc", "circa", "stamped", "verso"
        ]
        
        valentine_count = sum(1 for keyword in valentine_keywords if keyword in text_lower)
        valentine_bonus = min(valentine_count * 2, 6)  # Higher bonus for Valentine content
        
        # Check for additional academic/cultural institution keywords
        academic_keywords = [
            "library", "university", "college", "institution", "archives",
            "special collections", "rare books", "manuscripts", "digitized",
            "repository", "finding aids", "catalog", "collection", "holdings"
        ]
        
        academic_count = sum(1 for keyword in academic_keywords if keyword in text_lower)
        academic_bonus = min(academic_count, 2)
        
        # Calculate total score
        total_score = useful_count + year_bonus + archival_bonus + temple_bonus + valentine_bonus + academic_bonus
        
        # Determine if sufficient
        if boilerplate_count > 3:
            return {
                "sufficient": False, 
                "score": total_score, 
                "reason": f"Too much boilerplate content ({boilerplate_count} instances)"
            }
        elif total_score >= 3 and len(text_clean) >= 30:  # Raised threshold due to enhanced scoring
            return {
                "sufficient": True, 
                "score": total_score, 
                "reason": f"Good quality metadata (score: {total_score})"
            }
        elif temple_bonus > 0 and total_score >= 2:  # Special case for Temple University content
            return {
                "sufficient": True, 
                "score": total_score, 
                "reason": f"Temple University content with good metadata (score: {total_score})"
            }
        elif valentine_bonus > 0 and total_score >= 2:  # Special case for Valentine Museum content
            return {
                "sufficient": True, 
                "score": total_score, 
                "reason": f"Valentine Museum content with good metadata (score: {total_score})"
            }
        elif useful_count >= 1 and len(text_clean) >= 40 and (year_bonus > 0 or archival_bonus > 0 or academic_bonus > 0):
            return {
                "sufficient": True, 
                "score": total_score, 
                "reason": f"Acceptable metadata with institutional content (score: {total_score})"
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