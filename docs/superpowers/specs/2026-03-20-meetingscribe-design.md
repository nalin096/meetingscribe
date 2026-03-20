# MeetingScribe — Design Spec

## Problem

Notion Pro ($20/mo) provides auto-detect meeting recording, transcription, and summarization. Build a self-hosted replacement leveraging existing Claude/Codex Pro subscriptions.

## Target Platforms

Meetings on: Google Meet, Zoom, Slack Huddles. Runs on macOS (Apple Silicon).

## Architecture: Hybrid Swift + Python

Two components communicating via a shared directory (`~/.meetingscribe/recordings/`).

### Component 1: Swift Menu Bar Daemon

**Purpose:** Meeting detection + dual audio capture. Sits in menu bar with status indicator.

**Detection:**
- `ScreenCaptureKit` enumerates running apps with active audio sessions
- Whitelist of meeting apps: `zoom.us`, `Slack`
- For Google Meet: detect Chrome with active audio session + use Accessibility API to check for "meet.google.com" in the active tab URL/title. Only trigger when both conditions are met.
- For Slack: apply a minimum duration threshold (>30 seconds of continuous audio) to ignore notification sounds
- Whitelisted app starts qualifying audio session → begin capture
- Audio session ends → stop capture, notify Python

**Dual Audio Capture:**
- `SCStream` captures app-specific audio (remote participants' voices)
- `AVAudioEngine` captures local microphone input (user's voice)
- Both streams recorded as separate WAV files per chunk, merged during processing
- Audio format: 16kHz mono 16-bit WAV (sufficient for speech, ~1.9MB/min per stream)
- Records in 5-minute chunks for crash resilience (not losing entire recording if app dies)
- Chunks overlap by 1 second to prevent word-splitting at boundaries
- On meeting end, writes a JSON manifest atomically (write to `.tmp` then rename):

```json
{
  "meeting_id": "2026-03-20T14:00:05-0700-a3f2",
  "app": "zoom.us",
  "chunks": [
    {"remote": "chunk_001_remote.wav", "local": "chunk_001_local.wav"},
    {"remote": "chunk_002_remote.wav", "local": "chunk_002_local.wav"}
  ],
  "started": "2026-03-20T14:00:05-07:00",
  "ended": "2026-03-20T14:47:12-07:00"
}
```

**Crash Recovery:**
- On recording start, writes a `.recording` lock file with meeting metadata
- On next launch, checks for stale `.recording` locks
- If found: creates a manifest from orphaned chunks so Python can still process them
- If chunks are empty/corrupt: cleans them up

**Concurrent Meetings:**
- Only one recording at a time. If a second meeting app activates while recording, ignore it.
- Menu bar shows which app is being recorded so user can manually switch if needed.

**Menu Bar States:**
- Gray dot = idle, watching
- Red dot = recording (click shows which app, duration, and a "Discard" option)
- Click for status, recent meetings, manual start/stop

### Component 2: Python Backend (LaunchAgent daemon)

**Purpose:** Transcription, diarization, summarization, Obsidian output.

Watches `~/.meetingscribe/recordings/` for new manifest files.

**Pipeline (sequential per meeting):**

1. **Merge audio** — for each chunk, mix remote + local WAV streams into single file. Concatenate all chunks (with overlap cross-fade) into one audio file.
2. **Transcribe** — `faster-whisper` with `large-v3` model (~10x realtime on Apple Silicon). Outputs timestamped segments.
3. **Diarize** — `pyannote-audio` speaker diarization. Labels segments with speaker IDs. Requires one-time HuggingFace token setup (see Configuration).
4. **Align** — merge Whisper timestamps with pyannote speaker labels for speaker-attributed transcript
5. **Summarize** — pipe transcript to `claude -p --model sonnet` with prompt template. For transcripts exceeding ~12k words: split into sections, summarize each, then produce a final merged summary. Prompt template stored in `~/.meetingscribe/prompt.md` (user-editable).
6. **Write to vault** — generate markdown with YAML frontmatter, save to Obsidian vault

**Error Handling:**
- Transcription failure: keep WAV files, retry on next daemon cycle
- `claude -p` failure (rate limit, CLI unavailable): save transcript-only markdown, queue for re-summarization on next run
- Processed manifests move to `processed/` directory

**Disk Management:**
- WAV files deleted after successful processing by default
- Configurable retention: keep WAVs for N days (default: 0 = delete immediately after processing)
- Orphaned chunks older than 7 days auto-cleaned

**Logging:**
- Log to `~/.meetingscribe/logs/meetingscribe.log`
- Log rotation: 5MB max, keep 3 rotated files
- Levels: INFO (default), DEBUG (configurable)

### IPC

Swift daemon writes audio + manifest to watched directory. Python picks up via filesystem `watchdog`. Manifest written atomically (`.tmp` → rename) to prevent race conditions where Python reads an incomplete manifest.

## Obsidian Output Format

```markdown
---
date: 2026-03-20
time: "14:00 - 14:47"
duration_min: 47
app: Zoom
speakers: 3
speaker_map:
  Speaker 1: ""
  Speaker 2: ""
  Speaker 3: ""
topics: [roadmap, infrastructure, auth]
tags: [meeting]
status: has-action-items
---

# Meeting — 2026-03-20 14:00
> 47 min · Zoom · 3 speakers

## TL;DR
Q2 roadmap locked, auth pushed to Q3, staging budget greenlit.

## Summary
- Discussed Q2 roadmap priorities
- Agreed to defer auth migration to Q3
- Budget approved for staging env

## Action Items
- [ ] @Speaker 1: Draft Q2 timeline ⏰ 2026-03-24
- [ ] @Speaker 2: Share staging specs ⏰ 2026-03-22

## Key Decisions
- Auth migration → Q3 (compliance review)

## Topics Discussed
- [[Roadmap]] — Q2 priorities finalized
- [[Infrastructure]] — new staging env
- [[Auth Migration]] — deferred

## Transcript
**[00:00] Speaker 1:** Let's start with the roadmap...
**[00:23] Speaker 2:** I think we should prioritize...

---
*Transcribed by MeetingScribe · faster-whisper large-v3*
```

**Key features:**
- YAML frontmatter for Dataview queries
- `duration_min` field (always in minutes) for unambiguous querying
- Speaker map: empty by default, user fills in real names once. Future potential for auto-matching via voice embeddings.
- Topics as `[[wikilinks]]` to build knowledge graph across meetings
- Deadlines on action items extracted by Claude, compatible with Obsidian Tasks plugin
- `status` field for filtering meetings with pending items
- TL;DR one-liner for quick scanning

## Setup & Configuration

**Installation:**
- Swift daemon: standalone macOS app in `~/Applications`
- Python backend: installed via `pip`/`uv` into a virtualenv
- No BlackHole needed — `ScreenCaptureKit` handles audio natively
- First run: grant Screen Recording + Accessibility + Microphone permissions
- One-time: accept pyannote model license on HuggingFace, set token

**Config file** at `~/.meetingscribe/config.toml`:

```toml
[vault]
path = "~/ObsidianVault/Meetings"

[detection]
apps = ["zoom.us", "Google Chrome", "Slack"]
chrome_url_match = "meet.google.com"
min_duration_seconds = 30

[audio]
format = "wav"
sample_rate = 16000
channels = 1
bit_depth = 16

[transcription]
model = "large-v3"

[diarization]
hf_token = "hf_xxxxx"

[summary]
cli = "claude"
model_flag = "--model sonnet"
prompt_file = "~/.meetingscribe/prompt.md"

[storage]
retain_wav_days = 0  # 0 = delete after processing
orphan_cleanup_days = 7

[logging]
level = "INFO"
```

**Auto-start:**
- Swift daemon: macOS Login Item (launches on boot)
- Python backend: LaunchAgent (auto-restarts on crash)

## Dependencies

**Swift daemon:**
- macOS 14+ (Sonoma) for ScreenCaptureKit APIs
- Xcode / Swift toolchain

**Python backend:**
- Python 3.11+
- `faster-whisper` — local Whisper inference
- `pyannote-audio` — speaker diarization (requires HuggingFace token + model license acceptance)
- `watchdog` — filesystem watcher
- `claude` CLI — summarization via Pro subscription

## Non-Goals

- Real-time transcription (process after meeting ends)
- Cross-platform support (macOS only)
- Multi-user / team features
- Cloud storage or sync (Obsidian handles this)
- Web UI (Obsidian is the UI)
- Concurrent meeting recording (one at a time)
