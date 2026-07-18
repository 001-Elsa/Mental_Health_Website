"""add community media and realtime plaza

Revision ID: 0007_community_media_plaza
Revises: 0006_article_sources
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_community_media_plaza"
down_revision = "0006_article_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("discussions") as batch:
        batch.add_column(sa.Column("image_url", sa.String(length=512), nullable=False, server_default=""))
        batch.add_column(sa.Column("audio_url", sa.String(length=512), nullable=False, server_default=""))

    op.create_table(
        "plaza_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("image_url", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("audio_url", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="published"),
        sa.Column("moderation_reason", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_plaza_messages_user_id", "plaza_messages", ["user_id"])
    op.create_index("ix_plaza_messages_status", "plaza_messages", ["status"])
    op.create_index("ix_plaza_messages_created_at", "plaza_messages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_plaza_messages_created_at", table_name="plaza_messages")
    op.drop_index("ix_plaza_messages_status", table_name="plaza_messages")
    op.drop_index("ix_plaza_messages_user_id", table_name="plaza_messages")
    op.drop_table("plaza_messages")
    with op.batch_alter_table("discussions") as batch:
        batch.drop_column("audio_url")
        batch.drop_column("image_url")
