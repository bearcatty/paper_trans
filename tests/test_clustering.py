#!/usr/bin/env python3
"""
Test script to verify image clustering functionality
"""
import sys
sys.path.insert(0, '/Users/bytedance/work/author_parser')

from pdf_translator import ContentExtractor
import fitz

pdf_path = "Multi-Agent Evolve- LLM Self-Improve through Co-evolution .pdf"
doc = fitz.open(pdf_path)

# Test on page 2 (index 1)
page = doc[1]
extractor = ContentExtractor()

print("Testing image clustering on page 2...")
print(f"Page dimensions: {page.rect.width} x {page.rect.height}")
print()

blocks = extractor.extract_page(page, 2)

# Count images
image_blocks = [b for b in blocks if b.block_type == "image"]
text_blocks = [b for b in blocks if b.block_type == "text"]

print(f"Total blocks: {len(blocks)}")
print(f"  Text blocks: {len(text_blocks)}")
print(f"  Image blocks: {len(image_blocks)}")
print()

# Show image details
for i, img_block in enumerate(image_blocks, 1):
    print(f"Image {i}:")
    print(f"  Text: {img_block.text}")
    print(f"  BBox: {img_block.bbox}")
    print(f"  Extension: {img_block.image_ext}")
    print(f"  Size: {len(img_block.image_data)} bytes")
    print()

doc.close()

print("✓ Test complete!")
print(f"\nExpected: 1-2 image blocks (clustered from 6 original images)")
print(f"Actual: {len(image_blocks)} image blocks")
