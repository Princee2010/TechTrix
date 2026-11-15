import hashlib
import os
import threading
import uuid
from database import db
import config
from services import pdf_processor, text_chunker, embedding_service as emb, vector_store as vs


def list_documents():
    return [dict(r) for r in db.q("SELECT * FROM documents ORDER BY id DESC")]


def get_document(doc_id):
    r = db.q("SELECT * FROM documents WHERE id=?", (doc_id,), one=True)
    return dict(r) if r else None


def file_path(doc):
    return os.path.join(config.UPLOAD_DIR, doc["stored_name"])


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def add_document(file_storage):
    """Validate, save and queue one uploaded PDF. Checks happen BEFORE anything is written to disk."""
    name = os.path.basename(file_storage.filename or "")
    if not name.lower().endswith(".pdf"):
        raise ValueError(f"{name or 'File'}: only PDF files are allowed")
    stream = file_storage.stream
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    if size == 0:
        raise ValueError(f"{name} is empty")
    if size > config.MAX_FILE_MB * 1024 * 1024:
        raise ValueError(f"{name} is larger than {config.MAX_FILE_MB} MB")
    if b"%PDF-" not in stream.read(1024):
        raise ValueError(f"{name} is not a valid PDF")
    stream.seek(0)

    stored = uuid.uuid4().hex + ".pdf"
    path = os.path.join(config.UPLOAD_DIR, stored)
    file_storage.save(path)
    try:
        digest = _sha256(path)
        same = db.q("SELECT filename FROM documents WHERE file_hash=? AND status!='failed'", (digest,), one=True)
        if same:
            raise ValueError(f"{name} was already uploaded (as {same['filename']})")
        pages = pdf_processor.page_count(path)      # raises if corrupt or encrypted
        if pages == 0:
            raise ValueError(f"{name} has no pages")
    except Exception as e:
        os.remove(path)
        msg = str(e)
        if msg.startswith(name) or "already uploaded" in msg:
            raise ValueError(msg)
        if "password" in msg.lower():
            raise ValueError(f"{name} is password protected. Remove the password and try again")
        raise ValueError(f"{name} is not a valid PDF")
    doc_id = db.x("INSERT INTO documents(filename, stored_name, pages, size_bytes, file_hash) VALUES (?,?,?,?,?)",
                  (name, stored, pages, size, digest))
    threading.Thread(target=process_document, args=(doc_id,), daemon=True).start()
    return get_document(doc_id)


def _clear_index(doc_id):
    ids = [r["id"] for r in db.q("SELECT id FROM chunks WHERE document_id=?", (doc_id,))]
    try:
        vs.remove(ids)
    except Exception as e:
        print("[index] could not remove vectors:", e)
    db.x("DELETE FROM chunks WHERE document_id=?", (doc_id,))


def process_document(doc_id):
    """Extract page text (OCR if needed) -> chunk -> embed -> add to FAISS -> mark processed."""
    doc = get_document(doc_id)
    try:
        pages, empty, ocr = pdf_processor.extract_pages(file_path(doc))
        rows = [(doc_id, pno, ch) for pno, text in pages for ch in text_chunker.chunk_page(text)]
        if not rows:
            hint = ("OCR is switched off or Tesseract is not installed." if not pdf_processor.ocr_available()
                    else "OCR found no readable text.")
            raise ValueError(f"No extractable text found (scanned or image-only PDF). {hint}")
        conn = db.connect()
        conn.executemany("INSERT INTO chunks(document_id, page, text) VALUES (?,?,?)", rows)
        conn.commit()
        ids = [r[0] for r in conn.execute("SELECT id FROM chunks WHERE document_id=? ORDER BY id", (doc_id,))]
        conn.close()
        texts = [r[2] for r in rows]
        for i in range(0, len(texts), 64):
            vs.add(ids[i:i + 64], emb.embed(texts[i:i + 64]))
        db.x("UPDATE documents SET status='processed', chunk_count=?, char_count=?, empty_pages=?, ocr_pages=?, error=NULL "
             "WHERE id=?", (len(rows), sum(len(t) for t in texts), empty, ocr, doc_id))
    except Exception as e:
        _clear_index(doc_id)
        db.x("UPDATE documents SET status='failed', error=? WHERE id=?", (str(e)[:300], doc_id))


def reprocess(doc_id):
    doc = get_document(doc_id)
    if not doc or doc["status"] == "processing":
        return False
    _clear_index(doc_id)
    db.x("UPDATE documents SET status='processing', error=NULL, chunk_count=0, char_count=0 WHERE id=?", (doc_id,))
    threading.Thread(target=process_document, args=(doc_id,), daemon=True).start()
    return True


def delete_document(doc_id):
    doc = get_document(doc_id)
    if not doc:
        return False
    _clear_index(doc_id)
    db.x("DELETE FROM documents WHERE id=?", (doc_id,))   # chunks cascade
    try:
        os.remove(file_path(doc))
    except OSError:
        pass
    return True


def stats():
    d = db.q("SELECT COUNT(*) n, COALESCE(SUM(CASE WHEN status='processed' THEN pages END),0) pages, "
             "COALESCE(SUM(status='processed'),0) done FROM documents", one=True)
    qn = db.q("SELECT COUNT(*) n FROM messages WHERE role='user'", one=True)["n"]
    return {"documents": d["n"], "pages": d["pages"], "processed": d["done"], "questions": qn}
