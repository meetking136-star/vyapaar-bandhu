"""
VyapaarBandhu -- Celery Task: Daily Deadline Reminders
Scheduled at 3:30 UTC (9:00 AM IST) via celery beat.

RULE 6: Query clients where filing_deadline - now <= 7 days
AND last reminder sent > 24 hours ago. Max 1 reminder per 24h per client.
"""
from __future__ import annotations

import structlog

from app.tasks.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(
    name="app.tasks.reminder_task.send_daily_deadline_reminders",
    soft_time_limit=300,
    time_limit=360,
)
def send_daily_deadline_reminders():
    """
    Daily deadline reminder task.
    Finds clients with upcoming GSTR-3B deadlines (within 7 days)
    who haven't received a reminder in the last 24 hours.
    Sends WhatsApp reminders, never more than 1 per 24h per client.
    """
    import asyncio
    asyncio.run(_async_send_reminders())


async def _async_send_reminders():
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select, func, and_
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import async_session_factory
    from app.models.client import Client
    from app.models.invoice import Invoice
    from app.models.reminder_log import ReminderLog
    from app.services.compliance.deadline_calculator import get_gstr3b_deadline
    from app.services.whatsapp import client as wa_client
    from app.services.whatsapp.bilingual_templates import BILINGUAL_TEMPLATES

    now = datetime.now(timezone.utc)
    current_period = now.strftime("%Y-%m")
    deadline = get_gstr3b_deadline(current_period)

    days_remaining = (deadline - now.date()).days if hasattr(deadline, 'date') else (deadline - now.date()).days
    if days_remaining < 0 or days_remaining > 7:
        logger.info("reminders.skipped", reason="deadline_not_within_7_days", days=days_remaining)
        return

    cutoff_24h = now - timedelta(hours=24)

    async with async_session_factory() as db:
        # Find clients with consent who haven't been reminded in 24h
        result = await db.execute(
            select(Client).where(
                Client.is_active == True,
                Client.consent_given_at != None,
                Client.consent_withdrawn_at == None,
            )
        )
        clients = result.scalars().all()

        sent_count = 0
        for client in clients:
            # RULE 6: Check if reminder already sent in last 24 hours
            existing = await db.execute(
                select(ReminderLog).where(
                    ReminderLog.client_id == client.id,
                    ReminderLog.tax_period == current_period,
                    ReminderLog.sent_at > cutoff_24h,
                )
            )
            if existing.scalar_one_or_none():
                continue  # Already reminded within 24 hours

            # Count pending invoices for this client
            count_result = await db.execute(
                select(func.count(Invoice.id)).where(
                    Invoice.client_id == client.id,
                    Invoice.filing_period == current_period.replace("-", "-"),
                )
            )
            invoice_count = count_result.scalar() or 0

            # Determine reminder type based on days remaining
            if days_remaining <= 1:
                reminder_type = "1_day"
            elif days_remaining <= 3:
                reminder_type = "3_day"
            else:
                reminder_type = "7_day"

            # Send reminder in English (default for reminders)
            template = BILINGUAL_TEMPLATES["deadline_reminder"]["en"]
            message = template.format(days=days_remaining, count=invoice_count)

            try:
                wa_msg_id = await wa_client.send_text(
                    client.whatsapp_phone, message
                )

                # Log the reminder
                reminder_log = ReminderLog(
                    client_id=client.id,
                    tax_period=current_period,
                    reminder_type=reminder_type,
                    wa_message_id=wa_msg_id,
                )
                db.add(reminder_log)
                sent_count += 1

            except Exception as exc:
                logger.error(
                    "reminder.send_failed",
                    client_id=str(client.id),
                    error=str(exc)[:200],
                )

        await db.commit()

        logger.info(
            "reminders.complete",
            total_clients=len(clients),
            sent=sent_count,
            days_remaining=days_remaining,
        )
