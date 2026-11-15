import os
from flask import Blueprint, render_template, request, jsonify, send_file, abort
from services import document_service as ds

bp = Blueprint("documents", __name__)


@bp.get("/documents")
def page():
    return render_template("documents.html")


@bp.get("/api/documents")
def list_docs():
    return jsonify(ds.list_documents())


@bp.get("/api/documents/<int:doc_id>")
def detail(doc_id):
    doc = ds.get_document(doc_id)
    if not doc:
        abort(404)
    return jsonify(doc)


@bp.post("/api/documents/upload")
def upload():
    results, errors = [], []
    for f in request.files.getlist("files"):
        try:
            results.append(ds.add_document(f))
        except Exception as e:
            errors.append({"file": f.filename, "error": str(e)})
    status = 200 if results else 400
    return jsonify(uploaded=results, errors=errors), status


@bp.post("/api/documents/<int:doc_id>/reprocess")
def reprocess(doc_id):
    if not ds.reprocess(doc_id):
        return jsonify(error="This document can't be reprocessed right now."), 409
    return jsonify(ok=True)


@bp.get("/api/chunks/<int:chunk_id>")
def chunk(chunk_id):
    """Text of a cited passage, used by the viewer to highlight it on the page."""
    from database import db
    r = db.q("SELECT id, document_id, page, text FROM chunks WHERE id=?", (chunk_id,), one=True)
    if not r:
        abort(404)
    return jsonify(dict(r))


@bp.delete("/api/documents/<int:doc_id>")
def delete(doc_id):
    if not ds.delete_document(doc_id):
        abort(404)
    return jsonify(ok=True)


@bp.get("/api/documents/<int:doc_id>/file")
def file(doc_id):
    doc = ds.get_document(doc_id)
    if not doc or not os.path.exists(ds.file_path(doc)):
        abort(404)
    return send_file(ds.file_path(doc), mimetype="application/pdf", download_name=doc["filename"],
                     as_attachment=request.args.get("download") == "1", conditional=True)
