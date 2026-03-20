from meetingscribe.transcriber import TranscriptSegment
from meetingscribe.diarizer import SpeakerSegment
from meetingscribe.aligner import align, AlignedSegment


def test_align_assigns_speakers_to_transcript():
    transcript = [
        TranscriptSegment(start=0.0, end=2.0, text="Hello everyone"),
        TranscriptSegment(start=2.5, end=5.0, text="Thanks for joining"),
        TranscriptSegment(start=5.5, end=8.0, text="Let's begin"),
    ]
    speakers = [
        SpeakerSegment(start=0.0, end=3.0, speaker="SPEAKER_00"),
        SpeakerSegment(start=3.0, end=6.0, speaker="SPEAKER_01"),
        SpeakerSegment(start=6.0, end=9.0, speaker="SPEAKER_00"),
    ]
    aligned = align(transcript, speakers)
    assert len(aligned) == 3
    assert aligned[0].speaker == "Speaker 1"
    assert aligned[1].speaker == "Speaker 2"
    assert aligned[2].speaker == "Speaker 1"


def test_align_no_speakers_defaults_to_unknown():
    transcript = [TranscriptSegment(start=0.0, end=2.0, text="Hello")]
    aligned = align(transcript, [])
    assert aligned[0].speaker == "Speaker 1"


def test_align_empty_transcript():
    aligned = align([], [])
    assert aligned == []
