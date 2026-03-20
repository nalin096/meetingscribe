from unittest.mock import patch, MagicMock
from meetingscribe.transcriber import transcribe, TranscriptSegment


def test_transcribe_returns_segments():
    mock_segment = MagicMock()
    mock_segment.start = 0.0
    mock_segment.end = 2.5
    mock_segment.text = " Hello, this is a test."
    mock_info = MagicMock()
    mock_info.language = "en"
    mock_info.language_probability = 0.98
    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([mock_segment], mock_info)
    with patch("meetingscribe.transcriber.WhisperModel", return_value=mock_model):
        segments = transcribe("/fake/audio.wav", model_size="tiny")
    assert len(segments) == 1
    assert isinstance(segments[0], TranscriptSegment)
    assert segments[0].start == 0.0
    assert segments[0].end == 2.5
    assert segments[0].text == "Hello, this is a test."


def test_transcribe_empty_audio_returns_empty():
    mock_model = MagicMock()
    mock_info = MagicMock()
    mock_model.transcribe.return_value = ([], mock_info)
    with patch("meetingscribe.transcriber.WhisperModel", return_value=mock_model):
        segments = transcribe("/fake/silent.wav", model_size="tiny")
    assert segments == []
