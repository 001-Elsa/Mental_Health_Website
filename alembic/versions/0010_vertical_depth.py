"""deepen risk case workflow and audit trail

Revision ID: 0010_vertical_depth
Revises: 0009_recommendation_preference
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_vertical_depth"
down_revision = "0009_recommendation_preference"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("risk_actions") as batch:
        batch.add_column(sa.Column("request_id", sa.String(length=64), nullable=False, server_default=""))
        batch.add_column(sa.Column("ip_address", sa.String(length=64), nullable=False, server_default=""))
        batch.create_index("ix_risk_actions_request_id", ["request_id"])
    op.create_index("ix_risk_events_queue", "risk_events", ["status", "level", "created_at"])
    op.create_index("ix_risk_events_user_open_window", "risk_events", ["user_id", "event_type", "level", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_risk_events_user_open_window", table_name="risk_events")
    op.drop_index("ix_risk_events_queue", table_name="risk_events")
    with op.batch_alter_table("risk_actions") as batch:
        batch.drop_index("ix_risk_actions_request_id")
        batch.drop_column("ip_address")
        batch.drop_column("request_id")
