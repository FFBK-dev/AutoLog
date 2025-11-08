#!/usr/bin/env python3
"""
Create RGB Thumbnail - Standalone Image Processor

Converts an image to RGB and creates a 588x588 thumbnail.
Returns the thumbnail path for FileMaker to upload to container field.

This is a simpler version that doesn't access FileMaker - just processes an image file.
FileMaker handles the container field upload.
"""

import sys
import os
import warnings
from pathlib import Path
from PIL import Image, ImageFile

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore')

ImageFile.LOAD_TRUNCATED_IMAGES = True

__ARGS__ = ["image_path", "output_path"]

def convert_to_rgb(img):
    """Convert image to RGB."""
    mode = img.mode
    
    if mode == 'RGB':
        return img
    
    if mode in ('L', '1'):  # Grayscale
        return img.convert('RGB')
    
    if mode == 'RGBA':  # Remove alpha
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        return background
    
    if mode == 'CMYK':
        return img.convert('RGB')
    
    if mode == 'P':  # Palette
        return img.convert('RGB')
    
    # Any other mode
    return img.convert('RGB')

def create_thumbnail(image_path, output_path, max_size=588, quality=85):
    """
    Create RGB thumbnail matching Stills workflow.
    
    Args:
        image_path: Path to source image
        output_path: Path to save thumbnail
        max_size: Maximum dimension (default: 588)
        quality: JPEG quality (default: 85)
    
    Returns:
        bool: Success
    """
    try:
        print(f"📸 Processing: {image_path}")
        
        if not os.path.exists(image_path):
            print(f"❌ File not found: {image_path}")
            return False
        
        # Open image
        with Image.open(image_path) as img:
            original_mode = img.mode
            original_size = img.size
            
            print(f"  Original: {original_size[0]}x{original_size[1]}, Mode: {original_mode}")
            
            # Convert to RGB
            img_rgb = convert_to_rgb(img)
            if img_rgb.mode != original_mode:
                print(f"  → Converted {original_mode} to RGB")
            
            # Create thumbnail
            thumb = img_rgb.copy()
            thumb.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            print(f"  → Thumbnail: {thumb.size[0]}x{thumb.size[1]}")
            
            # Save
            thumb.save(output_path, 'JPEG', quality=quality)
            
            file_size = os.path.getsize(output_path)
            print(f"  ✅ Saved: {output_path} ({file_size/1024:.1f} KB)")
            
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Create RGB Thumbnail for REVERSE_IMAGE_SEARCH")
        print("")
        print("Usage:")
        print("  python create_thumbnail_rgb.py <image_path> [output_path]")
        print("")
        print("Examples:")
        print("  python create_thumbnail_rgb.py /path/to/image.jpg")
        print("  python create_thumbnail_rgb.py /path/to/image.jpg /tmp/thumb.jpg")
        print("")
        print("Output:")
        print("  If output_path not specified, creates thumbnail in /tmp/")
        print("  Returns thumbnail path on success")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    # Generate output path if not provided
    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        # Default: /tmp/thumb_<filename>.jpg
        filename = os.path.splitext(os.path.basename(image_path))[0]
        output_path = f"/tmp/thumb_{filename}.jpg"
    
    success = create_thumbnail(image_path, output_path)
    
    if success:
        # Output the thumbnail path for FileMaker to capture
        print(f"THUMBNAIL_PATH:{output_path}")
        sys.exit(0)
    else:
        sys.exit(1)

