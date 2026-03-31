"""Phase 5 -- Dashboard columns for clients and invoices

Revision ID: 003_phase5_dashboard
Revises: 002_phase3_ocr
Create Date: 2026-03-31

Adds:
  - clients.last_reminder_sent TIMESTAMP WITH TIME ZONE
  - clients.gstr3b_filed_periods TEXT[]
  - invoices.bulk_action_at TIMESTAMP WITH TIME ZONE
  - invoices.bulk_action_by UUID FK to ca_accounts
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision: str = "003_phase5_dashboard"
down_revision: Union[str, None] = "002_phase3_ocr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── New columns on clients ────────────────────────────────────
    op.add_column(
        "clients",
        sa.Column("last_reminder_sent", sa.DateTime(timezone=True), nullable=True),
        schema="vyapaar",
    )
    op.add_column(
        "clients",
        sa.Column("gstr3b_filed_periods", ARRAY(sa.Text()), nullable=True),
        schema="vyapaar",
    )

    # ── New columns on invoices ───────────────────────────────────
    op.add_column(
        "invoices",
        sa.Column("bulk_action_at", sa.DateTime(timezone=True), nullable=True),
        schema="vyapaar",
    )
    op.add_column(
        "invoices",
        sa.Column(
            "bulk_action_by",
            UUID(as_uuid=True),
            sa.ForeignKey("vyapaar.ca_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema="vyapaar",
    )

    # ── Index for bulk action queries ─────────────────────────────
    op.create_index(
        "idx_invoices_bulk_action_by",
        "invoices",
        ["bulk_action_by"],
        schema="vyapaar",
    )


def downgrade() -> None:
    op.drop_index("idx_invoices_bulk_action_by", table_name="invoices", schema="vyapaar")
    op.drop_column("invoices", "bulk_action_by", schema="vyapaar")
    op.drop_column("invoices", "bulk_action_at", schema="vyapaar")
    op.drop_column("clients", "gstr3b_filed_periods", schema="vyapaar")
    op.drop_column("clients", "last_reminder_sent", schema="vyapaar")
