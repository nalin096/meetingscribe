from pathlib import Path
from meetingscribe.aligner import AlignedSegment
from meetingscribe.markdown_writer import write_meeting_note, MeetingMetadata


def test_write_meeting_note_creates_file(tmp_path):
    meta = MeetingMetadata(
        date="2026-03-20", time="14:00 - 14:47", timezone="America/Los_Angeles",
        duration_min=47, app="Zoom", speakers=2,
        speaker_map={"Speaker 1": "", "Speaker 2": ""},
    )
    segments = [
        AlignedSegment(start=0.0, end=2.0, text="Hello everyone", speaker="Speaker 1"),
        AlignedSegment(start=2.5, end=5.0, text="Hi there", speaker="Speaker 2"),
    ]
    summary = "## TL;DR\nShort meeting.\n\n## Summary\n- Greetings exchanged"
    out = tmp_path / "2026-03-20-1400.md"
    write_meeting_note(out, meta, segments, summary)
    content = out.read_text()
    assert "---" in content
    assert "date: 2026-03-20" in content
    assert "duration_min: 47" in content
    assert "Speaker 1:" in content
    assert "## Transcript" in content
    assert "**[00:00] Speaker 1:**" in content


def test_write_meeting_note_no_summary(tmp_path):
    meta = MeetingMetadata(
        date="2026-03-20", time="14:00 - 14:30", timezone="UTC",
        duration_min=30, app="Zoom", speakers=1,
        speaker_map={"Speaker 1": ""},
    )
    segments = [AlignedSegment(start=0.0, end=1.0, text="Test", speaker="Speaker 1")]
    out = tmp_path / "meeting.md"
    write_meeting_note(out, meta, segments, summary="")
    content = out.read_text()
    assert "status: needs-summary" in content
    assert "## Transcript" in content


def test_write_meeting_note_no_speech(tmp_path):
    meta = MeetingMetadata(
        date="2026-03-20", time="14:00 - 14:05", timezone="UTC",
        duration_min=5, app="Zoom", speakers=0, speaker_map={},
    )
    out = tmp_path / "meeting.md"
    write_meeting_note(out, meta, segments=[], summary="")
    content = out.read_text()
    assert "status: no-speech" in content
