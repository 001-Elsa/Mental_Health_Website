"""add profiles, exercises and community interaction constraints

Revision ID: 0004_profiles_community
Revises: 0003_rag_memory
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_profiles_community"
down_revision = "0003_rag_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("dominant_emotions", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("stressors", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("coping_preferences", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_user_profiles_user_id", "user_profiles", ["user_id"], unique=True)

    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="情绪调节"),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("steps", sa.Text(), nullable=False, server_default=""),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="published"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_exercises_category", "exercises", ["category"])
    op.create_index("ix_exercises_status", "exercises", ["status"])

    op.create_table(
        "discussion_likes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("discussion_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("discussion_id", "user_id", name="uq_discussion_like_user"),
    )
    op.create_index("ix_discussion_likes_discussion_id", "discussion_likes", ["discussion_id"])
    op.create_index("ix_discussion_likes_user_id", "discussion_likes", ["user_id"])

    with op.batch_alter_table("discussions") as batch:
        batch.add_column(sa.Column("visibility", sa.String(length=16), nullable=False, server_default="公开"))
        batch.create_index("ix_discussions_visibility", ["visibility"])

    with op.batch_alter_table("risk_events") as batch:
        batch.alter_column("consultation_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("event_type", sa.String(length=24), nullable=False, server_default="conversation"))
        batch.add_column(sa.Column("model_level", sa.String(length=16), nullable=False, server_default=""))
        batch.add_column(sa.Column("model_reason", sa.String(length=512), nullable=False, server_default=""))
        batch.create_index("ix_risk_events_event_type", ["event_type"])


def downgrade() -> None:
    with op.batch_alter_table("risk_events") as batch:
        batch.drop_index("ix_risk_events_event_type")
        batch.drop_column("model_reason")
        batch.drop_column("model_level")
        batch.drop_column("event_type")
        batch.alter_column("consultation_id", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("discussions") as batch:
        batch.drop_index("ix_discussions_visibility")
        batch.drop_column("visibility")
    op.drop_table("discussion_likes")
    op.drop_table("exercises")
    op.drop_table("user_profiles")
