"""
VyapaarBandhu — Filing Summary PDF Generator
WeasyPrint + Jinja2. CA-branded with disclaimer footer.

CRITICAL: rcm_liability must be passed as Decimal to template.
Template uses {% if rcm_liability > 0 %} which requires numeric type.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from decimal import Decimal

import structlog
from jinja2 import Template

logger = structlog.get_logger()

PDF_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
  @page { size: A4; margin: 20mm; }
  body { font-family: 'Noto Sans', sans-serif; font-size: 10pt; color: #1a1a1a; }
  .header { display: flex; justify-content: space-between; border-bottom: 2px solid #2563EB; padding-bottom: 10px; margin-bottom: 15px; }
  .ca-firm-name { font-size: 16pt; font-weight: bold; color: #2563EB; }
  .pending-notice {
    background: #FEF3C7; border: 1px solid #F59E0B;
    padding: 8px; border-radius: 4px; margin: 10px 0;
    font-size: 9pt;
  }
  .flagged-notice {
    background: #FEE2E2; border: 1px solid #EF4444;
    padding: 8px; border-radius: 4px; margin: 10px 0;
    font-size: 9pt;
  }
  table { width: 100%; border-collapse: collapse; margin: 10px 0; }
  th { background: #2563EB; color: white; padding: 6px; font-size: 9pt; text-align: left; }
  td { padding: 5px; border-bottom: 1px solid #E5E7EB; font-size: 9pt; }
  .blocked { color: #DC2626; }
  .eligible { color: #16A34A; }
  .pending-badge { color: #D97706; }
  .summary-table td { font-weight: bold; }
  .disclaimer { font-size: 7pt; color: #6B7280; font-style: italic; margin-top: 20px; }
  .footer { font-size: 7pt; color: #9CA3AF; margin-top: 10px; border-top: 1px solid #E5E7EB; padding-top: 5px; }
</style>
</head>
<body>
  <div class="header">
    <div>
      <div class="ca-firm-name">{{ ca_firm_name }}</div>
      <div>{{ ca_proprietor_name }}</div>
    </div>
    <div style="text-align: right">
      <div><strong>GST Filing Summary</strong></div>
      <div>Period: {{ tax_period }}</div>
      <div>Client: {{ client_name }}</div>
      <div>GSTIN: {{ client_gstin or 'Not provided' }}</div>
      <div>Generated: {{ generated_at }}</div>
    </div>
  </div>

  {% if pending_count > 0 %}
  <div class="pending-notice">
    This summary includes {{ pending_count }} invoice(s) pending CA review.
    ITC figures are final only after all invoices are reviewed and approved.
  </div>
  {% endif %}

  <h3>ITC Summary</h3>
  <table class="summary-table">
    <tr><th>Type</th><th>Confirmed (Rs.)</th><th>Pending (Rs.)</th><th>Rejected (Rs.)</th></tr>
    <tr>
      <td>CGST Input Credit</td>
      <td class="eligible">{{ confirmed_cgst_itc }}</td>
      <td class="pending-badge">{{ pending_cgst_itc }}</td>
      <td class="blocked">{{ rejected_cgst_itc }}</td>
    </tr>
    <tr>
      <td>SGST Input Credit</td>
      <td class="eligible">{{ confirmed_sgst_itc }}</td>
      <td class="pending-badge">{{ pending_sgst_itc }}</td>
      <td class="blocked">{{ rejected_sgst_itc }}</td>
    </tr>
    <tr>
      <td>IGST Input Credit</td>
      <td class="eligible">{{ confirmed_igst_itc }}</td>
      <td class="pending-badge">{{ pending_igst_itc }}</td>
      <td class="blocked">{{ rejected_igst_itc }}</td>
    </tr>
    <tr>
      <td><strong>Total ITC</strong></td>
      <td><strong>{{ confirmed_total_itc }}</strong></td>
      <td><strong>{{ pending_total_itc }}</strong></td>
      <td><strong>{{ rejected_total_itc }}</strong></td>
    </tr>
  </table>

  {% if rcm_liability > 0 %}
  <h3>RCM Liability</h3>
  <table class="summary-table">
    <tr><th>Description</th><th>Amount (Rs.)</th></tr>
    <tr><td>Reverse Charge Mechanism Liability</td><td class="blocked">{{ rcm_liability }}</td></tr>
  </table>
  {% endif %}

  <h3>Invoice Details (Top {{ invoices|length }} of {{ invoice_count }} invoices)</h3>
  <table>
    <tr>
      <th>Invoice No</th><th>Date</th><th>Seller GSTIN</th>
      <th>Seller</th><th>Total</th><th>Status</th>
    </tr>
    {% for inv in invoices %}
    <tr>
      <td>{{ inv.invoice_number or 'N/A' }}</td>
      <td>{{ inv.invoice_date or 'N/A' }}</td>
      <td>{{ inv.seller_gstin or 'N/A' }}</td>
      <td>{{ (inv.seller_name or 'N/A')[:30] }}</td>
      <td>{{ inv.total_amount or 0 }}</td>
      <td class="{{ 'eligible' if inv.status == 'ca_approved' else ('blocked' if inv.status == 'ca_rejected' else 'pending-badge') }}">
        {{ inv.status | replace('_', ' ') | title }}
      </td>
    </tr>
    {% endfor %}
  </table>

  {% if flagged_invoices|length > 0 %}
  <h3>Flagged Invoices ({{ flagged_invoices|length }})</h3>
  <div class="flagged-notice">
    The following invoices require attention before filing.
  </div>
  <table>
    <tr>
      <th>Invoice No</th><th>Date</th><th>Seller</th>
      <th>Amount</th><th>Flag Reason</th>
    </tr>
    {% for inv in flagged_invoices %}
    <tr>
      <td>{{ inv.invoice_number or 'N/A' }}</td>
      <td>{{ inv.invoice_date or 'N/A' }}</td>
      <td>{{ (inv.seller_name or 'N/A')[:30] }}</td>
      <td>{{ inv.total_amount or 0 }}</td>
      <td class="blocked">{{ inv.status | replace('_', ' ') | title }}</td>
    </tr>
    {% endfor %}
  </table>
  {% endif %}

  <div class="disclaimer">
    This document is prepared by {{ ca_firm_name }} using VyapaarBandhu document management software.
    All ITC eligibility determinations have been reviewed and approved by {{ ca_proprietor_name }}.
    This is a supporting document -- the GSTR-3B filing on the GSTN portal is the authoritative record.
  </div>

  <div class="footer">Generated by VyapaarBandhu | Not a substitute for CA review | {{ generated_at }} | Confidential</div>
</body>
</html>
"""


async def generate_filing_pdf(
    ca_firm_name: str,
    ca_proprietor_name: str,
    client_name: str,
    client_gstin: str | None,
    tax_period: str,
    invoices: list,
    confirmed_cgst_itc: str = "0.00",
    confirmed_sgst_itc: str = "0.00",
    confirmed_igst_itc: str = "0.00",
    confirmed_total_itc: str = "0.00",
    pending_cgst_itc: str = "0.00",
    pending_sgst_itc: str = "0.00",
    pending_igst_itc: str = "0.00",
    pending_total_itc: str = "0.00",
    rejected_cgst_itc: str = "0.00",
    rejected_sgst_itc: str = "0.00",
    rejected_igst_itc: str = "0.00",
    rejected_total_itc: str = "0.00",
    rcm_liability: Decimal = Decimal("0.00"),
    pending_count: int = 0,
    flagged_invoices: list | None = None,
    invoice_count: int = 0,
) -> bytes:
    """
    Generate filing summary PDF using WeasyPrint.

    CRITICAL: rcm_liability is Decimal (not string) so template comparison works.
    Template uses {% if rcm_liability > 0 %} which requires numeric type.
    """
    from weasyprint import HTML

    if flagged_invoices is None:
        flagged_invoices = []

    # Limit invoices to top 20 by amount
    top_invoices = sorted(
        invoices,
        key=lambda i: float(getattr(i, "total_amount", 0) or 0),
        reverse=True,
    )[:20]

    template = Template(PDF_TEMPLATE)
    html_content = template.render(
        ca_firm_name=ca_firm_name,
        ca_proprietor_name=ca_proprietor_name,
        client_name=client_name,
        client_gstin=client_gstin,
        tax_period=tax_period,
        invoices=top_invoices,
        confirmed_cgst_itc=confirmed_cgst_itc,
        confirmed_sgst_itc=confirmed_sgst_itc,
        confirmed_igst_itc=confirmed_igst_itc,
        confirmed_total_itc=confirmed_total_itc,
        pending_cgst_itc=pending_cgst_itc,
        pending_sgst_itc=pending_sgst_itc,
        pending_igst_itc=pending_igst_itc,
        pending_total_itc=pending_total_itc,
        rejected_cgst_itc=rejected_cgst_itc,
        rejected_sgst_itc=rejected_sgst_itc,
        rejected_igst_itc=rejected_igst_itc,
        rejected_total_itc=rejected_total_itc,
        rcm_liability=rcm_liability,  # Decimal, not string -- for template comparison
        pending_count=pending_count,
        invoice_count=invoice_count or len(invoices),
        flagged_invoices=flagged_invoices,
        generated_at=datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
    )

    pdf_bytes = HTML(string=html_content).write_pdf()
    logger.info("export.pdf.generated", size=len(pdf_bytes), invoices=len(invoices))
    return pdf_bytes
