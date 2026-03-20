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
    model = _get_model(model_size)
    segments_iter, info = model.transcribe(
        str(audio_path),
        beam_size=1,
        temperature=0.0,
        language="en",
        vad_filter=True,
        vad_parameters={"threshold": 0.35, "min_silence_duration_ms": 500, "speech_pad_ms": 200},
        condition_on_previous_text=False,
        no_speech_threshold=0.6,
        log_prob_threshold=-1.0,
        compression_ratio_threshold=2.4,
    )
    # Known Whisper hallucinations when audio is quiet
    HALLUCINATIONS = {"thank you for watching", "thanks for watching", ".", ""}

    segments = []
    for seg in segments_iter:
        text = seg.text.strip()
        if text and text.lower() not in HALLUCINATIONS:
            segments.append(TranscriptSegment(start=seg.start, end=seg.end, text=text))
    return segments
