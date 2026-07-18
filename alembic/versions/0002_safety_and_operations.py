"""add safety, moderation and operations capabilities

Revision ID: 0002_safety_operations
Revises: 0001_initial_schema
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_safety_operations"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("role", sa.String(length=16), nullable=False, server_default="student"))
        batch.create_index("ix_users_role", ["role"])

    with op.batch_alter_table("consultations") as batch:
        batch.add_column(sa.Column("risk_level", sa.String(length=16), nullable=False, server_default="low"))
        batch.add_column(sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("risk_reason", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("intervention_status", sa.String(length=24), nullable=False, server_default="none"))
        batch.add_column(sa.Column("last_message_at", sa.DateTime(), nullable=True))
        batch.create_index("ix_consultations_risk_level", ["risk_level"])
        batch.create_index("ix_consultations_intervention_status", ["intervention_status"])

    with op.batch_alter_table("discussions") as batch:
        batch.add_column(sa.Column("like_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("status", sa.String(length=24), nullable=False, server_default="published"))
        batch.add_column(sa.Column("moderation_reason", sa.String(length=256), nullable=False, server_default=""))
        batch.create_index("ix_discussions_status", ["status"])

    with op.batch_alter_table("replies") as batch:
        batch.add_column(sa.Column("status", sa.String(length=24), nullable=False, server_default="published"))
        batch.create_index("ix_replies_status", ["status"])

    op.create_table(
        "risk_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("consultation_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("signals", sa.Text(), nullable=False, server_default=""),
        sa.Column("excerpt", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("handled_by", sa.Integer(), nullable=True),
        sa.Column("handled_note", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("handled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    for column in ("user_id", "consultation_id", "conversation_id", "level", "status"):
        op.create_index(f"ix_risk_events_{column}", "risk_events", [column])

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("reporter_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("handled_by", sa.Integer(), nullable=True),
        sa.Column("handled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    for column in ("reporter_id", "target_id", "status"):
        op.create_index(f"ix_reports_{column}", "reports", [column])

    op.create_table(
        "sensitive_words",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("word", sa.String(length=64), nullable=False, unique=True),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="unsafe"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("sensitive_words")
    op.drop_table("reports")
    op.drop_table("risk_events")
    with op.batch_alter_table("replies") as batch:
        batch.drop_index("ix_replies_status")
        batch.drop_column("status")
    with op.batch_alter_table("discussions") as batch:
        batch.drop_index("ix_discussions_status")
        batch.drop_column("moderation_reason")
        batch.drop_column("status")
        batch.drop_column("like_count")
    with op.batch_alter_table("consultations") as batch:
        batch.drop_index("ix_consultations_intervention_status")
        batch.drop_index("ix_consultations_risk_level")
        batch.drop_column("last_message_at")
        batch.drop_column("intervention_status")
        batch.drop_column("risk_reason")
        batch.drop_column("risk_score")
        batch.drop_column("risk_level")
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_role")
        batch.drop_column("role")
