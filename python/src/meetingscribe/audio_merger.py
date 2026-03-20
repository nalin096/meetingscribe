"""Merge dual audio streams and concatenate chunks with cross-fade."""

import struct
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample


def fix_wav_header(path: Path) -> None:
    """Fix WAV files where the RIFF/data sizes weren't updated (AVAudioFile bug).
    Reads actual file size and rewrites the header sizes."""
    size = path.stat().st_size
    if size < 44:
        return
    with open(path, "r+b") as f:
        # Read format info
        f.seek(0)
        riff = f.read(4)
        if riff != b"RIFF":
            return
        # Fix RIFF chunk size = file_size - 8
        f.seek(4)
        f.write(struct.pack("<I", size - 8))
        # Find data chunk and fix its size
        f.seek(12)  # skip RIFF header
        while f.tell() < size:
            chunk_id = f.read(4)
            if len(chunk_id) < 4:
                break
            chunk_size = struct.unpack("<I", f.read(4))[0]
            if chunk_id == b"data":
                actual_data_size = size - f.tell()
                f.seek(-4, 1)
                f.write(struct.pack("<I", actual_data_size))
                break
            f.seek(chunk_size, 1)


def merge_chunk_pair(remote_path: Path, local_path: Path, output_path: Path, drift_ms: float = 0) -> None:
    """Mix remote + local WAV into a single mono file. Resample local if drift detected."""
    remote, sr_r = sf.read(str(remote_path), dtype="float32")
    local, sr_l = sf.read(str(local_path), dtype="float32")

    # Resample to match if different sample rates
    if sr_r != sr_l:
        if len(local) > 0 and sr_l > 0:
            new_len = int(len(local) * sr_r / sr_l)
            local = resample(local, new_len).astype(np.float32)

    if abs(drift_ms) > 10 and len(remote) > 0:
        local = resample(local, len(remote)).astype(np.float32)

    min_len = min(len(remote), len(local))
    remote = remote[:min_len]
    local = local[:min_len]

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
            # Resample to target rate instead of failing
            from scipy.signal import resample as scipy_resample
            new_len = int(len(data) * sample_rate / sr)
            data = scipy_resample(data, new_len).astype(np.float32)
            sr = sample_rate

        if result is None:
            result = data
            continue

        if overlap_samples > 0 and len(result) >= overlap_samples and len(data) >= overlap_samples:
            fade_out = np.linspace(1.0, 0.0, overlap_samples, dtype=np.float32)
            fade_in = np.linspace(0.0, 1.0, overlap_samples, dtype=np.float32)
            overlap_mixed = result[-overlap_samples:] * fade_out + data[:overlap_samples] * fade_in
            result = np.concatenate([result[:-overlap_samples], overlap_mixed, data[overlap_samples:]])
        else:
            result = np.concatenate([result, data])

    if result is not None:
        sf.write(str(output_path), result, sample_rate, subtype="PCM_16")
