import pytest
from meetingscribe.transcriber import TranscriptSegment
from meetingscribe.diarizer import SpeakerSegment
from meetingscribe.aligner import align, AlignedSegment, group_segments


# --- align() tests ---

def test_align_returns_tuple():
    result = align([], [])
    assert isinstance(result, tuple) and len(result) == 2


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
    aligned, raw_to_friendly = align(transcript, speakers)
    assert len(aligned) == 3
    assert aligned[0].speaker == "Speaker 1"
    assert aligned[1].speaker == "Speaker 2"
    assert aligned[2].speaker == "Speaker 1"


def test_align_exposes_raw_to_friendly_mapping():
    transcript = [TranscriptSegment(start=0.0, end=2.0, text="Hi")]
    speakers = [SpeakerSegment(start=0.0, end=2.0, speaker="SPEAKER_00")]
    _, raw_to_friendly = align(transcript, speakers)
    assert raw_to_friendly == {"SPEAKER_00": "Speaker 1"}


def test_align_no_speakers_defaults_to_unknown():
    transcript = [TranscriptSegment(start=0.0, end=2.0, text="Hello")]
    aligned, _ = align(transcript, [])
    assert aligned[0].speaker == "Speaker 1"


def test_align_empty_transcript():
    aligned, raw_to_friendly = align([], [])
    assert aligned == []
    assert raw_to_friendly == {}


def test_align_passes_through_resolved_names():
    """Labels not matching SPEAKER_\\d+ pattern pass through unchanged."""
    transcript = [
        TranscriptSegment(start=0.0, end=2.0, text="Hello"),
        TranscriptSegment(start=2.5, end=5.0, text="World"),
    ]
    speakers = [
        SpeakerSegment(start=0.0, end=3.0, speaker="Nalin"),     # resolved
        SpeakerSegment(start=3.0, end=6.0, speaker="SPEAKER_01"),  # unresolved
    ]
    aligned, raw_to_friendly = align(transcript, speakers)
    assert aligned[0].speaker == "Nalin"
    assert aligned[1].speaker == "Speaker 1"
    assert "Nalin" not in raw_to_friendly
    assert "SPEAKER_01" in raw_to_friendly


def test_align_unknown_label_is_treated_as_unresolved():
    transcript = [TranscriptSegment(start=0.0, end=2.0, text="Hi")]
    speakers = [SpeakerSegment(start=0.0, end=2.0, speaker="UNKNOWN")]
    aligned, raw_to_friendly = align(transcript, speakers)
    assert aligned[0].speaker == "Speaker 1"
    assert "UNKNOWN" in raw_to_friendly


# --- group_segments() tests ---

def test_group_segments_merges_close_same_speaker():
    segments = [
        AlignedSegment(start=0.0, end=2.0, text="Hello", speaker="Nalin"),
        AlignedSegment(start=3.5, end=5.0, text="World", speaker="Nalin"),  # gap=1.5s ≤ 2s
    ]
    result = group_segments(segments, gap_threshold=2.0)
    assert len(result) == 1
    assert result[0].text == "Hello World"
    assert result[0].start == 0.0
    assert result[0].end == 5.0


def test_group_segments_does_not_merge_large_gap():
    segments = [
        AlignedSegment(start=0.0, end=2.0, text="Hello", speaker="Nalin"),
        AlignedSegment(start=5.0, end=7.0, text="World", speaker="Nalin"),  # gap=3s > 2s
    ]
    result = group_segments(segments, gap_threshold=2.0)
    assert len(result) == 2


def test_group_segments_does_not_merge_different_speakers():
    segments = [
        AlignedSegment(start=0.0, end=2.0, text="Hello", speaker="Nalin"),
        AlignedSegment(start=2.5, end=5.0, text="Hi there", speaker="John"),
    ]
    result = group_segments(segments, gap_threshold=2.0)
    assert len(result) == 2


def test_group_segments_empty():
    assert group_segments([], gap_threshold=2.0) == []


def test_group_segments_single():
    seg = AlignedSegment(start=0.0, end=2.0, text="Hello", speaker="Nalin")
    assert group_segments([seg], gap_threshold=2.0) == [seg]


def test_group_segments_chains_three():
    segments = [
        AlignedSegment(start=0.0, end=1.0, text="A", speaker="Nalin"),
        AlignedSegment(start=1.5, end=2.5, text="B", speaker="Nalin"),
        AlignedSegment(start=3.0, end=4.0, text="C", speaker="Nalin"),
    ]
    result = group_segments(segments, gap_threshold=2.0)
    assert len(result) == 1
    assert result[0].text == "A B C"
