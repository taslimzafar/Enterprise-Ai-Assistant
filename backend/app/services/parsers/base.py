from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PageContent:
    """Represents extracted text from a single page or section."""
    page: int | None  # None if page info not available
    text: str


class DocumentParser(ABC):
    """Abstract base class for document text extraction."""

    @abstractmethod
    def extract(self, file_bytes: bytes) -> list[PageContent]:
        """Extract text content from raw file bytes.
        
        Returns a list of PageContent objects, one per logical page/section.
        """
        ...
