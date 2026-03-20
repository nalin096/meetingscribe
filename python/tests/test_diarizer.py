from unittest.mock import patch, MagicMock
from meetingscribe.diarizer import diarize, SpeakerSegment


def test_diarize_returns_speaker_segments():
    mock_turn = MagicMock()
    mock_turn.start = 0.0
    mock_turn.end = 3.5
    mock_label = "SPEAKER_00"
    mock_pipeline = MagicMock()
    mock_pipeline.return_value.itertracks.return_value = [(mock_turn, None, mock_label)]
    with patch("meetingscribe.diarizer.Pipeline.from_pretrained", return_value=mock_pipeline):
        segments = diarize("/fake/audio.wav", hf_token="fake_token")
    assert len(segments) == 1
    assert isinstance(segments[0], SpeakerSegment)
    assert segments[0].speaker == "SPEAKER_00"
    assert segments[0].start == 0.0
    assert segments[0].end == 3.5


def test_diarize_empty_returns_empty():
    mock_pipeline = MagicMock()
    mock_pipeline.return_value.itertracks.return_value = []
    with patch("meetingscribe.diarizer.Pipeline.from_pretrained", return_value=mock_pipeline):
        segments = diarize("/fake/silent.wav", hf_token="fake_token")
    assert segments == []
