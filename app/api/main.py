"""API layer: FastAPI application and REST endpoints."""
import logging
import os
from pathlib import Path
from typing import List
from datetime import datetime, timezone

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.foundation import settings, init_db, get_db
from app.data import Receipt, LineItem, InvoiceSchema, ReceiptResponseSchema, UploadReceiptResponse, ErrorResponse
from app.processing import extract_text, enrich_and_categorize, validate_and_parse, generate_report_pdf

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Smart Receipt Analyzer",
    description="Process PDF invoices with OCR and LLM enrichment",
    version="1.0.0"
)


@app.on_event("startup")
async def startup_event():
    """Initialize database on application startup."""
    logger.info("Starting Smart Receipt Analyzer")
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Smart Receipt Analyzer",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.post(
    "/api/receipts",
    response_model=UploadReceiptResponse,
    summary="Upload and process a PDF invoice",
    tags=["Receipts"]
)
async def upload_receipt(
    file: UploadFile = File(..., description="PDF invoice file"),
    db: Session = Depends(get_db)
):
    """
    Upload and process a PDF invoice through the complete pipeline:
    1. OCR extraction (pdfplumber or Groq Vision)
    2. LLM enrichment and categorization (Groq llama-3.3-70b)
    3. Validation with Pydantic schemas
    4. Database persistence
    5. PDF report generation
    
    Returns:
        Receipt data with processing status and report URL
    """
    temp_file_path = None
    
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=400,
                detail="File must be a PDF. Please upload a .pdf file."
            )
        
        # Save uploaded file temporarily
        temp_file_path = Path(settings.temp_storage_path) / file.filename
        logger.info(f"Saving uploaded file: {temp_file_path}")
        
        contents = await file.read()
        with open(temp_file_path, 'wb') as f:
            f.write(contents)
        
        logger.info(f"File uploaded successfully: {len(contents)} bytes")
        
        # STEP 1: Extract text from PDF (OCR)
        logger.info("Step 1: OCR text extraction")
        raw_text = extract_text(str(temp_file_path))
        
        if not raw_text.strip():
            raise ValueError("No text could be extracted from the PDF")
        
        logger.info(f"Extracted {len(raw_text)} characters")
        
        # STEP 2: Enrich with LLM and get categorization
        logger.info("Step 2: LLM enrichment and categorization")
        raw_llm_response = enrich_and_categorize(raw_text)
        
        # STEP 3: Validate with Pydantic schema
        logger.info("Step 3: Schema validation")
        raw_response, invoice_schema = validate_and_parse(raw_llm_response)
        
        # STEP 4: Persist to database (with transaction)
        logger.info("Step 4: Database persistence")
        
        # Create Receipt record
        receipt = Receipt(
            invoice_number=invoice_schema.invoice_number or None,
            invoice_date=invoice_schema.invoice_date or None,
            issuer_name=invoice_schema.issuer_name,
            issuer_id=invoice_schema.issuer_id,
            receiver_name=invoice_schema.receiver_name,
            receiver_id=invoice_schema.receiver_id,
            total_amount=invoice_schema.total_amount,
            currency=invoice_schema.currency,
            processing_timestamp=datetime.now(timezone.utc),
            raw_llm_response=raw_response,
            parsed_result=invoice_schema.model_dump()
        )
        
        db.add(receipt)
        db.flush()  # Get the receipt ID without committing
        receipt_id = receipt.id
        logger.info(f"Receipt created with ID: {receipt_id}")
        
        # Create LineItem records
        for line_item_schema in invoice_schema.line_items:
            line_item = LineItem(
                receipt_id=receipt_id,
                description=line_item_schema.description,
                category=line_item_schema.category,
                quantity=line_item_schema.quantity,
                unit_price=line_item_schema.unit_price,
                amount=line_item_schema.amount
            )
            db.add(line_item)
        
        db.flush()  # Flush line items
        logger.info(f"Added {len(invoice_schema.line_items)} line items")
        
        # STEP 5: Generate PDF report
        logger.info("Step 5: PDF report generation")
        pdf_path = generate_report_pdf(
            invoice_schema,
            receipt_id,
            settings.storage_volume_path
        )
        
        # STEP 6: Update receipt with PDF path and commit
        receipt.pdf_report_path = pdf_path
        db.commit()
        logger.info(f"Receipt committed to database with PDF: {pdf_path}")
        
        # Clean up temp file
        if temp_file_path and temp_file_path.exists():
            temp_file_path.unlink()
        
        return UploadReceiptResponse(
            status="success",
            receipt_id=receipt_id,
            message="Invoice processed successfully",
            invoice_number=invoice_schema.invoice_number or "N/A",
            total_amount=float(invoice_schema.total_amount),
            currency=invoice_schema.currency,
            line_items_count=len(invoice_schema.line_items),
            pdf_report_url=f"/api/receipts/{receipt_id}/report"
        )
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        db.rollback()
        if temp_file_path and temp_file_path.exists():
            temp_file_path.unlink()
        raise HTTPException(status_code=400, detail=str(e))
    
    except Exception as e:
        logger.error(f"Processing error: {e}", exc_info=True)
        db.rollback()
        if temp_file_path and temp_file_path.exists():
            temp_file_path.unlink()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process invoice: {str(e)}"
        )


@app.get(
    "/api/receipts/{receipt_id}",
    response_model=ReceiptResponseSchema,
    summary="Get receipt details",
    tags=["Receipts"]
)
async def get_receipt(
    receipt_id: int,
    db: Session = Depends(get_db)
):
    """
    Retrieve a previously processed receipt by ID.
    
    Args:
        receipt_id: The database ID of the receipt
        
    Returns:
        Receipt details with all line items
    """
    try:
        receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
        
        if not receipt:
            raise HTTPException(status_code=404, detail=f"Receipt {receipt_id} not found")
        
        logger.info(f"Retrieved receipt {receipt_id}")
        return ReceiptResponseSchema.model_validate(receipt)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving receipt {receipt_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve receipt")


@app.get(
    "/api/receipts",
    response_model=dict,
    summary="List all processed receipts",
    tags=["Receipts"]
)
async def list_receipts(
    skip: int = Query(0, ge=0, description="Number of receipts to skip"),
    limit: int = Query(10, ge=1, le=100, description="Maximum receipts to return"),
    db: Session = Depends(get_db)
):
    """
    List all processed receipts with pagination.
    
    Args:
        skip: Number of receipts to skip (for pagination)
        limit: Maximum number of receipts to return
        
    Returns:
        Paginated list of receipts with metadata
    """
    try:
        total = db.query(Receipt).count()
        receipts = db.query(Receipt).order_by(desc(Receipt.processing_timestamp)).offset(skip).limit(limit).all()
        
        logger.info(f"Listed {len(receipts)} receipts (total: {total})")
        
        return {
            "status": "success",
            "total": total,
            "skip": skip,
            "limit": limit,
            "count": len(receipts),
            "receipts": [ReceiptResponseSchema.model_validate(r) for r in receipts]
        }
        
    except Exception as e:
        logger.error(f"Error listing receipts: {e}")
        raise HTTPException(status_code=500, detail="Failed to list receipts")


@app.get(
    "/api/receipts/{receipt_id}/report",
    summary="Download PDF expense report",
    tags=["Receipts"]
)
async def download_report(
    receipt_id: int,
    db: Session = Depends(get_db)
):
    """
    Download the generated PDF expense report for a receipt.
    
    Args:
        receipt_id: The database ID of the receipt
        
    Returns:
        PDF file as attachment
    """
    try:
        receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
        
        if not receipt:
            raise HTTPException(status_code=404, detail=f"Receipt {receipt_id} not found")
        
        if not receipt.pdf_report_path or not Path(receipt.pdf_report_path).exists():
            raise HTTPException(
                status_code=404,
                detail=f"PDF report not found for receipt {receipt_id}"
            )
        
        logger.info(f"Downloading report for receipt {receipt_id}")
        
        return FileResponse(
            receipt.pdf_report_path,
            media_type="application/pdf",
            filename=f"expense_report_{receipt_id}.pdf"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading report for receipt {receipt_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to download report")


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            status="error",
            detail=exc.detail,
            error_type="HTTPException"
        ).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle unexpected exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            status="error",
            detail="An unexpected error occurred",
            error_type=type(exc).__name__
        ).model_dump()
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.app_port)
