"""add refresh token rotation and token versioning

Revision ID: 0011_security_tokens
Revises: 0010_vertical_depth
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_security_tokens"
down_revision = "0010_vertical_depth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("replaced_by_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])
    op.create_index("ix_refresh_tokens_revoked_at", "refresh_tokens", ["revoked_at"])


def downgrade() -> None:
    op.drop_table("refresh_tokens")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("token_version")
