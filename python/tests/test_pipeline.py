import json
import numpy as np
from unittest.mock import patch, MagicMock
from pathlib import Path
from meetingscribe.pipeline import process_meeting, _safe_filename
from meetingscribe.manifest import Manifest, ChunkInfo


def _make_manifest(meeting_id="zoom_2026-03-20T14:00:05+05:30"):
    return Manifest(
        meeting_id=meeting_id,
        app="zoom.us",
        chunks=[ChunkInfo(
            remote="c1_remote.wav", local="c1_local.wav",
            start_mach_time=123, start_iso="2026-03-20T14:00:05+05:30",
        )],
        started="2026-03-20T14:00:05+05:30",
        ended="2026-03-20T14:47:12+05:30",
    )


def test_safe_filename_strips_colons():
    assert ":" not in _safe_filename("zoom_2026-03-20T14:00:05+05:30")


def test_safe_filename_is_stable():
    """Same meeting_id always produces same safe filename."""
    mid = "zoom_2026-03-20T14:00:05+05:30"
    assert _safe_filename(mid) == _safe_filename(mid)


def test_process_meeting_full_pipeline(tmp_path, sample_config):
    from meetingscribe.config import load_config
    config = load_config(sample_config)
    manifest = _make_manifest()
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir(exist_ok=True)

    mock_segments = [MagicMock(start=0.0, end=2.0, text="Hello")]
    mock_speakers = [MagicMock(start=0.0, end=2.0, speaker="SPEAKER_00")]
    mock_aligned = [MagicMock(start=0.0, end=2.0, text="Hello", speaker="Speaker 1")]

    with patch("meetingscribe.pipeline.merge_chunk_pair"), \
         patch("meetingscribe.pipeline.concatenate_chunks"), \
         patch("meetingscribe.pipeline.transcribe", return_value=mock_segments), \
         patch("meetingscribe.pipeline.diarize", return_value=(mock_speakers, {})), \
         patch("meetingscribe.pipeline.align", return_value=(mock_aligned, {})), \
         patch("meetingscribe.pipeline.group_segments", return_value=mock_aligned), \
         patch("meetingscribe.pipeline.summarize", return_value="## TL;DR\nTest"), \
         patch("meetingscribe.pipeline.write_meeting_note") as mock_write, \
         patch("meetingscribe.pipeline._warmup_models"), \
         patch("keyring.get_password", return_value="fake_token"):
        process_meeting(manifest, recordings_dir, config)
        mock_write.assert_called_once()


def test_process_meeting_no_speech(tmp_path, sample_config):
    from meetingscribe.config import load_config
    config = load_config(sample_config)
    manifest = Manifest(
        meeting_id="zoom_2026-03-20T14:00:05+05:30",
        app="zoom.us", chunks=[], started="2026-03-20T14:00:05+05:30",
        ended="2026-03-20T14:05:00+05:30",
    )
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir(exist_ok=True)

    with patch("meetingscribe.pipeline.transcribe", return_value=[]), \
         patch("meetingscribe.pipeline.merge_chunk_pair"), \
         patch("meetingscribe.pipeline.concatenate_chunks"), \
         patch("meetingscribe.pipeline.write_meeting_note") as mock_write, \
         patch("meetingscribe.pipeline._warmup_models"), \
         patch("keyring.get_password", return_value="fake_token"):
        process_meeting(manifest, recordings_dir, config)
        mock_write.assert_called_once()


def test_process_meeting_writes_meeting_id_to_note(tmp_path, sample_config):
    from meetingscribe.config import load_config
    config = load_config(sample_config)
    manifest = _make_manifest(meeting_id="zoom_test_id_2026-03-20T10:00:00+05:30")
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir(exist_ok=True)

    mock_aligned = [MagicMock(start=0.0, end=2.0, text="Hello", speaker="Speaker 1")]

    with patch("meetingscribe.pipeline.merge_chunk_pair"), \
         patch("meetingscribe.pipeline.concatenate_chunks"), \
         patch("meetingscribe.pipeline.transcribe", return_value=[MagicMock(start=0.0, end=2.0, text="Hello")]), \
         patch("meetingscribe.pipeline.diarize", return_value=([], {})), \
         patch("meetingscribe.pipeline.align", return_value=(mock_aligned, {})), \
         patch("meetingscribe.pipeline.group_segments", return_value=mock_aligned), \
         patch("meetingscribe.pipeline.summarize", return_value="## TL;DR\nTest"), \
         patch("meetingscribe.pipeline.write_meeting_note") as mock_write, \
         patch("meetingscribe.pipeline._warmup_models"), \
         patch("keyring.get_password", return_value="fake_token"):
        process_meeting(manifest, recordings_dir, config)
    meta = mock_write.call_args[0][1]
    assert meta.meeting_id == "zoom_test_id_2026-03-20T10:00:00+05:30"


def test_process_meeting_writes_sidecar_json(tmp_path, sample_config):
    """Side-car JSON written with safe filename when raw_to_friendly is non-empty."""
    from meetingscribe.config import load_config
    config = load_config(sample_config)
    meeting_id = "zoom_2026-03-20T10:00:00+05:30"
    manifest = _make_manifest(meeting_id=meeting_id)
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir(exist_ok=True)
    embeddings_dir = tmp_path / "embeddings"
    embeddings_dir.mkdir(parents=True, exist_ok=True)

    mock_aligned = [MagicMock(start=0.0, end=2.0, text="Hello", speaker="Speaker 1")]
    raw_to_friendly = {"SPEAKER_00": "Speaker 1"}

    with patch("meetingscribe.pipeline.merge_chunk_pair"), \
         patch("meetingscribe.pipeline.concatenate_chunks"), \
         patch("meetingscribe.pipeline.transcribe", return_value=[MagicMock(start=0.0, end=2.0, text="Hello")]), \
         patch("meetingscribe.pipeline.diarize", return_value=([], {})), \
         patch("meetingscribe.pipeline.align", return_value=(mock_aligned, raw_to_friendly)), \
         patch("meetingscribe.pipeline.group_segments", return_value=mock_aligned), \
         patch("meetingscribe.pipeline.summarize", return_value=""), \
         patch("meetingscribe.pipeline.write_meeting_note"), \
         patch("meetingscribe.pipeline._warmup_models"), \
         patch("meetingscribe.pipeline.EMBEDDINGS_DIR", embeddings_dir), \
         patch("keyring.get_password", return_value="fake_token"):
        process_meeting(manifest, recordings_dir, config)

    safe = _safe_filename(meeting_id)
    sidecar = embeddings_dir / f"{safe}.json"
    assert sidecar.exists(), f"Expected {sidecar}"
    data = json.loads(sidecar.read_text())
    assert data == {"Speaker 1": "SPEAKER_00"}
