import json
import time
from flask import Blueprint, render_template, request, jsonify
import config
from database import db
from services import retrieval_service, answer_service

bp = Blueprint("chat", __name__)


@bp.get("/chat")
def page():
    return render_template("chat.html")


@bp.post("/api/chat")
def ask():
    data = request.get_json(silent=True) or {}
    question = " ".join(str(data.get("question") or "").split())
    if not question:
        return jsonify(error="Type a question first."), 400
    if len(question) > config.MAX_QUESTION_CHARS:
        return jsonify(error=f"Questions can be up to {config.MAX_QUESTION_CHARS} characters. Yours has {len(question)}."), 400
    try:
        requested = {int(i) for i in data.get("document_ids") or []}
    except (TypeError, ValueError):
        return jsonify(error="Invalid document selection."), 400
    if not requested:
        return jsonify(error="Select at least one processed document."), 400
    marks = ",".join("?" * len(requested))
    doc_ids = [r["id"] for r in db.q(f"SELECT id FROM documents WHERE status='processed' AND id IN ({marks})", list(requested))]
    if not doc_ids:
        return jsonify(error="The selected documents aren't ready. Wait until they show Processed."), 400

    start = time.time()
    conv_id = data.get("conversation_id")
    if not conv_id or not db.q("SELECT id FROM conversations WHERE id=?", (conv_id,), one=True):
        conv_id = db.x("INSERT INTO conversations(title) VALUES (?)", (question[:60],))
    db.x("INSERT INTO messages(conversation_id, role, content, doc_ids) VALUES (?,?,?,?)",
         (conv_id, "user", question, json.dumps(doc_ids)))

    try:
        hits, _best = retrieval_service.retrieve(question, doc_ids)   # relevance check happens BEFORE the LLM
    except Exception:
        return jsonify(error="Search failed. Check the terminal for details, then try again.", conversation_id=conv_id), 500

    settings = db.get_settings()
    no_match, answer, warning = True, answer_service.NO_MATCH_TEXT, None
    if hits:
        text, found, warning = answer_service.generate(question, hits, settings["language"], settings["style"])
        if found:
            no_match, answer = False, text
        else:
            warning = None
    sources = [] if no_match else [
        {"n": i, "document_id": h["document_id"], "chunk_id": h["chunk_id"], "filename": h["filename"],
         "page": h["page"], "snippet": h["text"][:220], "score": h["score"]} for i, h in enumerate(hits, 1)]

    ms = int((time.time() - start) * 1000)
    msg_id = db.x("INSERT INTO messages(conversation_id, role, content, sources, doc_ids, no_match, response_ms) "
                  "VALUES (?,?,?,?,?,?,?)",
                  (conv_id, "assistant", answer, json.dumps(sources), json.dumps(doc_ids), int(no_match), ms))
    return jsonify(conversation_id=conv_id, message_id=msg_id, answer=answer, sources=sources,
                   no_match=no_match, warning=warning, ms=ms)


@bp.post("/api/messages/<int:msg_id>/feedback")
def feedback(msg_id):
    value = (request.get_json(silent=True) or {}).get("value")
    if value not in (1, -1):
        return jsonify(error="Invalid feedback"), 400
    db.x("UPDATE messages SET feedback=? WHERE id=? AND role='assistant'", (value, msg_id))
    return jsonify(ok=True)
