"""Tests for resummarize_pending: finds vault notes needing re-summarization."""

from pathlib import Path
from meetingscribe.watcher import resummarize_pending


def test_resummarize_finds_needs_summary_notes(tmp_path):
    note = tmp_path / "2026-03-20-meeting.md"
    note.write_text("---\nstatus: needs-summary\n---\n\n## Transcript\nHello\n")
    result = resummarize_pending(tmp_path)
    assert note in result


def test_resummarize_skips_completed_notes(tmp_path):
    note = tmp_path / "2026-03-20-done.md"
    note.write_text("---\nstatus: complete\n---\n\n## Summary\nDone.\n")
    result = resummarize_pending(tmp_path)
    assert note not in result


def test_resummarize_returns_empty_when_none_pending(tmp_path):
    result = resummarize_pending(tmp_path)
    assert result == []
