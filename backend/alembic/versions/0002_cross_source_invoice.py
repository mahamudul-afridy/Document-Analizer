"""cross-verification rows belong to a specific source invoice

Revision ID: 0002_cross_source_invoice
Revises: 0001_initial
Create Date: 2026-11-07
"""
from alembic import op

revision = "0002_cross_source_invoice"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cross_verification_results ADD COLUMN source_invoice_id UUID "
               "REFERENCES invoices (id) ON DELETE CASCADE")
    op.execute("CREATE INDEX ix_cross_verification_results_source_invoice_id "
               "ON cross_verification_results (source_invoice_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_cross_verification_results_source_invoice_id")
    op.execute("ALTER TABLE cross_verification_results DROP COLUMN source_invoice_id")
