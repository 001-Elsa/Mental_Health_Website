"""guard idempotency payloads and duplicate SLA escalation

Revision ID: 0012_idempotency_and_sla_guards
Revises: 0011_security_tokens
Create Date: 2026-07-24
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_idempotency_and_sla_guards"
down_revision = "0011_security_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("idempotency_records") as batch:
        batch.add_column(
            sa.Column("request_fingerprint", sa.String(length=64), nullable=False, server_default="")
        )
    op.create_index(
        "uq_risk_actions_sla_escalation",
        "risk_actions",
        ["risk_event_id"],
        unique=True,
        sqlite_where=sa.text("action = 'sla_escalated'"),
        postgresql_where=sa.text("action = 'sla_escalated'"),
    )


def downgrade() -> None:
    op.drop_index("uq_risk_actions_sla_escalation", table_name="risk_actions")
    with op.batch_alter_table("idempotency_records") as batch:
        batch.drop_column("request_fingerprint")
