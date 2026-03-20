"""Summarize meeting transcripts via Claude CLI."""

import subprocess
from pathlib import Path

WORD_LIMIT = 10000


def _call_claude(prompt: str, cli: str, model_flag: str) -> tuple[str, bool]:
    """Call claude CLI with prompt. Returns (output, success)."""
    cmd = [cli, "-p"]
    if model_flag:
        cmd.extend(model_flag.split())
    result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        return "", False
    return result.stdout.strip(), True


def _split_transcript(transcript: str, max_words: int = WORD_LIMIT) -> list[str]:
    """Split transcript at line boundaries into chunks under max_words."""
    lines = transcript.split("\n")
    chunks = []
    current_chunk: list[str] = []
    current_words = 0
    for line in lines:
        line_words = len(line.split())
        if current_words + line_words > max_words and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_words = 0
        current_chunk.append(line)
        current_words += line_words
    if current_chunk:
        chunks.append("\n".join(current_chunk))
    return chunks


def summarize(transcript: str, prompt_file: Path, cli: str = "claude", model_flag: str = "--model sonnet") -> str:
    """Summarize transcript using Claude CLI. Returns markdown summary or empty string on failure."""
    prompt_template = prompt_file.read_text().strip()
    words = transcript.split()

    if len(words) <= WORD_LIMIT:
        full_prompt = f"{prompt_template}\n\nTranscript:\n{transcript}"
        output, ok = _call_claude(full_prompt, cli, model_flag)
        return output if ok else ""

    chunks = _split_transcript(transcript)
    section_summaries = []
    for i, chunk in enumerate(chunks):
        section_prompt = f"Summarize this section ({i+1}/{len(chunks)}) of a meeting transcript. Focus on key points, decisions, and action items.\n\nTranscript section:\n{chunk}"
        output, ok = _call_claude(section_prompt, cli, model_flag)
        if ok:
            section_summaries.append(output)
    if not section_summaries:
        return ""

    merge_prompt = f"{prompt_template}\n\nBelow are summaries of different sections of the same meeting. Merge them into a single cohesive summary:\n\n" + "\n\n---\n\n".join(section_summaries)
    output, ok = _call_claude(merge_prompt, cli, model_flag)
    return output if ok else ""
