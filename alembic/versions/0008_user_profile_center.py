"""add editable user profile fields

Revision ID: 0008_user_profile_center
Revises: 0007_community_media_plaza
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_user_profile_center"
down_revision = "0007_community_media_plaza"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("email", sa.String(length=254), nullable=True))
        batch.add_column(sa.Column("background_url", sa.String(length=512), nullable=False, server_default=""))
        batch.add_column(sa.Column("signature", sa.String(length=120), nullable=False, server_default=""))
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now()))
        batch.create_index("ix_users_email", ["email"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_email")
        batch.drop_column("updated_at")
        batch.drop_column("signature")
        batch.drop_column("background_url")
        batch.drop_column("email")
