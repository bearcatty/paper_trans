import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os
from pathlib import Path

# Mock fitz before importing pdf_translator
sys.modules['fitz'] = MagicMock()
sys.modules['pdf_translator.mcp_server'] = MagicMock()

# Add the directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pdf_translator.core import PDFTranslator

class TestPDFTranslator(unittest.IsolatedAsyncioTestCase):
    async def test_translate_pdf_enforces_markdown(self):
        # Mock dependencies
        with patch('pdf_translator.core.LMStudioClient') as MockClient, \
             patch('pdf_translator.core.os.path.exists', return_value=True), \
             patch('builtins.open', new_callable=MagicMock), \
             patch('pdf_translator.core.PDFTranslator.create_markdown_from_text') as mock_create_md:
            
            # Setup mock client
            mock_client_instance = MockClient.return_value
            mock_client_instance.chat_completion = AsyncMock(return_value={
                "choices": [{"message": {"content": "Translated content"}}]
            })
            
            # Setup mock PDF document via the mocked fitz module
            mock_doc = MagicMock()
            mock_page = MagicMock()
            mock_page.rect.height = 100
            mock_page.rect.width = 100
            # Mock get_text to return a list of blocks
            # Block format: (x0, y0, x1, y1, "text content", block_no, block_type)
            mock_page.get_text.return_value = [
                (0, 0, 100, 10, "Hello World", 0, 0) # text block
            ]
            mock_page.get_images.return_value = []
            mock_doc.__len__.return_value = 1
            mock_doc.__getitem__.return_value = mock_page
            
            # Configure fitz.open to return our mock doc
            sys.modules['fitz'].open.return_value = mock_doc
            
            translator = PDFTranslator()
            
            # Run translation
            output_path = await translator.translate_pdf("test.pdf")
            
            # Verify output path extension
            self.assertTrue(output_path.endswith(".md"))
            
            # Verify create_markdown_from_text was called
            mock_create_md.assert_called_once()
            
            # Verify create_pdf_from_text does NOT exist
            self.assertFalse(hasattr(translator, 'create_pdf_from_text'))

if __name__ == '__main__':
    unittest.main()
