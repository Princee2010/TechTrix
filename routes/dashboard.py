from flask import Blueprint, render_template, request, jsonify, abort
import config
from database import db
from services import document_service as ds, embedding_service, answer_service

bp = Blueprint("dashboard", __name__)


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/dashboard")
def dashboard():
    questions = db.q("SELECT content, conversation_id, created_at FROM messages "
                     "WHERE role='user' ORDER BY id DESC LIMIT 5")
    return render_template("dashboard.html", stats=ds.stats(), docs=ds.list_documents()[:5], questions=questions)


@bp.get("/viewer")
def viewer():
    doc_id = request.args.get("document_id", type=int)
    page = request.args.get("page", 1, type=int)
    doc = None
    if doc_id:
        doc = ds.get_document(doc_id)
        if not doc:
            abort(404)
        page = max(1, min(page, doc["pages"] or 1))
    return render_template("viewer.html", doc=doc, page=page, docs=ds.list_documents())


@bp.get("/settings")
def settings():
    return render_template("settings.html")


@bp.get("/about")
def about():
    return render_template("about.html", dev_name=config.DEVELOPER_NAME, dev_details=config.DEVELOPER_DETAILS,
                           version=config.APP_VERSION)


@bp.get("/api/settings")
def get_settings():
    return jsonify(db.get_settings())


@bp.post("/api/settings")
def save_settings():
    data = request.get_json(silent=True) or {}
    if data.get("language") in ("English", "Hindi", "Hinglish"):
        db.set_setting("language", data["language"])
    if data.get("style") in ("Simple", "Detailed"):
        db.set_setting("style", data["style"])
    return jsonify(db.get_settings())


@bp.get("/api/status")
def status():
    from services import pdf_processor
    return jsonify(ai=answer_service.gemini_status(), embeddings=embedding_service.backend(),
                   ocr=pdf_processor.ocr_available())
