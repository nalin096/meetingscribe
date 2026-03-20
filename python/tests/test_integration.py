"""End-to-end test: manifest → pipeline → Obsidian markdown output."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from meetingscribe.watcher import process_pending_manifests


def test_end_to_end_manifest_to_markdown(tmp_path, sample_config, make_wav):
    from meetingscribe.config import load_config
    config = load_config(sample_config)

    recordings = tmp_path / "recordings"
    recordings.mkdir()
    remote = make_wav("c1_remote.wav", duration_s=10.0)
    local = make_wav("c1_local.wav", duration_s=10.0)

    import shutil
    shutil.copy(remote, recordings / "c1_remote.wav")
    shutil.copy(local, recordings / "c1_local.wav")

    manifest = {
        "meeting_id": "test-e2e-001",
        "app": "zoom.us",
        "chunks": [{
            "remote": "c1_remote.wav", "local": "c1_local.wav",
            "start_mach_time": 123, "start_iso": "2026-03-20T14:00:05-07:00"
        }],
        "started": "2026-03-20T14:00:05-07:00",
        "ended": "2026-03-20T14:10:05-07:00",
    }
    (recordings / "test-e2e-001.json").write_text(json.dumps(manifest))

    mock_transcript = [MagicMock(start=0.0, end=5.0, text="Hello everyone")]
    mock_speakers = [MagicMock(start=0.0, end=5.0, speaker="SPEAKER_00")]
    mock_aligned = [MagicMock(start=0.0, end=5.0, text="Hello everyone", speaker="Speaker 1")]

    with patch("meetingscribe.pipeline.transcribe", return_value=mock_transcript), \
         patch("meetingscribe.pipeline.diarize", return_value=mock_speakers), \
         patch("meetingscribe.pipeline.align", return_value=mock_aligned), \
         patch("meetingscribe.pipeline.summarize", return_value="## TL;DR\nTest meeting"), \
         patch("keyring.get_password", return_value="fake_token"):
        process_pending_manifests(recordings, config)

    assert list(recordings.glob("*.done"))
    vault_files = list(config.vault.path.glob("*.md"))
    assert len(vault_files) == 1
    content = vault_files[0].read_text()
    assert "zoom" in content.lower() or "Zoom" in content
    assert "TL;DR" in content
