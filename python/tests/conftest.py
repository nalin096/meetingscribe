import os
import tempfile
from pathlib import Path
import pytest


@pytest.fixture
def tmp_home(tmp_path):
    """Temporary home directory with .meetingscribe/ structure."""
    ms_dir = tmp_path / ".meetingscribe"
    ms_dir.mkdir()
    (ms_dir / "recordings").mkdir()
    (ms_dir / "logs").mkdir()
    return tmp_path


@pytest.fixture
def sample_config(tmp_home):
    """Write a minimal valid config.toml and return its path."""
    vault_dir = tmp_home / "vault" / "Meetings"
    vault_dir.mkdir(parents=True)
    config_path = tmp_home / ".meetingscribe" / "config.toml"
    config_path.write_text(f"""
[vault]
path = "{vault_dir}"
timezone = "America/Los_Angeles"

[detection]
apps = ["zoom.us", "com.google.Chrome", "com.tinyspeck.slackmacgap"]
chrome_window_match = "Meet -|meet.google.com"
slack_min_duration_seconds = 30
poll_interval_seconds = 3

[audio]
sample_rate = 16000
channels = 1
bit_depth = 16
chunk_duration_seconds = 300
chunk_overlap_seconds = 1

[transcription]
model = "large-v3"

[diarization]
keychain_service = "meetingscribe"
keychain_account = "hf_token"

[summary]
cli = "claude"
model_flag = "--model sonnet"
prompt_file = "{tmp_home / '.meetingscribe' / 'prompt.md'}"

[retry]
max_retries = 3
backoff_minutes = [1, 5, 30]
summary_retry_interval_minutes = 15

[storage]
retain_wav_days = 0
orphan_cleanup_days = 7

[logging]
level = "INFO"
""")
    # Also create the prompt file
    (tmp_home / ".meetingscribe" / "prompt.md").write_text("Summarize this meeting.")
    return config_path
