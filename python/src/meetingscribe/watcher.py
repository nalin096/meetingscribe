"""Filesystem watcher daemon for processing meeting manifests."""

import json
import logging
import time
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent

from meetingscribe.config import MeetingScribeConfig
from meetingscribe.manifest import load_manifest, claim_manifest, complete_manifest, fail_manifest, recover_stale
from meetingscribe.pipeline import process_meeting
from meetingscribe.retry import RetryTracker
from meetingscribe.notify import notify

logger = logging.getLogger(__name__)


def process_single_manifest(json_path: Path, config: MeetingScribeConfig, retry_tracker: RetryTracker) -> None:
    """Process a single manifest file through the pipeline."""
    manifest = load_manifest(json_path)
    retry_count = manifest.retry_count

    if not retry_tracker.should_retry(manifest.meeting_id, retry_count):
        logger.warning(f"Max retries exceeded for {manifest.meeting_id}")
        return

    if not retry_tracker.is_ready(manifest.meeting_id, retry_count):
        return

    processing_path = claim_manifest(json_path)
    retry_tracker.record_attempt(manifest.meeting_id)

    try:
        process_meeting(manifest, json_path.parent, config)
        complete_manifest(processing_path)
        logger.info(f"Completed: {manifest.meeting_id}")
    except Exception as e:
        logger.error(f"Failed processing {manifest.meeting_id}: {e}")
        result_path = fail_manifest(processing_path, str(e), retry_count=retry_count, max_retries=config.retry.max_retries)
        if result_path.suffix == ".failed":
            notify("MeetingScribe", f"Failed to process meeting {manifest.meeting_id}")


def process_pending_manifests(recordings_dir: Path, config: MeetingScribeConfig, retry_tracker: RetryTracker | None = None) -> None:
    """Scan for pending .json manifests and process them."""
    if retry_tracker is None:
        retry_tracker = RetryTracker(max_retries=config.retry.max_retries, backoff_minutes=config.retry.backoff_minutes)

    for json_path in sorted(recordings_dir.glob("*.json")):
        process_single_manifest(json_path, config, retry_tracker)


class ManifestHandler(FileSystemEventHandler):
    def __init__(self, config: MeetingScribeConfig, retry_tracker: RetryTracker):
        self.config = config
        self.retry_tracker = retry_tracker

    def _handle_json(self, path: Path) -> None:
        time.sleep(0.5)
        try:
            process_single_manifest(path, self.config, self.retry_tracker)
        except Exception as e:
            logger.error(f"Error handling new manifest {path}: {e}")

    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(".json"):
            self._handle_json(Path(event.src_path))

    def on_moved(self, event):
        if not event.is_directory and event.dest_path.endswith(".json"):
            self._handle_json(Path(event.dest_path))


def resummarize_pending(vault_path: Path) -> list[Path]:
    """Scan vault for .md files with status: needs-summary in frontmatter. Returns list of matches."""
    pending = []
    for md in vault_path.glob("*.md"):
        try:
            content = md.read_text(encoding="utf-8")
            if "status: needs-summary" in content:
                pending.append(md)
                logger.info(f"Found needs-summary note: {md.name}")
        except OSError as e:
            logger.warning(f"Could not read {md}: {e}")
    return pending


def run_daemon(config: MeetingScribeConfig) -> None:
    """Start the filesystem watcher daemon."""
    recordings_dir = Path("~/.meetingscribe/recordings").expanduser()
    recordings_dir.mkdir(parents=True, exist_ok=True)

    retry_tracker = RetryTracker(max_retries=config.retry.max_retries, backoff_minutes=config.retry.backoff_minutes)

    recovered = recover_stale(recordings_dir)
    if recovered:
        logger.info(f"Recovered {len(recovered)} stale manifests")

    process_pending_manifests(recordings_dir, config, retry_tracker)

    handler = ManifestHandler(config, retry_tracker)
    observer = Observer()
    observer.schedule(handler, str(recordings_dir), recursive=False)
    observer.start()

    logger.info(f"Watching {recordings_dir} for new manifests...")

    try:
        while True:
            time.sleep(config.retry.summary_retry_interval_minutes * 60)
            process_pending_manifests(recordings_dir, config, retry_tracker)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
