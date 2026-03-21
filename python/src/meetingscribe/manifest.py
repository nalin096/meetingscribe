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
            except json.JSONDecodeError:
                pass
        data["_retry_count"] = retry_count + 1
        path.write_text(json.dumps(data, indent=2))
        return _atomic_rename(path, ".json")


def recover_stale(directory: Path) -> list[Path]:
    """Find .processing files (stale from crash) and reset to .json."""
    recovered = []
    for p in directory.glob("*.processing"):
        new_path = _atomic_rename(p, ".json")
        recovered.append(new_path)
    return recovered
