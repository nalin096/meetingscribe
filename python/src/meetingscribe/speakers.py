"""Speaker identity persistence (v2 enhancement)."""

from pathlib import Path
from dataclasses import dataclass

SPEAKERS_PATH = Path("~/.meetingscribe/speakers.toml").expanduser()


@dataclass
class SpeakerProfile:
    name: str
    embedding: str


def load_speakers() -> list[SpeakerProfile]:
    """Load known speaker profiles. Returns empty list if file doesn't exist."""
    if not SPEAKERS_PATH.exists():
        return []
    return []


def match_speaker(embedding: str, known: list[SpeakerProfile], threshold: float = 0.75) -> str | None:
    """Match a speaker embedding against known profiles. Returns name or None."""
    return None
