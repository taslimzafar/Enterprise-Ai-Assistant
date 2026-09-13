import io
from PyPDF2 import PdfReader

from app.services.parsers.base import DocumentParser, PageContent


class PDFParser(DocumentParser):
    """Extract text from PDF files using PyPDF2."""

    def extract(self, file_bytes: bytes) -> list[PageContent]:
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(PageContent(page=i + 1, text=text))
        return pages
