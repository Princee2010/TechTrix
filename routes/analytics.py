import re
from collections import Counter
from flask import Blueprint, render_template, request, jsonify
from database import db
from services import document_service as ds, retrieval_service, vector_store, embedding_service

bp = Blueprint("analytics", __name__)
STOP = set("""what is are the a an of to in on and or for with how why when which who does do can explain define describe
difference between about give list tell me my this that from into your you please state steps types""".split())


@bp.get("/analytics")
def page():
    return render_template("analytics.html")


@bp.get("/api/analytics")
def data():
    s = ds.stats()
    chunks = db.q("SELECT COUNT(*) n FROM chunks", one=True)["n"]
    avg = db.q("SELECT AVG(response_ms) a FROM messages WHERE role='assistant' AND response_ms IS NOT NULL", one=True)["a"]
    words = Counter()
    for r in db.q("SELECT content FROM messages WHERE role='user'"):
        words.update(w for w in re.findall(r"[a-zA-Z]{3,}", r["content"].lower()) if w not in STOP)
    fb = db.q("SELECT SUM(feedback=1) up, SUM(feedback=-1) down, SUM(no_match=1) nomatch FROM messages "
              "WHERE role='assistant'", one=True)
    return jsonify(documents=s["documents"], pages=s["pages"], chunks=chunks, vectors=vector_store.total(),
                   questions=s["questions"], avg_ms=int(avg) if avg else None,
                   topics=[{"word": w, "count": c} for w, c in words.most_common(8)],
                   helpful=fb["up"] or 0, not_helpful=fb["down"] or 0, no_match=fb["nomatch"] or 0,
                   embeddings=embedding_service.backend())


@bp.post("/api/analytics/evaluate")
def evaluate():
    """Run a test set against the real index.

    Body: {"tests": [{"question": "...", "document": "OS.pdf", "page": 24, "answerable": true}, ...]}
    answerable=false marks a question that must return no match.
    """
    tests = (request.get_json(silent=True) or {}).get("tests")
    if not isinstance(tests, list) or not tests:
        return jsonify(error="Provide a non-empty list of tests."), 400
    if len(tests) > 200:
        return jsonify(error="Please run at most 200 questions at a time."), 400
    docs = ds.list_documents()
    ids = [d["id"] for d in docs if d["status"] == "processed"]
    if not ids:
        return jsonify(error="Upload and process at least one document first."), 400
    by_name = {d["filename"]: d["id"] for d in docs}
    prec, rec, cite, nm, rows = [], [], [], [], []
    good_scores, bad_scores = [], []
    for n, t in enumerate(tests, 1):
        if not isinstance(t, dict) or not str(t.get("question", "")).strip():
            return jsonify(error=f"Test {n} needs a \"question\"."), 400
        answerable = t.get("answerable", True)
        pages = t.get("pages") or ([t["page"]] if "page" in t else [])
        if answerable and (t.get("document") not in by_name or not pages):
            return jsonify(error=f"Test {n}: \"document\" must match an uploaded file name and \"page\" is required."), 400
        hits, best = retrieval_service.retrieve(t["question"], ids)
        if answerable:
            rel = [h for h in hits if h["document_id"] == by_name[t["document"]] and h["page"] in pages]
            prec.append(len(rel) / len(hits) if hits else 0.0)
            rec.append(1.0 if rel else 0.0)
            top_ok = bool(hits) and hits[0] in rel
            cite.append(1.0 if top_ok else 0.0)
            good_scores.append(best)
            rows.append({"question": t["question"], "type": "answerable", "retrieved": len(hits), "best_score": round(best, 3),
                         "found_expected_page": bool(rel), "top_is_correct": top_ok})
        else:
            ok = not hits
            nm.append(1.0 if ok else 0.0)
            bad_scores.append(best)
            rows.append({"question": t["question"], "type": "no-match", "retrieved": len(hits), "best_score": round(best, 3),
                         "correct": ok})
    avg = lambda xs: round(sum(xs) / len(xs), 3) if xs else None
    threshold = {"current": round(embedding_service.min_score(), 3), "suggested": None, "note": None}
    if good_scores and bad_scores:
        lo, hi = min(good_scores), max(bad_scores)
        if lo > hi:
            threshold["suggested"] = round((lo + hi) / 2, 3)
            threshold["note"] = "Every answerable question scored above every unanswerable one, so this value separates them."
        else:
            threshold["note"] = ("Scores overlap: some unanswerable questions scored as high as answerable ones. "
                                 "No single cutoff fixes this. Try a stronger embedding model or add more test questions.")
    else:
        threshold["note"] = "Include both answerable and unanswerable questions to get a threshold suggestion."
    return jsonify(precision_at_5=avg(prec), recall_at_5=avg(rec), citation_correctness=avg(cite),
                   no_match_accuracy=avg(nm), n_answerable=len(prec), n_no_match=len(nm), threshold=threshold, rows=rows)
