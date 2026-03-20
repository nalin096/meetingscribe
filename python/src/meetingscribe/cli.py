"""CLI entry point for MeetingScribe."""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

MEETINGSCRIBE_DIR = Path("~/.meetingscribe").expanduser()


def setup_command() -> None:
    """Interactive first-run setup wizard."""
    print("MeetingScribe Setup")
    print("=" * 40)

    MEETINGSCRIBE_DIR.mkdir(exist_ok=True)
    (MEETINGSCRIBE_DIR / "recordings").mkdir(exist_ok=True)
    (MEETINGSCRIBE_DIR / "logs").mkdir(exist_ok=True)

    vault_path = input("Obsidian vault meetings folder path: ").strip()
    vault_path = Path(vault_path).expanduser()
    if not vault_path.is_dir():
        print(f"Error: {vault_path} does not exist. Create it first.")
        sys.exit(1)

    hf_token = input("HuggingFace token (for pyannote-audio): ").strip()
    if hf_token:
        subprocess.run([
            "security", "add-generic-password",
            "-s", "meetingscribe", "-a", "hf_token",
            "-w", hf_token, "-U",
        ], check=False)

    config_content = _default_config(vault_path)
    (MEETINGSCRIBE_DIR / "config.toml").write_text(config_content)

    (MEETINGSCRIBE_DIR / "prompt.md").write_text(
        "Given this meeting transcript with speaker labels, produce:\n"
        "1. **TL;DR** — one sentence\n"
        "2. **Summary** — 3-5 bullet points\n"
        "3. **Action Items** — checklist with @owner and deadline\n"
        "4. **Key Decisions** — bulleted list\n"
        "5. **Topics** — as [[wikilinks]]\n"
    )

    print(f"\nConfig written to {MEETINGSCRIBE_DIR / 'config.toml'}")
    print(f"Prompt template at {MEETINGSCRIBE_DIR / 'prompt.md'}")
    print("\nSetup complete! Run 'meetingscribe daemon' to start.")


def _default_config(vault_path: Path) -> str:
    return f"""[vault]
path = "{vault_path}"
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
prompt_file = "{str(MEETINGSCRIBE_DIR / 'prompt.md')}"

[retry]
max_retries = 3
backoff_minutes = [1, 5, 30]
summary_retry_interval_minutes = 15

[storage]
retain_wav_days = 0
orphan_cleanup_days = 7

[logging]
level = "INFO"
"""


def install_command() -> None:
    """Install LaunchAgent plist and load it."""
    import shutil
    from importlib.resources import files

    launch_agents_dir = Path("~/Library/LaunchAgents").expanduser()
    launch_agents_dir.mkdir(parents=True, exist_ok=True)

    plist_src = Path(__file__).parent.parent.parent / "resources" / "com.meetingscribe.daemon.plist"
    if not plist_src.exists():
        # Try importlib resources fallback
        try:
            pkg_resources = files("meetingscribe")
            plist_data = (pkg_resources / "resources" / "com.meetingscribe.daemon.plist").read_text()
            plist_dest = launch_agents_dir / "com.meetingscribe.daemon.plist"
            plist_dest.write_text(plist_data)
        except Exception:
            print("Error: plist resource not found.")
            sys.exit(1)
    else:
        plist_dest = launch_agents_dir / "com.meetingscribe.daemon.plist"
        shutil.copy(plist_src, plist_dest)

    result = subprocess.run(
        ["launchctl", "load", str(plist_dest)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"launchctl load failed: {result.stderr.strip()}")
        sys.exit(1)

    print(f"LaunchAgent installed: {plist_dest}")
    print("MeetingScribe daemon will run at login and is now active.")


def run_daemon_command() -> None:
    """Start the watcher daemon."""
    from meetingscribe.config import load_config
    from meetingscribe.watcher import run_daemon

    config_path = MEETINGSCRIBE_DIR / "config.toml"
    if not config_path.exists():
        print("No config found. Run 'meetingscribe setup' first.")
        sys.exit(1)

    config = load_config(config_path)

    log_path = MEETINGSCRIBE_DIR / "logs" / "meetingscribe.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    from logging.handlers import RotatingFileHandler
    handler = RotatingFileHandler(log_path, maxBytes=5_000_000, backupCount=3)
    logging.basicConfig(
        level=getattr(logging, config.logging.level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[handler, logging.StreamHandler()],
    )

    run_daemon(config)


def main() -> None:
    parser = argparse.ArgumentParser(prog="meetingscribe")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("setup", help="Run first-time setup wizard")
    sub.add_parser("daemon", help="Start the processing daemon")
    sub.add_parser("install", help="Install LaunchAgent and start daemon at login")
    sub.add_parser("label-speaker", help="Label speakers in meeting notes (v2)")
    args = parser.parse_args()

    if args.command == "setup":
        setup_command()
    elif args.command == "daemon":
        run_daemon_command()
    elif args.command == "install":
        install_command()
    elif args.command == "label-speaker":
        print("Speaker labeling will be available in v2.")
    else:
        parser.print_help()
