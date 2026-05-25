"""OCR (Optical Character Recognition) engine for extracting text from PDF invoices."""
import os
import logging
from pathlib import Path
from typing import Optional
import pdfplumber
from pdf2image import convert_from_path
from groq import Groq
from app.foundation.config import settings

logger = logging.getLogger(__name__)


def extract_text_local(pdf_path: str) -> str:
    """
    Extract text from PDF using pdfplumber (fast local method for text-embedded PDFs).
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Extracted text string, or empty string if PDF is image-only (scan)
    """
    try:
        text_content = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_content.append(page_text)
        
        full_text = "\n".join(text_content)
        logger.info(f"Local extraction successful: {len(full_text)} characters extracted")
        return full_text
    except Exception as e:
        logger.warning(f"Local extraction failed: {e}")
        return ""


def extract_text_vision(pdf_path: str) -> str:
    """
    Extract text from PDF using Groq Vision API (llama-3.2-11b-vision-preview).
    Handles image-only PDFs and complex layouts.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Extracted text from Vision API
        
    Raises:
        ValueError: If Groq API key is not configured
        Exception: If vision extraction fails
    """
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY environment variable not set")
    
    client = Groq(api_key=settings.groq_api_key)
    
    try:
        logger.info(f"Converting PDF to images: {pdf_path}")
        # Convert PDF to images (JPEG format in memory)
        images = convert_from_path(pdf_path, dpi=200)
        logger.info(f"Converted to {len(images)} pages")
        
        if not images:
            raise ValueError("PDF conversion produced no images")
        
        text_content = []
        
        # Process each page with Groq Vision API
        for page_num, image in enumerate(images, 1):
            logger.info(f"Processing page {page_num}/{len(images)} with Vision API")
            
            # Convert PIL Image to bytes (JPEG format)
            from io import BytesIO
            img_bytes = BytesIO()
            image.save(img_bytes, format="JPEG")
            img_bytes.seek(0)
            base64_image = __import__('base64').b64encode(img_bytes.read()).decode()
            
            # Call Groq Vision API
            response = client.chat.completions.create(
                model="llama-3.2-11b-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Transcribe ALL text from this invoice image exactly as it appears. Use markdown formatting with line breaks and columns. Include: vendor name, invoice number, date, all line items with descriptions, quantities, prices, and total amount. Be precise and complete."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.1,
                max_tokens=2048
            )
            
            page_text = response.choices[0].message.content
            if page_text:
                text_content.append(f"--- Page {page_num} ---\n{page_text}")
        
        full_text = "\n".join(text_content)
        logger.info(f"Vision extraction successful: {len(full_text)} characters extracted from {len(images)} pages")
        return full_text
        
    except Exception as e:
        logger.error(f"Vision extraction failed: {e}")
        raise


def extract_text(pdf_path: str, skip_local: bool = False) -> str:
    """
    Main extraction orchestrator. Uses Vision API by default, optionally falls back to pdfplumber.
    
    Args:
        pdf_path: Path to the PDF file
        skip_local: If True, skip pdfplumber fallback and use only Vision API (default: False)
        
    Returns:
        Extracted text string
        
    Raises:
        FileNotFoundError: If PDF file not found
        Exception: If all extraction methods fail
    """
    # Validate file exists
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    logger.info(f"Starting text extraction from {pdf_path}")
    
    # Try Vision API first (primary method)
    try:
        vision_text = extract_text_vision(pdf_path)
        if vision_text.strip():
            logger.info("Vision API extraction successful")
            return vision_text
        logger.warning("Vision API returned empty text")
    except Exception as e:
        logger.warning(f"Vision API extraction failed: {e}")
    
    # Fallback to pdfplumber if Vision fails (unless skipped)
    if not skip_local:
        logger.info("Falling back to pdfplumber extraction")
        try:
            local_text = extract_text_local(pdf_path)
            if local_text.strip():
                logger.info("pdfplumber extraction successful")
                return local_text
        except Exception as e:
            logger.warning(f"pdfplumber fallback also failed: {e}")
    
    # If both methods failed, raise error
    logger.error("All extraction methods failed")
    raise RuntimeError(f"Failed to extract text from PDF: {pdf_path}")
