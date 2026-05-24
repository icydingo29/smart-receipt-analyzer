"""LLM processor for enriching OCR data and categorizing line items using Groq API."""
import json
import logging
from typing import Tuple
from groq import Groq
from app.config import settings
from app.schemas import InvoiceSchema

logger = logging.getLogger(__name__)


def enrich_and_categorize(raw_text: str) -> str:
    """
    Send extracted text to Groq LLM for enrichment and categorization.
    Uses llama-3.3-70b-versatile with JSON mode for structured output.
    
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
    
    system_prompt = """You are an expert receipt analyzer. Your task is to parse raw OCR text from invoices and:

1. IDENTIFY and CORRECT any OCR errors in item names and descriptions
2. CATEGORIZE each line item into a spending category such as:
   - Dairy (milk, cheese, yogurt, etc.)
   - Bakery (bread, pastries, cakes, etc.)
   - Beverages (juice, coffee, tea, water, etc.)
   - Meat (chicken, beef, pork, fish, etc.)
   - Household (soap, cleaning supplies, paper products, etc.)
   - Electronics (gadgets, batteries, cables, etc.)
   - Clothing (apparel, shoes, accessories, etc.)
   - Books (educational materials, magazines, etc.)
   - Pharmacy (medicines, health products, etc.)
   - Other (miscellaneous items)

3. EXTRACT structured fields:
   - invoice_number (vendor's invoice/receipt ID)
   - invoice_date (transaction date in YYYY-MM-DD format)
   - issuer_name (vendor/store name - REQUIRED)
   - issuer_id (vendor tax ID or registration number, if visible)
   - receiver_name (customer name, if visible)
   - receiver_id (customer ID, if visible)

4. ENSURE all line items have:
   - description (product/service name)
   - category (from list above)
   - quantity (number of units)
   - unit_price (price per unit)
   - amount (quantity × unit_price)

5. VERIFY mathematical consistency:
   - Ensure each line amount = quantity × unit_price
   - Ensure total_amount ≈ sum of all line amounts (allow 5% variance for taxes/discounts)
   - If amounts don't add up, recalculate assuming the largest items are correct

6. RETURN ONLY valid JSON matching this exact structure:
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

CRITICAL: Return ONLY valid JSON. No explanations, no markdown code blocks, no additional text."""

    user_prompt = f"""Parse this raw OCR text from an invoice and extract structured data:

{raw_text}

Return only valid JSON matching the required schema."""

    try:
        logger.info("Calling Groq LLM for enrichment and categorization")
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
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
            max_tokens=2048,
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
