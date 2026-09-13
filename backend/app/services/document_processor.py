from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import logger
from app.db.models.document import Document, DocumentStatus
from app.db.models.document_chunk import DocumentChunk
from app.services.storage import get_storage_backend
from app.services.parsers import get_parser
from app.services.text_normalizer import normalize_text
from app.services.chunker import chunk_text


class DocumentProcessor:
    """Orchestrates the document processing pipeline:
    
    Read file → Extract text → Normalize → Chunk → Store chunks in DB.
    
    Designed to be called inline for now but easily extractable to a
    background worker queue later.
    """

    async def process(self, document_id: str, db: AsyncSession) -> None:
        """Process a document through the full pipeline.
        
        Updates document status to PROCESSING → PROCESSED or FAILED.
        """
        # Fetch the document record
        result = await db.execute(select(Document).filter(Document.id == document_id))
        doc = result.scalar_one_or_none()
        if not doc:
            logger.error(f"Document not found for processing: id={document_id}")
            return

        logger.info(
            f"Processing started: doc_id={doc.id}, "
            f"org_id={doc.organization_id}, "
            f"file_type={doc.file_type}, "
            f"original_filename={doc.original_filename}"
        )

        # Set status to PROCESSING
        doc.status = DocumentStatus.PROCESSING
        doc.processing_error = None
        await db.commit()

        try:
            # 1. Read file from storage
            storage = get_storage_backend()
            file_bytes = await storage.read(doc.storage_path)

            # 2. Extract text
            parser = get_parser(doc.file_type)
            pages = parser.extract(file_bytes)

            if not pages:
                raise ValueError("No text content could be extracted from document")

            # 3. Normalize text on each page
            for page in pages:
                page.text = normalize_text(page.text)

            # Filter out empty pages after normalization
            pages = [p for p in pages if p.text.strip()]

            if not pages:
                raise ValueError("Document contained no meaningful text after normalization")

            # 4. Chunk text
            chunks = chunk_text(
                pages,
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP,
            )

            if not chunks:
                raise ValueError("Chunking produced no chunks")

            # 5. Store chunks in DB
            for chunk in chunks:
                db_chunk = DocumentChunk(
                    document_id=doc.id,
                    organization_id=doc.organization_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    char_count=chunk.char_count,
                    page_number=chunk.page_number,
                )
                db.add(db_chunk)

            # 6. Update document status
            doc.status = DocumentStatus.PROCESSED
            doc.chunk_count = len(chunks)
            doc.processed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                f"Processing completed: doc_id={doc.id}, "
                f"chunks={len(chunks)}"
            )

        except Exception as e:
            await db.rollback()
            # Re-fetch after rollback
            result = await db.execute(select(Document).filter(Document.id == document_id))
            doc = result.scalar_one_or_none()
            if doc:
                doc.status = DocumentStatus.FAILED
                doc.processing_error = str(e)[:500]  # Truncate for safety
                await db.commit()

            logger.error(
                f"Processing failed: doc_id={document_id}, "
                f"error={str(e)[:200]}"
            )
