#!/usr/bin/env python3
"""
Debug script to analyze PDF image structure
"""
import fitz  # PyMuPDF

pdf_path = "data/Multi-Agent Evolve- LLM Self-Improve through Co-evolution .pdf"
doc = fitz.open(pdf_path)

# Analyze page 2 (index 1)
page = doc[1]
print(f"Page 2 analysis:")
print(f"Page dimensions: {page.rect.width} x {page.rect.height}")
print()

# Get all images
image_list = page.get_images(full=True)
print(f"Total images found: {len(image_list)}")
print()

for img_index, img in enumerate(image_list, 1):
    xref = img[0]
    print(f"\nImage {img_index}:")
    print(f"  xref: {xref}")
    
    # Get image rectangles
    image_rects = page.get_image_rects(xref)
    print(f"  Number of rectangles: {len(image_rects)}")
    
    if image_rects:
        for i, rect in enumerate(image_rects):
            print(f"    Rect {i+1}: ({rect.x0:.2f}, {rect.y0:.2f}, {rect.x1:.2f}, {rect.y1:.2f})")
            print(f"      Width: {rect.x1 - rect.x0:.2f}, Height: {rect.y1 - rect.y0:.2f}")
    
    # Get image info
    try:
        base_image = doc.extract_image(xref)
        print(f"  Image format: {base_image['ext']}")
        print(f"  Image size: {len(base_image['image'])} bytes")
    except Exception as e:
        print(f"  Error extracting image: {e}")

doc.close()
