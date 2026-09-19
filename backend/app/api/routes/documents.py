import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sa_delete

from app.api.dependencies import get_db, get_current_active_user, RoleChecker
from app.db.models.user import User
from app.db.models.membership import Membership, RoleEnum
from app.db.models.document import Document, DocumentStatus
from app.db.models.document_chunk import DocumentChunk
from app.services.storage import get_storage_backend
from app.services.document_processor import DocumentProcessor
from app.core.config import settings
from app.core.logging import logger

router = APIRouter()

# MIME type mapping for validation
ALLOWED_MIME_TYPES = {
    "pdf": ["application/pdf"],
    "docx": [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ],
    "txt": ["text/plain"],
}

EXTENSION_MAP = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
}


def _get_file_type(filename: str, content_type: str | None) -> str:
    """Determine file type from extension and validate against content type.
    
    Returns the file type string (pdf, docx, txt) or raises HTTPException.
    """
    # Extract extension
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()

    file_type = EXTENSION_MAP.get(ext)
    if not file_type:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension: {ext or 'none'}. Allowed: {', '.join(EXTENSION_MAP.keys())}"
        )

    if file_type not in settings.ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file_type}' is not allowed."
        )

    # Validate MIME type if provided
    if content_type:
        allowed_mimes = ALLOWED_MIME_TYPES.get(file_type, [])
        # Be lenient with MIME: some clients send application/octet-stream
        if content_type not in allowed_mimes and content_type != "application/octet-stream":
            raise HTTPException(
                status_code=400,
                detail=f"MIME type '{content_type}' does not match file extension '{ext}'."
            )

    return file_type


import os
from app.core.rate_limit import rate_limiter
from app.core.audit_logger import log_security_event


def _validate_magic_bytes(file_type: str, file_bytes: bytes) -> None:
    """Verify file magic bytes against declared file type to prevent malicious upload masquerading."""
    if file_type == "pdf":
        if not file_bytes.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=400,
                detail="File content signature does not match PDF format (missing %PDF- header)."
            )
    elif file_type == "docx":
        # DOCX files are OpenXML ZIP archives starting with PK\x03\x04
        if not file_bytes.startswith(b"PK\x03\x04"):
            raise HTTPException(
                status_code=400,
                detail="File content signature does not match DOCX format (invalid archive header)."
            )
    elif file_type == "txt":
        # Disallow executable signatures masked as text
        if file_bytes.startswith(b"MZ") or file_bytes.startswith(b"\x7fELF"):
            raise HTTPException(
                status_code=400,
                detail="Executable binary files cannot be uploaded as text."
            )
        # Plain text should not contain null bytes
        if b"\x00" in file_bytes[:1024]:
            raise HTTPException(
                status_code=400,
                detail="Binary content with null bytes is not permitted for text files."
            )


def _sanitize_filename(filename: str) -> str:
    """Sanitize original filename against path traversal, null bytes, and dangerous characters."""
    import urllib.parse
    decoded = urllib.parse.unquote(filename)
    if "\x00" in filename or "\x00" in decoded or "%00" in filename.lower():
        raise HTTPException(status_code=400, detail="Filename contains illegal null bytes.")
    
    # Strip any directory paths
    clean = os.path.basename(filename).strip()
    clean = clean.replace("/", "").replace("\\", "")
    
    # Check for path traversal markers
    if ".." in clean or clean in ("", ".", ".."):
        clean = "sanitized_document"
        
    return clean[:255]


@router.post("")
async def upload_document(
    file: UploadFile = File(...),
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(RoleChecker([RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.MANAGER])),
):
    """Upload a document for processing.
    
    Validates file type, size, magic bytes signature, sanitizes filename, and stores securely.
    Triggers document processing (text extraction → normalization → chunking).
    """
    raw_filename = file.filename or "untitled"
    original_filename = _sanitize_filename(raw_filename)
    
    # Rate limit uploads per org/user
    await rate_limiter.check(
        f"upload:{membership.organization_id}:{membership.user_id}",
        limit=settings.RATE_LIMIT_UPLOAD_PER_MINUTE,
    )

    logger.info(
        f"Document upload started: org_id={org_id}, "
        f"filename={original_filename}, "
        f"user_id={membership.user_id}"
    )

    # Validate file extension and MIME type
    file_type = _get_file_type(original_filename, file.content_type)

    # Read file content
    file_bytes = await file.read()
    file_size = len(file_bytes)

    # Validate file size
    max_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file_size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File size ({file_size} bytes) exceeds maximum ({settings.MAX_UPLOAD_SIZE_MB} MB)."
        )

    if file_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Validate magic bytes / file signatures
    _validate_magic_bytes(file_type, file_bytes)

    # Generate safe storage key — never use raw user filename
    safe_filename = f"{uuid.uuid4().hex}.{file_type}"
    storage_key = f"{membership.organization_id}/{safe_filename}"

    # Store file
    storage = get_storage_backend()
    await storage.save(storage_key, file_bytes)

    # Create DB record scoped to verified membership organization
    doc = Document(
        organization_id=membership.organization_id,
        uploaded_by=membership.user_id,
        filename=safe_filename,
        original_filename=original_filename,
        file_type=file_type,
        mime_type=file.content_type,
        file_size=file_size,
        storage_path=storage_key,
        status=DocumentStatus.UPLOADED,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    logger.info(f"Document stored: doc_id={doc.id}, storage_key={storage_key}")

    # Process document (inline for now — extractable to worker queue later)
    processor = DocumentProcessor()
    await processor.process(doc.id, db)

    # Re-fetch to get updated status
    await db.refresh(doc)

    return {
        "id": doc.id,
        "original_filename": doc.original_filename,
        "file_type": doc.file_type,
        "file_size": doc.file_size,
        "status": doc.status,
        "chunk_count": doc.chunk_count,
        "created_at": doc.created_at,
    }


@router.get("")
async def list_documents(
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(RoleChecker([RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.MANAGER, RoleEnum.MEMBER])),
):
    """List all documents for the given organization."""
    result = await db.execute(
        select(Document)
        .filter(Document.organization_id == membership.organization_id)
        .order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()

    return [
        {
            "id": doc.id,
            "original_filename": doc.original_filename,
            "file_type": doc.file_type,
            "file_size": doc.file_size,
            "status": doc.status,
            "processing_error": doc.processing_error,
            "chunk_count": doc.chunk_count,
            "created_at": doc.created_at,
            "processed_at": doc.processed_at,
        }
        for doc in docs
    ]


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(RoleChecker([RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.MANAGER, RoleEnum.MEMBER])),
):
    """Get document metadata by ID. Enforces organization isolation."""
    result = await db.execute(
        select(Document).filter(
            Document.id == document_id,
            Document.organization_id == membership.organization_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": doc.id,
        "original_filename": doc.original_filename,
        "file_type": doc.file_type,
        "mime_type": doc.mime_type,
        "file_size": doc.file_size,
        "status": doc.status,
        "processing_error": doc.processing_error,
        "chunk_count": doc.chunk_count,
        "created_at": doc.created_at,
        "processed_at": doc.processed_at,
    }


@router.get("/{document_id}/status")
async def get_document_status(
    document_id: str,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(RoleChecker([RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.MANAGER, RoleEnum.MEMBER])),
):
    """Get document processing status. Enforces organization isolation."""
    result = await db.execute(
        select(Document).filter(
            Document.id == document_id,
            Document.organization_id == membership.organization_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": doc.id,
        "status": doc.status,
        "processing_error": doc.processing_error,
        "chunk_count": doc.chunk_count,
        "processed_at": doc.processed_at,
    }


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(RoleChecker([RoleEnum.OWNER, RoleEnum.ADMIN])),
):
    """Delete a document, its chunks, and storage file. Only OWNER/ADMIN can delete."""
    result = await db.execute(
        select(Document).filter(
            Document.id == document_id,
            Document.organization_id == membership.organization_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    logger.info(f"Document deletion: doc_id={doc.id}, org_id={membership.organization_id}, user_id={membership.user_id}")

    # Delete chunks
    await db.execute(
        sa_delete(DocumentChunk).where(DocumentChunk.document_id == doc.id)
    )

    # Delete file from storage
    try:
        storage = get_storage_backend()
        await storage.delete(doc.storage_path)
    except Exception as e:
        logger.error(f"Failed to delete storage file: {e}")
        # Continue with DB deletion even if file deletion fails

    # Delete document record
    await db.delete(doc)
    await db.commit()

    return {"status": "deleted", "id": document_id}
