"""Run this once on YOUR computer:   python check_setup.py
It checks the parts that need your internet connection, API key and installed programs."""
import os
import shutil
import sys

import config

OK, BAD, WARN = "[ OK ]", "[FAIL]", "[WARN]"
problems = 0


def report(ok, msg, hint=""):
    global problems
    print(f"{OK if ok else BAD} {msg}")
    if not ok:
        problems += 1
        if hint:
            print(f"       -> {hint}")


print(f"DocuMind AI setup check (Python {sys.version.split()[0]})\n")
report(sys.version_info >= (3, 9), "Python 3.9 or newer", "Install a newer Python")
for mod, pipname in [("flask", "flask"), ("pymupdf", "pymupdf"), ("faiss", "faiss-cpu"), ("numpy", "numpy"),
                     ("requests", "requests"), ("dotenv", "python-dotenv"), ("sentence_transformers", "sentence-transformers")]:
    try:
        __import__(mod)
        report(True, f"package {pipname}")
    except Exception as e:
        report(False, f"package {pipname}", f"pip install {pipname}   ({e.__class__.__name__})")

print()
try:
    from services import embedding_service as emb
    emb._load()
    ok = emb.backend() == "sentence-transformers"
    report(ok, f"embedding model '{config.EMBED_MODEL}' loads",
           "It downloads on first use and needs internet. Until it loads, the app uses a weaker keyword fallback.")
    if ok:
        v = emb.embed(["A process is a program in execution.", "A running program is called a process.",
                       "The recipe needs two cups of flour."])
        related, unrelated = float(v[0] @ v[1]), float(v[0] @ v[2])
        print(f"       similar sentences score {related:.2f}, unrelated {unrelated:.2f} (MIN_SCORE is {config.MIN_SCORE})")
        report(related > unrelated + 0.2, "model separates related from unrelated text")
except Exception as e:
    report(False, "embedding model", str(e))

print()
if not config.GEMINI_API_KEY:
    report(False, "GEMINI_API_KEY is set", "Copy .env.example to .env and paste your key (https://aistudio.google.com/apikey)")
else:
    from services import answer_service
    st = answer_service.gemini_status()
    report(st["ok"], f"Gemini model '{config.GEMINI_MODEL}' reachable", st["detail"] + ". Check GEMINI_API_KEY / GEMINI_MODEL in .env")
    if st["ok"]:
        text, found, warn = answer_service.generate(
            "What colour is the sky?", [{"filename": "t.pdf", "page": 1, "text": "On a clear day the sky is blue."}])
        report(found and not warn and "blue" in text.lower(), "Gemini answers from supplied passages", warn or text[:80])
        text, found, warn = answer_service.generate(
            "What is the capital of France?", [{"filename": "t.pdf", "page": 1, "text": "On a clear day the sky is blue."}])
        report(not found, "Gemini refuses when passages don't contain the answer (NOT_FOUND)", f"it answered: {text[:80]}")

print()
from services import pdf_processor
if shutil.which("tesseract"):
    report(True, "Tesseract found (scanned-PDF OCR available)")
else:
    print(f"{WARN} Tesseract not found. Scanned PDFs will fail with a clear message. Optional:")
    print("       Windows: https://github.com/UB-Mannheim/tesseract/wiki   macOS: brew install tesseract   Linux: sudo apt install tesseract-ocr")

for d in (config.UPLOAD_DIR, config.INDEX_DIR, config.META_DIR):
    os.makedirs(d, exist_ok=True)
    report(os.access(d, os.W_OK), f"can write to {os.path.relpath(d, config.BASE_DIR)}/")

print(f"\n{'Everything needed is ready. Start the app with: python app.py' if not problems else str(problems) + ' problem(s) found. Fix the items marked [FAIL].'}")
sys.exit(1 if problems else 0)
