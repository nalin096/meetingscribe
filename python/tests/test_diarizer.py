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
    yield
    diarizer_mod._pipeline_cache = None


def _make_annotation_mock(turns):
    """turns: list of (start, end, label)"""
    mock_turns = []
    for start, end, label in turns:
        t = MagicMock()
        t.start = start
        t.end = end
        mock_turns.append((t, None, label))
    mock_annotation = MagicMock()
    mock_annotation.itertracks.return_value = mock_turns
    mock_annotation.labels.return_value = [t[2] for t in turns]
    return mock_annotation


def _make_pipeline_mock(turns, speaker_embeddings=None):
    """Return pipeline mock yielding DiarizeOutput-like object."""
    mock_annotation = _make_annotation_mock(turns)
    mock_output = MagicMock()
    mock_output.speaker_diarization = mock_annotation
    mock_output.speaker_embeddings = speaker_embeddings
    mock_pipeline = MagicMock(return_value=mock_output)
    return mock_pipeline


def test_diarize_returns_tuple():
    mock_pipeline = _make_pipeline_mock([(0.0, 3.5, "SPEAKER_00")])
    with patch("meetingscribe.diarizer._get_pipeline", return_value=mock_pipeline), \
         patch("soundfile.read", return_value=(_FAKE_WAVEFORM, _FAKE_SR)):
        result = diarize("/fake/audio.wav", hf_token="fake_token")
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_diarize_returns_speaker_segments():
    mock_pipeline = _make_pipeline_mock([(0.0, 3.5, "SPEAKER_00")])
    with patch("meetingscribe.diarizer._get_pipeline", return_value=mock_pipeline), \
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
         patch("soundfile.read", return_value=(_FAKE_WAVEFORM, _FAKE_SR)):
        segments, embeddings = diarize("/fake/silent.wav", hf_token="fake_token")
    assert segments == []
    assert embeddings == {}


def test_diarize_returns_empty_embeddings_when_none():
    mock_pipeline = _make_pipeline_mock([(0.0, 3.5, "SPEAKER_00")], speaker_embeddings=None)
    with patch("meetingscribe.diarizer._get_pipeline", return_value=mock_pipeline), \
         patch("soundfile.read", return_value=(_FAKE_WAVEFORM, _FAKE_SR)):
        segments, embeddings = diarize("/fake/audio.wav", hf_token="fake_token")
    assert embeddings == {}


def test_diarize_extracts_embeddings_from_output():
    """Embeddings from pipeline output are returned per speaker."""
    emb = np.ones((1, 256), dtype=np.float32)
    mock_pipeline = _make_pipeline_mock([(0.0, 6.0, "SPEAKER_00")], speaker_embeddings=emb)
    with patch("meetingscribe.diarizer._get_pipeline", return_value=mock_pipeline), \
         patch("soundfile.read", return_value=(_FAKE_WAVEFORM, _FAKE_SR)):
        segments, embeddings = diarize("/fake/audio.wav", hf_token="fake_token")
    assert "SPEAKER_00" in embeddings
    assert isinstance(embeddings["SPEAKER_00"], np.ndarray)


def test_diarize_multiple_speakers():
    emb = np.eye(2, dtype=np.float32)
    mock_pipeline = _make_pipeline_mock(
        [(0.0, 5.0, "SPEAKER_00"), (5.0, 10.0, "SPEAKER_01")],
        speaker_embeddings=emb,
    )
    with patch("meetingscribe.diarizer._get_pipeline", return_value=mock_pipeline), \
         patch("soundfile.read", return_value=(_FAKE_WAVEFORM, _FAKE_SR)):
        segments, embeddings = diarize("/fake/audio.wav", hf_token="fake_token")
    assert len(segments) == 2
    assert "SPEAKER_00" in embeddings
    assert "SPEAKER_01" in embeddings
