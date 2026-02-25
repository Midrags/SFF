"""Convert sff.png to sff.ico for PyInstaller"""

import sys
from pathlib import Path

def convert_png_to_ico():
    """Convert PNG to ICO format"""
    try:
        from PIL import Image
    except ImportError:
        print("ERROR: Pillow is not installed!")
        print("Install it with: pip install Pillow")
        return False
    
    png_path = Path("sff.png")
    ico_path = Path("sff.ico")
    
    if not png_path.exists():
        print(f"ERROR: {png_path} not found!")
        return False
    
    try:
        print(f"Converting {png_path} to {ico_path}...")
        img = Image.open(png_path)
        
        # Convert to RGBA if needed
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # Save as ICO with multiple sizes
        img.save(ico_path, format='ICO', sizes=[
            (16, 16),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256)
        ])
        
        print(f"✓ Successfully created {ico_path}")
        print(f"  Size: {ico_path.stat().st_size / 1024:.1f} KB")
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to convert image: {e}")
        return False

if __name__ == "__main__":
    success = convert_png_to_ico()
    sys.exit(0 if success else 1)
