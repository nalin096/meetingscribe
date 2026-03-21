import json
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import patch


def make_embedding(value: float, dim: int = 8) -> np.ndarray:
    v = np.full(dim, value, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_load_db_returns_empty_when_file_missing(tmp_path):
    with patch("meetingscribe.speakers.DB_PATH", tmp_path / "speakers.npz"):
        from meetingscribe.speakers import load_db
        names, embeddings = load_db()
    assert names == {}
    assert embeddings == {}


def test_save_and_load_roundtrip(tmp_path):
    with patch("meetingscribe.speakers.DB_PATH", tmp_path / "speakers.npz"):
        from meetingscribe.speakers import save_db, load_db
        emb = make_embedding(1.0)
        save_db({"nalin": "Nalin"}, {"nalin": emb})
        names, embeddings = load_db()
    assert names == {"nalin": "Nalin"}
    assert "nalin" in embeddings
    np.testing.assert_array_almost_equal(embeddings["nalin"], emb)


def test_match_speaker_returns_name_above_threshold(tmp_path):
    with patch("meetingscribe.speakers.DB_PATH", tmp_path / "speakers.npz"):
        from meetingscribe.speakers import save_db, match_speaker
        emb = make_embedding(1.0)
        save_db({"nalin": "Nalin"}, {"nalin": emb})
        result = match_speaker(emb, threshold=0.75)
    assert result == "Nalin"


def test_match_speaker_returns_none_below_threshold(tmp_path):
    with patch("meetingscribe.speakers.DB_PATH", tmp_path / "speakers.npz"):
        from meetingscribe.speakers import save_db, match_speaker
        stored = make_embedding(1.0)
        query = make_embedding(-1.0)  # opposite direction → similarity ≈ -1.0
        save_db({"nalin": "Nalin"}, {"nalin": stored})
        result = match_speaker(query, threshold=0.75)
    assert result is None


def test_match_speaker_returns_none_when_db_empty(tmp_path):
    with patch("meetingscribe.speakers.DB_PATH", tmp_path / "speakers.npz"):
        from meetingscribe.speakers import match_speaker
        result = match_speaker(make_embedding(1.0), threshold=0.75)
    assert result is None


def test_upsert_speaker_adds_new_entry(tmp_path):
    with patch("meetingscribe.speakers.DB_PATH", tmp_path / "speakers.npz"):
        from meetingscribe.speakers import upsert_speaker, load_db
        emb = make_embedding(1.0)
        upsert_speaker("Nalin Bhan", emb)
        names, embeddings = load_db()
    assert names.get("nalin_bhan") == "Nalin Bhan"
    assert "nalin_bhan" in embeddings


def test_upsert_speaker_overwrites_existing(tmp_path):
    with patch("meetingscribe.speakers.DB_PATH", tmp_path / "speakers.npz"):
        from meetingscribe.speakers import upsert_speaker, load_db
        emb1 = make_embedding(1.0)
        emb2 = make_embedding(0.5)
        upsert_speaker("Nalin", emb1)
        upsert_speaker("Nalin", emb2)
        _, embeddings = load_db()
    np.testing.assert_array_almost_equal(embeddings["nalin"], emb2)


def test_save_db_writes_single_file(tmp_path):
    db = tmp_path / "speakers.npz"
    with patch("meetingscribe.speakers.DB_PATH", db):
        from meetingscribe.speakers import save_db
        save_db({"k": "Name"}, {"k": make_embedding(1.0)})
    assert db.exists()
    # Only one file — no separate .json
    assert not (tmp_path / "speakers.json").exists()
