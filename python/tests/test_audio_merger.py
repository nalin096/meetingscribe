import numpy as np
import soundfile as sf
from meetingscribe.audio_merger import merge_chunk_pair, concatenate_chunks


def test_merge_chunk_pair_produces_mono(make_wav, tmp_path):
    remote = make_wav("remote.wav", duration_s=3.0)
    local = make_wav("local.wav", duration_s=3.0)
    out = tmp_path / "merged.wav"
    merge_chunk_pair(remote, local, out, drift_ms=0)
    data, sr = sf.read(str(out))
    assert sr == 16000
    assert len(data.shape) == 1  # mono
    assert abs(len(data) - 3.0 * 16000) < 100


def test_merge_chunk_pair_handles_drift(make_wav, tmp_path):
    remote = make_wav("remote.wav", duration_s=3.0)
    local = make_wav("local.wav", duration_s=3.05)
    out = tmp_path / "merged.wav"
    merge_chunk_pair(remote, local, out, drift_ms=50)
    data, sr = sf.read(str(out))
    assert sr == 16000
    assert abs(len(data) - 3.0 * 16000) < 100


def test_concatenate_chunks_with_overlap(make_wav, tmp_path):
    c1 = make_wav("c1.wav", duration_s=5.0)
    c2 = make_wav("c2.wav", duration_s=5.0)
    out = tmp_path / "full.wav"
    concatenate_chunks([c1, c2], out, overlap_seconds=1.0, sample_rate=16000)
    data, sr = sf.read(str(out))
    expected_samples = 9.0 * 16000
    assert abs(len(data) - expected_samples) < 200
