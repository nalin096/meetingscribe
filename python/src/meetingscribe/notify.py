"""macOS notifications via osascript."""

import subprocess


def notify(title: str, message: str) -> None:
    """Send a macOS notification. Escapes inputs to prevent AppleScript injection."""
    safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
    safe_message = message.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{safe_message}" with title "{safe_title}"'
    subprocess.run(["osascript", "-e", script], capture_output=True)
