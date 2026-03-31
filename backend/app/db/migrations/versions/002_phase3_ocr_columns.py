"""Phase 3 -- OCR pipeline columns on invoices table

Revision ID: 002_phase3_ocr
Revises: 001_initial
Create Date: 2026-03-31

Adds:
  - ocr_raw_text (TEXT)
  - ocr_engine_used (VARCHAR(20))
  - ocr_confidence_json (JSONB)
  - extracted_fields_json (JSONB)
  - low_confidence_fields (TEXT[])
  - classification_json (JSONB)
  - processing_attempts (INTEGER DEFAULT 0)
  - last_error_message (TEXT)
  - filing_period (VARCHAR(7))
  - New statuses: queued, processing, manual_review_required, failed
  - Index: invoices(client_id, status)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision: str = "002_phase3_ocr"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── New columns on invoices ────────────────────────────────────
    op.add_column(
        "invoices",
        sa.Column("ocr_raw_text", sa.Text(), nullable=True),
        schema="vyapaar",
    )
    op.add_column(
        "invoices",
        sa.Column("ocr_engine_used", sa.String(20), nullable=True),
        schema="vyapaar",
    )
    op.add_column(
        "invoices",
        sa.Column("ocr_confidence_json", JSONB(), nullable=True),
        schema="vyapaar",
    )
    op.add_column(
        "invoices",
        sa.Column("extracted_fields_json", JSONB(), nullable=True),
        schema="vyapaar",
    )
    op.add_column(
        "invoices",
        sa.Column("low_confidence_fields", ARRAY(sa.Text()), nullable=True),
        schema="vyapaar",
    )
    op.add_column(
        "invoices",
        sa.Column("classification_json", JSONB(), nullable=True),
        schema="vyapaar",
    )
    op.add_column(
        "invoices",
        sa.Column(
            "processing_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        schema="vyapaar",
    )
    op.add_column(
        "invoices",
        sa.Column("last_error_message", sa.Text(), nullable=True),
        schema="vyapaar",
    )
    op.add_column(
        "invoices",
        sa.Column("filing_period", sa.String(7), nullable=True),
        schema="vyapaar",
    )

    # ── Update status CHECK constraint to include new statuses ─────
    # Drop old constraint if it exists and add new one
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE vyapaar.invoices
                DROP CONSTRAINT IF EXISTS ck_invoices_status;
        EXCEPTION WHEN undefined_object THEN
            NULL;
        END $$;
    """)
    op.execute("""
        ALTER TABLE vyapaar.invoices
            ADD CONSTRAINT ck_invoices_status CHECK (
                status IN (
                    'queued', 'processing',
                    'pending_client_confirmation', 'pending_ca_review',
                    'flagged_low_confidence', 'flagged_classification',
                    'flagged_anomaly', 'manual_review_required',
                    'ca_approved', 'ca_rejected', 'ca_overridden',
                    'failed'
                )
            );
    """)

    # ── Composite index for reprocess_failed query ─────────────────
    op.create_index(
        "idx_invoices_client_status",
        "invoices",
        ["client_id", "status"],
        schema="vyapaar",
    )

    # ── Grant on new columns to app role ───────────────────────────
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'vyapaar_app') THEN
                GRANT SELECT, INSERT, UPDATE ON vyapaar.invoices TO vyapaar_app;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # ── Drop index ─────────────────────────────────────────────────
    op.drop_index("idx_invoices_client_status", table_name="invoices", schema="vyapaar")

    # ── Restore original status constraint ─────────────────────────
    op.execute("""
        ALTER TABLE vyapaar.invoices
            DROP CONSTRAINT IF EXISTS ck_invoices_status;
    """)
    op.execute("""
        ALTER TABLE vyapaar.invoices
            ADD CONSTRAINT ck_invoices_status CHECK (
                status IN (
                    'pending_client_confirmation', 'pending_ca_review',
                    'flagged_low_confidence', 'flagged_classification',
                    'flagged_anomaly',
                    'ca_approved', 'ca_rejected', 'ca_overridden'
                )
            );
    """)

    # ── Drop new columns (reverse order) ───────────────────────────
    op.drop_column("invoices", "filing_period", schema="vyapaar")
    op.drop_column("invoices", "last_error_message", schema="vyapaar")
    op.drop_column("invoices", "processing_attempts", schema="vyapaar")
    op.drop_column("invoices", "classification_json", schema="vyapaar")
    op.drop_column("invoices", "low_confidence_fields", schema="vyapaar")
    op.drop_column("invoices", "extracted_fields_json", schema="vyapaar")
    op.drop_column("invoices", "ocr_confidence_json", schema="vyapaar")
    op.drop_column("invoices", "ocr_engine_used", schema="vyapaar")
    op.drop_column("invoices", "ocr_raw_text", schema="vyapaar")
