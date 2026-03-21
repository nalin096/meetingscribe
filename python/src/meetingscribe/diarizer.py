"""Speaker diarization using pyannote-audio."""

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Patch torchaudio compat shims before any pyannote.audio import
try:
    import torchaudio as _torchaudio
    if not hasattr(_torchaudio, "list_audio_backends"):
        _torchaudio.list_audio_backends = lambda: []
    if not hasattr(_torchaudio, "set_audio_backend"):
        _torchaudio.set_audio_backend = lambda _: None
except ImportError:
    pass

logger = logging.getLogger(__name__)

_pipeline_cache = None
_embedding_cache = None


@dataclass
class SpeakerSegment:
    start: float
    end: float
    speaker: str


def _get_pipeline(hf_token: str):
    global _pipeline_cache
    if _pipeline_cache is None:
        import torchaudio
        if not hasattr(torchaudio, "list_audio_backends"):
            torchaudio.list_audio_backends = lambda: []
        if not hasattr(torchaudio, "set_audio_backend"):
            torchaudio.set_audio_backend = lambda _: None
        from pyannote.audio import Pipeline
        _pipeline_cache = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=hf_token,
        )
    return _pipeline_cache


def _get_embedding_model(hf_token: str):
    """Load wespeaker embedding model. Returns None if unavailable."""
    global _embedding_cache
    if _embedding_cache is None:
        try:
            from pyannote.audio import Inference
            _embedding_cache = Inference(
                "pyannote/wespeaker-voxceleb-resnet34-LM",
                window="whole",
                token=hf_token,
            )
        except Exception as e:
            logger.warning(f"Embedding model unavailable: {e}")
            # Use sentinel to avoid retrying on every call
            _embedding_cache = False
    return _embedding_cache if _embedding_cache is not False else None


def warmup(hf_token: str) -> None:
    """Pre-load both models to avoid lazy-init during parallel execution."""
    _get_pipeline(hf_token)
    _get_embedding_model(hf_token)


def diarize(
    audio_path: str | Path, hf_token: str
) -> tuple[list[SpeakerSegment], dict[str, np.ndarray]]:
    """Run speaker diarization on audio file.

    Returns:
        (speaker_segments, embeddings_per_speaker)
        embeddings_per_speaker: raw_label → averaged embedding.
        Returns {} embeddings if model unavailable or extraction fails.
    """
    import torch
    import soundfile as sf

    waveform, sample_rate = sf.read(str(audio_path), dtype="float32", always_2d=True)
    waveform_tensor = torch.from_numpy(waveform.T)  # (channels, samples)

    pipeline = _get_pipeline(hf_token)
    diarization = pipeline({"waveform": waveform_tensor, "sample_rate": sample_rate})

    segments: list[SpeakerSegment] = []
    segments_by_speaker: dict[str, list[SpeakerSegment]] = {}
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        seg = SpeakerSegment(start=turn.start, end=turn.end, speaker=speaker)
        segments.append(seg)
        segments_by_speaker.setdefault(speaker, []).append(seg)

    embeddings: dict[str, np.ndarray] = {}
    embedding_model = _get_embedding_model(hf_token)
    if embedding_model is not None:
        for speaker_label, speaker_segs in segments_by_speaker.items():
            total_duration = sum(s.end - s.start for s in speaker_segs)
            if total_duration < 10.0:
                continue
            try:
                speaker_embeddings = []
                for seg in speaker_segs:
                    start_sample = int(seg.start * sample_rate)
                    end_sample = int(seg.end * sample_rate)
                    crop = waveform_tensor[:, start_sample:end_sample]
                    if crop.shape[1] < int(sample_rate * 0.5):
                        continue
                    emb = embedding_model({"waveform": crop, "sample_rate": sample_rate})
                    if emb is not None:
                        speaker_embeddings.append(np.array(emb).flatten())
                if speaker_embeddings:
                    embeddings[speaker_label] = np.mean(speaker_embeddings, axis=0)
            except Exception as e:
                logger.warning(f"Embedding extraction failed for {speaker_label}: {e}")

    return segments, embeddings
