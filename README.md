# MeetingScribe

Auto-detects Zoom, Google Meet, and Slack Huddle meetings, records system audio, transcribes with speaker labels, and writes a summarized Markdown note to your Obsidian vault.

## Architecture

- **Swift app** (`swift/MeetingScribe/`) — menu bar daemon that detects meetings and records system audio into chunked WAV files
- **Python daemon** (`python/`) — watches for new WAV files, runs Whisper transcription + pyannote diarization in parallel, calls Claude CLI for summarization, writes Obsidian notes

## Prerequisites

| Requirement | Notes |
|---|---|
| macOS 14 (Sonoma) or later | Swift app requires macOS 14+ |
| Xcode Command Line Tools | `xcode-select --install` |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Python package manager |
| HuggingFace account | Free account at huggingface.co |
| pyannote model access | Accept terms for `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0` on HuggingFace |
| [Claude CLI](https://claude.ai/download) | `claude` must be in PATH; used for summarization |

## 1. Build and install the Swift recorder app

```bash
cd swift/MeetingScribe
./scripts/build-app.sh
cp -r build/MeetingScribe.app ~/Applications/
open ~/Applications/MeetingScribe.app
```

On first launch macOS will prompt for **Microphone** and **Screen Recording** permissions — grant both. The app appears in the menu bar.

## 2. Install the Python daemon

```bash
cd python
uv sync
```

This creates a `.venv` and installs all dependencies (faster-whisper, pyannote-audio, watchdog, etc.).

## 3. Run first-time setup

```bash
cd python
uv run meetingscribe setup
```

The wizard asks for:
1. **Obsidian vault meetings folder** — absolute path to the folder where notes should be written (must exist)
2. **HuggingFace token** — stored securely in macOS Keychain (used by pyannote for speaker diarization)

This writes `~/.meetingscribe/config.toml` and a default `~/.meetingscribe/prompt.md` summarization template.

## 4. Grant macOS permissions

Open **System Settings → Privacy & Security** and enable:

| Permission | Required by |
|---|---|
| **Microphone** | Swift recorder app |
| **Screen Recording** | Swift app (detects meeting windows) |
| **Accessibility** | Swift app (reads window titles for Slack/Zoom/Meet detection) |

## 5. Start the Python daemon

**Manually (foreground, for testing):**

```bash
cd python
uv run meetingscribe daemon
```

Logs go to `~/.meetingscribe/logs/meetingscribe.log`.

**As a LaunchAgent (starts at login, runs in background):**

```bash
cd python
uv run meetingscribe install
```

This installs `~/Library/LaunchAgents/com.meetingscribe.daemon.plist` and loads it immediately. The daemon will restart automatically on login.

To stop: `launchctl unload ~/Library/LaunchAgents/com.meetingscribe.daemon.plist`

## 6. Verify end-to-end

1. Join a Zoom, Google Meet, or Slack Huddle call (≥30 seconds for Slack)
2. The menu bar app detects the meeting and records audio
3. After the meeting ends, the Python daemon transcribes and diarizes the audio, calls `claude` for a summary, and writes a Markdown note to your vault

## Optional: learn-speakers (voice recognition)

MeetingScribe can learn to recognize recurring speakers by name. After a meeting note is created in your vault, add a `speaker_map` to the note's frontmatter:

```yaml
---
meeting_id: "2026-03-22T14-00-00-standup"
speaker_map:
  SPEAKER_00: Alice
  SPEAKER_01: Bob
---
```

Then run (while the daemon is **not** running):

```bash
cd python
uv run meetingscribe learn-speakers
```

This reads speaker embeddings saved alongside each meeting and associates them with real names. Future meetings will automatically label these speakers by name instead of `SPEAKER_NN`.

## Configuration

Edit `~/.meetingscribe/config.toml` to customize:

- `[vault]` — output path and timezone
- `[transcription]` — Whisper model (default: `large-v3`)
- `[diarization]` — speaker similarity threshold
- `[summary]` — Claude model flag and prompt file path
- `[detection]` — meeting apps and Slack minimum duration
- `[storage]` — how long to retain raw WAV files

## Troubleshooting

- **No notes appearing** — check `~/.meetingscribe/logs/meetingscribe.log`
- **LaunchAgent stdout/stderr** — `/tmp/meetingscribe-stdout.log` and `/tmp/meetingscribe-stderr.log`
- **pyannote auth error** — re-run `meetingscribe setup` to re-enter your HuggingFace token; verify model access was accepted on huggingface.co
- **`claude` not found** — ensure Claude CLI is installed and `claude` is on your PATH; test with `claude --version`
