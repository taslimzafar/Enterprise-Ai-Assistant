"""phase_6_pgvector_embeddings

Revision ID: b5b7dbfab810
Revises: f85ba4439d5d
Create Date: 2026-09-13 18:11:22.901789

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector


# revision identifiers, used by Alembic.
revision: str = 'b5b7dbfab810'
down_revision: Union[str, None] = 'f85ba4439d5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Ensure vector extension is installed
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Add EMBEDDING status to documentstatus enum
    op.execute("ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'EMBEDDING' AFTER 'PROCESSING';")

    # 3. Add embedding vector column to document_chunks
    op.add_column(
        'document_chunks',
        sa.Column('embedding', pgvector.sqlalchemy.Vector(768), nullable=True)
    )

    # 4. Create HNSW index for vector cosine similarity search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops);"
    )

    # 5. Create GIN index for full-text keyword search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_content_fts "
        "ON document_chunks USING gin (to_tsvector('english', content));"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_fts;")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw;")
    op.drop_column('document_chunks', 'embedding')
