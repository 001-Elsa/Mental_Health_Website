"""add risk case workflow, audit, idempotency and notifications

Revision ID: 0005_case_workflow
Revises: 0004_profiles_community
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_case_workflow"
down_revision = "0004_profiles_community"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("risk_events") as batch:
        batch.add_column(sa.Column("assigned_to", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("due_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("next_follow_up_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="0"))
        batch.create_index("ix_risk_events_assigned_to", ["assigned_to"])
        batch.create_index("ix_risk_events_due_at", ["due_at"])
        batch.create_index("ix_risk_events_next_follow_up_at", ["next_follow_up_at"])

    op.create_table(
        "risk_actions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("risk_event_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=False, server_default=""),
        sa.Column("to_status", sa.String(length=24), nullable=False, server_default=""),
        sa.Column("note", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_risk_actions_risk_event_id", "risk_actions", ["risk_event_id"])
    op.create_index("ix_risk_actions_actor_id", "risk_actions", ["actor_id"])
    op.create_index("ix_risk_actions_action", "risk_actions", ["action"])
    op.create_index("ix_risk_actions_created_at", "risk_actions", ["created_at"])

    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("request_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    for column in ("actor_id", "action", "target_type", "target_id", "request_id", "created_at"):
        op.create_index(f"ix_admin_audit_logs_{column}", "admin_audit_logs", [column])

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="processing"),
        sa.Column("response_json", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "operation", "idempotency_key", name="uq_idempotency_operation_key"),
    )
    op.create_index("ix_idempotency_records_user_id", "idempotency_records", ["user_id"])
    op.create_index("ix_idempotency_records_operation", "idempotency_records", ["operation"])
    op.create_index("ix_idempotency_records_status", "idempotency_records", ["status"])

    op.create_table(
        "user_notifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("notification_type", sa.String(length=32), nullable=False, server_default="support"),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("content", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("link", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    for column in ("user_id", "notification_type", "read_at", "created_at"):
        op.create_index(f"ix_user_notifications_{column}", "user_notifications", [column])


def downgrade() -> None:
    op.drop_table("user_notifications")
    op.drop_table("idempotency_records")
    op.drop_table("admin_audit_logs")
    op.drop_table("risk_actions")
    with op.batch_alter_table("risk_events") as batch:
        batch.drop_index("ix_risk_events_next_follow_up_at")
        batch.drop_index("ix_risk_events_due_at")
        batch.drop_index("ix_risk_events_assigned_to")
        batch.drop_column("version")
        batch.drop_column("next_follow_up_at")
        batch.drop_column("due_at")
        batch.drop_column("assigned_to")
