"""LLM processor for enriching OCR data and categorizing line items using Groq API."""
import json
import logging
from typing import Tuple
from groq import Groq
from app.foundation.config import settings
from app.data.schemas import InvoiceSchema

logger = logging.getLogger(__name__)


def enrich_and_categorize(raw_text: str) -> str:
    """
    Send extracted text to Groq LLM for enrichment and categorization.
    Uses llama-3.3-70b-versatile by default with JSON mode for structured output.
    
    Args:
        raw_text: Raw unstructured text from OCR
        
    Returns:
        Raw JSON string response from LLM
        
    Raises:
        ValueError: If Groq API key is not configured
        Exception: If API call fails
    """
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY environment variable not set")
    
    client = Groq(api_key=settings.groq_api_key)
    
    system_prompt = """You are an expert receipt analyzer. Your task is to parse raw OCR text from invoices and return a strict, validated JSON result.

1. IDENTIFY and CORRECT OCR ERRORS:
    - Correct obvious OCR mistakes in product names, numbers, and dates.

2. CONTEXT-AWARE CATEGORIZATION:
    - Determine vendor type (e.g., grocery store, restaurant, pharmacy, clothing store, etc.) and use categories appropriate to that vendor.
    - For grocery stores: use categories like Dairy, Bakery, Beverages, Meat, Produce, Household, etc.
    - For restaurants: use Appetizers, Main Course, Dessert, Beverages (Alcoholic), Beverages (Non-Alcoholic), etc.
    - For pharmacies: use Medications, Health Products, Personal Care, Supplements, etc.
    - For other vendors: adapt categories to the business context and group similar items together.

3. DIVERSIFY CATEGORIES (Important):
    - Do NOT assign the exact same category to more than 60% of distinct line items.
    - If assigning one category would exceed 60%, you MUST:
         a) split that category into meaningful subcategories based on item descriptions, OR
         b) assign more specific categories (e.g., Food → Appetizer/Main Course/Dessert).

4. EXTRACT STRUCTURED FIELDS (required):
    - invoice_number: string
    - invoice_date: YYYY-MM-DD
    - issuer_name: string (REQUIRED)
    - issuer_id: string or null
    - receiver_name: string or null
    - receiver_id: string or null
    - total_amount: float
    - currency: 3-letter ISO code (e.g., USD)

5. LINE ITEM REQUIREMENTS:
    - Each line item MUST include:
         - description: non-empty string
         - category: non-empty string
         - quantity: integer (if missing, assume 1)
         - unit_price: float (MUST be > 0; two decimals)
         - amount: float (MUST be > 0; amount = quantity × unit_price)
    - If a line item does NOT have a readable non-zero price or quantity, DO NOT include it in `line_items`.

6. NUMERIC FORMATTING RULES:
    - Return `unit_price`, `amount`, and `total_amount` as floats rounded to two decimal places (e.g., 12.34).

7. OCR QUALITY FAILURE:
    - If the OCR text is too poor to extract reliable prices for the majority of items, return an error JSON object instead of fabricated values:
      {"error": "ocr_quality", "detail": "brief explanation"}

8. OUTPUT REQUIREMENTS:
    - Return ONLY valid JSON, matching the exact schema below. No explanatory text, no markdown, no extra fields outside the schema.

Required JSON schema (include these fields exactly):
{
  "invoice_number": "string",
  "invoice_date": "YYYY-MM-DD",
  "issuer_name": "string",
  "issuer_id": "string or null",
  "receiver_name": "string or null",
  "receiver_id": "string or null",
  "line_items": [
    {
      "description": "string",
      "category": "string",
      "quantity": integer,
      "unit_price": float,
      "amount": float
    }
  ],
  "total_amount": float,
  "currency": "USD or other ISO code"
}

CRITICAL: Return ONLY valid JSON that strictly follows the schema above. No additional text.
"""

    user_prompt = f"""Parse this raw OCR text from an invoice and extract structured data:

{raw_text}

Return only valid JSON matching the required schema."""

    try:
        logger.info("Calling Groq LLM for enrichment and categorization")
        
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            temperature=0.1,  # Low temperature for consistency
            max_tokens=4096,
            response_format={"type": "json_object"}
        )
        
        raw_response = getattr(response.choices[0].message, "content", "") or ""
        logger.info(f"LLM response received: {len(raw_response)} characters")
        return raw_response
        
    except Exception as e:
        logger.error(f"LLM enrichment failed: {e}")
        raise RuntimeError(f"Failed to enrich data with LLM: {e}")


def validate_and_parse(raw_llm_response: str) -> Tuple[str, InvoiceSchema]:
    """
    Validate and parse the raw LLM response using Pydantic schema.
    
    Args:
        raw_llm_response: Raw JSON string from LLM
        
    Returns:
        Tuple of (raw_response, validated InvoiceSchema instance)
        
    Raises:
        ValueError: If JSON parsing or validation fails
    """
    try:
        logger.info("Validating LLM response with Pydantic schema")
        
        # Parse JSON
        try:
            json_data = json.loads(raw_llm_response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}")
            raise ValueError(f"Invalid JSON from LLM: {e}")
        
        # Check for OCR quality failure reported by the LLM
        if "error" in json_data:
            detail = json_data.get("detail", "OCR quality too poor to extract reliable data")
            logger.error(f"LLM reported OCR quality failure: {detail}")
            raise ValueError(f"OCR quality error: {detail}")

        # Validate with Pydantic schema
        try:
            invoice_schema = InvoiceSchema.model_validate(json_data)
            logger.info(f"Validation successful: {len(invoice_schema.line_items)} line items, total: {invoice_schema.total_amount}")
            return raw_llm_response, invoice_schema
        except Exception as e:
            logger.error(f"Schema validation failed: {e}")
            raise ValueError(f"Schema validation failed: {e}")
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during validation: {e}")
        raise ValueError(f"Unexpected error during validation: {e}")
