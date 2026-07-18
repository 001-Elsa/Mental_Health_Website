"""add conversation memory and knowledge documents

Revision ID: 0003_rag_memory
Revises: 0002_safety_operations
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_rag_memory"
down_revision = "0002_safety_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("consultations") as batch:
        batch.add_column(sa.Column("memory_summary", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("source", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="published"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_documents_status", "knowledge_documents", ["status"])


def downgrade() -> None:
    op.drop_table("knowledge_documents")
    with op.batch_alter_table("consultations") as batch:
        batch.drop_column("message_count")
        batch.drop_column("memory_summary")
