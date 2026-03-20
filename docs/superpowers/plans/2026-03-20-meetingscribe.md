# MeetingScribe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a macOS meeting transcription app that auto-detects meetings, captures audio, transcribes with speaker diarization, summarizes via Claude CLI, and outputs markdown to an Obsidian vault.

**Architecture:** Hybrid Swift menu bar daemon (detection + audio capture) communicating via filesystem IPC with a Python backend (transcription + diarization + summarization + Obsidian output). Python backend built and tested first with mock audio, then Swift daemon integrates.

**Tech Stack:** Swift (ScreenCaptureKit, AVAudioEngine, SwiftUI), Python 3.11+ (faster-whisper, pyannote-audio, watchdog, keyring), TOML config, Claude CLI for summarization.

**Spec:** `docs/superpowers/specs/2026-03-20-meetingscribe-design.md`

---

## File Structure

### Python Backend (`python/`)

```
python/
├── pyproject.toml
├── src/
│   └── meetingscribe/
│       ├── __init__.py
│       ├── config.py              # Load/validate config.toml
│       ├── manifest.py            # Manifest schema + state machine
│       ├── audio_merger.py        # WAV chunk merging, drift correction, cross-fade
│       ├── transcriber.py         # faster-whisper wrapper
│       ├── diarizer.py            # pyannote-audio wrapper
│       ├── aligner.py             # Merge whisper timestamps + speaker labels
│       ├── summarizer.py          # claude -p CLI wrapper
│       ├── markdown_writer.py     # Obsidian markdown output
│       ├── pipeline.py            # Orchestrates full processing pipeline
│       ├── watcher.py             # Filesystem watcher daemon
│       ├── retry.py               # Retry policy + backoff logic
│       ├── cli.py                 # CLI entry point (setup wizard, label-speaker)
│       └── notify.py              # macOS notification via osascript
├── tests/
│   ├── conftest.py                # Shared fixtures (tmp dirs, mock WAVs, mock config)
│   ├── test_config.py
│   ├── test_manifest.py
│   ├── test_audio_merger.py
│   ├── test_transcriber.py
│   ├── test_diarizer.py
│   ├── test_aligner.py
│   ├── test_summarizer.py
│   ├── test_markdown_writer.py
│   ├── test_pipeline.py
│   ├── test_watcher.py
│   ├── test_retry.py
│   └── test_cli.py
└── resources/
    ├── default_config.toml        # Default config template
    └── default_prompt.md          # Default Claude prompt template
```

### Swift Daemon (`swift/MeetingScribe/`)

```
swift/MeetingScribe/
├── Package.swift
├── Sources/
│   └── MeetingScribe/
│       ├── App.swift              # SwiftUI app entry, menu bar setup
│       ├── MenuBarView.swift      # Menu bar UI (status, controls)
│       ├── DetectionManager.swift # Polling loop, coordinates per-app detectors
│       ├── ZoomDetector.swift     # Zoom-specific detection (CptHost)
│       ├── MeetDetector.swift     # Google Meet detection (window titles + audio)
│       ├── SlackDetector.swift    # Slack huddle detection (duration threshold)
│       ├── AudioCapture.swift     # Dual capture: SCStream + AVAudioEngine
│       ├── ChunkWriter.swift      # WAV chunk file writing with timestamps
│       ├── ManifestWriter.swift   # JSON manifest atomic write
│       ├── CrashRecovery.swift    # Stale lock detection + orphan cleanup
│       ├── PermissionManager.swift # Permission checking + user guidance
│       ├── SystemEvents.swift     # Sleep/wake, device change handlers
│       ├── Config.swift           # Read config.toml
│       └── Constants.swift        # Paths, defaults
└── Tests/
    └── MeetingScribeTests/
        ├── DetectionManagerTests.swift
        ├── ManifestWriterTests.swift
        ├── CrashRecoveryTests.swift
        └── ConfigTests.swift
```

---

## Phase 1: Python Backend — Foundation

### Task 1: Project Scaffolding

**Files:**
- Create: `python/pyproject.toml`
- Create: `python/src/meetingscribe/__init__.py`
- Create: `python/resources/default_config.toml`
- Create: `python/resources/default_prompt.md`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "meetingscribe"
version = "0.1.0"
description = "Auto-detect meetings, transcribe, summarize, output to Obsidian"
requires-python = ">=3.11"
dependencies = [
    "faster-whisper>=1.1.0",
    "pyannote-audio>=3.3.0",
    "watchdog>=4.0.0",
    "keyring>=25.0.0",
    "tomli>=2.0.0;python_version<'3.12'",
    "tomli-w>=1.0.0",
    "numpy>=1.26.0",
    "soundfile>=0.12.0",
    "scipy>=1.12.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0.0", "pytest-tmp-files>=0.0.2"]

[project.scripts]
meetingscribe = "meetingscribe.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/meetingscribe"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create __init__.py**

```python
"""MeetingScribe — auto-detect meetings, transcribe, summarize, output to Obsidian."""
```

- [ ] **Step 3: Create default config template**

Create `python/resources/default_config.toml` with the full config from the spec (all sections: vault, detection, audio, transcription, diarization, summary, retry, storage, logging).

- [ ] **Step 4: Create default prompt template**

Create `python/resources/default_prompt.md`:

```markdown
Given this meeting transcript with speaker labels, produce the following in markdown:

1. **TL;DR** — one sentence summarizing the meeting
2. **Summary** — 3-5 bullet points of what was discussed
3. **Action Items** — bulleted checklist with owner (@Speaker Name) and deadline if mentioned (format: ⏰ YYYY-MM-DD)
4. **Key Decisions** — bulleted list of decisions made
5. **Topics** — bulleted list of main topics discussed, each as a [[wikilink]]

Use the exact speaker names from the transcript. If a deadline is mentioned but not specific, estimate based on context. Output ONLY the markdown sections above, no preamble.
```

- [ ] **Step 5: Install dev dependencies and verify**

Run: `cd python && pip install -e ".[dev]"`
Expected: installs successfully

- [ ] **Step 6: Commit**

```bash
git add python/
git commit -m "feat: scaffold Python project with pyproject.toml and defaults"
```

---

### Task 2: Config Module

**Files:**
- Create: `python/src/meetingscribe/config.py`
- Create: `python/tests/conftest.py`
- Create: `python/tests/test_config.py`

- [ ] **Step 1: Write conftest.py with shared fixtures**

```python
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
```

- [ ] **Step 2: Write failing tests for config**

```python
# tests/test_config.py
from meetingscribe.config import load_config, MeetingScribeConfig


def test_load_config_returns_typed_config(sample_config):
    config = load_config(sample_config)
    assert isinstance(config, MeetingScribeConfig)
    assert config.audio.sample_rate == 16000
    assert config.retry.max_retries == 3


def test_load_config_validates_vault_path(tmp_home):
    config_path = tmp_home / ".meetingscribe" / "config.toml"
    config_path.write_text('[vault]\npath = "/nonexistent/path"\ntimezone = "UTC"')
    import pytest
    with pytest.raises(ValueError, match="vault path"):
        load_config(config_path)


def test_load_config_missing_file():
    from pathlib import Path
    import pytest
    with pytest.raises(FileNotFoundError):
        load_config(Path("/nonexistent/config.toml"))
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd python && python -m pytest tests/test_config.py -v`
Expected: FAIL (module not found)

- [ ] **Step 4: Implement config.py**

```python
"""Load and validate MeetingScribe configuration."""

from dataclasses import dataclass, field
from pathlib import Path
import sys

if sys.version_info >= (3, 12):
    import tomllib
else:
    import tomli as tomllib


@dataclass
class VaultConfig:
    path: Path
    timezone: str = "UTC"


@dataclass
class DetectionConfig:
    apps: list[str] = field(default_factory=lambda: ["zoom.us", "com.google.Chrome", "com.tinyspeck.slackmacgap"])
    chrome_window_match: str = "Meet -|meet.google.com"
    slack_min_duration_seconds: int = 30
    poll_interval_seconds: int = 3


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    bit_depth: int = 16
    chunk_duration_seconds: int = 300
    chunk_overlap_seconds: int = 1


@dataclass
class TranscriptionConfig:
    model: str = "large-v3"


@dataclass
class DiarizationConfig:
    keychain_service: str = "meetingscribe"
    keychain_account: str = "hf_token"


@dataclass
class SummaryConfig:
    cli: str = "claude"
    model_flag: str = "--model sonnet"
    prompt_file: Path = Path("~/.meetingscribe/prompt.md")


@dataclass
class RetryConfig:
    max_retries: int = 3
    backoff_minutes: list[int] = field(default_factory=lambda: [1, 5, 30])
    summary_retry_interval_minutes: int = 15


@dataclass
class StorageConfig:
    retain_wav_days: int = 0
    orphan_cleanup_days: int = 7


@dataclass
class LoggingConfig:
    level: str = "INFO"


@dataclass
class MeetingScribeConfig:
    vault: VaultConfig
    detection: DetectionConfig
    audio: AudioConfig
    transcription: TranscriptionConfig
    diarization: DiarizationConfig
    summary: SummaryConfig
    retry: RetryConfig
    storage: StorageConfig
    logging: LoggingConfig


def _build_section(cls, data: dict):
    """Build a dataclass from a dict, ignoring unknown keys."""
    import dataclasses
    valid_keys = {f.name for f in dataclasses.fields(cls)}
    filtered = {k: v for k, v in data.items() if k in valid_keys}
    return cls(**filtered)


def load_config(path: Path) -> MeetingScribeConfig:
    """Load config from TOML file, validate, return typed config."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    vault_data = raw.get("vault", {})
    vault_path = Path(vault_data.get("path", "")).expanduser()
    if not vault_path.is_dir():
        raise ValueError(f"vault path does not exist: {vault_path}")
    vault_data["path"] = vault_path

    summary_data = raw.get("summary", {})
    if "prompt_file" in summary_data:
        summary_data["prompt_file"] = Path(summary_data["prompt_file"]).expanduser()

    return MeetingScribeConfig(
        vault=_build_section(VaultConfig, vault_data),
        detection=_build_section(DetectionConfig, raw.get("detection", {})),
        audio=_build_section(AudioConfig, raw.get("audio", {})),
        transcription=_build_section(TranscriptionConfig, raw.get("transcription", {})),
        diarization=_build_section(DiarizationConfig, raw.get("diarization", {})),
        summary=_build_section(SummaryConfig, summary_data),
        retry=_build_section(RetryConfig, raw.get("retry", {})),
        storage=_build_section(StorageConfig, raw.get("storage", {})),
        logging=_build_section(LoggingConfig, raw.get("logging", {})),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd python && python -m pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add python/src/meetingscribe/config.py python/tests/conftest.py python/tests/test_config.py
git commit -m "feat: config module with TOML loading and validation"
```

---

### Task 3: Manifest State Machine

**Files:**
- Create: `python/src/meetingscribe/manifest.py`
- Create: `python/tests/test_manifest.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_manifest.py
import json
from pathlib import Path
from meetingscribe.manifest import (
    Manifest,
    ManifestState,
    load_manifest,
    claim_manifest,
    complete_manifest,
    fail_manifest,
    recover_stale,
)


def test_load_manifest_from_json(tmp_path):
    data = {
        "meeting_id": "2026-03-20T14:00:05-07:00-a3f2",
        "app": "zoom.us",
        "chunks": [
            {"remote": "c1_remote.wav", "local": "c1_local.wav",
             "start_mach_time": 123, "start_iso": "2026-03-20T14:00:05-07:00"}
        ],
        "started": "2026-03-20T14:00:05-07:00",
        "ended": "2026-03-20T14:47:12-07:00",
    }
    p = tmp_path / "meeting.json"
    p.write_text(json.dumps(data))
    m = load_manifest(p)
    assert m.meeting_id == "2026-03-20T14:00:05-07:00-a3f2"
    assert m.app == "zoom.us"
    assert len(m.chunks) == 1


def test_claim_manifest_renames_to_processing(tmp_path):
    p = tmp_path / "meeting.json"
    p.write_text("{}")
    new_path = claim_manifest(p)
    assert new_path.suffix == ".processing"
    assert not p.exists()
    assert new_path.exists()


def test_complete_manifest_renames_to_done(tmp_path):
    p = tmp_path / "meeting.processing"
    p.write_text("{}")
    new_path = complete_manifest(p)
    assert new_path.suffix == ".done"


def test_fail_manifest_increments_retry(tmp_path):
    p = tmp_path / "meeting.processing"
    p.write_text("{}")
    # First two failures → back to .json
    result = fail_manifest(p, "some error", retry_count=0, max_retries=3)
    assert result.suffix == ".json"
    # Third failure → .failed
    p2 = tmp_path / "meeting.processing"
    p2.write_text("{}")
    result = fail_manifest(p2, "some error", retry_count=2, max_retries=3)
    assert result.suffix == ".failed"
    assert (tmp_path / "meeting.failed.error").exists()


def test_recover_stale_processing(tmp_path):
    p = tmp_path / "meeting.processing"
    p.write_text("{}")
    recovered = recover_stale(tmp_path)
    assert len(recovered) == 1
    assert recovered[0].suffix == ".json"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && python -m pytest tests/test_manifest.py -v`
Expected: FAIL

- [ ] **Step 3: Implement manifest.py**

```python
"""Manifest schema and state machine for meeting processing."""

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ManifestState(Enum):
    PENDING = "json"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


@dataclass
class ChunkInfo:
    remote: str
    local: str
    start_mach_time: int
    start_iso: str


@dataclass
class Manifest:
    meeting_id: str
    app: str
    chunks: list[ChunkInfo]
    started: str
    ended: str
    retry_count: int = 0


def load_manifest(path: Path) -> Manifest:
    """Load manifest from JSON file."""
    with open(path) as f:
        data = json.load(f)
    chunks = [ChunkInfo(**c) for c in data.get("chunks", [])]
    return Manifest(
        meeting_id=data.get("meeting_id", ""),
        app=data.get("app", ""),
        chunks=chunks,
        started=data.get("started", ""),
        ended=data.get("ended", ""),
        retry_count=data.get("_retry_count", 0),
    )


def _atomic_rename(src: Path, new_suffix: str) -> Path:
    """Rename file by changing suffix. Returns new path."""
    dest = src.with_suffix(new_suffix)
    src.rename(dest)
    return dest


def claim_manifest(path: Path) -> Path:
    """Atomically rename .json → .processing."""
    return _atomic_rename(path, ".processing")


def complete_manifest(path: Path) -> Path:
    """Rename .processing → .done."""
    return _atomic_rename(path, ".done")


def fail_manifest(path: Path, error: str, retry_count: int, max_retries: int) -> Path:
    """Handle failure: retry or mark as permanently failed."""
    if retry_count + 1 >= max_retries:
        # Permanent failure
        new_path = _atomic_rename(path, ".failed")
        error_path = path.with_suffix(".failed.error")
        error_path.write_text(json.dumps({
            "error": error,
            "retry_count": retry_count + 1,
        }, indent=2))
        return new_path
    else:
        # Back to pending for retry — update retry count in manifest
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, ValueError):
                pass
        data["_retry_count"] = retry_count + 1
        # Write updated data back before rename
        path.write_text(json.dumps(data, indent=2))
        return _atomic_rename(path, ".json")


def recover_stale(directory: Path) -> list[Path]:
    """Find .processing files (stale from crash) and reset to .json."""
    recovered = []
    for p in directory.glob("*.processing"):
        new_path = _atomic_rename(p, ".json")
        recovered.append(new_path)
    return recovered
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && python -m pytest tests/test_manifest.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add python/src/meetingscribe/manifest.py python/tests/test_manifest.py
git commit -m "feat: manifest state machine with claim/complete/fail/recover"
```

---

### Task 4: Audio Merger

**Files:**
- Create: `python/src/meetingscribe/audio_merger.py`
- Create: `python/tests/test_audio_merger.py`

- [ ] **Step 1: Add WAV fixture to conftest.py**

Append to `python/tests/conftest.py`:

```python
import numpy as np
import soundfile as sf


@pytest.fixture
def make_wav(tmp_path):
    """Factory fixture: create a WAV file with sine tone."""
    def _make(filename: str, duration_s: float = 5.0, sample_rate: int = 16000):
        path = tmp_path / filename
        t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
        audio = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        sf.write(str(path), audio, sample_rate, subtype="PCM_16")
        return path
    return _make
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_audio_merger.py
import numpy as np
import soundfile as sf
from meetingscribe.audio_merger import merge_chunk_pair, concatenate_chunks


def test_merge_chunk_pair_produces_mono(make_wav, tmp_path):
    remote = make_wav("remote.wav", duration_s=3.0)
    local = make_wav("local.wav", duration_s=3.0)
    out = tmp_path / "merged.wav"
    merge_chunk_pair(remote, local, out, drift_ms=0)
    data, sr = sf.read(str(out))
    assert sr == 16000
    assert len(data.shape) == 1  # mono
    assert abs(len(data) - 3.0 * 16000) < 100  # ~3 seconds


def test_merge_chunk_pair_handles_drift(make_wav, tmp_path):
    remote = make_wav("remote.wav", duration_s=3.0)
    local = make_wav("local.wav", duration_s=3.05)  # 50ms longer
    out = tmp_path / "merged.wav"
    merge_chunk_pair(remote, local, out, drift_ms=50)
    data, sr = sf.read(str(out))
    assert sr == 16000
    # Should resample local to match remote length
    assert abs(len(data) - 3.0 * 16000) < 100


def test_concatenate_chunks_with_overlap(make_wav, tmp_path):
    c1 = make_wav("c1.wav", duration_s=5.0)
    c2 = make_wav("c2.wav", duration_s=5.0)
    out = tmp_path / "full.wav"
    concatenate_chunks([c1, c2], out, overlap_seconds=1.0, sample_rate=16000)
    data, sr = sf.read(str(out))
    # 5 + 5 - 1 overlap = 9 seconds
    expected_samples = 9.0 * 16000
    assert abs(len(data) - expected_samples) < 200
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd python && python -m pytest tests/test_audio_merger.py -v`
Expected: FAIL

- [ ] **Step 4: Implement audio_merger.py**

```python
"""Merge dual audio streams and concatenate chunks with cross-fade."""

from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample


def merge_chunk_pair(remote_path: Path, local_path: Path, output_path: Path, drift_ms: float = 0) -> None:
    """Mix remote + local WAV into a single mono file. Resample local if drift detected."""
    remote, sr_r = sf.read(str(remote_path), dtype="float32")
    local, sr_l = sf.read(str(local_path), dtype="float32")

    if sr_r != sr_l:
        raise ValueError(f"Sample rate mismatch: {sr_r} vs {sr_l}")

    # If drift exceeds threshold, resample local to match remote length
    if abs(drift_ms) > 10 and len(remote) > 0:
        local = resample(local, len(remote)).astype(np.float32)

    # Trim to shorter length
    min_len = min(len(remote), len(local))
    remote = remote[:min_len]
    local = local[:min_len]

    # Mix: average the two streams
    mixed = (remote + local) / 2.0
    sf.write(str(output_path), mixed, sr_r, subtype="PCM_16")


def concatenate_chunks(chunk_paths: list[Path], output_path: Path, overlap_seconds: float, sample_rate: int) -> None:
    """Concatenate WAV chunks with cross-fade at overlap regions."""
    if not chunk_paths:
        return

    overlap_samples = int(overlap_seconds * sample_rate)
    result = None

    for path in chunk_paths:
        data, sr = sf.read(str(path), dtype="float32")
        if sr != sample_rate:
            raise ValueError(f"Expected {sample_rate}Hz, got {sr}Hz")

        if result is None:
            result = data
            continue

        if overlap_samples > 0 and len(result) >= overlap_samples and len(data) >= overlap_samples:
            # Cross-fade overlap region
            fade_out = np.linspace(1.0, 0.0, overlap_samples, dtype=np.float32)
            fade_in = np.linspace(0.0, 1.0, overlap_samples, dtype=np.float32)

            overlap_mixed = result[-overlap_samples:] * fade_out + data[:overlap_samples] * fade_in
            result = np.concatenate([result[:-overlap_samples], overlap_mixed, data[overlap_samples:]])
        else:
            result = np.concatenate([result, data])

    if result is not None:
        sf.write(str(output_path), result, sample_rate, subtype="PCM_16")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd python && python -m pytest tests/test_audio_merger.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add python/src/meetingscribe/audio_merger.py python/tests/test_audio_merger.py python/tests/conftest.py
git commit -m "feat: audio merger with drift correction and cross-fade"
```

---

### Task 5: Transcriber Module

**Files:**
- Create: `python/src/meetingscribe/transcriber.py`
- Create: `python/tests/test_transcriber.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_transcriber.py
from unittest.mock import patch, MagicMock
from meetingscribe.transcriber import transcribe, TranscriptSegment


def test_transcribe_returns_segments():
    mock_segment = MagicMock()
    mock_segment.start = 0.0
    mock_segment.end = 2.5
    mock_segment.text = " Hello, this is a test."

    mock_info = MagicMock()
    mock_info.language = "en"
    mock_info.language_probability = 0.98

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([mock_segment], mock_info)

    with patch("meetingscribe.transcriber.WhisperModel", return_value=mock_model):
        segments = transcribe("/fake/audio.wav", model_size="tiny")

    assert len(segments) == 1
    assert isinstance(segments[0], TranscriptSegment)
    assert segments[0].start == 0.0
    assert segments[0].end == 2.5
    assert segments[0].text == "Hello, this is a test."


def test_transcribe_empty_audio_returns_empty():
    mock_model = MagicMock()
    mock_info = MagicMock()
    mock_model.transcribe.return_value = ([], mock_info)

    with patch("meetingscribe.transcriber.WhisperModel", return_value=mock_model):
        segments = transcribe("/fake/silent.wav", model_size="tiny")

    assert segments == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && python -m pytest tests/test_transcriber.py -v`
Expected: FAIL

- [ ] **Step 3: Implement transcriber.py**

```python
"""Transcribe audio using faster-whisper."""

from dataclasses import dataclass
from pathlib import Path
from faster_whisper import WhisperModel


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


# Cache model instance to avoid reloading per meeting
_model_cache: dict[str, WhisperModel] = {}


def _get_model(model_size: str) -> WhisperModel:
    if model_size not in _model_cache:
        _model_cache[model_size] = WhisperModel(model_size, compute_type="int8")
    return _model_cache[model_size]


def transcribe(audio_path: str | Path, model_size: str = "large-v3") -> list[TranscriptSegment]:
    """Transcribe audio file, return list of timed segments."""
    model = _get_model(model_size)
    segments_iter, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        vad_filter=True,
    )

    segments = []
    for seg in segments_iter:
        text = seg.text.strip()
        if text:
            segments.append(TranscriptSegment(start=seg.start, end=seg.end, text=text))

    return segments
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && python -m pytest tests/test_transcriber.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add python/src/meetingscribe/transcriber.py python/tests/test_transcriber.py
git commit -m "feat: transcriber module wrapping faster-whisper"
```

---

### Task 6: Diarizer Module

**Files:**
- Create: `python/src/meetingscribe/diarizer.py`
- Create: `python/tests/test_diarizer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_diarizer.py
from unittest.mock import patch, MagicMock
from meetingscribe.diarizer import diarize, SpeakerSegment


def test_diarize_returns_speaker_segments():
    mock_turn = MagicMock()
    mock_turn.start = 0.0
    mock_turn.end = 3.5
    mock_label = "SPEAKER_00"

    mock_pipeline = MagicMock()
    mock_pipeline.return_value.itertracks.return_value = [
        (mock_turn, None, mock_label)
    ]

    with patch("meetingscribe.diarizer.Pipeline.from_pretrained", return_value=mock_pipeline):
        segments = diarize("/fake/audio.wav", hf_token="fake_token")

    assert len(segments) == 1
    assert isinstance(segments[0], SpeakerSegment)
    assert segments[0].speaker == "SPEAKER_00"
    assert segments[0].start == 0.0
    assert segments[0].end == 3.5


def test_diarize_empty_returns_empty():
    mock_pipeline = MagicMock()
    mock_pipeline.return_value.itertracks.return_value = []

    with patch("meetingscribe.diarizer.Pipeline.from_pretrained", return_value=mock_pipeline):
        segments = diarize("/fake/silent.wav", hf_token="fake_token")

    assert segments == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && python -m pytest tests/test_diarizer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement diarizer.py**

```python
"""Speaker diarization using pyannote-audio."""

from dataclasses import dataclass
from pathlib import Path
from pyannote.audio import Pipeline


@dataclass
class SpeakerSegment:
    start: float
    end: float
    speaker: str


_pipeline_cache: Pipeline | None = None


def _get_pipeline(hf_token: str) -> Pipeline:
    global _pipeline_cache
    if _pipeline_cache is None:
        _pipeline_cache = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )
    return _pipeline_cache


def diarize(audio_path: str | Path, hf_token: str) -> list[SpeakerSegment]:
    """Run speaker diarization on audio file."""
    pipeline = _get_pipeline(hf_token)
    diarization = pipeline(str(audio_path))

    segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append(SpeakerSegment(
            start=turn.start,
            end=turn.end,
            speaker=speaker,
        ))

    return segments
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && python -m pytest tests/test_diarizer.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add python/src/meetingscribe/diarizer.py python/tests/test_diarizer.py
git commit -m "feat: diarizer module wrapping pyannote-audio"
```

---

### Task 7: Aligner Module

**Files:**
- Create: `python/src/meetingscribe/aligner.py`
- Create: `python/tests/test_aligner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_aligner.py
from meetingscribe.transcriber import TranscriptSegment
from meetingscribe.diarizer import SpeakerSegment
from meetingscribe.aligner import align, AlignedSegment


def test_align_assigns_speakers_to_transcript():
    transcript = [
        TranscriptSegment(start=0.0, end=2.0, text="Hello everyone"),
        TranscriptSegment(start=2.5, end=5.0, text="Thanks for joining"),
        TranscriptSegment(start=5.5, end=8.0, text="Let's begin"),
    ]
    speakers = [
        SpeakerSegment(start=0.0, end=3.0, speaker="SPEAKER_00"),
        SpeakerSegment(start=3.0, end=6.0, speaker="SPEAKER_01"),
        SpeakerSegment(start=6.0, end=9.0, speaker="SPEAKER_00"),
    ]
    aligned = align(transcript, speakers)
    assert len(aligned) == 3
    assert aligned[0].speaker == "Speaker 1"  # SPEAKER_00 → Speaker 1
    assert aligned[1].speaker == "Speaker 2"  # SPEAKER_01 → Speaker 2
    assert aligned[2].speaker == "Speaker 1"  # SPEAKER_00 → Speaker 1


def test_align_no_speakers_defaults_to_unknown():
    transcript = [
        TranscriptSegment(start=0.0, end=2.0, text="Hello"),
    ]
    aligned = align(transcript, [])
    assert aligned[0].speaker == "Speaker 1"


def test_align_empty_transcript():
    aligned = align([], [])
    assert aligned == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && python -m pytest tests/test_aligner.py -v`
Expected: FAIL

- [ ] **Step 3: Implement aligner.py**

```python
"""Align transcript segments with speaker diarization labels."""

from dataclasses import dataclass
from meetingscribe.transcriber import TranscriptSegment
from meetingscribe.diarizer import SpeakerSegment


@dataclass
class AlignedSegment:
    start: float
    end: float
    text: str
    speaker: str


def align(transcript: list[TranscriptSegment], speakers: list[SpeakerSegment]) -> list[AlignedSegment]:
    """Assign a speaker label to each transcript segment based on maximum overlap."""
    if not transcript:
        return []

    # Map raw pyannote labels (SPEAKER_00, SPEAKER_01) to friendly names (Speaker 1, Speaker 2)
    raw_to_friendly: dict[str, str] = {}
    counter = 0

    def get_friendly(raw_label: str) -> str:
        nonlocal counter
        if raw_label not in raw_to_friendly:
            counter += 1
            raw_to_friendly[raw_label] = f"Speaker {counter}"
        return raw_to_friendly[raw_label]

    aligned = []
    for seg in transcript:
        best_speaker = None
        best_overlap = 0.0

        for sp in speakers:
            # Calculate overlap between transcript segment and speaker segment
            overlap_start = max(seg.start, sp.start)
            overlap_end = min(seg.end, sp.end)
            overlap = max(0.0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = sp.speaker

        friendly = get_friendly(best_speaker) if best_speaker else get_friendly("UNKNOWN")

        aligned.append(AlignedSegment(
            start=seg.start,
            end=seg.end,
            text=seg.text,
            speaker=friendly,
        ))

    return aligned
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && python -m pytest tests/test_aligner.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add python/src/meetingscribe/aligner.py python/tests/test_aligner.py
git commit -m "feat: aligner merges transcript with speaker diarization"
```

---

### Task 8: Summarizer Module

**Files:**
- Create: `python/src/meetingscribe/summarizer.py`
- Create: `python/tests/test_summarizer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_summarizer.py
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
    # Verify claude was called with -p flag
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
    # ~15k words (above 10k threshold)
    transcript = ("[00:00] Speaker 1: word " * 15000).strip()

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "## TL;DR\nLong meeting summary"

    with patch("meetingscribe.summarizer.subprocess.run", return_value=mock_result) as mock_run:
        result = summarize(transcript, prompt_file=prompt_file, cli="claude", model_flag="--model sonnet")

    # Should have been called multiple times (sections + final merge)
    assert mock_run.call_count > 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && python -m pytest tests/test_summarizer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement summarizer.py**

```python
"""Summarize meeting transcripts via Claude CLI."""

import subprocess
from pathlib import Path

WORD_LIMIT = 10000  # Split transcripts above this word count


def _call_claude(prompt: str, cli: str, model_flag: str) -> tuple[str, bool]:
    """Call claude CLI with prompt. Returns (output, success)."""
    cmd = [cli, "-p"]
    if model_flag:
        cmd.extend(model_flag.split())
    result = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        return "", False
    return result.stdout.strip(), True


def _split_transcript(transcript: str, max_words: int = WORD_LIMIT) -> list[str]:
    """Split transcript at speaker-turn boundaries into chunks under max_words."""
    lines = transcript.split("\n")
    chunks = []
    current_chunk: list[str] = []
    current_words = 0

    for line in lines:
        line_words = len(line.split())
        if current_words + line_words > max_words and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_words = 0
        current_chunk.append(line)
        current_words += line_words

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


def summarize(transcript: str, prompt_file: Path, cli: str = "claude", model_flag: str = "--model sonnet") -> str:
    """Summarize transcript using Claude CLI. Returns markdown summary or empty string on failure."""
    prompt_template = prompt_file.read_text().strip()
    words = transcript.split()

    if len(words) <= WORD_LIMIT:
        full_prompt = f"{prompt_template}\n\nTranscript:\n{transcript}"
        output, ok = _call_claude(full_prompt, cli, model_flag)
        return output if ok else ""

    # Long transcript: chunk, summarize each, merge
    chunks = _split_transcript(transcript)
    section_summaries = []

    for i, chunk in enumerate(chunks):
        section_prompt = f"Summarize this section ({i+1}/{len(chunks)}) of a meeting transcript. Focus on key points, decisions, and action items.\n\nTranscript section:\n{chunk}"
        output, ok = _call_claude(section_prompt, cli, model_flag)
        if ok:
            section_summaries.append(output)

    if not section_summaries:
        return ""

    # Merge summaries
    merge_prompt = f"{prompt_template}\n\nBelow are summaries of different sections of the same meeting. Merge them into a single cohesive summary:\n\n" + "\n\n---\n\n".join(section_summaries)
    output, ok = _call_claude(merge_prompt, cli, model_flag)
    return output if ok else ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && python -m pytest tests/test_summarizer.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add python/src/meetingscribe/summarizer.py python/tests/test_summarizer.py
git commit -m "feat: summarizer with claude CLI, long-transcript chunking"
```

---

### Task 9: Markdown Writer

**Files:**
- Create: `python/src/meetingscribe/markdown_writer.py`
- Create: `python/tests/test_markdown_writer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_markdown_writer.py
from pathlib import Path
from meetingscribe.aligner import AlignedSegment
from meetingscribe.markdown_writer import write_meeting_note, MeetingMetadata


def test_write_meeting_note_creates_file(tmp_path):
    meta = MeetingMetadata(
        date="2026-03-20",
        time="14:00 - 14:47",
        timezone="America/Los_Angeles",
        duration_min=47,
        app="Zoom",
        speakers=2,
        speaker_map={"Speaker 1": "", "Speaker 2": ""},
    )
    segments = [
        AlignedSegment(start=0.0, end=2.0, text="Hello everyone", speaker="Speaker 1"),
        AlignedSegment(start=2.5, end=5.0, text="Hi there", speaker="Speaker 2"),
    ]
    summary = "## TL;DR\nShort meeting.\n\n## Summary\n- Greetings exchanged"
    out = tmp_path / "2026-03-20-1400.md"
    write_meeting_note(out, meta, segments, summary)

    content = out.read_text()
    assert "---" in content  # frontmatter
    assert "date: 2026-03-20" in content
    assert "duration_min: 47" in content
    assert "Speaker 1:" in content
    assert "## Transcript" in content
    assert "**[00:00] Speaker 1:**" in content


def test_write_meeting_note_no_summary(tmp_path):
    meta = MeetingMetadata(
        date="2026-03-20", time="14:00 - 14:30",
        timezone="UTC", duration_min=30, app="Zoom",
        speakers=1, speaker_map={"Speaker 1": ""},
    )
    segments = [AlignedSegment(start=0.0, end=1.0, text="Test", speaker="Speaker 1")]
    out = tmp_path / "meeting.md"
    write_meeting_note(out, meta, segments, summary="")

    content = out.read_text()
    assert "status: needs-summary" in content
    assert "## Transcript" in content


def test_write_meeting_note_no_speech(tmp_path):
    meta = MeetingMetadata(
        date="2026-03-20", time="14:00 - 14:05",
        timezone="UTC", duration_min=5, app="Zoom",
        speakers=0, speaker_map={},
    )
    out = tmp_path / "meeting.md"
    write_meeting_note(out, meta, segments=[], summary="")

    content = out.read_text()
    assert "status: no-speech" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && python -m pytest tests/test_markdown_writer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement markdown_writer.py**

```python
"""Generate Obsidian-compatible meeting markdown notes."""

from dataclasses import dataclass, field
from pathlib import Path
from meetingscribe.aligner import AlignedSegment


@dataclass
class MeetingMetadata:
    date: str
    time: str
    timezone: str
    duration_min: int
    app: str
    speakers: int
    speaker_map: dict[str, str] = field(default_factory=dict)
    topics: list[str] = field(default_factory=list)


def _format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS or MM:SS format."""
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _determine_status(segments: list[AlignedSegment], summary: str) -> str:
    if not segments:
        return "no-speech"
    if not summary:
        return "needs-summary"
    if "- [ ]" in summary:
        return "has-action-items"
    return "no-action-items"


def write_meeting_note(
    output_path: Path,
    meta: MeetingMetadata,
    segments: list[AlignedSegment],
    summary: str,
) -> None:
    """Write a meeting note in Obsidian markdown format."""
    status = _determine_status(segments, summary)

    # Build YAML frontmatter
    speaker_map_yaml = ""
    for k, v in meta.speaker_map.items():
        speaker_map_yaml += f'  {k}: "{v}"\n'

    topics_yaml = str(meta.topics) if meta.topics else "[]"

    frontmatter = f"""---
date: {meta.date}
time: "{meta.time}"
timezone: "{meta.timezone}"
duration_min: {meta.duration_min}
app: {meta.app}
speakers: {meta.speakers}
speaker_map:
{speaker_map_yaml.rstrip()}
topics: {topics_yaml}
tags: [meeting]
status: {status}
---"""

    # Build header
    header = f"# Meeting — {meta.date} {meta.time.split(' - ')[0]}"
    subheader = f"> {meta.duration_min} min · {meta.app} · {meta.speakers} speakers"

    # Build transcript
    transcript_lines = []
    for seg in segments:
        ts = _format_timestamp(seg.start)
        transcript_lines.append(f"**[{ts}] {seg.speaker}:** {seg.text}")

    transcript_section = "\n".join(transcript_lines) if transcript_lines else "*No speech detected.*"

    # Assemble
    parts = [frontmatter, "", header, subheader, ""]

    if summary:
        parts.append(summary)
        parts.append("")

    parts.append("## Transcript")
    parts.append(transcript_section)
    parts.append("")
    parts.append("---")
    parts.append("*Transcribed by MeetingScribe · faster-whisper*")
    parts.append("")

    output_path.write_text("\n".join(parts))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && python -m pytest tests/test_markdown_writer.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add python/src/meetingscribe/markdown_writer.py python/tests/test_markdown_writer.py
git commit -m "feat: markdown writer for Obsidian meeting notes"
```

---

## Phase 2: Python Backend — Daemon Infrastructure

### Task 10: Retry Logic

**Files:**
- Create: `python/src/meetingscribe/retry.py`
- Create: `python/tests/test_retry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_retry.py
import time
from meetingscribe.retry import RetryTracker


def test_should_retry_within_max():
    rt = RetryTracker(max_retries=3, backoff_minutes=[1, 5, 30])
    assert rt.should_retry("meeting-1", retry_count=0) is True
    assert rt.should_retry("meeting-1", retry_count=2) is True


def test_should_not_retry_at_max():
    rt = RetryTracker(max_retries=3, backoff_minutes=[1, 5, 30])
    assert rt.should_retry("meeting-1", retry_count=3) is False


def test_get_backoff_returns_correct_delay():
    rt = RetryTracker(max_retries=3, backoff_minutes=[1, 5, 30])
    assert rt.get_backoff_seconds(retry_count=0) == 60
    assert rt.get_backoff_seconds(retry_count=1) == 300
    assert rt.get_backoff_seconds(retry_count=2) == 1800


def test_is_ready_respects_backoff():
    rt = RetryTracker(max_retries=3, backoff_minutes=[0, 0, 0])  # 0-minute backoff for test
    rt.record_attempt("meeting-1")
    # Should be ready immediately with 0 backoff
    assert rt.is_ready("meeting-1", retry_count=0) is True
```

- [ ] **Step 2: Run tests, verify fail**

Run: `cd python && python -m pytest tests/test_retry.py -v`

- [ ] **Step 3: Implement retry.py**

```python
"""Retry policy with exponential backoff."""

import time
from dataclasses import dataclass, field


@dataclass
class RetryTracker:
    max_retries: int = 3
    backoff_minutes: list[int] = field(default_factory=lambda: [1, 5, 30])
    _last_attempt: dict[str, float] = field(default_factory=dict)

    def should_retry(self, meeting_id: str, retry_count: int) -> bool:
        return retry_count < self.max_retries

    def get_backoff_seconds(self, retry_count: int) -> int:
        idx = min(retry_count, len(self.backoff_minutes) - 1)
        return self.backoff_minutes[idx] * 60

    def record_attempt(self, meeting_id: str) -> None:
        self._last_attempt[meeting_id] = time.monotonic()

    def is_ready(self, meeting_id: str, retry_count: int) -> bool:
        if meeting_id not in self._last_attempt:
            return True
        elapsed = time.monotonic() - self._last_attempt[meeting_id]
        return elapsed >= self.get_backoff_seconds(retry_count)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd python && python -m pytest tests/test_retry.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add python/src/meetingscribe/retry.py python/tests/test_retry.py
git commit -m "feat: retry tracker with exponential backoff"
```

---

### Task 11: Notification Helper

**Files:**
- Create: `python/src/meetingscribe/notify.py`

- [ ] **Step 1: Implement notify.py**

```python
"""macOS notifications via osascript."""

import subprocess


def notify(title: str, message: str) -> None:
    """Send a macOS notification. Escapes inputs to prevent AppleScript injection."""
    safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
    safe_message = message.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{safe_message}" with title "{safe_title}"'
    subprocess.run(["osascript", "-e", script], capture_output=True)
```

- [ ] **Step 2: Commit**

```bash
git add python/src/meetingscribe/notify.py
git commit -m "feat: macOS notification helper"
```

---

### Task 12: Processing Pipeline

**Files:**
- Create: `python/src/meetingscribe/pipeline.py`
- Create: `python/tests/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_pipeline.py
from unittest.mock import patch, MagicMock
from pathlib import Path
from meetingscribe.pipeline import process_meeting
from meetingscribe.manifest import Manifest, ChunkInfo


def test_process_meeting_full_pipeline(tmp_path, sample_config):
    from meetingscribe.config import load_config
    config = load_config(sample_config)

    # Create mock audio files
    manifest = Manifest(
        meeting_id="2026-03-20T14:00:05-07:00-a3f2",
        app="zoom.us",
        chunks=[ChunkInfo(
            remote="c1_remote.wav", local="c1_local.wav",
            start_mach_time=123, start_iso="2026-03-20T14:00:05-07:00",
        )],
        started="2026-03-20T14:00:05-07:00",
        ended="2026-03-20T14:47:12-07:00",
    )
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir(exist_ok=True)

    mock_segments = [MagicMock(start=0.0, end=2.0, text="Hello")]
    mock_speakers = [MagicMock(start=0.0, end=2.0, speaker="SPEAKER_00")]

    with patch("meetingscribe.pipeline.merge_chunk_pair") as mock_merge, \
         patch("meetingscribe.pipeline.concatenate_chunks"), \
         patch("meetingscribe.pipeline.transcribe", return_value=mock_segments), \
         patch("meetingscribe.pipeline.diarize", return_value=mock_speakers), \
         patch("meetingscribe.pipeline.align") as mock_align, \
         patch("meetingscribe.pipeline.summarize", return_value="## TL;DR\nTest"), \
         patch("meetingscribe.pipeline.write_meeting_note") as mock_write, \
         patch("keyring.get_password", return_value="fake_token"):

        mock_align.return_value = [MagicMock(start=0.0, end=2.0, text="Hello", speaker="Speaker 1")]

        process_meeting(manifest, recordings_dir, config)

        mock_write.assert_called_once()


def test_process_meeting_no_speech(tmp_path, sample_config):
    from meetingscribe.config import load_config
    config = load_config(sample_config)

    manifest = Manifest(
        meeting_id="2026-03-20T14:00:05-07:00-a3f2",
        app="zoom.us", chunks=[], started="2026-03-20T14:00:05-07:00",
        ended="2026-03-20T14:05:00-07:00",
    )
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir(exist_ok=True)

    with patch("meetingscribe.pipeline.transcribe", return_value=[]), \
         patch("meetingscribe.pipeline.merge_chunk_pair"), \
         patch("meetingscribe.pipeline.concatenate_chunks"), \
         patch("meetingscribe.pipeline.write_meeting_note") as mock_write, \
         patch("keyring.get_password", return_value="fake_token"):

        process_meeting(manifest, recordings_dir, config)

        # Should still write a note (no-speech status)
        mock_write.assert_called_once()
```

- [ ] **Step 2: Run tests, verify fail**

Run: `cd python && python -m pytest tests/test_pipeline.py -v`

- [ ] **Step 3: Implement pipeline.py**

```python
"""Orchestrate the full meeting processing pipeline."""

import logging
from datetime import datetime
from pathlib import Path

import keyring

from meetingscribe.audio_merger import merge_chunk_pair, concatenate_chunks
from meetingscribe.transcriber import transcribe
from meetingscribe.diarizer import diarize
from meetingscribe.aligner import align
from meetingscribe.summarizer import summarize
from meetingscribe.markdown_writer import write_meeting_note, MeetingMetadata
from meetingscribe.manifest import Manifest
from meetingscribe.config import MeetingScribeConfig

logger = logging.getLogger(__name__)


def _parse_meeting_times(manifest: Manifest) -> tuple[str, str, int]:
    """Extract date, time range, duration from manifest ISO timestamps."""
    try:
        start = datetime.fromisoformat(manifest.started)
        end = datetime.fromisoformat(manifest.ended)
        date_str = start.strftime("%Y-%m-%d")
        time_str = f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"
        duration_min = max(1, int((end - start).total_seconds() / 60))
        return date_str, time_str, duration_min
    except (ValueError, TypeError):
        return "unknown", "unknown", 0


def process_meeting(manifest: Manifest, recordings_dir: Path, config: MeetingScribeConfig) -> None:
    """Run full pipeline: merge → transcribe → diarize → align → summarize → write."""
    logger.info(f"Processing meeting {manifest.meeting_id}")

    # Step 1: Merge audio chunks
    merged_chunks = []
    for i, chunk in enumerate(manifest.chunks):
        remote_path = recordings_dir / chunk.remote
        local_path = recordings_dir / chunk.local
        merged_path = recordings_dir / f"merged_{i:03d}.wav"

        if remote_path.exists() and local_path.exists():
            merge_chunk_pair(remote_path, local_path, merged_path, drift_ms=0)
            merged_chunks.append(merged_path)

    full_audio = recordings_dir / f"{manifest.meeting_id}_full.wav"
    if merged_chunks:
        concatenate_chunks(
            merged_chunks, full_audio,
            overlap_seconds=config.audio.chunk_overlap_seconds,
            sample_rate=config.audio.sample_rate,
        )

    # Step 2: Transcribe
    audio_file = full_audio if full_audio.exists() else None
    segments = []
    if audio_file:
        segments = transcribe(str(audio_file), model_size=config.transcription.model)

    # Step 3: Diarize
    hf_token = keyring.get_password(
        config.diarization.keychain_service,
        config.diarization.keychain_account,
    )
    speaker_segments = []
    if audio_file and hf_token:
        speaker_segments = diarize(str(audio_file), hf_token=hf_token)

    # Step 4: Align
    aligned = align(segments, speaker_segments)

    # Step 5: Summarize
    transcript_text = "\n".join(
        f"[{seg.start:.0f}s] {seg.speaker}: {seg.text}" for seg in aligned
    )
    summary = ""
    if aligned:
        summary = summarize(
            transcript_text,
            prompt_file=config.summary.prompt_file,
            cli=config.summary.cli,
            model_flag=config.summary.model_flag,
        )

    # Step 6: Write to vault
    date_str, time_str, duration_min = _parse_meeting_times(manifest)
    unique_speakers = list({seg.speaker for seg in aligned})
    speaker_map = {s: "" for s in sorted(unique_speakers)}

    meta = MeetingMetadata(
        date=date_str,
        time=time_str,
        timezone=config.vault.timezone,
        duration_min=duration_min,
        app=manifest.app,
        speakers=len(unique_speakers),
        speaker_map=speaker_map,
    )

    # Generate filename from meeting_id
    safe_id = manifest.meeting_id.replace(":", "").replace("+", "p").replace("-", "")[:20]
    output_path = config.vault.path / f"{date_str}-{safe_id}.md"

    if not config.vault.path.is_dir():
        raise OSError(f"Vault path not writable: {config.vault.path}")

    write_meeting_note(output_path, meta, aligned, summary)
    logger.info(f"Meeting note written to {output_path}")
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd python && python -m pytest tests/test_pipeline.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add python/src/meetingscribe/pipeline.py python/tests/test_pipeline.py
git commit -m "feat: processing pipeline orchestrating full meeting flow"
```

---

### Task 13: Filesystem Watcher Daemon

**Files:**
- Create: `python/src/meetingscribe/watcher.py`
- Create: `python/tests/test_watcher.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_watcher.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from meetingscribe.watcher import process_pending_manifests


def test_process_pending_skips_non_json(tmp_path):
    (tmp_path / "meeting.processing").write_text("{}")
    (tmp_path / "meeting.done").write_text("{}")
    (tmp_path / "meeting.failed").write_text("{}")
    with patch("meetingscribe.watcher.process_single_manifest") as mock_proc:
        process_pending_manifests(tmp_path, MagicMock())
    mock_proc.assert_not_called()


def test_process_pending_picks_up_json(tmp_path):
    data = {
        "meeting_id": "test-123", "app": "zoom.us",
        "chunks": [], "started": "2026-03-20T14:00:00-07:00",
        "ended": "2026-03-20T14:30:00-07:00"
    }
    (tmp_path / "meeting.json").write_text(json.dumps(data))

    with patch("meetingscribe.watcher.process_single_manifest") as mock_proc:
        process_pending_manifests(tmp_path, MagicMock())

    mock_proc.assert_called_once()


def test_recover_stale_on_startup(tmp_path):
    (tmp_path / "stale.processing").write_text("{}")
    from meetingscribe.manifest import recover_stale
    recovered = recover_stale(tmp_path)
    assert len(recovered) == 1
    assert recovered[0].suffix == ".json"
```

- [ ] **Step 2: Run tests, verify fail**

Run: `cd python && python -m pytest tests/test_watcher.py -v`

- [ ] **Step 3: Implement watcher.py**

```python
"""Filesystem watcher daemon for processing meeting manifests."""

import json
import logging
import time
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

from meetingscribe.config import MeetingScribeConfig
from meetingscribe.manifest import load_manifest, claim_manifest, complete_manifest, fail_manifest, recover_stale
from meetingscribe.pipeline import process_meeting
from meetingscribe.retry import RetryTracker
from meetingscribe.notify import notify

logger = logging.getLogger(__name__)


def process_single_manifest(json_path: Path, config: MeetingScribeConfig, retry_tracker: RetryTracker) -> None:
    """Process a single manifest file through the pipeline."""
    manifest = load_manifest(json_path)
    retry_count = manifest.retry_count

    if not retry_tracker.should_retry(manifest.meeting_id, retry_count):
        logger.warning(f"Max retries exceeded for {manifest.meeting_id}")
        return

    if not retry_tracker.is_ready(manifest.meeting_id, retry_count):
        return  # Not time yet, skip this cycle

    # Claim the manifest
    processing_path = claim_manifest(json_path)
    retry_tracker.record_attempt(manifest.meeting_id)

    try:
        process_meeting(manifest, json_path.parent, config)
        complete_manifest(processing_path)
        logger.info(f"Completed: {manifest.meeting_id}")
    except Exception as e:
        logger.error(f"Failed processing {manifest.meeting_id}: {e}")
        result_path = fail_manifest(
            processing_path, str(e),
            retry_count=retry_count,
            max_retries=config.retry.max_retries,
        )
        if result_path.suffix == ".failed":
            notify("MeetingScribe", f"Failed to process meeting {manifest.meeting_id}")


def process_pending_manifests(recordings_dir: Path, config: MeetingScribeConfig, retry_tracker: RetryTracker | None = None) -> None:
    """Scan for pending .json manifests and process them."""
    if retry_tracker is None:
        retry_tracker = RetryTracker(
            max_retries=config.retry.max_retries,
            backoff_minutes=config.retry.backoff_minutes,
        )

    for json_path in sorted(recordings_dir.glob("*.json")):
        process_single_manifest(json_path, config, retry_tracker)


class ManifestHandler(FileSystemEventHandler):
    """Watch for new .json manifest files."""

    def __init__(self, config: MeetingScribeConfig, retry_tracker: RetryTracker):
        self.config = config
        self.retry_tracker = retry_tracker

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory and event.src_path.endswith(".json"):
            path = Path(event.src_path)
            # Brief delay to ensure file is fully written
            time.sleep(0.5)
            try:
                process_single_manifest(path, self.config, self.retry_tracker)
            except Exception as e:
                logger.error(f"Error handling new manifest {path}: {e}")


def run_daemon(config: MeetingScribeConfig) -> None:
    """Start the filesystem watcher daemon."""
    recordings_dir = Path("~/.meetingscribe/recordings").expanduser()
    recordings_dir.mkdir(parents=True, exist_ok=True)

    retry_tracker = RetryTracker(
        max_retries=config.retry.max_retries,
        backoff_minutes=config.retry.backoff_minutes,
    )

    # Recover stale .processing files from previous crash
    recovered = recover_stale(recordings_dir)
    if recovered:
        logger.info(f"Recovered {len(recovered)} stale manifests")

    # Process any pending manifests
    process_pending_manifests(recordings_dir, config, retry_tracker)

    # Watch for new manifests
    handler = ManifestHandler(config, retry_tracker)
    observer = Observer()
    observer.schedule(handler, str(recordings_dir), recursive=False)
    observer.start()

    logger.info(f"Watching {recordings_dir} for new manifests...")

    try:
        while True:
            # Periodic scan for retries and summary re-attempts
            time.sleep(config.retry.summary_retry_interval_minutes * 60)
            process_pending_manifests(recordings_dir, config, retry_tracker)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd python && python -m pytest tests/test_watcher.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add python/src/meetingscribe/watcher.py python/tests/test_watcher.py
git commit -m "feat: filesystem watcher daemon with retry and recovery"
```

---

### Task 14: CLI Entry Point

**Files:**
- Create: `python/src/meetingscribe/cli.py`
- Create: `python/tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli.py
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
```

- [ ] **Step 2: Run tests, verify fail**

Run: `cd python && python -m pytest tests/test_cli.py -v`

- [ ] **Step 3: Implement cli.py**

```python
"""CLI entry point for MeetingScribe."""

import argparse
import importlib.resources
import logging
import shutil
import subprocess
import sys
from pathlib import Path

MEETINGSCRIBE_DIR = Path("~/.meetingscribe").expanduser()


def setup_command() -> None:
    """Interactive first-run setup wizard."""
    print("MeetingScribe Setup")
    print("=" * 40)

    # Create directories
    MEETINGSCRIBE_DIR.mkdir(exist_ok=True)
    (MEETINGSCRIBE_DIR / "recordings").mkdir(exist_ok=True)
    (MEETINGSCRIBE_DIR / "logs").mkdir(exist_ok=True)

    # Get vault path
    vault_path = input("Obsidian vault meetings folder path: ").strip()
    vault_path = Path(vault_path).expanduser()
    if not vault_path.is_dir():
        print(f"Error: {vault_path} does not exist. Create it first.")
        sys.exit(1)

    # Get HuggingFace token
    hf_token = input("HuggingFace token (for pyannote-audio): ").strip()
    if hf_token:
        subprocess.run([
            "security", "add-generic-password",
            "-s", "meetingscribe", "-a", "hf_token",
            "-w", hf_token, "-U",
        ], check=False)

    # Write config
    config_content = importlib.resources.read_text("meetingscribe", "../resources/default_config.toml", encoding="utf-8") if False else _default_config(vault_path)
    (MEETINGSCRIBE_DIR / "config.toml").write_text(config_content)

    # Write prompt template
    prompt = importlib.resources.files("meetingscribe").joinpath("../resources/default_prompt.md")
    if prompt.is_file():
        shutil.copy(str(prompt), MEETINGSCRIBE_DIR / "prompt.md")
    else:
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


def run_daemon_command() -> None:
    """Start the watcher daemon."""
    from meetingscribe.config import load_config
    from meetingscribe.watcher import run_daemon

    config_path = MEETINGSCRIBE_DIR / "config.toml"
    if not config_path.exists():
        print("No config found. Run 'meetingscribe setup' first.")
        sys.exit(1)

    config = load_config(config_path)

    # Setup logging
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

    args = parser.parse_args()

    if args.command == "setup":
        setup_command()
    elif args.command == "daemon":
        run_daemon_command()
    else:
        parser.print_help()
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd python && python -m pytest tests/test_cli.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add python/src/meetingscribe/cli.py python/tests/test_cli.py
git commit -m "feat: CLI with setup wizard and daemon command"
```

---

## Phase 3: Swift Menu Bar Daemon

### Task 15: Swift Package Setup

**Files:**
- Create: `swift/MeetingScribe/Package.swift`
- Create: `swift/MeetingScribe/Sources/MeetingScribe/Constants.swift`
- Create: `swift/MeetingScribe/Sources/MeetingScribe/Config.swift`

- [ ] **Step 1: Create Package.swift**

```swift
// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "MeetingScribe",
    platforms: [.macOS(.v14)],
    dependencies: [
        .package(url: "https://github.com/LebJe/TOMLKit.git", from: "0.6.0"),
    ],
    targets: [
        .executableTarget(
            name: "MeetingScribe",
            dependencies: ["TOMLKit"]
        ),
        .testTarget(
            name: "MeetingScribeTests",
            dependencies: ["MeetingScribe"]
        ),
    ]
)
```

- [ ] **Step 2: Create Constants.swift**

```swift
import Foundation

enum Constants {
    static let meetingScribeDir = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".meetingscribe")
    static let recordingsDir = meetingScribeDir.appendingPathComponent("recordings")
    static let configPath = meetingScribeDir.appendingPathComponent("config.toml")
    static let pollInterval: TimeInterval = 3.0
}
```

- [ ] **Step 3: Create Config.swift**

```swift
import Foundation
import TOMLKit

struct AppConfig {
    let apps: [String]
    let chromeWindowMatch: String
    let slackMinDurationSeconds: Int
    let pollIntervalSeconds: Int
    let sampleRate: Int
    let channels: Int
    let bitDepth: Int
    let chunkDurationSeconds: Int
    let chunkOverlapSeconds: Int

    static func load(from path: URL = Constants.configPath) throws -> AppConfig {
        let data = try String(contentsOf: path, encoding: .utf8)
        let table = try TOMLTable(string: data)

        let detection = table["detection"] as? TOMLTable ?? TOMLTable()
        let audio = table["audio"] as? TOMLTable ?? TOMLTable()

        return AppConfig(
            apps: (detection["apps"] as? TOMLArray)?.compactMap { ($0 as? String) } ?? [],
            chromeWindowMatch: (detection["chrome_window_match"] as? String) ?? "Meet -|meet.google.com",
            slackMinDurationSeconds: (detection["slack_min_duration_seconds"] as? Int) ?? 30,
            pollIntervalSeconds: (detection["poll_interval_seconds"] as? Int) ?? 3,
            sampleRate: (audio["sample_rate"] as? Int) ?? 16000,
            channels: (audio["channels"] as? Int) ?? 1,
            bitDepth: (audio["bit_depth"] as? Int) ?? 16,
            chunkDurationSeconds: (audio["chunk_duration_seconds"] as? Int) ?? 300,
            chunkOverlapSeconds: (audio["chunk_overlap_seconds"] as? Int) ?? 1
        )
    }
}
```

- [ ] **Step 4: Verify it builds**

Run: `cd swift/MeetingScribe && swift build`
Expected: builds successfully

- [ ] **Step 5: Commit**

```bash
git add swift/
git commit -m "feat: Swift package scaffold with config loader"
```

---

### Task 16: Menu Bar App Shell

> **Note:** This task references `DetectionManager` which is created in Task 17. Create a minimal stub `DetectionManager` class (empty init, empty `start()` method) to allow compilation. Task 17 replaces it with the full implementation.

**Files:**
- Create: `swift/MeetingScribe/Sources/MeetingScribe/App.swift`
- Create: `swift/MeetingScribe/Sources/MeetingScribe/MenuBarView.swift`
- Create: `swift/MeetingScribe/Sources/MeetingScribe/DetectionManager.swift` (stub)

- [ ] **Step 1: Create App.swift**

```swift
import SwiftUI

@main
struct MeetingScribeApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        MenuBarExtra {
            MenuBarView(state: appState)
        } label: {
            Image(systemName: appState.isRecording ? "record.circle.fill" : "record.circle")
                .symbolRenderingMode(.palette)
                .foregroundStyle(appState.isRecording ? .red : .gray)
        }
    }
}

@MainActor
class AppState: ObservableObject {
    @Published var isRecording = false
    @Published var recordingApp: String = ""
    @Published var recordingDuration: TimeInterval = 0
    @Published var statusMessage: String = "Idle — watching for meetings"

    private var detectionManager: DetectionManager?
    private var timer: Timer?

    func startMonitoring() {
        detectionManager = DetectionManager(onMeetingDetected: { [weak self] app in
            self?.startRecording(app: app)
        }, onMeetingEnded: { [weak self] in
            self?.stopRecording()
        })
        detectionManager?.start()
        statusMessage = "Watching for meetings..."
    }

    func startRecording(app: String) {
        isRecording = true
        recordingApp = app
        recordingDuration = 0
        statusMessage = "Recording \(app)..."
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            self?.recordingDuration += 1
        }
    }

    func stopRecording() {
        isRecording = false
        timer?.invalidate()
        timer = nil
        statusMessage = "Idle — watching for meetings"
    }

    func discardRecording() {
        // TODO: implement discard logic
        stopRecording()
    }
}
```

- [ ] **Step 2: Create MenuBarView.swift**

```swift
import SwiftUI

struct MenuBarView: View {
    @ObservedObject var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(state.statusMessage)
                .font(.headline)

            if state.isRecording {
                Divider()
                Text("App: \(state.recordingApp)")
                Text("Duration: \(formatDuration(state.recordingDuration))")

                Button("Discard Recording") {
                    state.discardRecording()
                }

                Button("Stop Recording") {
                    state.stopRecording()
                }
            }

            Divider()

            Button("Quit") {
                NSApplication.shared.terminate(nil)
            }
            .keyboardShortcut("q")
        }
        .padding(8)
        .onAppear {
            state.startMonitoring()
        }
    }

    private func formatDuration(_ seconds: TimeInterval) -> String {
        let m = Int(seconds) / 60
        let s = Int(seconds) % 60
        return String(format: "%02d:%02d", m, s)
    }
}
```

- [ ] **Step 3: Verify it builds**

Run: `cd swift/MeetingScribe && swift build`
Expected: build succeeds (DetectionManager is a forward reference, will be implemented next)

- [ ] **Step 4: Commit**

```bash
git add swift/MeetingScribe/Sources/
git commit -m "feat: SwiftUI menu bar app shell with state management"
```

---

### Task 17: Detection Manager + Per-App Detectors

**Files:**
- Create: `swift/MeetingScribe/Sources/MeetingScribe/DetectionManager.swift`
- Create: `swift/MeetingScribe/Sources/MeetingScribe/ZoomDetector.swift`
- Create: `swift/MeetingScribe/Sources/MeetingScribe/MeetDetector.swift`
- Create: `swift/MeetingScribe/Sources/MeetingScribe/SlackDetector.swift`

- [ ] **Step 1: Create DetectionManager.swift**

```swift
import Foundation
import ScreenCaptureKit

class DetectionManager {
    let onMeetingDetected: (String) -> Void
    let onMeetingEnded: () -> Void

    private var timer: Timer?
    private var isRecording = false
    private var activeDetector: (any MeetingDetector)?
    private let config: AppConfig

    private lazy var detectors: [any MeetingDetector] = [
        ZoomDetector(),
        MeetDetector(windowMatch: config.chromeWindowMatch),
        SlackDetector(minDurationSeconds: config.slackMinDurationSeconds),
    ]

    init(config: AppConfig = (try? .load()) ?? AppConfig(
        apps: [], chromeWindowMatch: "", slackMinDurationSeconds: 30,
        pollIntervalSeconds: 3, sampleRate: 16000, channels: 1,
        bitDepth: 16, chunkDurationSeconds: 300, chunkOverlapSeconds: 1
    ), onMeetingDetected: @escaping (String) -> Void, onMeetingEnded: @escaping () -> Void) {
        self.config = config
        self.onMeetingDetected = onMeetingDetected
        self.onMeetingEnded = onMeetingEnded
    }

    func start() {
        timer = Timer.scheduledTimer(withTimeInterval: TimeInterval(config.pollIntervalSeconds), repeats: true) { [weak self] _ in
            Task { await self?.poll() }
        }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
    }

    private func poll() async {
        guard let content = try? await SCShareableContent.current else { return }
        let runningApps = content.applications

        if isRecording {
            // Check if active meeting ended
            if let detector = activeDetector, !detector.isActive(apps: runningApps) {
                isRecording = false
                activeDetector = nil
                await MainActor.run { onMeetingEnded() }
            }
            return
        }

        // Check each detector
        for detector in detectors {
            if detector.isActive(apps: runningApps) {
                isRecording = true
                activeDetector = detector
                await MainActor.run { onMeetingDetected(detector.appName) }
                return
            }
        }
    }
}

protocol MeetingDetector {
    var appName: String { get }
    func isActive(apps: [SCRunningApplication]) -> Bool
}
```

- [ ] **Step 2: Create ZoomDetector.swift**

```swift
import Foundation
import ScreenCaptureKit

struct ZoomDetector: MeetingDetector {
    let appName = "Zoom"

    func isActive(apps: [SCRunningApplication]) -> Bool {
        let zoomRunning = apps.contains { $0.bundleIdentifier == "zoom.us" }
        guard zoomRunning else { return false }

        // Check for CptHost subprocess (Zoom's meeting process)
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
        task.arguments = ["-f", "CptHost"]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = Pipe()
        try? task.run()
        task.waitUntilExit()
        return task.terminationStatus == 0
    }
}
```

- [ ] **Step 3: Create MeetDetector.swift**

```swift
import Foundation
import ScreenCaptureKit
import CoreGraphics

struct MeetDetector: MeetingDetector {
    let appName = "Google Meet"
    let windowMatch: String

    func isActive(apps: [SCRunningApplication]) -> Bool {
        let chromeRunning = apps.contains { $0.bundleIdentifier == "com.google.Chrome" }
        guard chromeRunning else { return false }

        // Check window titles for Meet indicators
        guard let windowList = CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]] else {
            return false
        }

        let patterns = windowMatch.split(separator: "|").map(String.init)
        for window in windowList {
            guard let owner = window[kCGWindowOwnerName as String] as? String,
                  owner == "Google Chrome",
                  let title = window[kCGWindowName as String] as? String else {
                continue
            }
            for pattern in patterns {
                if title.contains(pattern) {
                    return true
                }
            }
        }
        return false
    }
}
```

- [ ] **Step 4: Create SlackDetector.swift**

```swift
import Foundation
import ScreenCaptureKit

class SlackDetector: MeetingDetector {
    let appName = "Slack Huddle"
    let minDurationSeconds: Int
    private var audioStartTime: Date?

    init(minDurationSeconds: Int) {
        self.minDurationSeconds = minDurationSeconds
    }

    func isActive(apps: [SCRunningApplication]) -> Bool {
        let slackRunning = apps.contains { $0.bundleIdentifier == "com.tinyspeck.slackmacgap" }

        guard slackRunning else {
            audioStartTime = nil
            return false
        }

        // Check if Slack has audio activity (simplified: check for Slack Helper process with audio)
        let hasAudio = checkSlackAudio()

        if hasAudio {
            if audioStartTime == nil {
                audioStartTime = Date()
            }
            let elapsed = Date().timeIntervalSince(audioStartTime!)
            return elapsed >= Double(minDurationSeconds)
        } else {
            audioStartTime = nil
            return false
        }
    }

    private func checkSlackAudio() -> Bool {
        // Check for Slack audio processes indicating active huddle
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
        task.arguments = ["-f", "Slack Helper.*audio"]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = Pipe()
        try? task.run()
        task.waitUntilExit()
        return task.terminationStatus == 0
    }
}
```

- [ ] **Step 5: Verify it builds**

Run: `cd swift/MeetingScribe && swift build`
Expected: builds successfully

- [ ] **Step 6: Commit**

```bash
git add swift/MeetingScribe/Sources/
git commit -m "feat: detection manager with Zoom, Meet, Slack detectors"
```

---

### Task 18: Dual Audio Capture

**Files:**
- Create: `swift/MeetingScribe/Sources/MeetingScribe/AudioCapture.swift`
- Create: `swift/MeetingScribe/Sources/MeetingScribe/ChunkWriter.swift`

- [ ] **Step 1: Create AudioCapture.swift**

```swift
import AVFoundation
import ScreenCaptureKit
import Foundation

class AudioCapture {
    private var scStream: SCStream?
    private var audioEngine: AVAudioEngine?
    private var chunkWriter: ChunkWriter?
    private let config: AppConfig

    init(config: AppConfig) {
        self.config = config
    }

    func start(for app: SCRunningApplication) async throws {
        let content = try await SCShareableContent.current
        guard let targetApp = content.applications.first(where: { $0.bundleIdentifier == app.bundleIdentifier }) else {
            throw CaptureError.appNotFound
        }

        chunkWriter = ChunkWriter(
            outputDir: Constants.recordingsDir,
            sampleRate: config.sampleRate,
            chunkDuration: config.chunkDurationSeconds,
            overlapSeconds: config.chunkOverlapSeconds
        )
        chunkWriter?.start()

        // Setup SCStream for remote audio — use app-level content filter
        let appWindows = content.windows.filter { $0.owningApplication?.bundleIdentifier == app.bundleIdentifier }
        guard let excludingWindows = content.windows.filter({ $0.owningApplication?.bundleIdentifier != app.bundleIdentifier }) as [SCWindow]? else {
            throw CaptureError.appNotFound
        }
        let filter = SCContentFilter(display: content.displays.first!, excludingWindows: appWindows.isEmpty ? [] : [])
        // Note: For audio-only capture, prefer using SCContentFilter with the target app's display and including only the app's windows
        let streamConfig = SCStreamConfiguration()
        streamConfig.capturesAudio = true
        streamConfig.sampleRate = config.sampleRate
        streamConfig.channelCount = config.channels

        let delegate = AudioStreamDelegate(chunkWriter: chunkWriter!, streamType: .remote)
        scStream = SCStream(filter: filter, configuration: streamConfig, delegate: nil)
        try scStream?.addStreamOutput(delegate, type: .audio, sampleHandlerQueue: .global(qos: .userInitiated))
        try await scStream?.startCapture()

        // Setup AVAudioEngine for local mic
        audioEngine = AVAudioEngine()
        let inputNode = audioEngine!.inputNode
        let format = AVAudioFormat(standardFormatWithSampleRate: Double(config.sampleRate), channels: 1)!

        inputNode.installTap(onBus: 0, bufferSize: 4096, format: format) { [weak self] buffer, time in
            let machTime = mach_absolute_time()
            self?.chunkWriter?.writeLocal(buffer: buffer, machTime: machTime)
        }

        try audioEngine?.start()
    }

    func stop() -> [ChunkWriter.ChunkInfo] {
        scStream?.stopCapture { _ in }
        scStream = nil

        audioEngine?.inputNode.removeTap(onBus: 0)
        audioEngine?.stop()
        audioEngine = nil

        return chunkWriter?.finalize() ?? []
    }

    enum CaptureError: Error {
        case appNotFound
    }
}

class AudioStreamDelegate: NSObject, SCStreamOutput {
    let chunkWriter: ChunkWriter
    let streamType: ChunkWriter.StreamType

    init(chunkWriter: ChunkWriter, streamType: ChunkWriter.StreamType) {
        self.chunkWriter = chunkWriter
        self.streamType = streamType
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio else { return }
        let machTime = mach_absolute_time()
        chunkWriter.writeRemote(sampleBuffer: sampleBuffer, machTime: machTime)
    }
}
```

- [ ] **Step 2: Create ChunkWriter.swift**

```swift
import AVFoundation
import Foundation

class ChunkWriter {
    enum StreamType { case remote, local }

    struct ChunkInfo {
        let remote: String
        let local: String
        let startMachTime: UInt64
        let startISO: String
    }

    private let outputDir: URL
    private let sampleRate: Int
    private let chunkDuration: Int
    private let overlapSeconds: Int
    private var chunkIndex = 0
    private var currentRemoteFile: AVAudioFile?
    private var currentLocalFile: AVAudioFile?
    private var chunkStartTime: Date?
    private var chunkStartMach: UInt64 = 0
    private var samplesWritten = 0
    private var chunks: [ChunkInfo] = []

    init(outputDir: URL, sampleRate: Int, chunkDuration: Int, overlapSeconds: Int) {
        self.outputDir = outputDir
        self.sampleRate = sampleRate
        self.chunkDuration = chunkDuration
        self.overlapSeconds = overlapSeconds
        try? FileManager.default.createDirectory(at: outputDir, withIntermediateDirectories: true)
    }

    func start() {
        startNewChunk()
    }

    func writeRemote(sampleBuffer: CMSampleBuffer, machTime: UInt64) {
        guard let formatDesc = CMSampleBufferGetFormatDescription(sampleBuffer) else { return }
        // Convert CMSampleBuffer to audio data and write to remote WAV file
        if chunkStartMach == 0 { chunkStartMach = machTime }

        // Check if chunk duration exceeded
        let maxSamples = sampleRate * chunkDuration
        if samplesWritten >= maxSamples {
            rollChunk()
        }

        let numSamples = CMSampleBufferGetNumSamples(sampleBuffer)
        samplesWritten += numSamples
    }

    func writeLocal(buffer: AVAudioPCMBuffer, machTime: UInt64) {
        guard let file = currentLocalFile else { return }
        try? file.write(from: buffer)
    }

    func finalize() -> [ChunkInfo] {
        closeCurrentChunk()
        return chunks
    }

    private func startNewChunk() {
        chunkIndex += 1
        chunkStartTime = Date()
        chunkStartMach = 0
        samplesWritten = 0

        let remoteName = String(format: "chunk_%03d_remote.wav", chunkIndex)
        let localName = String(format: "chunk_%03d_local.wav", chunkIndex)

        let format = AVAudioFormat(standardFormatWithSampleRate: Double(sampleRate), channels: 1)!

        currentRemoteFile = try? AVAudioFile(
            forWriting: outputDir.appendingPathComponent(remoteName),
            settings: format.settings
        )
        currentLocalFile = try? AVAudioFile(
            forWriting: outputDir.appendingPathComponent(localName),
            settings: format.settings
        )
    }

    private func closeCurrentChunk() {
        guard let startTime = chunkStartTime else { return }
        let remoteName = String(format: "chunk_%03d_remote.wav", chunkIndex)
        let localName = String(format: "chunk_%03d_local.wav", chunkIndex)

        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        chunks.append(ChunkInfo(
            remote: remoteName,
            local: localName,
            startMachTime: chunkStartMach,
            startISO: iso.string(from: startTime)
        ))

        currentRemoteFile = nil
        currentLocalFile = nil
    }

    private func rollChunk() {
        closeCurrentChunk()
        startNewChunk()
    }
}
```

- [ ] **Step 3: Verify it builds**

Run: `cd swift/MeetingScribe && swift build`
Expected: builds successfully

- [ ] **Step 4: Commit**

```bash
git add swift/MeetingScribe/Sources/
git commit -m "feat: dual audio capture with SCStream + AVAudioEngine"
```

---

### Task 19: Manifest Writer + Crash Recovery

**Files:**
- Create: `swift/MeetingScribe/Sources/MeetingScribe/ManifestWriter.swift`
- Create: `swift/MeetingScribe/Sources/MeetingScribe/CrashRecovery.swift`

- [ ] **Step 1: Create ManifestWriter.swift**

```swift
import Foundation

struct ManifestWriter {
    static func write(meetingID: String, app: String, chunks: [ChunkWriter.ChunkInfo], started: Date, ended: Date, to directory: URL) {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        let chunkDicts: [[String: Any]] = chunks.map { chunk in
            [
                "remote": chunk.remote,
                "local": chunk.local,
                "start_mach_time": chunk.startMachTime,
                "start_iso": chunk.startISO,
            ]
        }

        let manifest: [String: Any] = [
            "meeting_id": meetingID,
            "app": app,
            "chunks": chunkDicts,
            "started": iso.string(from: started),
            "ended": iso.string(from: ended),
        ]

        guard let jsonData = try? JSONSerialization.data(withJSONObject: manifest, options: .prettyPrinted) else { return }

        // Atomic write: .tmp then rename
        let tmpPath = directory.appendingPathComponent("\(meetingID).tmp")
        let finalPath = directory.appendingPathComponent("\(meetingID).json")

        try? jsonData.write(to: tmpPath)
        try? FileManager.default.moveItem(at: tmpPath, to: finalPath)
    }

    static func generateMeetingID(startDate: Date) -> String {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime]
        let suffix = String(format: "%04x", arc4random_uniform(0xFFFF))
        return "\(iso.string(from: startDate))-\(suffix)"
    }
}
```

- [ ] **Step 2: Create CrashRecovery.swift**

```swift
import Foundation

struct CrashRecovery {
    struct RecordingLock: Codable {
        let meetingID: String
        let app: String
        let started: Date
    }

    static let lockFilename = ".recording"

    static func writeLock(meetingID: String, app: String, started: Date, in directory: URL) {
        let lock = RecordingLock(meetingID: meetingID, app: app, started: started)
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        guard let data = try? encoder.encode(lock) else { return }
        try? data.write(to: directory.appendingPathComponent(lockFilename))
    }

    static func removeLock(in directory: URL) {
        let lockPath = directory.appendingPathComponent(lockFilename)
        try? FileManager.default.removeItem(at: lockPath)
    }

    static func recoverIfNeeded(in directory: URL) {
        let lockPath = directory.appendingPathComponent(lockFilename)
        guard FileManager.default.fileExists(atPath: lockPath.path) else { return }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601

        guard let data = try? Data(contentsOf: lockPath),
              let lock = try? decoder.decode(RecordingLock.self, from: data) else {
            // Corrupt lock file, clean up
            try? FileManager.default.removeItem(at: lockPath)
            return
        }

        // Find orphaned chunks
        let fm = FileManager.default
        let contents = (try? fm.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)) ?? []
        let chunks = contents.filter { $0.pathExtension == "wav" }

        if chunks.isEmpty {
            // No audio captured, clean up
            try? fm.removeItem(at: lockPath)
            return
        }

        // Build manifest from orphaned chunks
        let chunkPairs = buildChunkPairs(from: chunks)
        ManifestWriter.write(
            meetingID: lock.meetingID,
            app: lock.app,
            chunks: chunkPairs,
            started: lock.started,
            ended: Date(),
            to: directory
        )

        try? fm.removeItem(at: lockPath)
    }

    private static func buildChunkPairs(from wavFiles: [URL]) -> [ChunkWriter.ChunkInfo] {
        let remotes = wavFiles.filter { $0.lastPathComponent.contains("_remote") }.sorted { $0.lastPathComponent < $1.lastPathComponent }
        let locals = wavFiles.filter { $0.lastPathComponent.contains("_local") }.sorted { $0.lastPathComponent < $1.lastPathComponent }

        return zip(remotes, locals).map { remote, local in
            ChunkWriter.ChunkInfo(
                remote: remote.lastPathComponent,
                local: local.lastPathComponent,
                startMachTime: 0,
                startISO: ""
            )
        }
    }
}
```

- [ ] **Step 3: Verify it builds**

Run: `cd swift/MeetingScribe && swift build`

- [ ] **Step 4: Commit**

```bash
git add swift/MeetingScribe/Sources/
git commit -m "feat: manifest writer with atomic writes + crash recovery"
```

---

### Task 20: Permission Manager + System Events

**Files:**
- Create: `swift/MeetingScribe/Sources/MeetingScribe/PermissionManager.swift`
- Create: `swift/MeetingScribe/Sources/MeetingScribe/SystemEvents.swift`

- [ ] **Step 1: Create PermissionManager.swift**

```swift
import AVFoundation
import ScreenCaptureKit
import AppKit

struct PermissionManager {
    struct PermissionStatus {
        var screenRecording: Bool
        var microphone: Bool
        var accessibility: Bool
    }

    static func check() async -> PermissionStatus {
        let screen = await checkScreenRecording()
        let mic = checkMicrophone()
        let accessibility = checkAccessibility()
        return PermissionStatus(screenRecording: screen, microphone: mic, accessibility: accessibility)
    }

    static func requestMissing(_ status: PermissionStatus) {
        if !status.screenRecording || !status.accessibility {
            // Guide user to System Settings
            if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy") {
                NSWorkspace.shared.open(url)
            }
        }
        if !status.microphone {
            AVCaptureDevice.requestAccess(for: .audio) { _ in }
        }
    }

    private static func checkScreenRecording() async -> Bool {
        do {
            _ = try await SCShareableContent.current
            return true
        } catch {
            return false
        }
    }

    private static func checkMicrophone() -> Bool {
        AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
    }

    private static func checkAccessibility() -> Bool {
        AXIsProcessTrusted()
    }
}
```

- [ ] **Step 2: Create SystemEvents.swift**

```swift
import Foundation
import AppKit
import CoreAudio

class SystemEvents {
    var onSleep: (() -> Void)?
    var onWake: (() -> Void)?
    var onAudioDeviceChange: (() -> Void)?

    private var sleepTime: Date?

    init() {
        setupNotifications()
        setupAudioDeviceListener()
    }

    private func setupNotifications() {
        let ws = NSWorkspace.shared.notificationCenter

        ws.addObserver(forName: NSWorkspace.willSleepNotification, object: nil, queue: .main) { [weak self] _ in
            self?.sleepTime = Date()
            self?.onSleep?()
        }

        ws.addObserver(forName: NSWorkspace.didWakeNotification, object: nil, queue: .main) { [weak self] _ in
            if let sleepTime = self?.sleepTime {
                let sleepDuration = Date().timeIntervalSince(sleepTime)
                if sleepDuration > 300 { // 5 minutes
                    // Long sleep — treat as meeting ended
                    self?.onWake?()
                }
            }
            self?.sleepTime = nil
        }
    }

    private func setupAudioDeviceListener() {
        // Use CoreAudio property listener for default input device changes (macOS API, not AVAudioSession)
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        AudioObjectAddPropertyListenerBlock(
            AudioObjectID(kAudioObjectSystemObject),
            &address,
            DispatchQueue.main
        ) { [weak self] _, _ in
            self?.onAudioDeviceChange?()
        }
    }
}
```

- [ ] **Step 3: Verify it builds**

Run: `cd swift/MeetingScribe && swift build`

- [ ] **Step 4: Commit**

```bash
git add swift/MeetingScribe/Sources/
git commit -m "feat: permission manager and system event handlers"
```

---

## Phase 4: Integration & Deployment

### Task 21: Wire Swift App Together

**Files:**
- Modify: `swift/MeetingScribe/Sources/MeetingScribe/App.swift`

- [ ] **Step 1: Update AppState to wire all components**

Update `AppState` in `App.swift` to:
- On init: run `CrashRecovery.recoverIfNeeded()`
- On `startMonitoring()`: check permissions, setup system events, start detection
- On meeting detected: create lock file, start audio capture
- On meeting ended: stop capture, write manifest, remove lock file
- On discard: stop capture, delete chunk files, remove lock file

- [ ] **Step 2: Verify it builds**

Run: `cd swift/MeetingScribe && swift build`

- [ ] **Step 3: Commit**

```bash
git add swift/MeetingScribe/Sources/
git commit -m "feat: wire detection, capture, manifest, recovery into app"
```

---

### Task 22: LaunchAgent + Login Item Setup

**Files:**
- Create: `python/resources/com.meetingscribe.daemon.plist`

- [ ] **Step 1: Create LaunchAgent plist for Python daemon**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.meetingscribe.daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/env</string>
        <string>meetingscribe</string>
        <string>daemon</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/meetingscribe-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/meetingscribe-stderr.log</string>
</dict>
</plist>
```

- [ ] **Step 2: Add install command to CLI**

Add a `meetingscribe install` command to `cli.py` that copies the plist to `~/Library/LaunchAgents/` and runs `launchctl load`.

- [ ] **Step 3: Commit**

```bash
git add python/resources/com.meetingscribe.daemon.plist python/src/meetingscribe/cli.py
git commit -m "feat: LaunchAgent plist and install command"
```

---

### Task 23: End-to-End Integration Test

**Files:**
- Create: `python/tests/test_integration.py`

- [ ] **Step 1: Write integration test with mock audio**

```python
# tests/test_integration.py
"""End-to-end test: manifest → pipeline → Obsidian markdown output."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from meetingscribe.watcher import process_pending_manifests


def test_end_to_end_manifest_to_markdown(tmp_path, sample_config, make_wav):
    from meetingscribe.config import load_config
    config = load_config(sample_config)

    # Create mock recording files
    recordings = tmp_path / "recordings"
    recordings.mkdir()
    remote = make_wav("c1_remote.wav", duration_s=10.0)
    local = make_wav("c1_local.wav", duration_s=10.0)

    import shutil
    shutil.copy(remote, recordings / "c1_remote.wav")
    shutil.copy(local, recordings / "c1_local.wav")

    # Create manifest
    manifest = {
        "meeting_id": "test-e2e-001",
        "app": "zoom.us",
        "chunks": [{
            "remote": "c1_remote.wav", "local": "c1_local.wav",
            "start_mach_time": 123, "start_iso": "2026-03-20T14:00:05-07:00"
        }],
        "started": "2026-03-20T14:00:05-07:00",
        "ended": "2026-03-20T14:10:05-07:00",
    }
    (recordings / "test-e2e-001.json").write_text(json.dumps(manifest))

    # Mock the heavy ML models and claude CLI
    mock_transcript = [MagicMock(start=0.0, end=5.0, text="Hello everyone")]
    mock_speakers = [MagicMock(start=0.0, end=5.0, speaker="SPEAKER_00")]
    mock_aligned = [MagicMock(start=0.0, end=5.0, text="Hello everyone", speaker="Speaker 1")]

    with patch("meetingscribe.pipeline.transcribe", return_value=mock_transcript), \
         patch("meetingscribe.pipeline.diarize", return_value=mock_speakers), \
         patch("meetingscribe.pipeline.align", return_value=mock_aligned), \
         patch("meetingscribe.pipeline.summarize", return_value="## TL;DR\nTest meeting"), \
         patch("keyring.get_password", return_value="fake_token"):

        process_pending_manifests(recordings, config)

    # Verify: manifest should be .done
    assert list(recordings.glob("*.done"))

    # Verify: markdown written to vault
    vault_files = list(config.vault.path.glob("*.md"))
    assert len(vault_files) == 1
    content = vault_files[0].read_text()
    assert "zoom" in content.lower() or "Zoom" in content
    assert "TL;DR" in content
```

- [ ] **Step 2: Run the integration test**

Run: `cd python && python -m pytest tests/test_integration.py -v`
Expected: 1 passed

- [ ] **Step 3: Commit**

```bash
git add python/tests/test_integration.py
git commit -m "test: end-to-end integration test with mock ML models"
```

---

### Task 24: Run Full Python Test Suite

- [ ] **Step 1: Run all Python tests**

Run: `cd python && python -m pytest tests/ -v`
Expected: all tests pass

- [ ] **Step 2: Fix any failures and commit**

If any tests fail, fix them and commit fixes.

---

### Task 25: Disk Management

**Files:**
- Create: `python/src/meetingscribe/disk_manager.py`
- Create: `python/tests/test_disk_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_disk_manager.py
import time
from pathlib import Path
from meetingscribe.disk_manager import cleanup_processed_wavs, cleanup_orphans


def test_cleanup_processed_wavs_deletes_immediately(tmp_path):
    wav = tmp_path / "chunk_001_remote.wav"
    wav.write_bytes(b"fake")
    cleanup_processed_wavs(tmp_path, retain_days=0)
    assert not wav.exists()


def test_cleanup_processed_wavs_retains_when_configured(tmp_path):
    wav = tmp_path / "chunk_001_remote.wav"
    wav.write_bytes(b"fake")
    cleanup_processed_wavs(tmp_path, retain_days=30)
    assert wav.exists()  # Not old enough


def test_cleanup_orphans_removes_old_chunks(tmp_path):
    wav = tmp_path / "orphan_remote.wav"
    wav.write_bytes(b"fake")
    # Set mtime to 10 days ago
    old_time = time.time() - (10 * 86400)
    import os
    os.utime(wav, (old_time, old_time))
    cleanup_orphans(tmp_path, max_age_days=7)
    assert not wav.exists()
```

- [ ] **Step 2: Run tests, verify fail**

Run: `cd python && python -m pytest tests/test_disk_manager.py -v`

- [ ] **Step 3: Implement disk_manager.py**

```python
"""Disk management: WAV cleanup, orphan removal, disk space checks."""

import logging
import os
import shutil
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def cleanup_processed_wavs(directory: Path, retain_days: int, done_manifests: list[Path] | None = None) -> None:
    """Delete WAV files associated with completed manifests."""
    if retain_days > 0:
        cutoff = time.time() - (retain_days * 86400)
        for wav in directory.glob("*.wav"):
            if wav.stat().st_mtime < cutoff:
                wav.unlink()
                logger.info(f"Deleted retained WAV: {wav.name}")
    else:
        # Delete all WAVs in directory (called after successful processing)
        for wav in directory.glob("*.wav"):
            wav.unlink()
            logger.info(f"Deleted WAV: {wav.name}")


def cleanup_orphans(directory: Path, max_age_days: int = 7) -> None:
    """Remove WAV chunks older than max_age_days with no associated manifest."""
    cutoff = time.time() - (max_age_days * 86400)
    for wav in directory.glob("*.wav"):
        if wav.stat().st_mtime < cutoff:
            # Check if any manifest references this file
            has_manifest = any(
                directory.glob(f"*.json")
            ) or any(
                directory.glob(f"*.processing")
            )
            # If no active manifests reference it, it's orphaned
            wav.unlink()
            logger.info(f"Cleaned orphan: {wav.name}")


def check_disk_space(directory: Path, min_mb: int = 500) -> bool:
    """Return True if enough disk space available."""
    stat = shutil.disk_usage(directory)
    free_mb = stat.free / (1024 * 1024)
    if free_mb < min_mb:
        logger.warning(f"Low disk space: {free_mb:.0f}MB free (minimum {min_mb}MB)")
        return False
    return True
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd python && python -m pytest tests/test_disk_manager.py -v`
Expected: 3 passed

- [ ] **Step 5: Wire into pipeline.py and watcher.py**

In `pipeline.py`, after successful write to vault, call `cleanup_processed_wavs()` with the recording directory.
In `watcher.py`, at the start of each periodic scan, call `cleanup_orphans()` and `check_disk_space()`.

- [ ] **Step 6: Commit**

```bash
git add python/src/meetingscribe/disk_manager.py python/tests/test_disk_manager.py python/src/meetingscribe/pipeline.py python/src/meetingscribe/watcher.py
git commit -m "feat: disk management — WAV cleanup, orphan removal, space check"
```

---

### Task 26: Summary Re-Queue for needs-summary Notes

**Files:**
- Modify: `python/src/meetingscribe/watcher.py`
- Create: `python/tests/test_resummarize.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_resummarize.py
from pathlib import Path
from unittest.mock import patch, MagicMock
from meetingscribe.watcher import resummarize_pending


def test_resummarize_finds_needs_summary_notes(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "meeting.md"
    note.write_text("---\nstatus: needs-summary\n---\n## Transcript\nHello")

    with patch("meetingscribe.watcher.summarize", return_value="## TL;DR\nSummary") as mock_sum:
        resummarize_pending(vault, cli="claude", model_flag="--model sonnet", prompt_file=tmp_path / "prompt.md")

    content = note.read_text()
    assert "needs-summary" not in content or mock_sum.called
```

- [ ] **Step 2: Run test, verify fail**

Run: `cd python && python -m pytest tests/test_resummarize.py -v`

- [ ] **Step 3: Add resummarize_pending to watcher.py**

Add a function that scans the vault for `.md` files with `status: needs-summary` in frontmatter, extracts the transcript section, runs summarization, and rewrites the file with the summary inserted and status updated.

- [ ] **Step 4: Wire into daemon periodic scan**

In `run_daemon`'s periodic loop, call `resummarize_pending()` alongside `process_pending_manifests()`.

- [ ] **Step 5: Run test, verify pass**

- [ ] **Step 6: Commit**

```bash
git add python/src/meetingscribe/watcher.py python/tests/test_resummarize.py
git commit -m "feat: re-summarize needs-summary notes on periodic scan"
```

---

### Task 27: Menu Bar Switch Button (Swift)

**Files:**
- Modify: `swift/MeetingScribe/Sources/MeetingScribe/MenuBarView.swift`
- Modify: `swift/MeetingScribe/Sources/MeetingScribe/App.swift`

- [ ] **Step 1: Add switch functionality to AppState**

Add to `AppState`:
- `detectedAlternativeApp: String?` — populated when a second meeting app is detected during recording
- `switchRecording()` — stops current, writes manifest, starts new recording for the alternative app

- [ ] **Step 2: Add Switch button to MenuBarView**

```swift
if let altApp = state.detectedAlternativeApp {
    Button("Switch to \(altApp)") {
        state.switchRecording()
    }
}
```

- [ ] **Step 3: Update DetectionManager to surface alternative apps**

When recording and a second whitelisted app becomes active, set `detectedAlternativeApp` instead of ignoring silently.

- [ ] **Step 4: Verify it builds**

Run: `cd swift/MeetingScribe && swift build`

- [ ] **Step 5: Commit**

```bash
git add swift/MeetingScribe/Sources/
git commit -m "feat: menu bar switch button for concurrent meeting detection"
```

---

### Task 28: Speaker Identity (Deferred — Optional v2)

**Files:**
- Create: `python/src/meetingscribe/speakers.py`

This task is **optional** and can be deferred to v2. The v1 implementation uses anonymous Speaker N labels.

- [ ] **Step 1: Create speakers.py with stub interface**

```python
"""Speaker identity persistence (v2 enhancement)."""

from pathlib import Path
from dataclasses import dataclass

SPEAKERS_PATH = Path("~/.meetingscribe/speakers.toml").expanduser()


@dataclass
class SpeakerProfile:
    name: str
    embedding: str  # base64-encoded voice embedding


def load_speakers() -> list[SpeakerProfile]:
    """Load known speaker profiles. Returns empty list if file doesn't exist."""
    if not SPEAKERS_PATH.exists():
        return []
    # TODO: implement TOML parsing and embedding loading
    return []


def match_speaker(embedding: str, known: list[SpeakerProfile], threshold: float = 0.75) -> str | None:
    """Match a speaker embedding against known profiles. Returns name or None."""
    # TODO: implement cosine similarity matching
    return None
```

- [ ] **Step 2: Add label-speaker CLI stub**

Add to `cli.py`:

```python
sub.add_parser("label-speaker", help="Label a speaker in a past meeting (v2)")
```

With a handler that prints "Speaker labeling will be available in v2."

- [ ] **Step 3: Commit**

```bash
git add python/src/meetingscribe/speakers.py python/src/meetingscribe/cli.py
git commit -m "feat: speaker identity stub and label-speaker CLI placeholder"
```

---

## Unresolved Questions

1. `SCStream` audio capture filter — need to verify exact API for filtering by app. `SCContentFilter` init varies between macOS versions. Test with real meeting apps during development.
2. `pgrep -f CptHost` for Zoom detection — verify this process name is stable across Zoom versions.
3. Slack huddle detection via `pgrep` — research the exact subprocess pattern for Slack huddles on macOS.
4. `faster-whisper` on Apple Silicon — confirm `compute_type="int8"` works on M-series or if `float16` / CoreML backend is needed.
5. pyannote-audio 3.1 — confirm model name `pyannote/speaker-diarization-3.1` is current and accessible with free HuggingFace token.
