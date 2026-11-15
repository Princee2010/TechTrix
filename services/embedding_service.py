import re
import zlib
import numpy as np
import config

DIM = 384
_model = None
_backend = None

_STOP = set("""a an the and or but if of to in on at by for with from as is are was were be been being it its this that
these those i you he she we they what which who whom how when where why do does did can could should would will
about into than then so not no yes your our their his her them there here also may might must shall""".split())


def _load():
    global _model, _backend
    if _backend:
        return
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(config.EMBED_MODEL)
        _backend = "sentence-transformers"
    except Exception as e:  # offline / not installed -> keyword-hash fallback so the app still runs
        print(f"[embedding] sentence-transformers unavailable ({e.__class__.__name__}); using hashing fallback")
        _backend = "hashing-fallback"


def warmup():
    _load()


def backend():
    _load()
    return _backend


def min_score():
    return config.MIN_SCORE if backend() == "sentence-transformers" else config.FALLBACK_MIN_SCORE


def _hash_embed(texts):
    out = np.zeros((len(texts), DIM), dtype="float32")
    for i, t in enumerate(texts):
        words = [w for w in re.findall(r"[a-z0-9\u0900-\u097f]+", t.lower()) if len(w) > 2 and w not in _STOP]
        grams = words + [a + "_" + b for a, b in zip(words, words[1:])]
        for g in grams:
            h = zlib.crc32(g.encode())
            out[i, h % DIM] += 1.0 if "_" not in g else 0.7
        n = np.linalg.norm(out[i])
        if n:
            out[i] /= n
    return out


def embed(texts):
    """Return L2-normalised float32 vectors, shape (n, 384)."""
    _load()
    if _backend == "sentence-transformers":
        return _model.encode(list(texts), normalize_embeddings=True, batch_size=32,
                             show_progress_bar=False).astype("float32")
    return _hash_embed(texts)
