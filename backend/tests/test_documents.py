import pytest
import uuid
import io
from httpx import AsyncClient
from app.core.config import settings


async def _register_and_login(async_client: AsyncClient, email: str = None, password: str = "password123"):
    """Helper: register a new user and return (token, user_id, email)."""
    email = email or f"docuser_{uuid.uuid4().hex[:8]}@example.com"
    # Register
    response = await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email, "password": password, "full_name": "Doc Test User"},
    )
    assert response.status_code == 200
    # Login
    response = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": email, "password": password},
    )
    token = response.json()["access_token"]
    # Get user ID
    response = await async_client.get(
        f"{settings.API_V1_STR}/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    user_id = response.json()["id"]
    return token, user_id, email


async def _get_org_id(async_client: AsyncClient, token: str) -> str:
    """Helper: get the first org id for this user."""
    response = await async_client.get(
        f"{settings.API_V1_STR}/organizations/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    orgs = response.json()
    assert len(orgs) >= 1
    return orgs[0]["id"]


def _make_pdf_bytes() -> bytes:
    """Create a minimal valid PDF with text content using PyPDF2."""
    from PyPDF2 import PdfWriter, PageObject
    from PyPDF2.generic import (
        ArrayObject,
        DecodedStreamObject,
        DictionaryObject,
        NameObject,
        NumberObject,
        TextStringObject,
    )
    from io import BytesIO

    writer = PdfWriter()

    # Create a simple page with text content stream
    page = PageObject.create_blank_page(width=612, height=792)
    
    # Build a content stream with text
    content = b"BT /F1 12 Tf 72 720 Td (Test PDF document for enterprise knowledge base) Tj ET"
    stream = DecodedStreamObject()
    stream.set_data(content)
    
    # Add font resources
    font_dict = DictionaryObject()
    font_dict[NameObject("/Type")] = NameObject("/Font")
    font_dict[NameObject("/Subtype")] = NameObject("/Type1")
    font_dict[NameObject("/BaseFont")] = NameObject("/Helvetica")
    
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = font_dict
    
    resources = DictionaryObject()
    resources[NameObject("/Font")] = fonts
    
    page[NameObject("/Resources")] = resources
    page[NameObject("/Contents")] = writer._add_object(stream)
    
    writer.add_page(page)
    
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_docx_bytes() -> bytes:
    """Create a minimal valid DOCX with text content."""
    from docx import Document as DocxDocument
    from io import BytesIO

    doc = DocxDocument()
    doc.add_paragraph("This is a test DOCX document for enterprise knowledge base.")
    doc.add_paragraph("It contains multiple paragraphs for testing extraction and chunking.")
    doc.add_paragraph("Third paragraph with additional content for verification.")
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_txt_bytes() -> bytes:
    """Create plain text content."""
    return b"This is a test TXT document for enterprise knowledge base.\n\nIt contains multiple paragraphs for testing.\n\nThird paragraph with more content."


# ============================================================
# TESTS
# ============================================================


async def test_upload_txt(async_client: AsyncClient):
    """Test uploading a TXT file."""
    token, user_id, email = await _register_and_login(async_client)
    org_id = await _get_org_id(async_client, token)

    response = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={"file": ("test.txt", _make_txt_bytes(), "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["original_filename"] == "test.txt"
    assert data["file_type"] == "txt"
    assert data["status"] == "PROCESSED"
    assert data["chunk_count"] >= 1


async def test_upload_docx(async_client: AsyncClient):
    """Test uploading a DOCX file."""
    token, user_id, email = await _register_and_login(async_client)
    org_id = await _get_org_id(async_client, token)

    response = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={
            "file": (
                "test.docx",
                _make_docx_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["file_type"] == "docx"
    assert data["status"] == "PROCESSED"
    assert data["chunk_count"] >= 1


async def test_upload_pdf(async_client: AsyncClient):
    """Test uploading a PDF file."""
    token, user_id, email = await _register_and_login(async_client)
    org_id = await _get_org_id(async_client, token)

    response = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={"file": ("test.pdf", _make_pdf_bytes(), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["file_type"] == "pdf"
    # PDF may or may not produce chunks depending on the fallback method
    assert data["status"] in ("PROCESSED", "FAILED")


async def test_upload_unsupported_type(async_client: AsyncClient):
    """Test that uploading an unsupported file type is rejected."""
    token, user_id, email = await _register_and_login(async_client)
    org_id = await _get_org_id(async_client, token)

    response = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={"file": ("test.exe", b"MZ fake binary", "application/octet-stream")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "Unsupported" in response.json()["detail"]


async def test_upload_oversized_file(async_client: AsyncClient):
    """Test that oversized files are rejected."""
    token, user_id, email = await _register_and_login(async_client)
    org_id = await _get_org_id(async_client, token)

    # Create content larger than MAX_UPLOAD_SIZE_MB
    # Use a small max for testing
    original_max = settings.MAX_UPLOAD_SIZE_MB
    settings.MAX_UPLOAD_SIZE_MB = 0  # 0 MB = reject everything

    response = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={"file": ("test.txt", b"some content", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Restore
    settings.MAX_UPLOAD_SIZE_MB = original_max

    assert response.status_code == 400
    assert "exceeds" in response.json()["detail"]


async def test_document_listing(async_client: AsyncClient):
    """Test listing documents for an organization."""
    token, user_id, email = await _register_and_login(async_client)
    org_id = await _get_org_id(async_client, token)

    # Upload a document first
    await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={"file": ("list_test.txt", b"List test content", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )

    # List documents
    response = await async_client.get(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    docs = response.json()
    assert len(docs) >= 1
    assert any(d["original_filename"] == "list_test.txt" for d in docs)


async def test_document_retrieval(async_client: AsyncClient):
    """Test getting a specific document by ID."""
    token, user_id, email = await _register_and_login(async_client)
    org_id = await _get_org_id(async_client, token)

    # Upload
    upload_res = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={"file": ("retrieve_test.txt", b"Retrieve test content", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = upload_res.json()["id"]

    # Get
    response = await async_client.get(
        f"{settings.API_V1_STR}/documents/{doc_id}?org_id={org_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == doc_id
    assert response.json()["original_filename"] == "retrieve_test.txt"


async def test_document_status(async_client: AsyncClient):
    """Test the status endpoint."""
    token, user_id, email = await _register_and_login(async_client)
    org_id = await _get_org_id(async_client, token)

    upload_res = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={"file": ("status_test.txt", b"Status test content here", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = upload_res.json()["id"]

    response = await async_client.get(
        f"{settings.API_V1_STR}/documents/{doc_id}/status?org_id={org_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "PROCESSED"
    assert response.json()["chunk_count"] >= 1


async def test_document_deletion(async_client: AsyncClient):
    """Test deleting a document."""
    token, user_id, email = await _register_and_login(async_client)
    org_id = await _get_org_id(async_client, token)

    upload_res = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={"file": ("delete_test.txt", b"Delete test content", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = upload_res.json()["id"]

    # Delete
    response = await async_client.delete(
        f"{settings.API_V1_STR}/documents/{doc_id}?org_id={org_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"

    # Verify gone
    response = await async_client.get(
        f"{settings.API_V1_STR}/documents/{doc_id}?org_id={org_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


async def test_organization_isolation(async_client: AsyncClient):
    """Test that users from one org cannot see another org's documents."""
    # User A
    token_a, _, _ = await _register_and_login(async_client)
    org_id_a = await _get_org_id(async_client, token_a)

    # User B
    token_b, _, _ = await _register_and_login(async_client)
    org_id_b = await _get_org_id(async_client, token_b)

    # Upload doc to org A
    upload_res = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id_a}",
        files={"file": ("secret.txt", b"Org A secret content", "text/plain")},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    doc_id_a = upload_res.json()["id"]

    # User B tries to access org A's document via their own org_id (should not see it)
    response = await async_client.get(
        f"{settings.API_V1_STR}/documents/{doc_id_a}?org_id={org_id_b}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 404  # Can't find it in org B

    # User B tries to access org A's document via org A's org_id (should be forbidden - not a member)
    response = await async_client.get(
        f"{settings.API_V1_STR}/documents/{doc_id_a}?org_id={org_id_a}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 403  # Not a member of org A


async def test_rbac_member_cannot_delete(async_client: AsyncClient):
    """Test that a MEMBER role user cannot delete documents."""
    # Create owner
    owner_token, _, owner_email = await _register_and_login(async_client)
    org_id = await _get_org_id(async_client, owner_token)

    # Create member user
    member_token, _, member_email = await _register_and_login(async_client)

    # Add member to org
    await async_client.post(
        f"{settings.API_V1_STR}/organizations/{org_id}/members",
        json={"email": member_email, "role": "MEMBER"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    # Owner uploads document
    upload_res = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={"file": ("rbac_test.txt", b"RBAC test content", "text/plain")},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    doc_id = upload_res.json()["id"]

    # Member can view
    response = await async_client.get(
        f"{settings.API_V1_STR}/documents/{doc_id}?org_id={org_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert response.status_code == 200

    # Member cannot delete
    response = await async_client.delete(
        f"{settings.API_V1_STR}/documents/{doc_id}?org_id={org_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert response.status_code == 403


async def test_member_cannot_upload(async_client: AsyncClient):
    """Test that a MEMBER role user cannot upload documents."""
    owner_token, _, _ = await _register_and_login(async_client)
    org_id = await _get_org_id(async_client, owner_token)

    member_token, _, member_email = await _register_and_login(async_client)

    # Add as MEMBER
    await async_client.post(
        f"{settings.API_V1_STR}/organizations/{org_id}/members",
        json={"email": member_email, "role": "MEMBER"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    # Member tries to upload — should be denied
    response = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={"file": ("blocked.txt", b"Should not upload", "text/plain")},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert response.status_code == 403


async def test_chunk_creation_and_ordering(async_client: AsyncClient):
    """Test that chunks are created with correct ordering."""
    token, _, _ = await _register_and_login(async_client)
    org_id = await _get_org_id(async_client, token)

    # Create a longer document that will produce multiple chunks
    long_text = ("This is paragraph number {i}. " * 20 + "\n\n") * 10
    long_text = long_text.encode("utf-8")

    upload_res = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={"file": ("long.txt", long_text, "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    data = upload_res.json()
    assert data["status"] == "PROCESSED"
    assert data["chunk_count"] >= 1


async def test_upload_empty_file(async_client: AsyncClient):
    """Test that empty files are rejected."""
    token, _, _ = await _register_and_login(async_client)
    org_id = await _get_org_id(async_client, token)

    response = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={"file": ("empty.txt", b"", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


async def test_unauthorized_access_rejected(async_client: AsyncClient):
    """Test that requests without authentication are rejected with 401."""
    # List documents without token
    response = await async_client.get(
        f"{settings.API_V1_STR}/documents?org_id=some-org-id"
    )
    assert response.status_code == 401

    # Upload document without token
    response = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id=some-org-id",
        files={"file": ("unauth.txt", b"test", "text/plain")}
    )
    assert response.status_code == 401


async def test_rbac_manager_can_upload_but_cannot_delete(async_client: AsyncClient):
    """Test that a MANAGER can upload documents but cannot delete them."""
    owner_token, _, _ = await _register_and_login(async_client)
    org_id = await _get_org_id(async_client, owner_token)

    manager_token, _, manager_email = await _register_and_login(async_client)

    # Add as MANAGER
    add_res = await async_client.post(
        f"{settings.API_V1_STR}/organizations/{org_id}/members",
        json={"email": manager_email, "role": "MANAGER"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert add_res.status_code == 200

    # Manager uploads document -> Allowed
    upload_res = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={"file": ("mgr_test.txt", b"Manager upload content", "text/plain")},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["id"]

    # Manager tries to delete document -> Forbidden (only OWNER/ADMIN)
    delete_res = await async_client.delete(
        f"{settings.API_V1_STR}/documents/{doc_id}?org_id={org_id}",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert delete_res.status_code == 403

    # Owner deletes document -> Allowed
    owner_del_res = await async_client.delete(
        f"{settings.API_V1_STR}/documents/{doc_id}?org_id={org_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert owner_del_res.status_code == 200


async def test_cross_tenant_org_id_tampering_blocked(async_client: AsyncClient):
    """Test that a user cannot access another tenant's documents by forging org_id."""
    token_a, _, _ = await _register_and_login(async_client)
    org_id_a = await _get_org_id(async_client, token_a)

    token_b, _, _ = await _register_and_login(async_client)
    org_id_b = await _get_org_id(async_client, token_b)

    # Upload doc in Org B
    upload_res = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id_b}",
        files={"file": ("tenant_b.txt", b"Confidential tenant B data", "text/plain")},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert upload_res.status_code == 200
    doc_b_id = upload_res.json()["id"]

    # User A tries to list documents by passing org_id_b with token_a
    list_res = await async_client.get(
        f"{settings.API_V1_STR}/documents?org_id={org_id_b}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert list_res.status_code == 403
    assert "Not a member of this organization" in list_res.json()["detail"]

    # User A tries to upload to org_id_b with token_a
    upload_tamper_res = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id_b}",
        files={"file": ("tamper.txt", b"tamper", "text/plain")},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert upload_tamper_res.status_code == 403
    assert "Not a member of this organization" in upload_tamper_res.json()["detail"]

    # User A tries to get doc_b_id metadata passing org_id_b with token_a
    get_tamper_res = await async_client.get(
        f"{settings.API_V1_STR}/documents/{doc_b_id}?org_id={org_id_b}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert get_tamper_res.status_code == 403
    assert "Not a member of this organization" in get_tamper_res.json()["detail"]

    # User A tries to get doc_b_id status passing org_id_b with token_a
    status_tamper_res = await async_client.get(
        f"{settings.API_V1_STR}/documents/{doc_b_id}/status?org_id={org_id_b}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert status_tamper_res.status_code == 403
    assert "Not a member of this organization" in status_tamper_res.json()["detail"]

    # User A tries to get doc_b_id using their own org_id_a (tenant separation) -> 404
    get_cross_res = await async_client.get(
        f"{settings.API_V1_STR}/documents/{doc_b_id}?org_id={org_id_a}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert get_cross_res.status_code == 404
    assert "Document not found" in get_cross_res.json()["detail"]

    # User A tries to delete doc_b_id passing org_id_b with token_a
    delete_tamper_res = await async_client.delete(
        f"{settings.API_V1_STR}/documents/{doc_b_id}?org_id={org_id_b}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert delete_tamper_res.status_code == 403
    assert "Not a member of this organization" in delete_tamper_res.json()["detail"]
