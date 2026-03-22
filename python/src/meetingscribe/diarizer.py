"""Speaker diarization using pyannote-audio."""

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Patch torchaudio APIs removed in 2.x that pyannote still calls at import time
try:
    import torchaudio as _ta
    if not hasattr(_ta, "list_audio_backends"):
        _ta.list_audio_backends = lambda: []
    if not hasattr(_ta, "set_audio_backend"):
        _ta.set_audio_backend = lambda _: None
    if not hasattr(_ta, "get_audio_backend"):
        _ta.get_audio_backend = lambda: None
except Exception:
    pass

logger = logging.getLogger(__name__)

_pipeline_cache = None


@dataclass
class SpeakerSegment:
    start: float
    end: float
    speaker: str


def _get_pipeline(hf_token: str):
    global _pipeline_cache
    if _pipeline_cache is None:
        from pyannote.audio import Pipeline
        _pipeline_cache = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=hf_token,
        )
    return _pipeline_cache


def warmup(hf_token: str) -> None:
    """Pre-load pipeline to avoid lazy-init during parallel execution."""
    _get_pipeline(hf_token)


def diarize(
    audio_path: str | Path, hf_token: str
) -> tuple[list[SpeakerSegment], dict[str, np.ndarray]]:
    """Run speaker diarization on audio file.

    Returns:
        (speaker_segments, embeddings_per_speaker)
        embeddings_per_speaker: raw_label -> embedding vector.
    """
    import soundfile as sf
    import torch

    waveform, sample_rate = sf.read(str(audio_path), dtype="float32", always_2d=True)
    waveform_tensor = torch.from_numpy(waveform.T)  # (channels, samples)

    pipeline = _get_pipeline(hf_token)
    output = pipeline({"waveform": waveform_tensor, "sample_rate": sample_rate})

    # pyannote 4.x returns DiarizeOutput; 3.x (legacy) returns Annotation directly
    if hasattr(output, "speaker_diarization"):
        annotation = output.speaker_diarization
        raw_embeddings_matrix = output.speaker_embeddings  # (num_speakers, dim) or None
    else:
        annotation = output
        raw_embeddings_matrix = None

    segments: list[SpeakerSegment] = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        segments.append(SpeakerSegment(
            start=float(turn.start),
            end=float(turn.end),
            speaker=str(speaker),
        ))

    embeddings: dict[str, np.ndarray] = {}
    if raw_embeddings_matrix is not None:
        for i, label in enumerate(annotation.labels()):
            if i < len(raw_embeddings_matrix):
                embeddings[str(label)] = np.array(raw_embeddings_matrix[i]).flatten()

    return segments, embeddings
