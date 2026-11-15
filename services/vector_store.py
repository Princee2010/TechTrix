import os
import threading
import numpy as np
import faiss
import config

_PATH = os.path.join(config.INDEX_DIR, "index.faiss")
_lock = threading.Lock()
_index = None


def _get(dim):
    global _index
    if _index is None:
        if os.path.exists(_PATH):
            _index = faiss.read_index(_PATH)
        else:
            _index = faiss.IndexIDMap2(faiss.IndexFlatIP(dim))  # cosine via normalised inner product
    return _index


def _save():
    os.makedirs(config.INDEX_DIR, exist_ok=True)
    faiss.write_index(_index, _PATH)


def add(ids, vectors):
    with _lock:
        idx = _get(vectors.shape[1])
        idx.add_with_ids(np.ascontiguousarray(vectors, dtype="float32"), np.array(ids, dtype="int64"))
        _save()


def remove(ids):
    if not ids:
        return
    with _lock:
        if _index is None and not os.path.exists(_PATH):
            return
        idx = _get(384)
        idx.remove_ids(np.array(ids, dtype="int64"))
        _save()


def search(vector, k):
    """Return (scores, ids) for the k nearest chunks across the whole library."""
    with _lock:
        if _index is None and not os.path.exists(_PATH):
            return [], []
        idx = _get(vector.shape[-1])
        if idx.ntotal == 0:
            return [], []
        scores, ids = idx.search(np.ascontiguousarray(vector.reshape(1, -1), dtype="float32"), min(k, idx.ntotal))
    return scores[0].tolist(), ids[0].tolist()


def total():
    with _lock:
        if _index is None and not os.path.exists(_PATH):
            return 0
        return _get(384).ntotal
