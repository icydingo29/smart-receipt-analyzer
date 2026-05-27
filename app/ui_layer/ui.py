"""Streamlit web interface for Smart Receipt Analyzer."""
import streamlit as st
import requests
import pandas as pd
from pathlib import Path
from typing import Optional
import json
import os

# Configure Streamlit
st.set_page_config(
    page_title="Smart Receipt Analyzer",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API configuration - use service name in Docker, localhost for development
API_URL = os.getenv("API_URL", "http://app:8000")

def check_api_health() -> bool:
    """Check if FastAPI backend is available."""
    try:
        response = requests.get(f"{API_URL}/health", timeout=2)
        return response.status_code == 200
    except:
        return False


def upload_receipt(pdf_file) -> Optional[dict]:
    """Upload and process a receipt PDF."""
    try:
        files = {"file": (pdf_file.name, pdf_file, "application/pdf")}
        response = requests.post(f"{API_URL}/api/receipts", files=files, timeout=120)
        
        if response.status_code == 200:
            return response.json()
        else:
            try:
                error_detail = response.json().get('detail', 'Unknown error')
            except:
                error_detail = f"HTTP {response.status_code}: {response.text}"
            st.error(f"Upload failed: {error_detail}")
            return None
    except Exception as e:
        st.error(f"Error uploading file: {str(e)}")
        return None


def get_receipt_details(receipt_id: int) -> Optional[dict]:
    """Fetch receipt details from API."""
    try:
        response = requests.get(f"{API_URL}/api/receipts/{receipt_id}", timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        st.error(f"Error fetching receipt: {str(e)}")
        return None


def get_receipts_list(skip: int = 0, limit: int = 20) -> Optional[dict]:
    """Fetch list of receipts from API."""
    try:
        response = requests.get(
            f"{API_URL}/api/receipts",
            params={"skip": skip, "limit": limit},
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        st.error(f"Error fetching receipts: {str(e)}")
        return None


def download_report(receipt_id: int) -> Optional[bytes]:
    """Download PDF report for a receipt."""
    try:
        response = requests.get(
            f"{API_URL}/api/receipts/{receipt_id}/report",
            timeout=10
        )
        if response.status_code == 200:
            return response.content
        else:
            st.error(f"Error downloading report: {response.json().get('detail', 'Unknown error')}")
            return None
    except Exception as e:
        st.error(f"Error downloading report: {str(e)}")
        return None


# Page header
st.title("📄 Smart Receipt Analyzer")
st.markdown("Process PDF invoices with OCR, AI enrichment, and automated categorization")

# Check API health
if not check_api_health():
    st.error("⚠️ Backend API is not available. Please ensure the FastAPI service is running on http://localhost:8000")
    st.stop()

# Create tabs
tab1, tab2, tab3 = st.tabs(["Upload Receipt", "View Receipts", "About"])

# Tab 1: Upload Receipt
with tab1:
    st.header("Upload Invoice")
    
    uploaded_file = st.file_uploader(
        "Select a PDF invoice to process",
        type=["pdf"],
        help="Upload a PDF invoice with at least 8 line items"
    )
    
    if uploaded_file:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.write(f"**File:** {uploaded_file.name}")
            st.write(f"**Size:** {uploaded_file.size / 1024:.2f} KB")
        
        with col2:
            if st.button("📤 Process Invoice", use_container_width=True, key="upload_btn"):
                with st.spinner("Processing invoice... This may take a minute."):
                    result = upload_receipt(uploaded_file)
                    
                    if result:
                        st.success("✅ Invoice processed successfully!")
                        
                        # Display results
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Receipt ID", result["receipt_id"])
                        with col2:
                            st.metric("Total Amount", f"{result['total_amount']:.2f} {result['currency']}")
                        with col3:
                            st.metric("Line Items", result["line_items_count"])
                        
                        st.info(f"Invoice #: {result['invoice_number']}")
                        
                        # Download button
                        pdf_data = download_report(result["receipt_id"])
                        if pdf_data:
                            st.download_button(
                                label="📥 Download PDF Report",
                                data=pdf_data,
                                file_name=f"expense_report_{result['receipt_id']}.pdf",
                                mime="application/pdf",
                                use_container_width=True,
                                key=f"download_upload_{result['receipt_id']}"
                            )
                        
                        # Store receipt ID in session for viewing
                        st.session_state.last_receipt_id = result["receipt_id"]


# Tab 2: View Receipts
with tab2:
    st.header("Processed Receipts")
    
    # Fetch receipts list
    receipts_data = get_receipts_list(limit=50)
    
    if receipts_data and receipts_data["count"] > 0:
        st.write(f"Total receipts: **{receipts_data['total']}**")
        
        # Display receipts in a table
        receipts = receipts_data["receipts"]
        
        table_data = []
        for receipt in receipts:
            table_data.append({
                "ID": receipt["id"],
                "Invoice #": receipt["invoice_number"] or "N/A",
                "Issuer": receipt["issuer_name"],
                "Receiver": receipt["receiver_name"],
                "Total": f"{receipt['total_amount']:.2f}",
                "Currency": f"{receipt['currency']}",
                "Items": len(receipt["line_items"]),
                "Invoice Date": receipt["invoice_date"] or "N/A",
                "Date of Processing": receipt["processing_timestamp"][:10]
            })
        
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # View receipt details
        st.subheader("Receipt Details")
        receipt_id = st.selectbox(
            "Select a receipt to view details:",
            options=[r["id"] for r in receipts],
            format_func=lambda x: f"Receipt #{x}: {next(r['issuer_name'] for r in receipts if r['id'] == x)}"
        )
        
        if receipt_id:
            receipt_details = get_receipt_details(receipt_id)
            if receipt_details:
                # Header information
                col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
                with col1:
                    st.metric("Invoice #", receipt_details["invoice_number"] or "N/A")
                with col2:
                    st.metric("Issuer", receipt_details["issuer_name"])
                with col3:
                    st.metric("Receiver", receipt_details["receiver_name"])
                with col4:
                    st.metric("Total", f"{receipt_details['total_amount']:.2f}")
                with col5:
                    st.metric("Currency", f"{receipt_details['currency']}")
                with col6:
                    st.metric("Invoice Date", receipt_details["invoice_date"] or "N/A")
                with col7:
                    st.metric("Date of Processing", receipt_details["processing_timestamp"][:10])
                
                # Line items table
                st.subheader("Line Items")
                line_items = receipt_details["line_items"]
                
                items_data = []
                for item in line_items:
                    items_data.append({
                        "Description": item["description"],
                        "Category": item["category"],
                        "Qty": item["quantity"],
                        "Unit Price": f"{item['unit_price']:.2f}",
                        "Amount": f"{item['amount']:.2f}"
                    })
                
                if items_data:
                    items_df = pd.DataFrame(items_data)
                    st.dataframe(items_df, use_container_width=True, hide_index=True)
                    
                    # Category summary
                    st.subheader("Category Summary")
                    category_totals = {}
                    for item in line_items:
                        category = item["category"]
                        if category not in category_totals:
                            category_totals[category] = 0
                        category_totals[category] += float(item["amount"])
                    
                    summary_df = pd.DataFrame([
                        {"Category": cat, "Total": f"{total:.2f}"}
                        for cat, total in sorted(category_totals.items())
                    ])
                    st.dataframe(summary_df, use_container_width=True, hide_index=True)
                
                # Download button
                col1, col2 = st.columns(2)
                with col1:
                    pdf_data = download_report(receipt_id)
                    if pdf_data:
                        st.download_button(
                            label="📥 Download PDF Report",
                            data=pdf_data,
                            file_name=f"expense_report_{receipt_id}.pdf",
                            mime="application/pdf",
                            key=f"download_view_{receipt_id}",
                            use_container_width=True
                        )
    else:
        st.info("No receipts processed yet. Upload one in the 'Upload Receipt' tab.")


# Tab 3: About
with tab3:
    st.header("About Smart Receipt Analyzer")
    
    st.markdown("""
    ### Features
    - 📄 **OCR Processing**: Extracts text from PDF invoices using advanced OCR
    - 🤖 **AI Enrichment**: Uses Groq LLM to categorize items and correct OCR errors
    - 💾 **Database Storage**: Persists all data in PostgreSQL
    - 📊 **PDF Reports**: Generates professional expense reports
    - 🔗 **REST API**: Full API access for programmatic usage
    
    ### How It Works
    1. **Upload**: Select a PDF invoice
    2. **Extract**: OCR extracts text from the PDF
    3. **Enrich**: LLM categorizes items and corrects errors
    4. **Validate**: Pydantic validates data integrity
    5. **Store**: Data saved to PostgreSQL
    6. **Report**: PDF expense report generated
    
    ### Technology Stack
    - **Backend**: FastAPI + FastAPI (Python)
    - **Database**: PostgreSQL
    - **OCR**: pdfplumber + Groq Vision
    - **LLM**: Groq (llama-3.3-70b-versatile)
    - **PDF**: ReportLab
    - **UI**: Streamlit
    
    ### API Endpoints
    - `POST /api/receipts` - Upload and process invoice
    - `GET /api/receipts` - List receipts
    - `GET /api/receipts/{id}` - Get receipt details
    - `GET /api/receipts/{id}/report` - Download PDF
    - `GET /health` - Health check
    """)
    
    st.info("For more information, visit the project repository on GitHub.")
