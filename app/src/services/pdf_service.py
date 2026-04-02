"""PDF generation for invoices and estimates using ReportLab."""

import io
import os
import logging
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.colors import HexColor

logger = logging.getLogger(__name__)

# Page dimensions
PAGE_WIDTH, PAGE_HEIGHT = letter
MARGIN = 0.6 * inch


def _hex_to_color(hex_str: str | None) -> colors.Color:
    """Convert hex color string to ReportLab color."""
    if not hex_str:
        return HexColor("#1e40af")
    try:
        return HexColor(hex_str)
    except Exception:
        return HexColor("#1e40af")


def generate_invoice_pdf(
    org: dict,
    invoice: dict,
    customer: dict,
    line_items: list[dict],
) -> bytes:
    """Generate a PDF for an invoice or estimate.

    Args:
        org: {name, phone, email, address, city, state, zip_code, primary_color}
        invoice: {invoice_number, document_type, subject, status, issue_date, due_date,
                  subtotal, discount, tax_rate, tax_amount, total, amount_paid, balance, notes}
        customer: {display_name, company_name, email, billing_address}
        line_items: [{description, quantity, unit_price, amount, is_taxed}]

    Returns:
        PDF file bytes
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )

    brand_color = _hex_to_color(org.get("primary_color"))
    styles = getSampleStyleSheet()

    # Custom styles
    style_title = ParagraphStyle("DocTitle", parent=styles["Heading1"], fontSize=22, textColor=brand_color, spaceAfter=2)
    style_subtitle = ParagraphStyle("DocSubtitle", parent=styles["Normal"], fontSize=9, textColor=colors.gray)
    style_label = ParagraphStyle("Label", parent=styles["Normal"], fontSize=8, textColor=colors.gray, spaceBefore=6)
    style_value = ParagraphStyle("Value", parent=styles["Normal"], fontSize=10)
    style_value_right = ParagraphStyle("ValueRight", parent=styles["Normal"], fontSize=10, alignment=TA_RIGHT)
    style_total_label = ParagraphStyle("TotalLabel", parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold", alignment=TA_RIGHT)
    style_total_value = ParagraphStyle("TotalValue", parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold", alignment=TA_RIGHT)
    style_notes = ParagraphStyle("Notes", parent=styles["Normal"], fontSize=9, textColor=colors.Color(0.3, 0.3, 0.3))
    style_footer = ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, textColor=colors.gray, alignment=TA_CENTER)

    elements = []
    is_estimate = invoice.get("document_type") == "estimate"
    doc_label = "ESTIMATE" if is_estimate else "INVOICE"

    # --- Header: Company name + doc type ---
    org_name = org.get("name", "")
    header_data = [
        [Paragraph(org_name, style_title), Paragraph(doc_label, style_title)],
    ]
    header_table = Table(header_data, colWidths=[3.5 * inch, 3.5 * inch])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    elements.append(header_table)

    # Org contact line
    org_parts = []
    if org.get("city"):
        loc = org["city"]
        if org.get("state"):
            loc += f", {org['state']}"
        if org.get("zip_code"):
            loc += f" {org['zip_code']}"
        org_parts.append(loc)
    if org.get("phone"):
        org_parts.append(org["phone"])
    if org.get("email"):
        org_parts.append(org["email"])
    if org_parts:
        elements.append(Paragraph(" · ".join(org_parts), style_subtitle))

    elements.append(Spacer(1, 12))
    elements.append(HRFlowable(width="100%", thickness=1, color=brand_color, spaceAfter=12))

    # --- Bill To + Invoice Details side by side ---
    # Left: Bill To
    bill_to_parts = []
    cust_name = customer.get("display_name") or customer.get("company_name") or ""
    if cust_name:
        bill_to_parts.append(Paragraph(f"<b>{cust_name}</b>", style_value))
    if customer.get("company_name") and customer.get("display_name") and customer["company_name"] != customer["display_name"]:
        bill_to_parts.append(Paragraph(customer["company_name"], style_value))
    if customer.get("billing_address"):
        for line in customer["billing_address"].split("\n"):
            bill_to_parts.append(Paragraph(line.strip(), style_value))
    if customer.get("email"):
        bill_to_parts.append(Paragraph(customer["email"], style_subtitle))

    left_cell = [Paragraph("BILL TO", style_label)] + bill_to_parts

    # Right: Invoice details
    inv_number = invoice.get("invoice_number") or "DRAFT"
    right_parts = [Paragraph("DETAILS", style_label)]
    right_parts.append(Paragraph(f"<b>Number:</b> {inv_number}", style_value))
    if invoice.get("issue_date"):
        d = invoice["issue_date"]
        if isinstance(d, date):
            d = d.strftime("%m/%d/%Y")
        right_parts.append(Paragraph(f"<b>Date:</b> {d}", style_value))
    if invoice.get("due_date") and not is_estimate:
        d = invoice["due_date"]
        if isinstance(d, date):
            d = d.strftime("%m/%d/%Y")
        right_parts.append(Paragraph(f"<b>Due:</b> {d}", style_value))
    if invoice.get("subject"):
        right_parts.append(Paragraph(f"<b>Subject:</b> {invoice['subject']}", style_value))

    info_data = [[left_cell, right_parts]]
    info_table = Table(info_data, colWidths=[3.5 * inch, 3.5 * inch])
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 20))

    # --- Line Items Table ---
    col_widths = [3.6 * inch, 0.7 * inch, 1.1 * inch, 1.1 * inch, 0.5 * inch]
    table_data = [["Description", "Qty", "Unit Price", "Amount", "Tax"]]

    for li in line_items:
        qty = li.get("quantity", 1)
        unit = li.get("unit_price", 0)
        amt = li.get("amount", qty * unit)
        taxed = "✓" if li.get("is_taxed") else ""
        table_data.append([
            Paragraph(li.get("description", ""), style_value),
            f"{qty:g}",
            f"${unit:,.2f}",
            f"${amt:,.2f}",
            taxed,
        ])

    items_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    items_table.setStyle(TableStyle([
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), brand_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        # Data rows
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        # Alignment
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (4, 0), (4, -1), "CENTER"),
        # Grid
        ("LINEBELOW", (0, 0), (-1, 0), 1, brand_color),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.Color(0.85, 0.85, 0.85)),
        # Alternating row colors
        *[("BACKGROUND", (0, i), (-1, i), colors.Color(0.97, 0.97, 0.97))
          for i in range(2, len(table_data), 2)],
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 16))

    # --- Totals ---
    subtotal = invoice.get("subtotal", 0)
    discount = invoice.get("discount", 0)
    tax_amount = invoice.get("tax_amount", 0)
    tax_rate = invoice.get("tax_rate", 0)
    total = invoice.get("total", 0)
    amount_paid = invoice.get("amount_paid", 0)
    balance = invoice.get("balance", 0)

    totals_data = []
    totals_data.append(["Subtotal", f"${subtotal:,.2f}"])
    if discount > 0:
        totals_data.append(["Discount", f"-${discount:,.2f}"])
    if tax_amount > 0:
        totals_data.append([f"Tax ({tax_rate}%)", f"${tax_amount:,.2f}"])
    totals_data.append(["Total", f"${total:,.2f}"])
    if not is_estimate and amount_paid > 0:
        totals_data.append(["Paid", f"${amount_paid:,.2f}"])
        totals_data.append(["Balance Due", f"${balance:,.2f}"])

    # Format totals as right-aligned paragraphs
    formatted_totals = []
    for i, (label, value) in enumerate(totals_data):
        is_bold = label in ("Total", "Balance Due")
        s_label = style_total_label if is_bold else style_value_right
        s_value = style_total_value if is_bold else style_value_right
        formatted_totals.append([Paragraph(label, s_label), Paragraph(value, s_value)])

    totals_table = Table(formatted_totals, colWidths=[1.4 * inch, 1.2 * inch])
    totals_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        # Line above Total row
        ("LINEABOVE", (0, -1 if is_estimate or amount_paid == 0 else -3), (-1, -1 if is_estimate or amount_paid == 0 else -3), 0.5, colors.Color(0.7, 0.7, 0.7)),
        # Line above Balance Due if it exists
        *([("LINEABOVE", (0, -1), (-1, -1), 1, brand_color)] if not is_estimate and amount_paid > 0 else []),
    ]))

    # Right-align the totals table
    wrapper = Table([[None, totals_table]], colWidths=[4.4 * inch, 2.6 * inch])
    wrapper.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    elements.append(wrapper)

    # --- Notes ---
    if invoice.get("notes"):
        elements.append(Spacer(1, 24))
        elements.append(Paragraph("NOTES", style_label))
        elements.append(Spacer(1, 4))
        for line in invoice["notes"].split("\n"):
            elements.append(Paragraph(line, style_notes))

    # --- Footer ---
    elements.append(Spacer(1, 30))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.Color(0.85, 0.85, 0.85), spaceAfter=8))
    elements.append(Paragraph(f"Thank you for your business — {org_name}", style_footer))

    doc.build(elements)
    return buf.getvalue()
