# MeetingScribe — Design Spec

## Problem

Notion Pro ($20/mo) provides auto-detect meeting recording, transcription, and summarization. Build a self-hosted replacement leveraging existing Claude/Codex Pro subscriptions.

## Target Platforms

Meetings on: Google Meet, Zoom, Slack Huddles. Runs on macOS (Apple Silicon).

## Architecture: Hybrid Swift + Python

Two components communicating via a shared directory (`~/.meetingscribe/recordings/`).

### Component 1: Swift Menu Bar Daemon (~200 lines)

**Purpose:** Meeting detection + audio capture. Sits in menu bar with status indicator.

**Detection:**
- `ScreenCaptureKit` enumerates running apps with active audio sessions
- Whitelist of meeting apps: `zoom.us`, `Google Chrome` (Meet), `Slack`
- Whitelisted app starts audio session → begin capture
- Audio session ends → stop capture, notify Python

**Audio Capture:**
- `SCStream` captures app-specific audio (not whole system)
- Records to WAV in 5-minute chunks to `~/.meetingscribe/recordings/`
- On meeting end, writes a JSON manifest:

```json
{
  "meeting_id": "2026-03-20T1400",
  "app": "zoom.us",
  "chunks": ["chunk_001.wav", "chunk_002.wav"],
  "started": "2026-03-20T14:00:05",
  "ended": "2026-03-20T14:47:12"
}
```

**Menu Bar States:**
- Gray dot = idle, watching
- Red dot = recording
- Click for status, recent meetings, manual start/stop

### Component 2: Python Backend (LaunchAgent daemon)

**Purpose:** Transcription, diarization, summarization, Obsidian output.

Watches `~/.meetingscribe/recordings/` for new manifest files.

**Pipeline (sequential per meeting):**

1. **Merge chunks** — concatenate WAV chunks into single audio file
2. **Transcribe** — `faster-whisper` with `large-v3` model (~10x realtime on Apple Silicon). Outputs timestamped segments.
3. **Diarize** — `pyannote-audio` speaker diarization. Labels segments with speaker IDs.
4. **Align** — merge Whisper timestamps with pyannote speaker labels for speaker-attributed transcript
5. **Summarize** — pipe transcript to `claude -p` with prompt template requesting summary, action items with deadlines, key decisions, topics, and a TL;DR one-liner
6. **Write to vault** — generate markdown with YAML frontmatter, save to Obsidian vault

**Error Handling:**
- Transcription failure: keep WAV files, retry later
- `claude -p` failure (rate limit, CLI unavailable): save transcript without summary, re-summarize on next run
- Processed manifests move to `processed/` directory

### IPC

Swift daemon writes audio + manifest to watched directory. Python picks up via filesystem watcher. No complex orchestration.

## Obsidian Output Format

```markdown
---
date: 2026-03-20
time: "14:00 - 14:47"
duration: 47
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
- Speaker map: empty by default, user fills in real names once. Future potential for auto-matching.
- Topics as `[[wikilinks]]` to build knowledge graph across meetings
- Deadlines on action items extracted by Claude, compatible with Obsidian Tasks plugin
- `status` field for filtering meetings with pending items
- TL;DR one-liner for quick scanning

## Setup & Configuration

**Installation:**
- Swift daemon: standalone macOS app in `~/Applications`
- Python backend: installed via `pip`/`uv` into a virtualenv
- No BlackHole needed — `ScreenCaptureKit` handles audio natively
- First run: grant Screen Recording + Accessibility permissions

**Config file** at `~/.meetingscribe/config.toml`:

```toml
[vault]
path = "~/ObsidianVault/Meetings"

[detection]
apps = ["zoom.us", "Google Chrome", "Slack"]

[transcription]
model = "large-v3"

[summary]
cli = "claude"
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
- `pyannote-audio` — speaker diarization (requires HuggingFace token for model access)
- `watchdog` — filesystem watcher
- `claude` CLI — summarization via Pro subscription

## Non-Goals

- Real-time transcription (process after meeting ends)
- Cross-platform support (macOS only)
- Multi-user / team features
- Cloud storage or sync (Obsidian handles this)
- Web UI (Obsidian is the UI)
