#!/usr/bin/env python3
"""
Local metadata quality evaluator using spaCy and rule-based heuristics.
Fast, free alternative to OpenAI-based evaluation.
"""

import re
import spacy
from typing import Dict, List, Tuple
from pathlib import Path

# Load spaCy model (install with: python -m spacy download en_core_web_sm)
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("spaCy model not found. Install with: python -m spacy download en_core_web_sm")
    nlp = None

class LocalMetadataEvaluator:
    def __init__(self):
        self.historical_keywords = {
            # Time periods
            'century', 'circa', 'c.', 'ca.', 'american civil war', 'world war', 'wwi', 'wwii',
            'reconstruction', 'antebellum', 'colonial', 'revolutionary war', 'great depression',
            'gilded age', 'progressive era', 'jazz age', '1800s', '1900s', 'nineteenth', 'twentieth',
            
            # Military/Political
            'general', 'president', 'colonel', 'captain', 'union', 'confederate', 'federal',
            'regiment', 'battalion', 'army', 'navy', 'military', 'battle', 'campaign', 'war',
            'politician', 'senator', 'congressman', 'governor', 'mayor',
            
            # Photography/Archives
            'photograph', 'daguerreotype', 'tintype', 'carte de visite', 'cabinet card',
            'albumen', 'gelatin silver', 'glass plate', 'negative', 'print', 'portrait',
            'studio', 'photographer', 'archive', 'collection', 'manuscript', 'library',
            
            # Geographic/Social
            'north', 'south', 'east', 'west', 'city', 'town', 'county', 'state', 'territory',
            'frontier', 'settlement', 'plantation', 'farm', 'railroad', 'factory', 'mill',
            'immigrant', 'migration', 'slavery', 'abolition', 'suffrage', 'temperance',
            
            # People/Family
            'family', 'husband', 'wife', 'children', 'son', 'daughter', 'father', 'mother',
            'brother', 'sister', 'uncle', 'aunt', 'cousin', 'grandfather', 'grandmother'
        }
        
        self.boilerplate_indicators = {
            'stock photo', 'getty images', 'download', 'license', 'royalty free', 'editorial use',
            'cookies', 'privacy policy', 'terms of service', 'log in', 'sign up', 'cart',
            'shopping', 'purchase', 'buy now', 'add to cart', 'checkout', 'payment',
            'search results', 'related images', 'similar photos', 'more like this',
            'advertisement', 'sponsored', 'promotion', 'sale', 'discount', 'offer'
        }
        
        self.archival_quality_indicators = {
            'archival', 'historical', 'manuscript', 'document', 'record', 'collection',
            'donated', 'acquired', 'preservation', 'digitized', 'original', 'vintage',
            'authentic', 'provenance', 'attribution', 'creator', 'photographer', 'artist'
        }

    def evaluate_metadata(self, text: str, has_url: bool = False) -> Dict[str, any]:
        """
        Evaluate metadata quality using local analysis.
        Uses different thresholds based on whether URL scraping is possible.
        Returns dict with 'sufficient' (bool), 'reason' (str), 'confidence' (str), 'score' (float)
        """
        if not text or not text.strip():
            return {
                'sufficient': False,
                'reason': 'No metadata text provided',
                'confidence': 'high',
                'score': 0.0
            }
        
        text_clean = text.strip()
        
        # Quick length check
        if len(text_clean) < 20:
            return {
                'sufficient': False,
                'reason': 'Text too short (less than 20 characters)',
                'confidence': 'high',
                'score': 0.1
            }
        
        score = 0.0
        reasons = []
        
        # 1. Basic text quality (20% of score)
        length_score = min(len(text_clean) / 100, 1.0)  # Cap at 100 chars for full points
        score += length_score * 0.2
        
        # 2. Check for boilerplate content (penalty)
        text_lower = text_clean.lower()
        boilerplate_count = sum(1 for phrase in self.boilerplate_indicators if phrase in text_lower)
        boilerplate_penalty = min(boilerplate_count * 0.1, 0.3)  # Max 30% penalty
        score -= boilerplate_penalty
        
        if boilerplate_count > 0:
            reasons.append(f"Contains {boilerplate_count} boilerplate phrases")
        
        # 3. Historical keywords (30% of score)
        historical_matches = sum(1 for keyword in self.historical_keywords if keyword in text_lower)
        historical_score = min(historical_matches / 3, 1.0)  # Full points for 3+ matches
        score += historical_score * 0.3
        
        if historical_matches > 0:
            reasons.append(f"Contains {historical_matches} historical keywords")
        
        # 4. Archival quality indicators (20% of score)
        archival_matches = sum(1 for indicator in self.archival_quality_indicators if indicator in text_lower)
        archival_score = min(archival_matches / 2, 1.0)  # Full points for 2+ matches
        score += archival_score * 0.2
        
        if archival_matches > 0:
            reasons.append(f"Contains {archival_matches} archival quality indicators")
        
        # 5. Named Entity Recognition (30% of score) - if spaCy available
        if nlp is not None:
            try:
                doc = nlp(text_clean)
                
                # Count valuable entity types
                entity_counts = {'PERSON': 0, 'DATE': 0, 'GPE': 0, 'ORG': 0, 'EVENT': 0}
                for ent in doc.ents:
                    if ent.label_ in entity_counts:
                        entity_counts[ent.label_] += 1
                
                # Score based on entity diversity and count
                total_entities = sum(entity_counts.values())
                entity_diversity = len([count for count in entity_counts.values() if count > 0])
                
                entity_score = min(total_entities / 5, 1.0) * 0.7 + min(entity_diversity / 4, 1.0) * 0.3
                score += entity_score * 0.3
                
                if total_entities > 0:
                    reasons.append(f"Contains {total_entities} named entities ({entity_diversity} types)")
                
            except Exception as e:
                # If spaCy fails, don't penalize
                pass
        
        # 6. Date pattern recognition (bonus points)
        date_patterns = [
            r'\b\d{4}\b',  # Years
            r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',  # Dates
            r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}\b',  # Month Day, Year
            r'\bcirca\s+\d{4}\b',  # Circa dates
            r'\bc\.\s*\d{4}\b',  # c. dates
        ]
        
        date_matches = sum(1 for pattern in date_patterns if re.search(pattern, text_lower))
        if date_matches > 0:
            score += 0.1  # Bonus for dates
            reasons.append(f"Contains {date_matches} date patterns")
        
        # Cap score at 1.0
        score = min(score, 1.0)
        
        # Determine sufficiency with URL-aware thresholds
        if has_url:
            # Stricter threshold when URL exists (we can improve metadata)
            threshold = 0.5
            context = "URL available - using stricter threshold"
        else:
            # More lenient threshold when no URL (can't improve metadata anyway)
            threshold = 0.3
            context = "No URL available - using lenient threshold"
        
        sufficient = score >= threshold
        
        # Determine confidence
        if score >= 0.6:  # Lowered from 0.8
            confidence = 'high'
        elif score >= 0.4:  # Lowered from 0.6
            confidence = 'medium'
        else:
            confidence = 'low'
        
        # Generate reason
        if sufficient:
            reason = f"Good quality metadata (score: {score:.2f}, threshold: {threshold:.1f}). {context}. " + "; ".join(reasons)
        else:
            reason = f"Insufficient metadata quality (score: {score:.2f}, threshold: {threshold:.1f}). {context}. " + "; ".join(reasons)
        
        return {
            'sufficient': sufficient,
            'reason': reason,
            'confidence': confidence,
            'score': score
        }

def test_evaluator():
    """Test the evaluator with sample texts and different URL scenarios."""
    evaluator = LocalMetadataEvaluator()
    
    test_cases = [
        "Portrait of General Ulysses S. Grant, circa 1865, taken during the American Civil War by photographer Mathew Brady",
        "Stock photo of a man in uniform, royalty free, download now",
        "Family photograph from the 1920s showing three generations",
        "Getty Images watermark visible",
        "Historical photograph from the Library of Congress collection showing President Abraham Lincoln with his cabinet members in 1864",
        "Short text"
    ]
    
    for i, text in enumerate(test_cases, 1):
        print(f"Test {i}: {text[:50]}...")
        
        # Test with URL available (stricter threshold)
        result_with_url = evaluator.evaluate_metadata(text, has_url=True)
        print(f"  With URL: {'✅ SUFFICIENT' if result_with_url['sufficient'] else '❌ INSUFFICIENT'}")
        print(f"    Score: {result_with_url['score']:.2f}, Reason: {result_with_url['reason']}")
        
        # Test without URL (lenient threshold)
        result_no_url = evaluator.evaluate_metadata(text, has_url=False)
        print(f"  No URL:  {'✅ SUFFICIENT' if result_no_url['sufficient'] else '❌ INSUFFICIENT'}")
        print(f"    Score: {result_no_url['score']:.2f}, Reason: {result_no_url['reason']}")
        print()

# Global instance
_evaluator = LocalMetadataEvaluator()

def evaluate_metadata_local(text: str, has_url: bool = False) -> Dict[str, any]:
    """Main function for metadata evaluation - matches OpenAI API format."""
    return _evaluator.evaluate_metadata(text, has_url)

if __name__ == "__main__":
    test_evaluator() 