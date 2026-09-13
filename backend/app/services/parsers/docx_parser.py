import io
from docx import Document as DocxDocument

from app.services.parsers.base import DocumentParser, PageContent


class DOCXParser(DocumentParser):
    """Extract text from DOCX files using python-docx."""

    def extract(self, file_bytes: bytes) -> list[PageContent]:
        doc = DocxDocument(io.BytesIO(file_bytes))
        # DOCX doesn't have native page numbers in the python-docx API,
        # so we treat the entire document as a single section.
        paragraphs = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                paragraphs.append(text)

        full_text = "\n\n".join(paragraphs)
        if full_text.strip():
            return [PageContent(page=None, text=full_text)]
        return []
