"""Generate Obsidian-compatible meeting markdown notes."""

from dataclasses import dataclass, field
from pathlib import Path
from meetingscribe.aligner import AlignedSegment


@dataclass
class MeetingMetadata:
    date: str
    time: str
    timezone: str
    duration_min: int
    app: str
    speakers: int
    speaker_map: dict[str, str] = field(default_factory=dict)
    topics: list[str] = field(default_factory=list)


def _format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS or MM:SS format."""
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _determine_status(segments: list[AlignedSegment], summary: str) -> str:
    if not segments:
        return "no-speech"
    if not summary:
        return "needs-summary"
    if "- [ ]" in summary:
        return "has-action-items"
    return "no-action-items"


def write_meeting_note(
    output_path: Path, meta: MeetingMetadata,
    segments: list[AlignedSegment], summary: str,
) -> None:
    """Write a meeting note in Obsidian markdown format."""
    status = _determine_status(segments, summary)
    speaker_map_yaml = ""
    for k, v in meta.speaker_map.items():
        speaker_map_yaml += f'  {k}: "{v}"\n'
    topics_yaml = str(meta.topics) if meta.topics else "[]"

    frontmatter = f"""---
date: {meta.date}
time: "{meta.time}"
timezone: "{meta.timezone}"
duration_min: {meta.duration_min}
app: {meta.app}
speakers: {meta.speakers}
speaker_map:
{speaker_map_yaml.rstrip()}
topics: {topics_yaml}
tags: [meeting]
status: {status}
---"""

    header = f"# Meeting — {meta.date} {meta.time.split(' - ')[0]}"
    subheader = f"> {meta.duration_min} min · {meta.app} · {meta.speakers} speakers"
    transcript_lines = []
    for seg in segments:
        ts = _format_timestamp(seg.start)
        transcript_lines.append(f"**[{ts}] {seg.speaker}:** {seg.text}")
    transcript_section = "\n".join(transcript_lines) if transcript_lines else "*No speech detected.*"

    parts = [frontmatter, "", header, subheader, ""]
    if summary:
        parts.append(summary)
        parts.append("")
    parts.append("## Transcript")
    parts.append(transcript_section)
    parts.append("")
    parts.append("---")
    parts.append("*Transcribed by MeetingScribe · faster-whisper*")
    parts.append("")
    output_path.write_text("\n".join(parts))
