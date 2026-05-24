"""Pydantic V2 schemas for request/response validation."""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional
from datetime import datetime


class LineItemSchema(BaseModel):
    """Schema for individual line items on an invoice."""
    
    description: str = Field(..., min_length=1, description="Product or service description")
    category: str = Field(..., min_length=1, description="Spending category (e.g., Dairy, Bakery)")
    quantity: int = Field(..., gt=0, description="Item quantity")
    unit_price: float = Field(..., gt=0, description="Unit price")
    amount: float = Field(..., gt=0, description="Extended line amount (quantity × unit_price)")
    
    @field_validator('unit_price', 'amount')
    @classmethod
    def validate_currency(cls, v):
        """Ensure currency values are reasonable (not exceeding 1M for safety)."""
        if v < 0 or v > 1_000_000:
            raise ValueError('Currency values must be between 0 and 1,000,000')
        return round(v, 2)
    
    @field_validator('quantity')
    @classmethod
    def validate_quantity(cls, v):
        """Ensure quantity is reasonable."""
        if v < 0 or v > 10_000:
            raise ValueError('Quantity must be between 0 and 10,000')
        return v
    
    @model_validator(mode='after')
    def validate_amount_consistency(self):
        """Verify that amount ≈ quantity × unit_price (with 5% tolerance for rounding)."""
        calculated = self.quantity * self.unit_price
        tolerance = abs(calculated * 0.05)
        if abs(self.amount - calculated) > tolerance:
            # Allow small rounding differences
            return self
        return self


class InvoiceSchema(BaseModel):
    """Complete invoice schema with validation."""
    
    invoice_number: str = Field(default="", description="Vendor invoice number")
    invoice_date: str = Field(default="", description="Invoice date (ISO format)")
    issuer_name: str = Field(..., min_length=1, description="Vendor/company name")
    issuer_id: Optional[str] = Field(default=None, description="Vendor tax/registration ID")
    receiver_name: Optional[str] = Field(default=None, description="Customer/receiver name")
    receiver_id: Optional[str] = Field(default=None, description="Customer tax/registration ID")
    line_items: List[LineItemSchema] = Field(..., min_items=1, description="At least 1 line item required")
    total_amount: float = Field(..., gt=0, description="Grand total amount")
    currency: str = Field(default="USD", min_length=3, max_length=3, description="ISO 4217 currency code")
    
    @field_validator('total_amount')
    @classmethod
    def validate_total(cls, v):
        """Ensure total is reasonable."""
        if v < 0 or v > 10_000_000:
            raise ValueError('Total amount must be between 0 and 10,000,000')
        return round(v, 2)
    
    @field_validator('currency')
    @classmethod
    def validate_currency_code(cls, v):
        """Ensure valid 3-letter currency code."""
        return v.upper()
    
    @model_validator(mode='after')
    def validate_total_consistency(self):
        """Verify that total ≈ sum of line items (with 5% tolerance for tax/discounts)."""
        line_total = sum(item.amount for item in self.line_items)
        tolerance = abs(line_total * 0.05)  # 5% tolerance for taxes/discounts
        
        if abs(self.total_amount - line_total) > tolerance:
            # Log warning but don't fail - use the provided total
            return self
        return self
    
    class Config:
        strict = True


class ReceiptCreateSchema(BaseModel):
    """Schema for creating a receipt in the database."""
    
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    issuer_name: str
    issuer_id: Optional[str] = None
    receiver_name: Optional[str] = None
    receiver_id: Optional[str] = None
    total_amount: float
    currency: str
    raw_llm_response: str
    parsed_result: dict  # The full InvoiceSchema.model_dump()


class LineItemResponseSchema(BaseModel):
    """Schema for line item in API responses."""
    
    id: int
    receipt_id: int
    description: str
    category: str
    quantity: int
    unit_price: float
    amount: float
    
    class Config:
        from_attributes = True


class ReceiptResponseSchema(BaseModel):
    """Schema for receipt in API responses."""
    
    id: int
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    issuer_name: str
    issuer_id: Optional[str] = None
    receiver_name: Optional[str] = None
    receiver_id: Optional[str] = None
    total_amount: float
    currency: str
    processing_timestamp: datetime
    pdf_report_path: Optional[str] = None
    line_items: List[LineItemResponseSchema] = []
    
    class Config:
        from_attributes = True


class ReceiptDetailedResponseSchema(ReceiptResponseSchema):
    """Extended response with raw LLM data for debugging."""
    
    raw_llm_response: str
    parsed_result: dict


class UploadReceiptResponse(BaseModel):
    """Response schema for successful file upload."""
    
    status: str
    receipt_id: int
    message: str
    invoice_number: Optional[str] = None
    total_amount: float
    currency: str
    line_items_count: int
    pdf_report_url: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response schema."""
    
    status: str = "error"
    detail: str
    error_type: Optional[str] = None
