"""Align transcript segments with speaker diarization labels."""

import re
from dataclasses import dataclass
from meetingscribe.transcriber import TranscriptSegment
from meetingscribe.diarizer import SpeakerSegment

# Unresolved pyannote label patterns
_RAW_LABEL_RE = re.compile(r"^speaker_", re.IGNORECASE)


def _is_raw_label(label: str) -> bool:
    """True if label is an unresolved pyannote label (e.g. SPEAKER_00, UNKNOWN)."""
    return bool(_RAW_LABEL_RE.match(label)) or label == "UNKNOWN"


@dataclass
class AlignedSegment:
    start: float
    end: float
    text: str
    speaker: str


def align(
    transcript: list[TranscriptSegment],
    speakers: list[SpeakerSegment],
) -> tuple[list[AlignedSegment], dict[str, str]]:
    """Assign a speaker label to each transcript segment based on maximum overlap.

    Returns:
        (aligned_segments, raw_to_friendly)
        raw_to_friendly maps unresolved raw labels → "Speaker N" strings only.
        Already-resolved labels (e.g. "Nalin") pass through unchanged.
    """
    if not transcript:
        return [], {}

    raw_to_friendly: dict[str, str] = {}
    counter = 0

    def get_friendly(raw_label: str) -> str:
        nonlocal counter
        if not _is_raw_label(raw_label):
            return raw_label  # already resolved by DB
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

    return aligned, raw_to_friendly


def group_segments(
    aligned: list[AlignedSegment], gap_threshold: float = 2.0
) -> list[AlignedSegment]:
    """Merge consecutive same-speaker segments with gap ≤ gap_threshold seconds."""
    if not aligned:
        return []

    result = [AlignedSegment(
        start=aligned[0].start, end=aligned[0].end,
        text=aligned[0].text, speaker=aligned[0].speaker,
    )]

    for seg in aligned[1:]:
        last = result[-1]
        if seg.speaker == last.speaker and (seg.start - last.end) <= gap_threshold:
            result[-1] = AlignedSegment(
                start=last.start, end=seg.end,
                text=last.text + " " + seg.text, speaker=last.speaker,
            )
        else:
            result.append(AlignedSegment(
                start=seg.start, end=seg.end,
                text=seg.text, speaker=seg.speaker,
            ))

    return result
