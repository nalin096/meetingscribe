import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from meetingscribe.watcher import process_pending_manifests


def test_process_pending_skips_non_json(tmp_path):
    (tmp_path / "meeting.processing").write_text("{}")
    (tmp_path / "meeting.done").write_text("{}")
    (tmp_path / "meeting.failed").write_text("{}")
    with patch("meetingscribe.watcher.process_single_manifest") as mock_proc:
        process_pending_manifests(tmp_path, MagicMock())
    mock_proc.assert_not_called()


def test_process_pending_picks_up_json(tmp_path):
    data = {
        "meeting_id": "test-123", "app": "zoom.us",
        "chunks": [], "started": "2026-03-20T14:00:00-07:00",
        "ended": "2026-03-20T14:30:00-07:00"
    }
    (tmp_path / "meeting.json").write_text(json.dumps(data))
    with patch("meetingscribe.watcher.process_single_manifest") as mock_proc:
        process_pending_manifests(tmp_path, MagicMock())
    mock_proc.assert_called_once()


def test_recover_stale_on_startup(tmp_path):
    (tmp_path / "stale.processing").write_text("{}")
    from meetingscribe.manifest import recover_stale
    recovered = recover_stale(tmp_path)
    assert len(recovered) == 1
    assert recovered[0].suffix == ".json"
