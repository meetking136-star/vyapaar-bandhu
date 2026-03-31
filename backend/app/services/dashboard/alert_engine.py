"""
VyapaarBandhu — Alert Engine
Generates compliance alerts for CA dashboard.
Checks deadlines, flagged invoices, missing filings, anomalies.

CRITICAL: This file must never import any ML/AI library.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import structlog
from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.invoice import Invoice
from app.services.compliance.deadline_calculator import get_gstr3b_deadline

logger = structlog.get_logger()

ZERO = Decimal("0.00")


async def generate_alerts(
    db: AsyncSession,
    *,
    ca_id: uuid.UUID,
) -> list[dict]:
    """
    Generate a list of compliance alerts for all active clients of a CA.

    Alert types:
    - deadline_critical: GSTR-3B deadline <= 3 days away
    - deadline_warning: GSTR-3B deadline 4-7 days away
    - flagged_invoices: Client has unreviewed flagged invoices
    - no_invoices: Client has zero invoices this period
    - high_pending: Client has > 10 pending invoices
    """
    today = date.today()
    tax_period = f"{today.year}-{today.month:02d}"
    gstr3b_deadline = get_gstr3b_deadline(tax_period)
    days_to_deadline = (gstr3b_deadline - today).days

    # Get all active clients with invoice counts in a single query
    result = await db.execute(
        select(
            Client.id,
            Client.business_name,
            Client.owner_name,
            func.count(Invoice.id).label("total_invoices"),
            func.count(case(
                (Invoice.status == "flagged_low_confidence", 1),
            )).label("flagged_count"),
            func.count(case(
                (Invoice.status == "pending_ca_review", 1),
            )).label("pending_count"),
        )
        .outerjoin(Invoice, Invoice.client_id == Client.id)
        .where(Client.ca_id == ca_id, Client.is_active == True)
        .group_by(Client.id)
    )
    rows = result.all()

    alerts: list[dict] = []

    # Global deadline alerts
    if days_to_deadline <= 3:
        alerts.append({
            "type": "deadline_critical",
            "severity": "red",
            "message": f"GSTR-3B deadline is in {days_to_deadline} days ({gstr3b_deadline.isoformat()})",
            "client_id": None,
            "client_name": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    elif days_to_deadline <= 7:
        alerts.append({
            "type": "deadline_warning",
            "severity": "yellow",
            "message": f"GSTR-3B deadline approaching: {days_to_deadline} days remaining ({gstr3b_deadline.isoformat()})",
            "client_id": None,
            "client_name": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    for row in rows:
        client_id = row.id
        business_name = row.business_name
        total = row.total_invoices or 0
        flagged = row.flagged_count or 0
        pending = row.pending_count or 0

        if flagged > 0:
            alerts.append({
                "type": "flagged_invoices",
                "severity": "red" if days_to_deadline <= 3 else "yellow",
                "message": f"{business_name}: {flagged} invoice(s) flagged for review",
                "client_id": str(client_id),
                "client_name": business_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        if total == 0:
            alerts.append({
                "type": "no_invoices",
                "severity": "yellow",
                "message": f"{business_name}: No invoices uploaded this period",
                "client_id": str(client_id),
                "client_name": business_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        if pending > 10:
            alerts.append({
                "type": "high_pending",
                "severity": "yellow",
                "message": f"{business_name}: {pending} invoices pending CA review",
                "client_id": str(client_id),
                "client_name": business_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

    # Sort by severity: red first, then yellow
    severity_order = {"red": 0, "yellow": 1, "green": 2}
    alerts.sort(key=lambda a: severity_order.get(a["severity"], 9))

    logger.info(
        "alerts.generated",
        ca_id=str(ca_id),
        alert_count=len(alerts),
    )

    return alerts
