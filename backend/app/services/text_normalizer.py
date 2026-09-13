import re


def normalize_text(text: str) -> str:
    """Normalize extracted document text.
    
    - Collapse multiple spaces/tabs into single space
    - Normalize line breaks  
    - Preserve paragraph structure (double newlines)
    - Strip leading/trailing whitespace from lines
    - Remove null bytes and control characters (except newlines)
    """
    if not text:
        return ""

    # Remove null bytes and non-printable control chars (keep \n \r \t)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    # Normalize line endings to \n
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Collapse tabs and multiple spaces within lines to single space
    text = re.sub(r'[^\S\n]+', ' ', text)

    # Strip whitespace from each line
    lines = [line.strip() for line in text.split('\n')]

    # Collapse 3+ consecutive blank lines into 2 (preserve paragraph breaks)
    result_lines = []
    blank_count = 0
    for line in lines:
        if line == '':
            blank_count += 1
            if blank_count <= 2:
                result_lines.append(line)
        else:
            blank_count = 0
            result_lines.append(line)

    return '\n'.join(result_lines).strip()
