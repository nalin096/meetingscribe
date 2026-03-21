"""Speaker identity DB: load, save, match, upsert voice embeddings.

Storage: single ~/.meetingscribe/speakers.npz file.
  - Embedding keys: sanitized speaker names (e.g. "nalin_bhan")
  - Canonical names: stored under special key "_names_json_" as a JSON string
Single os.replace() write = atomic.
"""

import json
import os
import re
import tempfile
from pathlib import Path

import numpy as np

DB_PATH = Path("~/.meetingscribe/speakers.npz").expanduser()

_NAMES_KEY = "_names_json_"


def _sanitize_key(name: str) -> str:
    """Lowercase, spaces→underscore, strip non-alphanumeric."""
    key = name.lower().strip()
    key = re.sub(r"\s+", "_", key)
    key = re.sub(r"[^a-z0-9_]", "", key)
    return key or "unknown"


def load_db() -> tuple[dict[str, str], dict[str, np.ndarray]]:
    """Load speaker DB from single .npz file.
    Returns (canonical_names, embeddings_by_key). Returns ({}, {}) on error.
    """
    try:
        if not DB_PATH.exists():
            return {}, {}
        data = np.load(str(DB_PATH), allow_pickle=False)
        canonical_names: dict[str, str] = {}
        if _NAMES_KEY in data.files:
            canonical_names = json.loads(str(data[_NAMES_KEY]))
        embeddings = {k: data[k] for k in data.files if k != _NAMES_KEY}
        return canonical_names, embeddings
    except Exception:
        return {}, {}


def save_db(canonical_names: dict[str, str], embeddings: dict[str, np.ndarray]) -> None:
    """Atomically write speaker DB. Single os.replace() prevents desync."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DB_PATH.parent / f"{DB_PATH.stem}.tmp.npz"
    names_json = json.dumps(canonical_names)
    np.savez(str(tmp), **{_NAMES_KEY: np.array(names_json)}, **embeddings)
    os.replace(str(tmp), str(DB_PATH))


def match_speaker(
    embedding: np.ndarray,
    threshold: float,
    canonical_names: dict[str, str] | None = None,
    embeddings: dict[str, np.ndarray] | None = None,
) -> str | None:
    """Cosine similarity match. Returns canonical name above threshold or None."""
    if canonical_names is None or embeddings is None:
        canonical_names, embeddings = load_db()
    if not embeddings:
        return None
    norm_emb = embedding / (np.linalg.norm(embedding) + 1e-10)
    best_key = None
    best_sim = -2.0
    for key, stored in embeddings.items():
        norm_stored = stored / (np.linalg.norm(stored) + 1e-10)
        sim = float(np.dot(norm_emb, norm_stored))
        if sim > best_sim:
            best_sim = sim
            best_key = key
    if best_sim >= threshold and best_key is not None:
        return canonical_names.get(best_key)
    return None


def upsert_speaker(name: str, embedding: np.ndarray) -> None:
    """Add or update speaker. Most recent write wins on key conflict."""
    canonical_names, embeddings = load_db()
    key = _sanitize_key(name)
    canonical_names[key] = name
    embeddings[key] = embedding
    save_db(canonical_names, embeddings)
