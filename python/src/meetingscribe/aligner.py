"""Align transcript segments with speaker diarization labels."""

from dataclasses import dataclass
from meetingscribe.transcriber import TranscriptSegment
from meetingscribe.diarizer import SpeakerSegment


@dataclass
class AlignedSegment:
    start: float
    end: float
    text: str
    speaker: str


def align(transcript: list[TranscriptSegment], speakers: list[SpeakerSegment]) -> list[AlignedSegment]:
    """Assign a speaker label to each transcript segment based on maximum overlap."""
    if not transcript:
        return []

    raw_to_friendly: dict[str, str] = {}
    counter = 0

    def get_friendly(raw_label: str) -> str:
        nonlocal counter
        if raw_label not in raw_to_friendly:
            counter += 1
            raw_to_friendly[raw_label] = f"Speaker {counter}"
        return raw_to_friendly[raw_label]

    aligned = []
    for seg in transcript:
        best_speaker = None
        best_overlap = 0.0
        for sp in speakers:
            overlap_start = max(seg.start, sp.start)
            overlap_end = min(seg.end, sp.end)
            overlap = max(0.0, overlap_end - overlap_start)
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = sp.speaker
        friendly = get_friendly(best_speaker) if best_speaker else get_friendly("UNKNOWN")
        aligned.append(AlignedSegment(start=seg.start, end=seg.end, text=seg.text, speaker=friendly))
    return aligned
