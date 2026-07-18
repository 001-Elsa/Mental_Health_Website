"""add external article source metadata

Revision ID: 0006_article_sources
Revises: 0005_case_workflow
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_article_sources"
down_revision = "0005_case_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("articles") as batch:
        batch.add_column(sa.Column("source_name", sa.String(length=128), nullable=False, server_default="平台原创"))
        batch.add_column(sa.Column("source_url", sa.String(length=1024), nullable=False, server_default=""))
        batch.add_column(sa.Column("published_at", sa.DateTime(), nullable=True))
        batch.create_index("ix_articles_source_url", ["source_url"])
        batch.create_index("ix_articles_published_at", ["published_at"])


def downgrade() -> None:
    with op.batch_alter_table("articles") as batch:
        batch.drop_index("ix_articles_published_at")
        batch.drop_index("ix_articles_source_url")
        batch.drop_column("published_at")
        batch.drop_column("source_url")
        batch.drop_column("source_name")
