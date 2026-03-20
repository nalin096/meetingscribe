"""Disk management: WAV cleanup, orphan removal, disk space checks."""

import logging
import shutil
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def cleanup_processed_wavs(directory: Path, retain_days: int) -> None:
    """Delete WAV files. If retain_days > 0, only delete files older than that."""
    if retain_days > 0:
        cutoff = time.time() - (retain_days * 86400)
        for wav in directory.glob("*.wav"):
            if wav.stat().st_mtime < cutoff:
                wav.unlink()
                logger.info(f"Deleted retained WAV: {wav.name}")
    else:
        for wav in directory.glob("*.wav"):
            wav.unlink()
            logger.info(f"Deleted WAV: {wav.name}")


def cleanup_orphans(directory: Path, max_age_days: int = 7) -> None:
    """Remove WAV chunks older than max_age_days."""
    cutoff = time.time() - (max_age_days * 86400)
    for wav in directory.glob("*.wav"):
        if wav.stat().st_mtime < cutoff:
            wav.unlink()
            logger.info(f"Cleaned orphan: {wav.name}")


def check_disk_space(directory: Path, min_mb: int = 500) -> bool:
    """Return True if enough disk space available."""
    stat = shutil.disk_usage(directory)
    free_mb = stat.free / (1024 * 1024)
    if free_mb < min_mb:
        logger.warning(f"Low disk space: {free_mb:.0f}MB free (minimum {min_mb}MB)")
        return False
    return True
