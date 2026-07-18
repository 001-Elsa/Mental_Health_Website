"""add manual recommendation emotion preference

Revision ID: 0009_recommendation_preference
Revises: 0008_user_profile_center
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_recommendation_preference"
down_revision = "0008_user_profile_center"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_profiles") as batch:
        batch.add_column(sa.Column("recommendation_emotion", sa.String(length=32), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("user_profiles") as batch:
        batch.drop_column("recommendation_emotion")
