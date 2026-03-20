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
