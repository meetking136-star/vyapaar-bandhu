"""
VyapaarBandhu — CA Dashboard API
Traffic light overview, client status grid, summary, alerts.
"""

from datetime import date
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.dependencies import CurrentCA
from app.models.client import Client
from app.models.invoice import Invoice
from app.schemas.summary import (
    ClientStatusItem,
    DashboardOverviewResponse,
    DashboardSummaryResponse,
    AlertItem,
    AlertsResponse,
)
from app.services.compliance.deadline_calculator import get_gstr3b_deadline
from app.services.dashboard.alert_engine import generate_alerts
from app.services.dashboard.summary_builder import build_period_summary

logger = structlog.get_logger()
router = APIRouter()

ZERO = Decimal("0.00")


@router.get("/overview", response_model=DashboardOverviewResponse)
async def dashboard_overview(
    ca: CurrentCA,
    db: AsyncSession = Depends(get_async_session),
):
    """
    CA dashboard overview — traffic light grid for all clients.
    Status logic (deterministic):
    - green: all invoices ca_approved AND days_to_deadline >= 7
    - yellow: some pending AND days_to_deadline 4-6, OR flagged AND days >= 4
    - red: days_to_deadline <= 3, OR any flagged_low_confidence unreviewed
    """
    today = date.today()
    tax_period = f"{today.year}-{today.month:02d}"
    gstr3b_deadline = get_gstr3b_deadline(tax_period)
    days_to_deadline = (gstr3b_deadline - today).days

    # Get all active clients for this CA
    clients_result = await db.execute(
        select(Client).where(Client.ca_id == ca.id, Client.is_active == True)
    )
    clients = clients_result.scalars().all()

    items: list[ClientStatusItem] = []
    total_draft_itc = ZERO
    total_confirmed_itc = ZERO
    total_invoices = 0

    for client in clients:
        # Get invoice counts and ITC totals
        inv_result = await db.execute(
            select(
                func.count(Invoice.id).label("total"),
                func.count(case(
                    (Invoice.status == "pending_ca_review", 1),
                )).label("pending"),
                func.count(case(
                    (Invoice.status == "flagged_low_confidence", 1),
                )).label("flagged"),
                func.coalesce(func.sum(
                    case(
                        (Invoice.is_itc_eligible_draft == True,
                         Invoice.cgst_amount + Invoice.sgst_amount + Invoice.igst_amount),
                        else_=Decimal("0"),
                    )
                ), Decimal("0")).label("draft_itc"),
                func.coalesce(func.sum(
                    case(
                        (Invoice.status == "ca_approved",
                         Invoice.cgst_amount + Invoice.sgst_amount + Invoice.igst_amount),
                        else_=Decimal("0"),
                    )
                ), Decimal("0")).label("confirmed_itc"),
            ).where(Invoice.client_id == client.id)
        )
        row = inv_result.one()
        inv_count = row.total or 0
        pending_count = row.pending or 0
        flagged_count = row.flagged or 0
        draft_itc = Decimal(str(row.draft_itc or 0))
        confirmed_itc = Decimal(str(row.confirmed_itc or 0))

        # Determine traffic light color
        status_color, status_reason = _compute_status(
            inv_count, pending_count, flagged_count, days_to_deadline
        )

        items.append(ClientStatusItem(
            client_id=client.id,
            business_name=client.business_name,
            owner_name=client.owner_name,
            status_color=status_color,
            status_reason=status_reason,
            invoice_count=inv_count,
            pending_ca_review_count=pending_count,
            flagged_low_confidence_count=flagged_count,
            draft_itc_total=draft_itc,
            confirmed_itc_total=confirmed_itc,
            gstr3b_deadline=gstr3b_deadline,
            days_to_deadline=days_to_deadline,
        ))

        total_draft_itc += draft_itc
        total_confirmed_itc += confirmed_itc
        total_invoices += inv_count

    return DashboardOverviewResponse(
        clients=items,
        total_clients=len(clients),
        total_invoices=total_invoices,
        total_draft_itc=total_draft_itc,
        total_confirmed_itc=total_confirmed_itc,
    )


@router.get("/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(
    ca: CurrentCA,
    db: AsyncSession = Depends(get_async_session),
    period: str = Query(..., regex=r"^\d{2}-\d{4}$", description="MM-YYYY"),
):
    """
    Aggregated ITC summary for a CA across all clients for a given period.
    Single aggregation query -- no N+1 loops.
    """
    summary = await build_period_summary(db, ca_id=ca.id, period=period)
    return summary


@router.get("/alerts", response_model=AlertsResponse)
async def dashboard_alerts(
    ca: CurrentCA,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Generate compliance alerts for the CA's clients.
    Checks deadlines, flagged invoices, missing filings.
    """
    alerts = await generate_alerts(db, ca_id=ca.id)
    return AlertsResponse(alerts=alerts, total=len(alerts))


def _compute_status(
    inv_count: int,
    pending_count: int,
    flagged_count: int,
    days_to_deadline: int,
) -> tuple[str, str]:
    """Deterministic traffic light status computation.
    CRITICAL: flagged+deadline<=3 check MUST come before bare deadline<=3
    to produce a more specific reason string.
    """
    if flagged_count > 0 and days_to_deadline <= 3:
        return "red", f"{flagged_count} flagged invoices, deadline in {days_to_deadline} days"
    if days_to_deadline <= 3:
        return "red", f"GSTR-3B deadline in {days_to_deadline} days"
    if flagged_count > 0:
        return "yellow", f"{flagged_count} invoices flagged for review"
    if pending_count > 0 and days_to_deadline <= 6:
        return "yellow", f"{pending_count} invoices pending review, deadline approaching"
    if pending_count > 0:
        return "yellow", f"{pending_count} invoices pending CA review"
    if inv_count == 0:
        return "red", "No invoices uploaded this period"
    return "green", "All invoices reviewed"
