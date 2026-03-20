# MeetingScribe — Design Spec

## Problem

Notion Pro ($20/mo) provides auto-detect meeting recording, transcription, and summarization. Build a self-hosted replacement leveraging existing Claude/Codex Pro subscriptions.

## Target Platforms

Meetings on: Google Meet, Zoom, Slack Huddles. Runs on macOS (Apple Silicon).

## Architecture: Hybrid Swift + Python

Two components communicating via a shared directory (`~/.meetingscribe/recordings/`).

### Component 1: Swift Menu Bar Daemon

**Purpose:** Meeting detection + dual audio capture. Sits in menu bar with status indicator.

**Detection — API Path:**
- Use `SCShareableContent.current` to get all shareable content (apps, windows)
- Filter `SCRunningApplication` list by `bundleIdentifier` against whitelist
- For each matched app, check if it has an active audio stream via `SCStream` configuration with `capturesAudio = true`
- Poll every 3 seconds (lightweight — no audio processing until a match triggers)

**Detection — Per-App Logic:**

*Zoom (`zoom.us`):*
- Detect `CptHost` subprocess (Zoom's meeting process, only runs during active calls)
- When detected + audio session active → begin capture
- When `CptHost` exits → stop capture

*Google Meet (Chrome):*
- Cannot rely on active tab — Meet often runs in background tabs
- Use `CGWindowListCopyWindowInfo` to enumerate all Chrome window titles
- Match any window title containing "Meet -" or "meet.google.com" (Meet includes these in the window/tab title)
- Fallback: also check `SCRunningApplication` for Chrome audio activity as a secondary signal
- Both signals present (Meet window title + Chrome audio) → begin capture
- Meet window closes OR Chrome audio stops → stop capture

*Slack (`com.tinyspeck.slackmacgap`):*
- Detect Slack's huddle-specific audio process/thread activation
- Apply minimum duration threshold (>30 seconds of continuous audio) to ignore notification sounds, ringtones
- 30s of sustained audio → begin capture
- Audio stops for >10 seconds → stop capture

**Dual Audio Capture with Sync:**
- `SCStream` captures app-specific audio (remote participants' voices)
- `AVAudioEngine` captures local microphone input (user's voice)
- **Clock sync strategy:** both streams use `mach_absolute_time()` as a shared monotonic clock. Each audio buffer callback records the mach timestamp alongside the sample count. During merge, the Python backend aligns streams by these timestamps, resampling if drift exceeds 10ms.
- Both streams recorded as separate WAV files per chunk with embedded timestamp metadata (custom WAV chunk or sidecar `.meta.json`)
- Audio format: 16kHz mono 16-bit WAV (sufficient for speech, ~1.9MB/min per stream)
- Records in 5-minute chunks for crash resilience (not losing entire recording if app dies)
- Chunks overlap by 1 second to prevent word-splitting at boundaries
- On meeting end, writes a JSON manifest atomically (write to `.tmp` then rename):

```json
{
  "meeting_id": "2026-03-20T14:00:05-07:00-a3f2",
  "app": "zoom.us",
  "chunks": [
    {
      "remote": "chunk_001_remote.wav",
      "local": "chunk_001_local.wav",
      "start_mach_time": 123456789,
      "start_iso": "2026-03-20T14:00:05-07:00"
    },
    {
      "remote": "chunk_002_remote.wav",
      "local": "chunk_002_local.wav",
      "start_mach_time": 123756789,
      "start_iso": "2026-03-20T14:05:04-07:00"
    }
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
- Menu bar shows which app is being recorded.
- "Switch" action in menu bar: stops current recording (writes manifest for what's captured so far), then starts new recording for the other app. Two separate transcripts produced.

**Menu Bar States:**
- Gray dot = idle, watching
- Red dot = recording (click shows: which app, duration, "Discard" button, "Switch to [other app]" if applicable)
- Click for status, recent meetings, manual start/stop

**Permission & System Event Handling:**
- On launch, verify Screen Recording + Microphone + Accessibility permissions. If missing, show a notification guiding user to System Settings.
- If permissions are revoked mid-session: stop recording gracefully, write manifest for what's captured, show notification.
- On system sleep: pause recording, resume on wake. If sleep exceeds 5 minutes, stop recording and finalize (meeting likely ended).
- On audio device change (e.g., headphones unplugged): re-acquire default input device via `AVAudioEngine`, continue recording. Log the device switch.

### Component 2: Python Backend (LaunchAgent daemon)

**Purpose:** Transcription, diarization, summarization, Obsidian output.

Watches `~/.meetingscribe/recordings/` for new manifest files (`.json` extension, ignores `.tmp`).

**Manifest Processing State Machine:**

Each manifest moves through explicit states tracked via file extension:

```
meeting_id.json          → pending (new, ready for processing)
meeting_id.processing    → in_progress (Python has claimed it)
meeting_id.done          → completed successfully
meeting_id.failed        → failed (after max retries)
meeting_id.failed.json   → contains error details and retry count
```

- On startup, any `.processing` files are stale (previous crash) → reset to `.json` for retry
- Python atomically renames `.json` → `.processing` before starting work (prevents duplicate processing if daemon restarts)
- On success: rename to `.done`, move WAVs per retention policy
- On failure: increment retry count, rename back to `.json` for retry. After 3 failures → rename to `.failed`, write error details to `.failed.json`, log a warning.
- A manifest stuck in `.failed` requires manual intervention (fix the issue, rename to `.json` to retry)

**Pipeline (sequential per meeting):**

1. **Merge audio** — for each chunk, align remote + local WAV streams using mach timestamp metadata (resample if drift >10ms). Mix into single file. Concatenate all chunks (with overlap cross-fade) into one audio file.
2. **Transcribe** — `faster-whisper` with `large-v3` model (~10x realtime on Apple Silicon). Outputs timestamped segments.
3. **Diarize** — `pyannote-audio` speaker diarization. Labels segments with speaker IDs.
4. **Align** — merge Whisper timestamps with pyannote speaker labels for speaker-attributed transcript. Consult `~/.meetingscribe/speakers.toml` to map speaker embeddings to known names (see Speaker Identity below).
5. **Summarize** — pipe transcript to `claude -p --model sonnet` with prompt template. Transcript chunking for long meetings: split at speaker-turn boundaries into ~10k-word sections (conservative estimate ≈ ~13k tokens), summarize each, then produce a final merged summary. Prompt template stored in `~/.meetingscribe/prompt.md` (user-editable).
6. **Write to vault** — generate markdown with YAML frontmatter, save to Obsidian vault. Validate vault path exists and is writable before writing; if not, log error and keep manifest in `.processing` for retry.

**Speaker Identity Persistence:**

Speaker diarization produces anonymous IDs (Speaker 1, 2, 3) per meeting with no cross-meeting correlation. To solve this:

- `~/.meetingscribe/speakers.toml` stores known speaker profiles:

```toml
[[speakers]]
name = "Alice"
# voice embedding stored as base64, generated from first labeled meeting
embedding = "base64..."

[[speakers]]
name = "Bob"
embedding = "base64..."
```

- After diarization, compare each speaker's embedding against known profiles (cosine similarity, threshold 0.75)
- Matches auto-populate the `speaker_map` in the output markdown
- Unmatched speakers remain as "Speaker N" — user can label them in Obsidian, then run a CLI command (`meetingscribe label-speaker --meeting <id> --speaker 2 --name "Carol"`) to save the embedding for future matching
- This is an enhancement — v1 can ship without it and use anonymous speaker IDs

**Error Handling & Retry Policy:**
- Max 3 retries per manifest, with exponential backoff (1min, 5min, 30min)
- Transcription failure: keep WAV files, retry per policy above
- `claude -p` failure (rate limit, CLI unavailable): save transcript-only markdown (status: `needs-summary`), queue for re-summarization. Separate retry queue scanned every 15 minutes.
- No-speech meetings (Whisper returns empty/near-empty transcript): write a minimal note with metadata only, status: `no-speech`, skip summarization
- Disk full: log error, do not delete any WAVs, pause processing until space available
- Poison messages (consistently failing after 3 retries): move to `.failed`, send macOS notification via `osascript`

**Disk Management:**
- WAV files deleted after successful processing by default
- Configurable retention: keep WAVs for N days (default: 0 = delete immediately after processing)
- Orphaned chunks older than 7 days auto-cleaned

**Logging:**
- Log to `~/.meetingscribe/logs/meetingscribe.log`
- Log rotation: 5MB max, keep 3 rotated files
- Levels: INFO (default), DEBUG (configurable)

### IPC

Swift daemon writes audio + manifest to watched directory. Python picks up via filesystem `watchdog` (watches for `.json` files only). Manifest written atomically (`.tmp` → rename) to prevent race conditions. State transitions are atomic renames to prevent duplicate processing.

## Obsidian Output Format

```markdown
---
date: 2026-03-20
time: "14:00 - 14:47"
timezone: "America/Los_Angeles"
duration_min: 47
app: Zoom
speakers: 3
speaker_map:
  Speaker 1: "Alice"
  Speaker 2: ""
  Speaker 3: "Bob"
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
- [ ] @Alice: Draft Q2 timeline ⏰ 2026-03-24
- [ ] @Speaker 2: Share staging specs ⏰ 2026-03-22

## Key Decisions
- Auth migration → Q3 (compliance review)

## Topics Discussed
- [[Roadmap]] — Q2 priorities finalized
- [[Infrastructure]] — new staging env
- [[Auth Migration]] — deferred

## Transcript
**[00:00] Alice:** Let's start with the roadmap...
**[00:23] Speaker 2:** I think we should prioritize...

---
*Transcribed by MeetingScribe · faster-whisper large-v3*
```

**Key features:**
- YAML frontmatter for Dataview queries
- `timezone` field for unambiguous time interpretation
- `duration_min` field (always in minutes) for unambiguous querying
- Speaker map: auto-populated from `speakers.toml` where matched, empty for unknown speakers
- Known speaker names used throughout the document (action items, transcript)
- Topics as `[[wikilinks]]` to build knowledge graph across meetings
- Deadlines on action items extracted by Claude, compatible with Obsidian Tasks plugin
- `status` field: `has-action-items`, `no-action-items`, `needs-summary`, `no-speech`
- TL;DR one-liner for quick scanning

## Setup & Configuration

**Installation:**
- Swift daemon: standalone macOS app in `~/Applications`
- Python backend: installed via `pip`/`uv` into a virtualenv
- No BlackHole needed — `ScreenCaptureKit` handles audio natively
- First run: grant Screen Recording + Accessibility + Microphone permissions (app guides user through each)
- One-time: accept pyannote model license on HuggingFace, store token in macOS Keychain

**First-run setup wizard (CLI):**
```bash
meetingscribe setup
```
- Validates all permissions are granted
- Prompts for Obsidian vault path (validates it exists and is writable)
- Prompts for HuggingFace token, stores in macOS Keychain (`security add-generic-password`)
- Downloads Whisper and pyannote models
- Creates default config at `~/.meetingscribe/config.toml`
- Creates default prompt template at `~/.meetingscribe/prompt.md`

**Config file** at `~/.meetingscribe/config.toml`:

```toml
[vault]
path = "~/ObsidianVault/Meetings"
timezone = "America/Los_Angeles"

[detection]
apps = ["zoom.us", "Google Chrome", "Slack"]
chrome_window_match = "Meet -|meet.google.com"
slack_min_duration_seconds = 30
poll_interval_seconds = 3

[audio]
format = "wav"
sample_rate = 16000
channels = 1
bit_depth = 16
chunk_duration_seconds = 300
chunk_overlap_seconds = 1

[transcription]
model = "large-v3"

[diarization]
# HuggingFace token stored in macOS Keychain under service "meetingscribe"
# Set via: meetingscribe setup (or security add-generic-password manually)
keychain_service = "meetingscribe"
keychain_account = "hf_token"

[summary]
cli = "claude"
model_flag = "--model sonnet"
prompt_file = "~/.meetingscribe/prompt.md"

[retry]
max_retries = 3
backoff_minutes = [1, 5, 30]
summary_retry_interval_minutes = 15

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
- `pyannote-audio` — speaker diarization (requires HuggingFace model license acceptance)
- `watchdog` — filesystem watcher
- `claude` CLI — summarization via Pro subscription
- `keyring` — macOS Keychain access for HuggingFace token

## Non-Goals

- Real-time transcription (process after meeting ends)
- Cross-platform support (macOS only)
- Multi-user / team features
- Cloud storage or sync (Obsidian handles this)
- Web UI (Obsidian is the UI)
- Concurrent meeting recording (one at a time)
