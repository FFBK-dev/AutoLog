#!/usr/bin/env python3
import sys
import numpy as np
import json

def load_embedding(file_path):
    """Load embedding from a UTF-16 encoded text file containing a Python list."""
    try:
        with open(file_path, 'r', encoding='utf-16') as f:
            # Read the content and evaluate it as a Python list
            content = f.read().strip()
            # Remove any BOM if present
            if content.startswith('\ufeff'):
                content = content[1:]
            # Parse the string as a Python list
            values = json.loads(content)
            return np.array(values, dtype=np.float32)
    except Exception as e:
        print(f"Error loading embedding from {file_path}: {str(e)}", file=sys.stderr)
        sys.exit(1)

def analyze_embedding(embedding, name):
    """Print diagnostic information about an embedding."""
    print(f"\n{name} Analysis:", file=sys.stderr)
    print(f"Shape: {embedding.shape}", file=sys.stderr)
    print(f"Mean: {np.mean(embedding):.6f}", file=sys.stderr)
    print(f"Std: {np.std(embedding):.6f}", file=sys.stderr)
    print(f"Min: {np.min(embedding):.6f}", file=sys.stderr)
    print(f"Max: {np.max(embedding):.6f}", file=sys.stderr)
    print(f"L2 norm: {np.linalg.norm(embedding):.6f}", file=sys.stderr)
    print(f"First 5 values: {embedding[:5].tolist()}", file=sys.stderr)

def main():
    if len(sys.argv) != 3:
        print("Usage: python fuse_embeddings.py <image_embedding_path> <text_embedding_path>", file=sys.stderr)
        sys.exit(1)

    image_embedding_path = sys.argv[1]
    text_embedding_path = sys.argv[2]

    # Load embeddings
    image_embedding = load_embedding(image_embedding_path)
    text_embedding = load_embedding(text_embedding_path)

    # Analyze input embeddings
    analyze_embedding(image_embedding, "Image Embedding")
    analyze_embedding(text_embedding, "Text Embedding")

    # Check if embeddings have the same shape
    if image_embedding.shape != text_embedding.shape:
        print(f"Error: Embedding shapes do not match. Image: {image_embedding.shape}, Text: {text_embedding.shape}", file=sys.stderr)
        sys.exit(1)

    # Fuse embeddings (weighted average instead of concatenation)
    fused_embedding = 0.5 * image_embedding + 0.5 * text_embedding
    # Normalize the fused embedding
    fused_embedding = fused_embedding / np.linalg.norm(fused_embedding)

    # Analyze fused embedding
    analyze_embedding(fused_embedding, "Fused Embedding")

    # Print the fused embedding as a formatted list
    print(json.dumps(fused_embedding.tolist()))

if __name__ == "__main__":
    main()