"""Transcribe audio using faster-whisper."""

from dataclasses import dataclass
from pathlib import Path
from faster_whisper import WhisperModel


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


_model_cache: dict[str, WhisperModel] = {}


def _get_model(model_size: str) -> WhisperModel:
    if model_size not in _model_cache:
        _model_cache[model_size] = WhisperModel(model_size, compute_type="int8")
    return _model_cache[model_size]


def transcribe(audio_path: str | Path, model_size: str = "large-v3") -> list[TranscriptSegment]:
    """Transcribe audio file, return list of timed segments."""
    model = WhisperModel(model_size, compute_type="int8")
    segments_iter, info = model.transcribe(str(audio_path), beam_size=5, vad_filter=True)
    segments = []
    for seg in segments_iter:
        text = seg.text.strip()
        if text:
            segments.append(TranscriptSegment(start=seg.start, end=seg.end, text=text))
    return segments
