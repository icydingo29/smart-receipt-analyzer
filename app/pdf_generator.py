"""PDF report generation using ReportLab Platypus."""
import logging
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from app.schemas import InvoiceSchema
from app.config import settings

logger = logging.getLogger(__name__)


def generate_report_pdf(invoice_schema: InvoiceSchema, receipt_id: int, output_path: str) -> str:
    """
    Generate a professional PDF expense report from validated invoice data.
    
    Args:
        invoice_schema: Validated InvoiceSchema instance
        receipt_id: Database receipt ID for file naming
        output_path: Directory path where PDF will be saved
        
    Returns:
        Full path to generated PDF file
        
    Raises:
        IOError: If PDF generation or file write fails
    """
    try:
        # Ensure output directory exists
        Path(output_path).mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        filename = f"report_{receipt_id}.pdf"
        filepath = Path(output_path) / filename
        
        logger.info(f"Generating PDF report: {filepath}")
        
        # Create PDF document
        doc = SimpleDocTemplate(
            str(filepath),
            pagesize=letter,
            rightMargin=0.5 * inch,
            leftMargin=0.5 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.5 * inch
        )
        
        # Container for PDF elements
        story = []
        
        # Get styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=20,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        header_style = ParagraphStyle(
            'CustomHeader',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#333333'),
            spaceAfter=4,
            alignment=TA_LEFT
        )
        
        # Add title
        story.append(Paragraph("EXPENSE REPORT", title_style))
        story.append(Spacer(1, 0.15 * inch))
        
        # Add header information
        header_data = [
            ["Vendor:", invoice_schema.issuer_name],
            ["Date:", invoice_schema.invoice_date or "N/A"],
            ["Invoice #:", invoice_schema.invoice_number or "N/A"],
            ["Currency:", invoice_schema.currency],
        ]
        
        if invoice_schema.issuer_id:
            header_data.append(["Vendor ID:", invoice_schema.issuer_id])
        
        for label, value in header_data:
            story.append(Paragraph(f"<b>{label}</b> {value}", header_style))
        
        story.append(Spacer(1, 0.2 * inch))
        
        # Calculate category totals
        category_totals = {}
        for item in invoice_schema.line_items:
            category = item.category
            if category not in category_totals:
                category_totals[category] = Decimal('0')
            category_totals[category] += Decimal(str(item.amount))
        
        # Build line items table
        line_items_table_data = [
            ["#", "Item Description", "Category", "Qty", "Amount"]
        ]
        
        for idx, item in enumerate(invoice_schema.line_items, 1):
            line_items_table_data.append([
                str(idx),
                item.description[:50],  # Truncate long descriptions
                item.category,
                str(item.quantity),
                f"{float(item.amount):.2f}"
            ])
        
        # Create line items table
        line_items_table = Table(
            line_items_table_data,
            colWidths=[0.4 * inch, 2.5 * inch, 1.2 * inch, 0.6 * inch, 1 * inch]
        )
        
        line_items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ]))
        
        story.append(line_items_table)
        story.append(Spacer(1, 0.2 * inch))
        
        # Build category summary table
        summary_data = [
            ["CATEGORY SUMMARY", ""]
        ]
        
        for category in sorted(category_totals.keys()):
            summary_data.append([
                category,
                f"{float(category_totals[category]):.2f}"
            ])
        
        # Add total row
        summary_data.append([
            "TOTAL",
            f"{float(invoice_schema.total_amount):.2f}"
        ])
        
        summary_table = Table(summary_data, colWidths=[3.5 * inch, 1.5 * inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor('#f5f5f5')),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.whitesmoke),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 11),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ]))
        
        story.append(summary_table)
        story.append(Spacer(1, 0.15 * inch))
        
        # Add footer with generation timestamp
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER
        )
        story.append(Paragraph(
            f"Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            footer_style
        ))
        
        # Build and write PDF
        doc.build(story)
        logger.info(f"PDF report generated successfully: {filepath}")
        return str(filepath)
        
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        raise IOError(f"Failed to generate PDF report: {e}")
