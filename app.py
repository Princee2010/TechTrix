import os
import threading
from flask import Flask, jsonify, request, render_template
import config
from database import db


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 400 * 1024 * 1024   # whole request; each file is capped at 20 MB separately
    for d in (config.UPLOAD_DIR, config.INDEX_DIR, config.META_DIR):
        os.makedirs(d, exist_ok=True)
    db.init_db()
    db.reset_stuck()

    from routes import dashboard, documents, chat, history, analytics
    for module in (dashboard, documents, chat, history, analytics):
        app.register_blueprint(module.bp)

    def wants_json():
        return request.path.startswith("/api/")

    @app.errorhandler(413)
    def too_large(_):
        return jsonify(error="Upload too large. Each file can be up to 20 MB."), 413

    @app.errorhandler(404)
    def not_found(_):
        if wants_json():
            return jsonify(error="Not found"), 404
        return render_template("error.html", code=404, message="That page or document doesn't exist."), 404

    @app.errorhandler(Exception)
    def crashed(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e
        app.logger.exception("Unhandled error")
        if wants_json():
            return jsonify(error="Something went wrong on the server. Check the terminal for details."), 500
        return render_template("error.html", code=500, message="Something went wrong on the server."), 500

    return app


if __name__ == "__main__":
    from services import embedding_service
    threading.Thread(target=embedding_service.warmup, daemon=True).start()   # load model while the server starts
    print("DocuMind AI running at http://127.0.0.1:5000")
    create_app().run(host="127.0.0.1", port=5000, debug=False, threaded=True)
