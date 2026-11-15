import re
import config


def chunk_page(text, size=None, overlap=None):
    """Split one page's text into overlapping chunks. Chunks never cross
    pages, so every citation maps to exactly one real page."""
    size = size or config.CHUNK_SIZE
    overlap = overlap if overlap is not None else config.CHUNK_OVERLAP
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text).strip()
    if not text:
        return []
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
    chunks, cur = [], ""
    for s in sentences:
        if cur and len(cur) + len(s) + 1 > size:
            chunks.append(cur)
            tail = cur[-overlap:] if overlap else ""
            cur = tail.split(" ", 1)[-1] if " " in tail else ""
        cur = (cur + " " + s).strip()
    if cur:
        chunks.append(cur)
    # merge a tiny trailing fragment into the previous chunk
    if len(chunks) > 1 and len(chunks[-1]) < 60:
        chunks[-2] += " " + chunks.pop()
    return [c for c in chunks if len(c) >= 25]
