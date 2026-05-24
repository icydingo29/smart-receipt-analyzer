"""SQLAlchemy ORM models for database persistence."""
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, Numeric, Index, func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone
from app.database import Base


class Receipt(Base):
    """Receipt metadata table storing invoice header information."""
    
    __tablename__ = "receipts"
    
    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(100), nullable=True, index=True)
    invoice_date = Column(String(50), nullable=True)  # Stored as ISO format string for flexibility
    issuer_name = Column(String(255), nullable=False)
    issuer_id = Column(String(100), nullable=True)
    receiver_name = Column(String(255), nullable=True)
    receiver_id = Column(String(100), nullable=True)
    total_amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    processing_timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    raw_llm_response = Column(Text, nullable=False)
    parsed_result = Column(JSONB, nullable=False)  # PostgreSQL JSONB for full parsed schema
    pdf_report_path = Column(String(512), nullable=True)
    
    # Relationship to line items
    line_items = relationship("LineItem", back_populates="receipt", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_invoice_number', 'invoice_number'),
        Index('idx_processing_timestamp', 'processing_timestamp'),
    )
    
    def __repr__(self):
        return f"<Receipt(id={self.id}, invoice_number={self.invoice_number}, total={self.total_amount})>"


class LineItem(Base):
    """Line items table storing individual invoice line details."""
    
    __tablename__ = "line_items"
    
    id = Column(Integer, primary_key=True, index=True)
    receipt_id = Column(Integer, ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(100), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    
    # Relationship back to receipt
    receipt = relationship("Receipt", back_populates="line_items")
    
    __table_args__ = (
        Index('idx_receipt_id', 'receipt_id'),
        Index('idx_category', 'category'),
    )
    
    def __repr__(self):
        return f"<LineItem(id={self.id}, receipt_id={self.receipt_id}, category={self.category}, amount={self.amount})>"
