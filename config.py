import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DATA_DIR = os.path.join(BASE_DIR, "data")
INDEX_DIR = os.path.join(DATA_DIR, "faiss_index")
META_DIR = os.path.join(DATA_DIR, "metadata")
DB_PATH = os.path.join(META_DIR, "documind.db")

MAX_FILE_MB = 20
CHUNK_SIZE = 700        # characters per chunk
CHUNK_OVERLAP = 100
TOP_K = 5

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.30"))
# Used only when sentence-transformers can't be loaded (offline fallback)
FALLBACK_MIN_SCORE = float(os.getenv("FALLBACK_MIN_SCORE", "0.18"))

# Scanned PDFs: used only if the Tesseract program is installed on this computer
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").lower() in ("1", "true", "yes")
OCR_LANG = os.getenv("OCR_LANG", "eng")          # e.g. "eng+hin" if the Hindi language data is installed
MAX_QUESTION_CHARS = 1000

# Shown on the About page
DEVELOPER_NAME = os.getenv("DEVELOPER_NAME", "Your Name")
DEVELOPER_DETAILS = os.getenv("DEVELOPER_DETAILS", "Add your college, course and contact details in .env")
APP_VERSION = "1.1"
