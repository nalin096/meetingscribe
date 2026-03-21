from unittest.mock import patch, MagicMock
from meetingscribe.cli import main
import sys


def test_cli_setup_creates_config(tmp_path):
    config_dir = tmp_path / ".meetingscribe"
    vault_dir = tmp_path / "vault" / "Meetings"
    vault_dir.mkdir(parents=True)

    with patch("builtins.input", side_effect=[str(vault_dir), "hf_fake_token"]), \
         patch("meetingscribe.cli.MEETINGSCRIBE_DIR", config_dir), \
         patch("subprocess.run") as mock_sub:
        mock_sub.return_value = MagicMock(returncode=0)
        sys.argv = ["meetingscribe", "setup"]
        main()

    assert (config_dir / "config.toml").exists()
    assert (config_dir / "prompt.md").exists()


def test_cli_daemon_starts(tmp_path):
    sys.argv = ["meetingscribe", "daemon"]
    with patch("meetingscribe.cli.run_daemon_command") as mock_daemon:
        main()
    mock_daemon.assert_called_once()


import json
import numpy as np


def _write_note(vault, filename, meeting_id, speaker_map):
    lines = "\n".join(f'  {k}: "{v}"' for k, v in speaker_map.items())
    content = f"---\ndate: 2026-03-20\nmeeting_id: {meeting_id}\nspeaker_map:\n{lines}\n---\n# Meeting\n"
    path = vault / filename
    path.write_text(content, encoding="utf-8")
    return path


def test_learn_speakers_no_labeled_notes(tmp_path, sample_config, capsys):
    from meetingscribe.config import load_config
    vault = load_config(sample_config).vault.path
    _write_note(vault, "meeting1.md", "zoom_abc", {"Speaker 1": ""})

    with patch("meetingscribe.cli.MEETINGSCRIBE_DIR", tmp_path / ".meetingscribe"), \
         patch("meetingscribe.cli._load_config_for_cli", return_value=load_config(sample_config)):
        from meetingscribe.cli import learn_speakers_command
        learn_speakers_command()

    assert "No labeled speakers found" in capsys.readouterr().out


def test_learn_speakers_learns_from_labeled_note(tmp_path, sample_config, capsys):
    from meetingscribe.config import load_config
    from meetingscribe.pipeline import _safe_filename
    config = load_config(sample_config)
    vault = config.vault.path
    ms_dir = tmp_path / ".meetingscribe"
    embeddings_dir = ms_dir / "embeddings"
    embeddings_dir.mkdir(parents=True, exist_ok=True)

    meeting_id = "zoom_2026-03-20T10:00:00+05:30"
    safe = _safe_filename(meeting_id)
    _write_note(vault, "meeting1.md", meeting_id, {"Speaker 1": "Nalin"})

    fake_emb = np.ones(256, dtype=np.float32)
    np.savez(str(embeddings_dir / f"{safe}.npz"), SPEAKER_00=fake_emb)
    (embeddings_dir / f"{safe}.json").write_text(
        json.dumps({"Speaker 1": "SPEAKER_00"}), encoding="utf-8"
    )

    upserted = {}

    with patch("meetingscribe.cli.MEETINGSCRIBE_DIR", ms_dir), \
         patch("meetingscribe.cli._load_config_for_cli", return_value=config), \
         patch("meetingscribe.cli.upsert_speaker", side_effect=lambda n, e: upserted.update({n: e})):
        from meetingscribe.cli import learn_speakers_command
        learn_speakers_command()

    assert "Nalin" in upserted
    assert "Learned 1 speaker" in capsys.readouterr().out


def test_learn_speakers_skips_note_without_meeting_id(tmp_path, sample_config, capsys):
    from meetingscribe.config import load_config
    config = load_config(sample_config)
    vault = config.vault.path
    (vault / "no_id.md").write_text(
        '---\nspeaker_map:\n  Speaker 1: "Nalin"\n---\n', encoding="utf-8"
    )

    with patch("meetingscribe.cli.MEETINGSCRIBE_DIR", tmp_path / ".meetingscribe"), \
         patch("meetingscribe.cli._load_config_for_cli", return_value=config):
        from meetingscribe.cli import learn_speakers_command
        learn_speakers_command()

    assert "No labeled speakers found" in capsys.readouterr().out
