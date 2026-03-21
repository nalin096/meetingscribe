"""Load and validate MeetingScribe configuration."""

from dataclasses import dataclass, field
from pathlib import Path
import sys

if sys.version_info >= (3, 12):
    import tomllib
else:
    import tomli as tomllib


@dataclass
class VaultConfig:
    path: Path
    timezone: str = "UTC"


@dataclass
class DetectionConfig:
    apps: list[str] = field(default_factory=lambda: ["zoom.us", "com.google.Chrome", "com.tinyspeck.slackmacgap"])
    chrome_window_match: str = "Meet -|meet.google.com"
    slack_min_duration_seconds: int = 30
    poll_interval_seconds: int = 3


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    bit_depth: int = 16
    chunk_duration_seconds: int = 300
    chunk_overlap_seconds: int = 1


@dataclass
class TranscriptionConfig:
    model: str = "large-v3"


@dataclass
class DiarizationConfig:
    keychain_service: str = "meetingscribe"
    keychain_account: str = "hf_token"
    speaker_similarity_threshold: float = 0.75


@dataclass
class SummaryConfig:
    cli: str = "claude"
    model_flag: str = "--model sonnet"
    prompt_file: Path = field(default_factory=lambda: Path("~/.meetingscribe/prompt.md"))


@dataclass
class RetryConfig:
    max_retries: int = 3
    backoff_minutes: list[int] = field(default_factory=lambda: [1, 5, 30])
    summary_retry_interval_minutes: int = 15


@dataclass
class StorageConfig:
    retain_wav_days: int = 0
    orphan_cleanup_days: int = 7


@dataclass
class LoggingConfig:
    level: str = "INFO"


@dataclass
class MeetingScribeConfig:
    vault: VaultConfig
    detection: DetectionConfig
    audio: AudioConfig
    transcription: TranscriptionConfig
    diarization: DiarizationConfig
    summary: SummaryConfig
    retry: RetryConfig
    storage: StorageConfig
    logging: LoggingConfig


def _build_section(cls, data: dict):
    """Build a dataclass from a dict, ignoring unknown keys."""
    import dataclasses
    valid_keys = {f.name for f in dataclasses.fields(cls)}
    filtered = {k: v for k, v in data.items() if k in valid_keys}
    return cls(**filtered)


def load_config(path: Path) -> MeetingScribeConfig:
    """Load config from TOML file, validate, return typed config."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    vault_data = raw.get("vault", {})
    vault_path = Path(vault_data.get("path", "")).expanduser()
    if not vault_path.is_dir():
        raise ValueError(f"vault path does not exist: {vault_path}")
    vault_data["path"] = vault_path

    summary_data = raw.get("summary", {})
    if "prompt_file" in summary_data:
        summary_data["prompt_file"] = Path(summary_data["prompt_file"]).expanduser()

    return MeetingScribeConfig(
        vault=_build_section(VaultConfig, vault_data),
        detection=_build_section(DetectionConfig, raw.get("detection", {})),
        audio=_build_section(AudioConfig, raw.get("audio", {})),
        transcription=_build_section(TranscriptionConfig, raw.get("transcription", {})),
        diarization=_build_section(DiarizationConfig, raw.get("diarization", {})),
        summary=_build_section(SummaryConfig, summary_data),
        retry=_build_section(RetryConfig, raw.get("retry", {})),
        storage=_build_section(StorageConfig, raw.get("storage", {})),
        logging=_build_section(LoggingConfig, raw.get("logging", {})),
    )
