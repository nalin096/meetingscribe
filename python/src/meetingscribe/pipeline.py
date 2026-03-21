"""Orchestrate the full meeting processing pipeline."""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf
import keyring

from meetingscribe.audio_merger import merge_chunk_pair, concatenate_chunks, fix_wav_header
from meetingscribe.transcriber import transcribe
from meetingscribe.diarizer import diarize, warmup as warmup_diarizer
from meetingscribe.aligner import align, group_segments
from meetingscribe.summarizer import summarize
from meetingscribe.markdown_writer import write_meeting_note, MeetingMetadata
from meetingscribe.manifest import Manifest
from meetingscribe.config import MeetingScribeConfig
from meetingscribe.speakers import match_speaker, load_db

logger = logging.getLogger(__name__)

EMBEDDINGS_DIR = Path("~/.meetingscribe/embeddings").expanduser()


def _safe_filename(meeting_id: str) -> str:
    """Strip characters invalid in macOS filenames (colons, slashes, etc.)."""
    return re.sub(r'[:/\\?*|"<>]', "_", meeting_id)


def _warmup_models(model_size: str, hf_token: str) -> None:
    """Pre-load transcription and diarization models before parallel execution."""
    from meetingscribe.transcriber import _get_model
    _get_model(model_size)
    warmup_diarizer(hf_token)


def _parse_meeting_times(manifest: Manifest) -> tuple[str, str, int]:
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
    """Run full pipeline: merge → transcribe → diarize → align → group → summarize → write."""
    logger.info(f"Processing meeting {manifest.meeting_id}")

    # Step 1: Fix WAV headers then merge audio chunks
    merged_chunks = []
    local_only_chunks = []
    for i, chunk in enumerate(manifest.chunks):
        remote_path = recordings_dir / chunk.remote
        local_path = recordings_dir / chunk.local
        merged_path = recordings_dir / f"merged_{i:03d}.wav"

        if remote_path.exists():
            fix_wav_header(remote_path)
        if local_path.exists():
            fix_wav_header(local_path)

        remote_samples = sf.info(str(remote_path)).frames if remote_path.exists() else 0
        local_samples = sf.info(str(local_path)).frames if local_path.exists() else 0

        logger.info(f"Chunk {i}: remote={remote_samples} samples, local={local_samples} samples")

        if remote_samples > 0 and local_samples > 0:
            merge_chunk_pair(remote_path, local_path, merged_path, drift_ms=0)
            merged_chunks.append(merged_path)
        elif local_samples > 0:
            logger.info(f"Remote audio empty for chunk {i}, using local mic only")
            local_only_chunks.append(local_path)
        elif remote_samples > 0:
            logger.info(f"Local audio empty for chunk {i}, using remote only")
            merged_chunks.append(remote_path)

    all_chunks = merged_chunks or local_only_chunks
    full_audio = recordings_dir / f"{_safe_filename(manifest.meeting_id)}_full.wav"
    if all_chunks:
        concatenate_chunks(all_chunks, full_audio, overlap_seconds=config.audio.chunk_overlap_seconds, sample_rate=config.audio.sample_rate)

    # Normalize audio level
    if full_audio.exists() and full_audio.stat().st_size > 100:
        data, sr = sf.read(str(full_audio), dtype="float32")
        if len(data) > 0:
            peak = np.max(np.abs(data))
            if 0 < peak < 0.8:
                gain = 0.9 / peak
                logger.info(f"Audio quiet (peak={peak:.4f}), boosting {gain:.1f}x")
                data = np.clip(data * gain, -1.0, 1.0)
                sf.write(str(full_audio), data, sr, subtype="PCM_16")

    audio_file = full_audio if full_audio.exists() and full_audio.stat().st_size > 100 else None
    hf_token = keyring.get_password(config.diarization.keychain_service, config.diarization.keychain_account)

    # Step 2+3: Transcribe and Diarize in parallel
    segments = []
    speaker_segments = []
    raw_embeddings: dict[str, np.ndarray] = {}

    if audio_file:
        if hf_token:
            _warmup_models(config.transcription.model, hf_token)
            with ThreadPoolExecutor(max_workers=2) as executor:
                f_transcribe = executor.submit(transcribe, str(audio_file), model_size=config.transcription.model)
                f_diarize = executor.submit(diarize, str(audio_file), hf_token=hf_token)
            segments = f_transcribe.result()
            try:
                speaker_segments, raw_embeddings = f_diarize.result()
            except Exception as e:
                logger.warning(f"Diarization failed (continuing without speaker labels): {e}")
        else:
            segments = transcribe(str(audio_file), model_size=config.transcription.model)

    # Step 3b: Resolve known speakers from DB; save per-meeting embeddings
    safe_id = _safe_filename(manifest.meeting_id)
    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    if raw_embeddings:
        canonical_names_db, embeddings_db = load_db()
        for raw_label, embedding in raw_embeddings.items():
            matched = match_speaker(
                embedding,
                threshold=config.diarization.speaker_similarity_threshold,
                canonical_names=canonical_names_db,
                embeddings=embeddings_db,
            )
            if matched:
                for seg in speaker_segments:
                    if seg.speaker == raw_label:
                        seg.speaker = matched
        np.savez(str(EMBEDDINGS_DIR / f"{safe_id}.npz"), **raw_embeddings)

    # Step 4: Align and expose raw_to_friendly for side-car
    aligned, raw_to_friendly = align(segments, speaker_segments)

    if raw_to_friendly:
        friendly_to_raw = {v: k for k, v in raw_to_friendly.items()}
        (EMBEDDINGS_DIR / f"{safe_id}.json").write_text(
            json.dumps(friendly_to_raw), encoding="utf-8"
        )

    # Step 4b: Group consecutive same-speaker segments
    aligned = group_segments(aligned)

    # Step 5: Summarize
    transcript_text = "\n".join(f"[{seg.start:.0f}s] {seg.speaker}: {seg.text}" for seg in aligned)
    summary = ""
    if aligned:
        summary = summarize(transcript_text, prompt_file=config.summary.prompt_file, cli=config.summary.cli, model_flag=config.summary.model_flag)

    # Step 6: Write to vault
    date_str, time_str, duration_min = _parse_meeting_times(manifest)
    unique_speakers = list({seg.speaker for seg in aligned})
    speaker_map = {s: "" for s in sorted(unique_speakers)}

    meta = MeetingMetadata(
        date=date_str, time=time_str, timezone=config.vault.timezone,
        duration_min=duration_min, app=manifest.app,
        speakers=len(unique_speakers), speaker_map=speaker_map,
        meeting_id=manifest.meeting_id,
    )

    output_path = config.vault.path / f"{date_str}-{safe_id[:30]}.md"

    if not config.vault.path.is_dir():
        raise OSError(f"Vault path not writable: {config.vault.path}")

    write_meeting_note(output_path, meta, aligned, summary)
    logger.info(f"Meeting note written to {output_path}")
