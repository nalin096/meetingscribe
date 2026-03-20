import json
from pathlib import Path
from meetingscribe.manifest import (
    Manifest,
    ManifestState,
    load_manifest,
    claim_manifest,
    complete_manifest,
    fail_manifest,
    recover_stale,
)


def test_load_manifest_from_json(tmp_path):
    data = {
        "meeting_id": "2026-03-20T14:00:05-07:00-a3f2",
        "app": "zoom.us",
        "chunks": [
            {"remote": "c1_remote.wav", "local": "c1_local.wav",
             "start_mach_time": 123, "start_iso": "2026-03-20T14:00:05-07:00"}
        ],
        "started": "2026-03-20T14:00:05-07:00",
        "ended": "2026-03-20T14:47:12-07:00",
    }
    p = tmp_path / "meeting.json"
    p.write_text(json.dumps(data))
    m = load_manifest(p)
    assert m.meeting_id == "2026-03-20T14:00:05-07:00-a3f2"
    assert m.app == "zoom.us"
    assert len(m.chunks) == 1


def test_claim_manifest_renames_to_processing(tmp_path):
    p = tmp_path / "meeting.json"
    p.write_text("{}")
    new_path = claim_manifest(p)
    assert new_path.suffix == ".processing"
    assert not p.exists()
    assert new_path.exists()


def test_complete_manifest_renames_to_done(tmp_path):
    p = tmp_path / "meeting.processing"
    p.write_text("{}")
    new_path = complete_manifest(p)
    assert new_path.suffix == ".done"


def test_fail_manifest_increments_retry(tmp_path):
    p = tmp_path / "meeting.processing"
    p.write_text("{}")
    # First two failures → back to .json
    result = fail_manifest(p, "some error", retry_count=0, max_retries=3)
    assert result.suffix == ".json"
    # Third failure → .failed
    p2 = tmp_path / "meeting.processing"
    p2.write_text("{}")
    result = fail_manifest(p2, "some error", retry_count=2, max_retries=3)
    assert result.suffix == ".failed"
    assert (tmp_path / "meeting.failed.error").exists()


def test_recover_stale_processing(tmp_path):
    p = tmp_path / "meeting.processing"
    p.write_text("{}")
    recovered = recover_stale(tmp_path)
    assert len(recovered) == 1
    assert recovered[0].suffix == ".json"
