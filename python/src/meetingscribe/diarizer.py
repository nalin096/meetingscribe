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
            token=hf_token,
        )
    return _pipeline_cache


def diarize(audio_path: str | Path, hf_token: str) -> list[SpeakerSegment]:
    """Run speaker diarization on audio file."""
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,
    )
    diarization = pipeline(str(audio_path))
    segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append(SpeakerSegment(start=turn.start, end=turn.end, speaker=speaker))
    return segments
