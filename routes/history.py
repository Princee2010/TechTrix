import json
from flask import Blueprint, render_template, jsonify, abort
from database import db

bp = Blueprint("history", __name__)


@bp.get("/history")
def page():
    return render_template("history.html")


@bp.get("/api/conversations")
def list_conversations():
    rows = db.q("SELECT c.id, c.title, c.created_at, "
                "(SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id AND m.role='user') AS questions "
                "FROM conversations c ORDER BY c.id DESC")
    return jsonify([dict(r) for r in rows])


@bp.get("/api/conversations/<int:conv_id>")
def get_conversation(conv_id):
    conv = db.q("SELECT * FROM conversations WHERE id=?", (conv_id,), one=True)
    if not conv:
        abort(404)
    msgs = []
    for m in db.q("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (conv_id,)):
        d = dict(m)
        d["sources"] = json.loads(d["sources"]) if d["sources"] else []
        d["doc_ids"] = json.loads(d["doc_ids"]) if d["doc_ids"] else []
        msgs.append(d)
    return jsonify(conversation=dict(conv), messages=msgs)


@bp.delete("/api/conversations/<int:conv_id>")
def delete_conversation(conv_id):
    db.x("DELETE FROM conversations WHERE id=?", (conv_id,))
    return jsonify(ok=True)


@bp.delete("/api/conversations")
def clear_all():
    db.x("DELETE FROM conversations")
    return jsonify(ok=True)
