import time
import os
from pathlib import Path
from meetingscribe.disk_manager import cleanup_processed_wavs, cleanup_orphans


def test_cleanup_processed_wavs_deletes_immediately(tmp_path):
    wav = tmp_path / "chunk_001_remote.wav"
    wav.write_bytes(b"fake")
    cleanup_processed_wavs(tmp_path, retain_days=0)
    assert not wav.exists()


def test_cleanup_processed_wavs_retains_when_configured(tmp_path):
    wav = tmp_path / "chunk_001_remote.wav"
    wav.write_bytes(b"fake")
    cleanup_processed_wavs(tmp_path, retain_days=30)
    assert wav.exists()


def test_cleanup_orphans_removes_old_chunks(tmp_path):
    wav = tmp_path / "orphan_remote.wav"
    wav.write_bytes(b"fake")
    old_time = time.time() - (10 * 86400)
    os.utime(wav, (old_time, old_time))
    cleanup_orphans(tmp_path, max_age_days=7)
    assert not wav.exists()
