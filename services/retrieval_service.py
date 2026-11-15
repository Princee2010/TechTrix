import config
from database import db
from services import embedding_service as emb, vector_store as vs


def retrieve(question, doc_ids, k=None):
    """Top passages for `question` inside the selected documents.

    Returns (hits, best_score). Only passages scoring above the relevance
    threshold are returned; an empty list means "no evidence" and the
    caller must NOT ask the LLM to answer.
    """
    k = k or config.TOP_K
    if not doc_ids:
        return [], 0.0
    marks = ",".join("?" * len(doc_ids))
    allowed = {r["id"] for r in db.q(f"SELECT id FROM chunks WHERE document_id IN ({marks})", list(doc_ids))}
    if not allowed:
        return [], 0.0
    scores, ids = vs.search(emb.embed([question])[0], 3000)
    picked = [(s, i) for s, i in zip(scores, ids) if i in allowed][:k]
    if not picked:
        return [], 0.0
    best = picked[0][0]
    threshold = emb.min_score()
    picked = [(s, i) for s, i in picked if s >= threshold]
    if not picked:
        return [], float(best)
    m2 = ",".join("?" * len(picked))
    rows = {r["id"]: r for r in db.q(
        f"SELECT c.id, c.document_id, c.page, c.text, d.filename FROM chunks c "
        f"JOIN documents d ON d.id = c.document_id WHERE c.id IN ({m2})", [i for _, i in picked])}
    hits = [{"chunk_id": i, "document_id": rows[i]["document_id"], "filename": rows[i]["filename"],
             "page": rows[i]["page"], "text": rows[i]["text"], "score": round(float(s), 3)}
            for s, i in picked if i in rows]
    return hits, float(best)
