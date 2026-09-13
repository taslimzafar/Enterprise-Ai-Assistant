from dataclasses import dataclass

from app.services.parsers.base import PageContent


@dataclass
class ChunkData:
    """A single chunk of document text."""
    chunk_index: int
    content: str
    char_count: int
    page_number: int | None


def chunk_text(
    pages: list[PageContent],
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[ChunkData]:
    """Split page content into overlapping chunks using a sliding window.
    
    Args:
        pages: List of PageContent from parser extraction.
        chunk_size: Target character count per chunk.
        chunk_overlap: Number of characters to overlap between consecutive chunks.
    
    Returns:
        Ordered list of ChunkData objects.
    """
    if not pages:
        return []

    # Build a flat list of (char_index, page_number) tuples for page tracking
    full_text = ""
    page_boundaries: list[tuple[int, int | None]] = []  # (start_offset, page_num)
    
    for page in pages:
        start = len(full_text)
        page_boundaries.append((start, page.page))
        if full_text:
            full_text += "\n\n"
            # Adjust start to account for the separator
            page_boundaries[-1] = (start + 2 if start > 0 else start, page.page)
        full_text += page.text

    if not full_text.strip():
        return []

    def _get_page_for_offset(offset: int) -> int | None:
        """Determine which page a character offset belongs to."""
        current_page = page_boundaries[0][1] if page_boundaries else None
        for boundary_start, page_num in page_boundaries:
            if offset >= boundary_start:
                current_page = page_num
            else:
                break
        return current_page

    chunks: list[ChunkData] = []
    start = 0
    chunk_index = 0
    text_len = len(full_text)

    while start < text_len:
        end = min(start + chunk_size, text_len)

        # Try to break at a sentence/paragraph boundary if not at end of text
        if end < text_len:
            # Look for paragraph break first
            break_pos = full_text.rfind('\n\n', start, end)
            if break_pos == -1 or break_pos <= start:
                # Look for sentence break
                break_pos = full_text.rfind('. ', start, end)
            if break_pos == -1 or break_pos <= start:
                # Look for any newline
                break_pos = full_text.rfind('\n', start, end)
            if break_pos > start:
                end = break_pos + 1  # Include the break character

        chunk_content = full_text[start:end].strip()
        if chunk_content:
            chunks.append(ChunkData(
                chunk_index=chunk_index,
                content=chunk_content,
                char_count=len(chunk_content),
                page_number=_get_page_for_offset(start),
            ))
            chunk_index += 1

        # Advance with overlap
        if end >= text_len:
            break
        start = max(start + 1, end - chunk_overlap)

    return chunks
