from unittest.mock import patch, MagicMock
from pathlib import Path
from meetingscribe.summarizer import summarize


def test_summarize_calls_claude_cli(tmp_path):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Summarize this meeting.")
    transcript = "[00:00] Speaker 1: Hello\n[00:05] Speaker 2: Hi there"
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "## TL;DR\nA short meeting.\n\n## Summary\n- Greetings exchanged"
    with patch("meetingscribe.summarizer.subprocess.run", return_value=mock_result) as mock_run:
        result = summarize(transcript, prompt_file=prompt_file, cli="claude", model_flag="--model sonnet")
    assert "TL;DR" in result
    call_args = mock_run.call_args[0][0]
    assert "claude" in call_args
    assert "-p" in call_args


def test_summarize_returns_empty_on_failure(tmp_path):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Summarize this meeting.")
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "rate limited"
    with patch("meetingscribe.summarizer.subprocess.run", return_value=mock_result):
        result = summarize("transcript", prompt_file=prompt_file, cli="claude", model_flag="--model sonnet")
    assert result == ""


def test_summarize_chunks_long_transcript(tmp_path):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Summarize this meeting.")
    transcript = ("[00:00] Speaker 1: word " * 15000).strip()
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "## TL;DR\nLong meeting summary"
    with patch("meetingscribe.summarizer.subprocess.run", return_value=mock_result) as mock_run:
        result = summarize(transcript, prompt_file=prompt_file, cli="claude", model_flag="--model sonnet")
    assert mock_run.call_count > 1
