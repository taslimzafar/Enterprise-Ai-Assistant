from app.services.parsers.base import DocumentParser
from app.services.parsers.pdf_parser import PDFParser
from app.services.parsers.docx_parser import DOCXParser
from app.services.parsers.txt_parser import TXTParser

_PARSERS: dict[str, type[DocumentParser]] = {
    "pdf": PDFParser,
    "docx": DOCXParser,
    "txt": TXTParser,
}


def get_parser(file_type: str) -> DocumentParser:
    """Factory function to get the appropriate parser for a file type.
    
    Raises ValueError if the file type is not supported.
    """
    parser_cls = _PARSERS.get(file_type.lower())
    if parser_cls is None:
        raise ValueError(f"Unsupported file type: {file_type}")
    return parser_cls()
