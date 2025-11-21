import re
import sys
import os

# Add current directory to path to import the package
# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pdf_translator.core import PDFTranslator

def test_regex():
    translator = PDFTranslator()
    
    # Test cases
    test_cases = [
        ("Some text <<IMAGE_1>> more text", ["Some text ", "<<IMAGE_1>>", " more text"]),
        ("Some text <<IMAGE_CLUSTER_1>> more text", ["Some text ", "<<IMAGE_CLUSTER_1>>", " more text"]),
        ("<<IMAGE_1>>", ["", "<<IMAGE_1>>", ""]),
        ("<<IMAGE_CLUSTER_1>>", ["", "<<IMAGE_CLUSTER_1>>", ""]),
        ("Text with <<IMAGE_1>> and <<IMAGE_CLUSTER_2>> mixed", ["Text with ", "<<IMAGE_1>>", " and ", "<<IMAGE_CLUSTER_2>>", " mixed"]),
    ]
    
    print("Running regex tests...")
    failed = False
    
    for text, expected in test_cases:
        # The regex used in core.py
        parts = re.split(r"(<<IMAGE(?:_CLUSTER)?_\d+>>)", text)
        # Filter out empty strings for easier comparison if needed, but split keeps them
        # Let's just print what we got
        print(f"Input: '{text}'")
        print(f"Output: {parts}")
        
        # Check if placeholders are correctly split
        placeholders = [p for p in parts if "<<" in p]
        expected_placeholders = [p for p in expected if "<<" in p]
        
        if placeholders != expected_placeholders:
            print(f"FAILED: Expected placeholders {expected_placeholders}, got {placeholders}")
            failed = True
        else:
            print("PASSED")
        print("-" * 20)
        
    if failed:
        print("Some tests failed!")
        sys.exit(1)
    else:
        print("All tests passed!")
        sys.exit(0)

if __name__ == "__main__":
    test_regex()
