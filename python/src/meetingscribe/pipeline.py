"""Orchestrate the full meeting processing pipeline."""

import logging
from datetime import datetime
from pathlib import Path

import keyring

from meetingscribe.audio_merger import merge_chunk_pair, concatenate_chunks, fix_wav_header
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

    # Step 1: Fix WAV headers (AVAudioFile may not update sizes on close)
    # then merge audio chunks (or use local-only if remote is empty)
    merged_chunks = []
    local_only_chunks = []
    for i, chunk in enumerate(manifest.chunks):
        remote_path = recordings_dir / chunk.remote
        local_path = recordings_dir / chunk.local
        merged_path = recordings_dir / f"merged_{i:03d}.wav"

        # Fix WAV headers before reading
        if remote_path.exists():
            fix_wav_header(remote_path)
        if local_path.exists():
            fix_wav_header(local_path)

        # Check actual sample count, not file size
        import soundfile as sf
        remote_samples = 0
        local_samples = 0
        if remote_path.exists():
            info = sf.info(str(remote_path))
            remote_samples = info.frames
        if local_path.exists():
            info = sf.info(str(local_path))
            local_samples = info.frames

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
    full_audio = recordings_dir / f"{manifest.meeting_id}_full.wav"
    if all_chunks:
        concatenate_chunks(all_chunks, full_audio, overlap_seconds=config.audio.chunk_overlap_seconds, sample_rate=config.audio.sample_rate)

    # Step 2: Transcribe
    audio_file = full_audio if full_audio.exists() and full_audio.stat().st_size > 100 else None
    segments = []
    if audio_file:
        segments = transcribe(str(audio_file), model_size=config.transcription.model)

    # Step 3: Diarize
    hf_token = keyring.get_password(config.diarization.keychain_service, config.diarization.keychain_account)
    speaker_segments = []
    if audio_file and hf_token:
        speaker_segments = diarize(str(audio_file), hf_token=hf_token)

    # Step 4: Align
    aligned = align(segments, speaker_segments)

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
    )

    safe_id = manifest.meeting_id.replace(":", "").replace("+", "p").replace("-", "")[:20]
    output_path = config.vault.path / f"{date_str}-{safe_id}.md"

    if not config.vault.path.is_dir():
        raise OSError(f"Vault path not writable: {config.vault.path}")

    write_meeting_note(output_path, meta, aligned, summary)
    logger.info(f"Meeting note written to {output_path}")
