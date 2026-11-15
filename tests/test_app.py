"""End-to-end tests. Run from the project folder:   python -m unittest -v tests.test_app

They use a temporary folder (your real uploads/database are untouched) and a mocked Gemini,
so they need no API key and no internet. They check the PIPELINE logic. The relevance threshold
for your real embedding model must still be calibrated on the Analytics page with your own PDFs.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import pymupdf
except ImportError:
    import fitz as pymupdf
import config

TMP = tempfile.mkdtemp(prefix="documind_test_")
config.UPLOAD_DIR = os.path.join(TMP, "uploads")
config.INDEX_DIR = os.path.join(TMP, "index")
config.META_DIR = os.path.join(TMP, "meta")
config.DB_PATH = os.path.join(config.META_DIR, "t.db")
config.GEMINI_API_KEY = "test-key"

from app import create_app                      # noqa: E402
from services import vector_store as vs, embedding_service as emb, answer_service, pdf_processor  # noqa: E402
vs._PATH = os.path.join(config.INDEX_DIR, "index.faiss")
emb._backend = "hashing-fallback"                # deterministic: never download a model during tests


def make_pdf(pages, scanned=False, password=None):
    d = pymupdf.open()
    for t in pages:
        p = d.new_page()
        p.insert_textbox(pymupdf.Rect(50, 50, 550, 780), t, fontsize=12)
    if scanned:                                  # turn every page into a picture with no text layer
        img = pymupdf.open()
        for page in d:
            pix = page.get_pixmap(dpi=200)
            n = img.new_page(width=page.rect.width, height=page.rect.height)
            n.insert_image(n.rect, pixmap=pix)
        d = img
    if password:
        return d.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
    return d.tobytes()


FILLER = "This chapter gives a general introduction to the course and its goals. "
OS_PAGES = [FILLER * 6 for _ in range(23)] + [
    "A process is an independent program in execution with its own memory space and resources. A thread is a smaller "
    "unit of execution within a process. Multiple threads share the resources of their parent process such as code, "
    "data and open files. Threads are lighter than processes.",
    "The four states of a process are new, ready, running, waiting and terminated. The scheduler moves a process from "
    "ready to running using CPU scheduling algorithms such as round robin and shortest job first."]
DB_PAGES = ["A relational database stores data in tables of rows and columns. Normalization reduces redundancy. ",
            "A primary key uniquely identifies each row in a table. A foreign key links one table to another."]


class FakeResp:
    def __init__(self, status=200, payload=None):
        self.status_code, self._p, self.ok = status, payload, status < 400
    def json(self):
        return self._p


def gemini_text(text):
    return FakeResp(200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        shutil.rmtree(TMP, ignore_errors=True)
        vs._index = None
        cls.app = create_app()
        cls.c = cls.app.test_client()

    def upload(self, files):
        data = {"files": [(io.BytesIO(b), n) for n, b in files]}
        return self.c.post("/api/documents/upload", data=data, content_type="multipart/form-data")

    def wait(self, timeout=60):
        for _ in range(int(timeout / 0.25)):
            docs = self.c.get("/api/documents").json
            if all(d["status"] != "processing" for d in docs):
                return docs
            time.sleep(0.25)
        self.fail("processing did not finish")

    def ask(self, q, ids, conv=None):
        return self.c.post("/api/chat", json={"question": q, "document_ids": ids, "conversation_id": conv})


class T1_Upload(Base):
    def test_1_valid_and_invalid_uploads(self):
        r = self.upload([("OS_Notes.pdf", make_pdf(OS_PAGES)), ("DBMS.pdf", make_pdf(DB_PAGES)),
                         ("fake.pdf", b"hello, not a pdf"), ("empty.pdf", b""), ("notes.txt", b"%PDF-1.4 hi"),
                         ("locked.pdf", make_pdf(DB_PAGES, password="secret")),
                         ("huge.pdf", b"%PDF-1.4\n" + b"0" * (21 * 1024 * 1024))])
        j = r.json
        self.assertEqual(r.status_code, 200)
        self.assertEqual(sorted(d["filename"] for d in j["uploaded"]), ["DBMS.pdf", "OS_Notes.pdf"])
        errs = {e["file"]: e["error"] for e in j["errors"]}
        self.assertIn("not a valid PDF", errs["fake.pdf"])
        self.assertIn("empty", errs["empty.pdf"])
        self.assertIn("only PDF", errs["notes.txt"])
        self.assertIn("password", errs["locked.pdf"].lower())
        self.assertIn("larger than 20 MB", errs["huge.pdf"])
        self.assertEqual(len(os.listdir(config.UPLOAD_DIR)), 2, "rejected files must not stay on disk")
        self.assertTrue(all(d["status"] == "processed" for d in self.wait()))

    def test_2_duplicate_and_all_invalid(self):
        pdf = make_pdf(DB_PAGES)
        self.assertEqual(self.upload([("a.pdf", pdf)]).status_code, 200)
        r = self.upload([("b.pdf", pdf)])
        self.assertEqual(r.status_code, 400)
        self.assertIn("already uploaded", r.json["errors"][0]["error"])
        self.assertEqual(self.upload([("junk.pdf", b"nope")]).status_code, 400)
        self.wait()


class T2_Processing(Base):
    def test_chunks_pages_and_vectors(self):
        self.upload([("OS_Notes.pdf", make_pdf(OS_PAGES))]); docs = self.wait()
        d = docs[0]
        self.assertEqual((d["status"], d["pages"]), ("processed", 25))
        from database import db
        rows = db.q("SELECT page, text FROM chunks WHERE document_id=?", (d["id"],))
        self.assertEqual(d["chunk_count"], len(rows))
        self.assertEqual({r["page"] for r in rows}, set(range(1, 26)), "pages must be 1-based and complete")
        self.assertTrue(all(25 <= len(r["text"]) <= 1500 for r in rows))
        self.assertTrue(any("thread" in r["text"] and r["page"] == 24 for r in rows))
        self.assertEqual(vs.total(), len(rows), "one vector per chunk")

    def test_scanned_pdf_with_ocr(self):
        if not pdf_processor.ocr_available():
            self.skipTest("Tesseract not installed")
        self.upload([("Scan.pdf", make_pdf(["Photosynthesis converts sunlight into chemical energy inside chloroplasts of plant cells."], scanned=True))])
        d = [x for x in self.wait() if x["filename"] == "Scan.pdf"][0]
        self.assertEqual(d["status"], "processed", d.get("error"))
        self.assertEqual(d["ocr_pages"], 1)
        hits = self.ask("How does photosynthesis convert sunlight into energy?", [d["id"]]).json
        self.assertFalse(hits["no_match"])

    def test_scanned_pdf_without_ocr_fails_clearly_and_can_retry(self):
        with mock.patch.object(config, "OCR_ENABLED", False):
            self.upload([("Scan2.pdf", make_pdf(["Mitochondria produce energy for the cell in the form of ATP molecules."], scanned=True))])
            d = [x for x in self.wait() if x["filename"] == "Scan2.pdf"][0]
        self.assertEqual(d["status"], "failed")
        self.assertIn("scanned", d["error"].lower())
        if pdf_processor.ocr_available():
            self.assertEqual(self.c.post(f"/api/documents/{d['id']}/reprocess").status_code, 200)
            d = [x for x in self.wait() if x["id"] == d["id"]][0]
            self.assertEqual(d["status"], "processed", d.get("error"))


class T3_Answers(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.upload(cls, [("OS_Notes.pdf", make_pdf(OS_PAGES)), ("DBMS.pdf", make_pdf(DB_PAGES))])
        cls.docs = {d["filename"]: d["id"] for d in cls.wait(cls)}
        cls.ids = list(cls.docs.values())

    def test_grounded_answer_with_correct_citation(self):
        with mock.patch.object(answer_service.requests, "post", return_value=gemini_text("A process owns its memory; threads share it [1].")) as p:
            j = self.ask("Explain the difference between a process and a thread.", self.ids).json
        self.assertFalse(j["no_match"]); self.assertEqual(p.call_count, 1)
        self.assertEqual((j["sources"][0]["filename"], j["sources"][0]["page"]), ("OS_Notes.pdf", 24))
        self.assertIn("chunk_id", j["sources"][0])
        sent = p.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
        self.assertIn("ONLY", sent); self.assertIn("page 24", sent)
        self.assertNotIn("key=", str(p.call_args))            # API key must not travel in the URL

    def test_document_filter_limits_sources(self):
        with mock.patch.object(answer_service.requests, "post", return_value=gemini_text("ok [1]")):
            j = self.ask("primary key foreign key", [self.docs["OS_Notes.pdf"]]).json
        self.assertTrue(all(s["filename"] == "OS_Notes.pdf" for s in j["sources"]))

    def test_no_match_never_calls_gemini(self):
        for q in ["Who won the 2018 football world cup final?", "Give me a recipe for chocolate cake", "What is the capital of France?"]:
            with mock.patch.object(answer_service.requests, "post") as p:
                j = self.ask(q, self.ids).json
            self.assertTrue(j["no_match"], q); self.assertEqual(j["sources"], []); self.assertEqual(p.call_count, 0, q)
            self.assertIn("couldn't find", j["answer"])

    def test_model_says_not_found(self):
        with mock.patch.object(answer_service.requests, "post", return_value=gemini_text("NOT_FOUND")):
            j = self.ask("Explain process scheduling in the garden", self.ids).json
        self.assertTrue(j["no_match"]); self.assertEqual(j["sources"], [])

    def test_gemini_failures_fall_back_to_passages(self):
        cases = [("rate limit", FakeResp(429, {})), ("bad key", FakeResp(403, {})), ("blocked", FakeResp(200, {"candidates": []})),
                 ("timeout", answer_service.requests.Timeout()), ("offline", answer_service.requests.ConnectionError())]
        for name, outcome in cases:
            kw = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
            with mock.patch.object(answer_service.requests, "post", **kw), mock.patch.object(answer_service.time, "sleep"):
                j = self.ask("What are the four states of a process?", self.ids).json
            self.assertFalse(j["no_match"], name); self.assertTrue(j["warning"], name); self.assertTrue(j["sources"], name)

    def test_hinglish_and_hindi_prompts(self):
        for lang, marker in (("Hinglish", "Roman"), ("Hindi", "Devanagari")):
            self.c.post("/api/settings", json={"language": lang, "style": "Detailed"})
            with mock.patch.object(answer_service.requests, "post", return_value=gemini_text("ok [1]")) as p:
                self.ask("What are the four states of a process?", self.ids)
            self.assertIn(marker, p.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"])
        self.c.post("/api/settings", json={"language": "English", "style": "Simple"})

    def test_bad_input_is_rejected_cleanly(self):
        self.assertEqual(self.ask("", self.ids).status_code, 400)
        self.assertEqual(self.ask("x" * 1001, self.ids).status_code, 400)
        self.assertEqual(self.ask("hello there", []).status_code, 400)
        self.assertEqual(self.ask("hello there", [9999]).status_code, 400)
        self.assertEqual(self.c.post("/api/chat", json={"question": "hi", "document_ids": ["abc"]}).status_code, 400)
        self.assertEqual(self.c.post("/api/chat", data="not json", content_type="text/plain").status_code, 400)
        self.assertEqual(self.c.get("/api/nothing").status_code, 404)
        self.assertEqual(self.c.get("/api/nothing").json, {"error": "Not found"})

    def test_retrieval_failure_is_reported(self):
        with mock.patch("routes.chat.retrieval_service.retrieve", side_effect=RuntimeError("boom")):
            r = self.ask("What are the four states of a process?", self.ids)
        self.assertEqual(r.status_code, 500); self.assertIn("Search failed", r.json["error"])


class T4_SourceExplorer(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.upload(cls, [("OS_Notes.pdf", make_pdf(OS_PAGES))])
        cls.doc = cls.wait(cls)[0]

    def test_viewer_pages_and_file(self):
        i = self.doc["id"]
        self.assertEqual(self.c.get(f"/viewer?document_id={i}&page=24").status_code, 200)
        self.assertIn('value="24"', self.c.get(f"/viewer?document_id={i}&page=24").text)
        self.assertIn('value="25"', self.c.get(f"/viewer?document_id={i}&page=999").text, "page is clamped to the last page")
        self.assertIn('value="1"', self.c.get(f"/viewer?document_id={i}&page=-4").text)
        self.assertEqual(self.c.get("/viewer?document_id=999").status_code, 404)
        self.assertEqual(self.c.get("/viewer").status_code, 200)
        f = self.c.get(f"/api/documents/{i}/file"); self.assertEqual((f.status_code, f.data[:5]), (200, b"%PDF-"))
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in ("pdf.min.js", "pdf.worker.min.js"):
            self.assertTrue(os.path.exists(os.path.join(root, "static", "pdfjs", name)), name + " must be bundled locally")
            self.assertEqual(self.c.get("/static/pdfjs/" + name).status_code, 200)

    def test_citation_opens_the_right_page_and_chunk(self):
        with mock.patch.object(answer_service.requests, "post", return_value=gemini_text("ok [1]")):
            j = self.ask("What are the four states of a process?", [self.doc["id"]]).json
        s = j["sources"][0]; self.assertEqual(s["page"], 25)
        ch = self.c.get(f"/api/chunks/{s['chunk_id']}").json
        self.assertEqual((ch["page"], ch["document_id"]), (25, self.doc["id"])); self.assertIn("round robin", ch["text"])
        # the PDF page itself really contains that text (1-based page 25 == PyMuPDF index 24)
        d = pymupdf.open(os.path.join(config.UPLOAD_DIR, self.doc["stored_name"]))
        self.assertIn("four states of a process", d[s["page"] - 1].get_text())


class T5_HistoryAnalytics(Base):
    def test_history_and_analytics_numbers(self):
        self.upload([("OS_Notes.pdf", make_pdf(OS_PAGES)), ("DBMS.pdf", make_pdf(DB_PAGES))]); docs = self.wait()
        ids = [d["id"] for d in docs]
        with mock.patch.object(answer_service.requests, "post", return_value=gemini_text("ok [1]")):
            a = self.ask("What are the four states of a process?", ids).json
            self.ask("What does a primary key do?", ids, a["conversation_id"])
        b = self.ask("Who won the football world cup?", ids).json
        self.c.post(f"/api/messages/{a['message_id']}/feedback", json={"value": 1})
        self.c.post(f"/api/messages/{b['message_id']}/feedback", json={"value": -1})
        self.assertEqual(self.c.post(f"/api/messages/{a['message_id']}/feedback", json={"value": 5}).status_code, 400)
        # history
        convs = self.c.get("/api/conversations").json
        self.assertEqual(len(convs), 2)
        self.assertEqual(sorted(c["questions"] for c in convs), [1, 2])
        detail = self.c.get(f"/api/conversations/{a['conversation_id']}").json
        self.assertEqual([m["role"] for m in detail["messages"]], ["user", "assistant", "user", "assistant"])
        self.assertTrue(detail["messages"][1]["sources"])
        # analytics must equal what is really stored
        an = self.c.get("/api/analytics").json
        from database import db
        self.assertEqual(an["documents"], len(docs))
        self.assertEqual(an["pages"], sum(d["pages"] for d in docs))
        self.assertEqual(an["chunks"], db.q("SELECT COUNT(*) n FROM chunks", one=True)["n"])
        self.assertEqual(an["vectors"], an["chunks"])
        self.assertEqual(an["questions"], 3)
        self.assertEqual((an["helpful"], an["not_helpful"], an["no_match"]), (1, 1, 1))
        self.assertGreaterEqual(an["avg_ms"], 0)
        dash = self.c.get("/dashboard").text
        self.assertIn(">3<", dash)       # questions asked card
        # delete + clear
        self.assertEqual(self.c.delete(f"/api/conversations/{b['conversation_id']}").status_code, 200)
        self.assertEqual(len(self.c.get("/api/conversations").json), 1)
        self.c.delete("/api/conversations"); self.assertEqual(self.c.get("/api/conversations").json, [])
        self.assertEqual(self.c.get(f"/api/conversations/{a['conversation_id']}").status_code, 404)

    def test_evaluation_endpoint(self):
        self.upload([("OS_Notes.pdf", make_pdf(OS_PAGES))]); self.wait()
        tests = [{"question": "What are the four states of a process?", "document": "OS_Notes.pdf", "page": 25},
                 {"question": "difference between a process and a thread", "document": "OS_Notes.pdf", "page": 24},
                 {"question": "Who won the 2018 football world cup final?", "answerable": False}]
        r = self.c.post("/api/analytics/evaluate", json={"tests": tests}).json
        self.assertEqual((r["recall_at_5"], r["citation_correctness"], r["no_match_accuracy"]), (1.0, 1.0, 1.0))
        self.assertIsNotNone(r["threshold"]["suggested"])
        for bad in ({}, {"tests": []}, {"tests": [{"question": ""}]}, {"tests": [{"question": "x", "document": "nope.pdf", "page": 1}]}):
            self.assertEqual(self.c.post("/api/analytics/evaluate", json=bad).status_code, 400)


class T6_Persistence(Base):
    def test_index_survives_restart_and_delete(self):
        self.upload([("OS_Notes.pdf", make_pdf(OS_PAGES)), ("DBMS.pdf", make_pdf(DB_PAGES))]); docs = self.wait()
        ids = [d["id"] for d in docs]; n = vs.total()
        before = self.ask("What are the four states of a process?", ids).json["sources"][0]
        # simulate stopping and restarting Flask: new app object, index re-read from disk
        vs._index = None
        c2 = create_app().test_client()
        self.assertEqual(vs.total(), n)
        after = c2.post("/api/chat", json={"question": "What are the four states of a process?", "document_ids": ids}).json["sources"][0]
        self.assertEqual((before["chunk_id"], before["page"]), (after["chunk_id"], after["page"]))
        # delete removes vectors from the saved index too
        dbms = [d for d in docs if d["filename"] == "DBMS.pdf"][0]
        self.assertEqual(c2.delete(f"/api/documents/{dbms['id']}").status_code, 200)
        vs._index = None
        self.assertEqual(vs.total(), n - dbms["chunk_count"])


class T7_Pages(Base):
    def test_every_page_loads(self):
        for p in ["/", "/dashboard", "/documents", "/chat", "/history", "/analytics", "/settings", "/about", "/viewer"]:
            self.assertEqual(self.c.get(p).status_code, 200, p)
        self.assertEqual(self.c.get("/nope").status_code, 404)
        self.assertEqual(self.c.post("/api/settings", json={"language": "Klingon"}).json["language"], "English")


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
