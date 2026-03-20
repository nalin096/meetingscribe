from unittest.mock import patch, MagicMock
from pathlib import Path
from meetingscribe.pipeline import process_meeting
from meetingscribe.manifest import Manifest, ChunkInfo


def test_process_meeting_full_pipeline(tmp_path, sample_config):
    from meetingscribe.config import load_config
    config = load_config(sample_config)

    manifest = Manifest(
        meeting_id="2026-03-20T14:00:05-07:00-a3f2",
        app="zoom.us",
        chunks=[ChunkInfo(
            remote="c1_remote.wav", local="c1_local.wav",
            start_mach_time=123, start_iso="2026-03-20T14:00:05-07:00",
        )],
        started="2026-03-20T14:00:05-07:00",
        ended="2026-03-20T14:47:12-07:00",
    )
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir(exist_ok=True)

    mock_segments = [MagicMock(start=0.0, end=2.0, text="Hello")]
    mock_speakers = [MagicMock(start=0.0, end=2.0, speaker="SPEAKER_00")]

    with patch("meetingscribe.pipeline.merge_chunk_pair") as mock_merge, \
         patch("meetingscribe.pipeline.concatenate_chunks"), \
         patch("meetingscribe.pipeline.transcribe", return_value=mock_segments), \
         patch("meetingscribe.pipeline.diarize", return_value=mock_speakers), \
         patch("meetingscribe.pipeline.align") as mock_align, \
         patch("meetingscribe.pipeline.summarize", return_value="## TL;DR\nTest"), \
         patch("meetingscribe.pipeline.write_meeting_note") as mock_write, \
         patch("keyring.get_password", return_value="fake_token"):

        mock_align.return_value = [MagicMock(start=0.0, end=2.0, text="Hello", speaker="Speaker 1")]
        process_meeting(manifest, recordings_dir, config)
        mock_write.assert_called_once()


def test_process_meeting_no_speech(tmp_path, sample_config):
    from meetingscribe.config import load_config
    config = load_config(sample_config)

    manifest = Manifest(
        meeting_id="2026-03-20T14:00:05-07:00-a3f2",
        app="zoom.us", chunks=[], started="2026-03-20T14:00:05-07:00",
        ended="2026-03-20T14:05:00-07:00",
    )
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir(exist_ok=True)

    with patch("meetingscribe.pipeline.transcribe", return_value=[]), \
         patch("meetingscribe.pipeline.merge_chunk_pair"), \
         patch("meetingscribe.pipeline.concatenate_chunks"), \
         patch("meetingscribe.pipeline.write_meeting_note") as mock_write, \
         patch("keyring.get_password", return_value="fake_token"):
        process_meeting(manifest, recordings_dir, config)
        mock_write.assert_called_once()
