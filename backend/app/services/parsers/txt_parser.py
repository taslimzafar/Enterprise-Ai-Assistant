from app.services.parsers.base import DocumentParser, PageContent


class TXTParser(DocumentParser):
    """Extract text from plain text files."""

    def extract(self, file_bytes: bytes) -> list[PageContent]:
        # Try UTF-8 first, fall back to latin-1 for binary-safe decoding
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1")

        if text.strip():
            return [PageContent(page=None, text=text)]
        return []
