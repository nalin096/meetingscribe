import numpy as np
import pytest
from unittest.mock import patch, MagicMock
import meetingscribe.diarizer as diarizer_mod
from meetingscribe.diarizer import diarize, SpeakerSegment

# Fake audio: 1-channel, 16kHz, 5 seconds of silence
_FAKE_WAVEFORM = np.zeros((5 * 16000, 1), dtype=np.float32)
_FAKE_SR = 16000


@pytest.fixture(autouse=True)
def reset_diarizer_caches():
    """Reset module-level caches before and after each test."""
    diarizer_mod._pipeline_cache = None
    diarizer_mod._embedding_cache = None
    yield
    diarizer_mod._pipeline_cache = None
    diarizer_mod._embedding_cache = None


def _make_pipeline_mock(turns):
    """turns: list of (start, end, label)"""
    mock_diarization = MagicMock()
    mock_turns = []
    for start, end, label in turns:
        t = MagicMock()
        t.start = start
        t.end = end
        mock_turns.append((t, None, label))
    mock_diarization.itertracks.return_value = mock_turns
    mock_pipeline = MagicMock(return_value=mock_diarization)
    return mock_pipeline


def test_diarize_returns_tuple():
    mock_pipeline = _make_pipeline_mock([(0.0, 3.5, "SPEAKER_00")])
    with patch("meetingscribe.diarizer._get_pipeline", return_value=mock_pipeline), \
         patch("meetingscribe.diarizer._get_embedding_model", return_value=None), \
         patch("soundfile.read", return_value=(_FAKE_WAVEFORM, _FAKE_SR)):
        result = diarize("/fake/audio.wav", hf_token="fake_token")
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_diarize_returns_speaker_segments():
    mock_pipeline = _make_pipeline_mock([(0.0, 3.5, "SPEAKER_00")])
    with patch("meetingscribe.diarizer._get_pipeline", return_value=mock_pipeline), \
         patch("meetingscribe.diarizer._get_embedding_model", return_value=None), \
         patch("soundfile.read", return_value=(_FAKE_WAVEFORM, _FAKE_SR)):
        segments, embeddings = diarize("/fake/audio.wav", hf_token="fake_token")
    assert len(segments) == 1
    assert isinstance(segments[0], SpeakerSegment)
    assert segments[0].speaker == "SPEAKER_00"
    assert segments[0].start == 0.0
    assert segments[0].end == 3.5


def test_diarize_empty_returns_empty():
    mock_pipeline = _make_pipeline_mock([])
    with patch("meetingscribe.diarizer._get_pipeline", return_value=mock_pipeline), \
         patch("meetingscribe.diarizer._get_embedding_model", return_value=None), \
         patch("soundfile.read", return_value=(_FAKE_WAVEFORM, _FAKE_SR)):
        segments, embeddings = diarize("/fake/silent.wav", hf_token="fake_token")
    assert segments == []
    assert embeddings == {}


def test_diarize_returns_empty_embeddings_when_model_unavailable():
    mock_pipeline = _make_pipeline_mock([(0.0, 3.5, "SPEAKER_00")])
    with patch("meetingscribe.diarizer._get_pipeline", return_value=mock_pipeline), \
         patch("meetingscribe.diarizer._get_embedding_model", return_value=None), \
         patch("soundfile.read", return_value=(_FAKE_WAVEFORM, _FAKE_SR)):
        segments, embeddings = diarize("/fake/audio.wav", hf_token="fake_token")
    assert embeddings == {}


def test_diarize_skips_speaker_with_too_little_speech():
    """Speaker with < 10s total should not appear in embeddings."""
    mock_pipeline = _make_pipeline_mock([(0.0, 3.5, "SPEAKER_00")])
    mock_emb_model = MagicMock()
    mock_emb_model.return_value = np.ones(256, dtype=np.float32)
    with patch("meetingscribe.diarizer._get_pipeline", return_value=mock_pipeline), \
         patch("meetingscribe.diarizer._get_embedding_model", return_value=mock_emb_model), \
         patch("soundfile.read", return_value=(_FAKE_WAVEFORM, _FAKE_SR)):
        segments, embeddings = diarize("/fake/audio.wav", hf_token="fake_token")
    assert "SPEAKER_00" not in embeddings


def test_diarize_extracts_embedding_for_long_speaker(make_wav):
    """Speaker with >= 10s total should appear in embeddings."""
    mock_pipeline = _make_pipeline_mock([
        (0.0, 6.0, "SPEAKER_00"),
        (6.5, 12.5, "SPEAKER_00"),
    ])
    mock_emb_model = MagicMock()
    mock_emb_model.return_value = np.ones(256, dtype=np.float32)
    audio_path = make_wav("long.wav", duration_s=15.0)
    with patch("meetingscribe.diarizer._get_pipeline", return_value=mock_pipeline), \
         patch("meetingscribe.diarizer._get_embedding_model", return_value=mock_emb_model):
        segments, embeddings = diarize(str(audio_path), hf_token="fake_token")
    assert "SPEAKER_00" in embeddings
    assert isinstance(embeddings["SPEAKER_00"], np.ndarray)
