#!/usr/bin/env python3
"""
Embedding Fusion Diagnostics Test Script

This script analyzes the first 50 records in the FileMaker database to diagnose
embedding fusion issues that may be causing semantic search problems.

Focus areas:
- Validate AI_ImageEmbedding and AI_TextEmbedding_CLIP field contents
- Check for valid JSON arrays with proper dimensions
- Identify data corruption, NaN/infinity values
- Test fusion math and normalization
- Provide detailed statistics and recommendations
"""

import sys
import os
import json
import time
import requests
import warnings
from pathlib import Path
import numpy as np
from datetime import datetime
import traceback

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

# Add the parent directory to the path to import existing config
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

# Field mappings
FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "img_embedding": "AI_ImageEmbedding",
    "txt_embedding": "AI_TextEmbedding_CLIP",
    "fused_embedding": "AI_FusedEmbedding",
    "status": "AutoLog_Status"
}

class EmbeddingDiagnostics:
    def __init__(self):
        self.total_records = 0
        self.records_with_img_embedding = 0
        self.records_with_txt_embedding = 0
        self.records_with_both_embeddings = 0
        self.fusion_successes = 0
        self.fusion_failures = 0
        self.errors = []
        self.dimension_mismatches = []
        self.invalid_json_records = []
        self.nan_infinity_records = []
        self.empty_embedding_records = []
        self.dimension_stats = {}

    def analyze_embedding_field(self, field_name, field_value, record_id, stills_id):
        """Analyze individual embedding field and return diagnostics."""
        result = {
            'is_populated': bool(field_value and field_value.strip()),
            'is_valid_json': False,
            'array_length': 0,
            'has_nan_inf': False,
            'value_range': None,
            'error': None
        }
        
        if not result['is_populated']:
            result['error'] = "Field is empty or whitespace"
            return result
        
        try:
            embedding_array = json.loads(field_value)
            result['is_valid_json'] = True
            
            if isinstance(embedding_array, list) and len(embedding_array) > 0:
                np_array = np.array(embedding_array, dtype=np.float32)
                result['array_length'] = len(embedding_array)
                result['shape'] = np_array.shape
                result['has_nan_inf'] = bool(np.isnan(np_array).any() or np.isinf(np_array).any())
                result['value_range'] = (float(np_array.min()), float(np_array.max()))
                result['mean'] = float(np_array.mean())
                result['std'] = float(np_array.std())
                
                # Track dimension statistics
                dim_key = f"{np_array.shape}"
                if dim_key not in self.dimension_stats:
                    self.dimension_stats[dim_key] = 0
                self.dimension_stats[dim_key] += 1
                
            else:
                result['error'] = "JSON is not a non-empty array"
                
        except json.JSONDecodeError as e:
            result['error'] = f"Invalid JSON: {str(e)}"
        except Exception as e:
            result['error'] = f"Analysis error: {str(e)}"
        
        return result

    def test_fusion(self, img_embedding_str, txt_embedding_str, record_id, stills_id):
        """Test the fusion process and return detailed results."""
        result = {
            'can_fuse': False,
            'fusion_successful': False,
            'error': None,
            'fused_stats': None
        }
        
        try:
            # Parse embeddings
            img_embedding = json.loads(img_embedding_str)
            txt_embedding = json.loads(txt_embedding_str)
            
            # Convert to numpy arrays
            img_array = np.array(img_embedding, dtype=np.float32)
            txt_array = np.array(txt_embedding, dtype=np.float32)
            
            # Check shape compatibility
            if img_array.shape != txt_array.shape:
                result['error'] = f"Shape mismatch: {img_array.shape} vs {txt_array.shape}"
                self.dimension_mismatches.append({
                    'record_id': record_id,
                    'stills_id': stills_id,
                    'img_shape': img_array.shape,
                    'txt_shape': txt_array.shape
                })
                return result
            
            result['can_fuse'] = True
            
            # Perform fusion
            fused_array = 0.5 * img_array + 0.5 * txt_array
            norm = np.linalg.norm(fused_array)
            
            if norm == 0:
                result['error'] = "Fused embedding norm is zero"
                return result
            
            # Normalize
            fused_array /= norm
            
            # Check for NaN/Inf in result
            if np.isnan(fused_array).any() or np.isinf(fused_array).any():
                result['error'] = "Fusion produced NaN or Infinity values"
                self.nan_infinity_records.append({
                    'record_id': record_id,
                    'stills_id': stills_id,
                    'stage': 'fusion_result'
                })
                return result
            
            result['fusion_successful'] = True
            result['fused_stats'] = {
                'shape': fused_array.shape,
                'norm': float(norm),
                'final_norm': float(np.linalg.norm(fused_array)),
                'value_range': (float(fused_array.min()), float(fused_array.max())),
                'mean': float(fused_array.mean()),
                'std': float(fused_array.std())
            }
            
        except Exception as e:
            result['error'] = f"Fusion error: {str(e)}"
        
        return result

    def print_summary(self):
        """Print comprehensive summary of diagnostics."""
        print("\n" + "="*80)
        print("🔍 EMBEDDING FUSION DIAGNOSTICS SUMMARY")
        print("="*80)
        
        print(f"\n📊 OVERALL STATISTICS:")
        print(f"   Total records analyzed: {self.total_records}")
        print(f"   Records with image embeddings: {self.records_with_img_embedding} ({self.records_with_img_embedding/self.total_records*100:.1f}%)")
        print(f"   Records with text embeddings: {self.records_with_txt_embedding} ({self.records_with_txt_embedding/self.total_records*100:.1f}%)")
        print(f"   Records with both embeddings: {self.records_with_both_embeddings} ({self.records_with_both_embeddings/self.total_records*100:.1f}%)")
        
        print(f"\n🔄 FUSION RESULTS:")
        print(f"   Successful fusions: {self.fusion_successes}")
        print(f"   Failed fusions: {self.fusion_failures}")
        if self.records_with_both_embeddings > 0:
            success_rate = self.fusion_successes / self.records_with_both_embeddings * 100
            print(f"   Fusion success rate: {success_rate:.1f}%")
        
        print(f"\n📐 DIMENSION ANALYSIS:")
        for shape, count in sorted(self.dimension_stats.items()):
            print(f"   Shape {shape}: {count} records")
        
        if self.dimension_mismatches:
            print(f"\n⚠️ DIMENSION MISMATCHES ({len(self.dimension_mismatches)}):")
            for mismatch in self.dimension_mismatches[:5]:  # Show first 5
                print(f"   Record {mismatch['record_id']} (ID: {mismatch['stills_id']}): {mismatch['img_shape']} vs {mismatch['txt_shape']}")
            if len(self.dimension_mismatches) > 5:
                print(f"   ... and {len(self.dimension_mismatches) - 5} more")
        
        if self.invalid_json_records:
            print(f"\n❌ INVALID JSON RECORDS ({len(self.invalid_json_records)}):")
            for record in self.invalid_json_records[:5]:
                print(f"   Record {record['record_id']} (ID: {record['stills_id']}): {record['field']} - {record['error']}")
            if len(self.invalid_json_records) > 5:
                print(f"   ... and {len(self.invalid_json_records) - 5} more")
        
        if self.nan_infinity_records:
            print(f"\n🚫 NaN/INFINITY ISSUES ({len(self.nan_infinity_records)}):")
            for record in self.nan_infinity_records:
                print(f"   Record {record['record_id']} (ID: {record['stills_id']}): {record['stage']}")
        
        if self.empty_embedding_records:
            print(f"\n📭 EMPTY EMBEDDING RECORDS ({len(self.empty_embedding_records)}):")
            for record in self.empty_embedding_records[:5]:
                print(f"   Record {record['record_id']} (ID: {record['stills_id']}): Missing {record['missing_fields']}")
            if len(self.empty_embedding_records) > 5:
                print(f"   ... and {len(self.empty_embedding_records) - 5} more")

        print(f"\n💡 RECOMMENDATIONS:")
        if self.fusion_failures > 0:
            print(f"   ❗ {self.fusion_failures} fusion failures detected - investigate dimension mismatches and data corruption")
        if self.dimension_mismatches:
            print(f"   📐 Fix dimension mismatches - ensure consistent embedding dimensions across all records")
        if self.invalid_json_records:
            print(f"   🔧 Repair invalid JSON in embedding fields")
        if self.nan_infinity_records:
            print(f"   🧹 Clean NaN/Infinity values from embeddings")
        if self.records_with_both_embeddings < self.total_records * 0.8:
            print(f"   📝 Many records missing embeddings - run embedding generation pipeline")
        
        if self.fusion_successes == self.records_with_both_embeddings and self.records_with_both_embeddings > 0:
            print(f"   ✅ All fusion operations successful - issue may be elsewhere in semantic search pipeline")

def main():
    print("🚀 Starting Embedding Fusion Diagnostics...")
    print(f"📅 Analysis started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    diagnostics = EmbeddingDiagnostics()
    
    try:
        # Get FileMaker token
        print("🔑 Getting FileMaker token...")
        token = config.get_token()
        
        # Query first 50 records
        print("📋 Querying first 50 records from FileMaker...")
        response = requests.get(
            config.url("layouts/Stills/records"),
            headers=config.api_headers(token),
            params={"_limit": 50},
            verify=False,
            timeout=30
        )
        
        response.raise_for_status()
        records = response.json()['response']['data']
        
        print(f"📊 Found {len(records)} records to analyze")
        diagnostics.total_records = len(records)
        
        # Analyze each record
        for i, record in enumerate(records):
            record_id = record['recordId']
            field_data = record['fieldData']
            
            stills_id = field_data.get(FIELD_MAPPING['stills_id'], 'Unknown')
            status = field_data.get(FIELD_MAPPING['status'], 'Unknown')
            
            print(f"\n🔍 Analyzing record {i+1}/{len(records)} - ID: {stills_id} (Record: {record_id})")
            print(f"   Status: {status}")
            
            # Get embedding fields
            img_embedding_str = field_data.get(FIELD_MAPPING['img_embedding'], "")
            txt_embedding_str = field_data.get(FIELD_MAPPING['txt_embedding'], "")
            fused_embedding_str = field_data.get(FIELD_MAPPING['fused_embedding'], "")
            
            # Analyze image embedding
            print("   📸 Analyzing image embedding...")
            img_analysis = diagnostics.analyze_embedding_field(
                'img_embedding', img_embedding_str, record_id, stills_id
            )
            
            if img_analysis['is_populated'] and img_analysis['is_valid_json']:
                diagnostics.records_with_img_embedding += 1
                print(f"      ✅ Valid - Shape: {img_analysis.get('shape', 'N/A')}, Range: {img_analysis.get('value_range', 'N/A')}")
                if img_analysis['has_nan_inf']:
                    print(f"      ⚠️  Contains NaN/Inf values")
                    diagnostics.nan_infinity_records.append({
                        'record_id': record_id,
                        'stills_id': stills_id,
                        'stage': 'img_embedding'
                    })
            else:
                print(f"      ❌ Invalid - {img_analysis['error']}")
                if img_analysis['error'] and 'JSON' in img_analysis['error']:
                    diagnostics.invalid_json_records.append({
                        'record_id': record_id,
                        'stills_id': stills_id,
                        'field': 'img_embedding',
                        'error': img_analysis['error']
                    })
            
            # Analyze text embedding
            print("   📝 Analyzing text embedding...")
            txt_analysis = diagnostics.analyze_embedding_field(
                'txt_embedding', txt_embedding_str, record_id, stills_id
            )
            
            if txt_analysis['is_populated'] and txt_analysis['is_valid_json']:
                diagnostics.records_with_txt_embedding += 1
                print(f"      ✅ Valid - Shape: {txt_analysis.get('shape', 'N/A')}, Range: {txt_analysis.get('value_range', 'N/A')}")
                if txt_analysis['has_nan_inf']:
                    print(f"      ⚠️  Contains NaN/Inf values")
                    diagnostics.nan_infinity_records.append({
                        'record_id': record_id,
                        'stills_id': stills_id,
                        'stage': 'txt_embedding'
                    })
            else:
                print(f"      ❌ Invalid - {txt_analysis['error']}")
                if txt_analysis['error'] and 'JSON' in txt_analysis['error']:
                    diagnostics.invalid_json_records.append({
                        'record_id': record_id,
                        'stills_id': stills_id,
                        'field': 'txt_embedding',
                        'error': txt_analysis['error']
                    })
            
            # Check if both embeddings are valid for fusion
            both_valid = (img_analysis['is_populated'] and img_analysis['is_valid_json'] and 
                         txt_analysis['is_populated'] and txt_analysis['is_valid_json'])
            
            if both_valid:
                diagnostics.records_with_both_embeddings += 1
                
                # Test fusion
                print("   🔄 Testing fusion...")
                fusion_result = diagnostics.test_fusion(
                    img_embedding_str, txt_embedding_str, record_id, stills_id
                )
                
                if fusion_result['fusion_successful']:
                    diagnostics.fusion_successes += 1
                    stats = fusion_result['fused_stats']
                    print(f"      ✅ Fusion successful - Shape: {stats['shape']}, Norm: {stats['final_norm']:.4f}")
                else:
                    diagnostics.fusion_failures += 1
                    print(f"      ❌ Fusion failed - {fusion_result['error']}")
            else:
                missing_fields = []
                if not (img_analysis['is_populated'] and img_analysis['is_valid_json']):
                    missing_fields.append('img_embedding')
                if not (txt_analysis['is_populated'] and txt_analysis['is_valid_json']):
                    missing_fields.append('txt_embedding')
                
                diagnostics.empty_embedding_records.append({
                    'record_id': record_id,
                    'stills_id': stills_id,
                    'missing_fields': missing_fields
                })
                print(f"   ⏭️  Skipping fusion - missing valid embeddings: {missing_fields}")
            
            # Show existing fused embedding status
            if fused_embedding_str:
                try:
                    existing_fused = json.loads(fused_embedding_str)
                    if isinstance(existing_fused, list):
                        print(f"   📋 Existing fused embedding: {len(existing_fused)} dimensions")
                    else:
                        print(f"   ⚠️  Existing fused embedding is not an array")
                except:
                    print(f"   ❌ Existing fused embedding is invalid JSON")
            else:
                print(f"   📭 No existing fused embedding")
        
        # Print final summary
        diagnostics.print_summary()
        
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR during diagnostics: {e}")
        traceback.print_exc()
        return False
    
    print(f"\n🏁 Diagnostics completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 