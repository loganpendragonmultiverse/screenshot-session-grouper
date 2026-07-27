from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
FILENAME_TIME = re.compile(
    r"(?P<date>\d{4}[-_]?\d{2}[-_]?\d{2})[-_ ](?P<time>\d{2}[-_]?\d{2}[-_]?\d{2})"
)


def _filename_timestamp(path: Path) -> datetime | None:
    match = FILENAME_TIME.search(path.stem)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group("date") + match.group("time"))
    try:
        return datetime.strptime(digits, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def scan(source: Path, gap_minutes: int = 90) -> dict[str, Any]:
    if not source.is_dir():
        raise ValueError("source must be a directory")
    if gap_minutes <= 0:
        raise ValueError("gap-minutes must be positive")
    screenshots = []
    for path in source.rglob("*"):
        if not path.is_file() or path.is_symlink() or path.suffix.casefold() not in EXTENSIONS:
            continue
        parsed = _filename_timestamp(path)
        timestamp = parsed or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        screenshots.append(
            {
                "path": path.relative_to(source).as_posix(),
                "timestamp": timestamp.isoformat(timespec="seconds"),
                "source": "filename" if parsed else "modified-time",
            }
        )
    screenshots.sort(key=lambda item: (item["timestamp"], item["path"]))
    sessions: list[dict[str, Any]] = []
    for item in screenshots:
        current = datetime.fromisoformat(item["timestamp"])
        if (
            not sessions
            or (current - datetime.fromisoformat(sessions[-1]["end"])).total_seconds()
            > gap_minutes * 60
        ):
            sessions.append(
                {
                    "id": f"session-{len(sessions) + 1:03d}",
                    "start": item["timestamp"],
                    "end": item["timestamp"],
                    "screenshots": [item],
                }
            )
        else:
            sessions[-1]["end"] = item["timestamp"]
            sessions[-1]["screenshots"].append(item)
    return {
        "version": 1,
        "source": str(source.resolve()),
        "gap_minutes": gap_minutes,
        "screenshot_count": len(screenshots),
        "session_count": len(sessions),
        "sessions": sessions,
    }


def export_copies(report: dict[str, Any], destination: Path) -> None:
    source = Path(report["source"])
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("copy destination already exists")
    if source == destination or source in destination.parents:
        raise ValueError("copy destination cannot be inside the screenshot source")
    temporary = destination.with_name(f".{destination.name}.tmp")
    if temporary.exists():
        raise ValueError("temporary export path already exists")
    try:
        for session in report["sessions"]:
            folder = temporary / session["id"]
            folder.mkdir(parents=True, exist_ok=True)
            for item in session["screenshots"]:
                source_file = source / item["path"]
                target = folder / source_file.name
                if target.exists():
                    raise ValueError(
                        f"duplicate screenshot filename in {session['id']}: {target.name}"
                    )
                shutil.copy2(source_file, target)
        os.replace(temporary, destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Screenshot Sessions",
        "",
        f"**{report['screenshot_count']} screenshots · {report['session_count']} likely sessions · {report['gap_minutes']} minute gap**",
        "",
    ]
    for session in report["sessions"]:
        lines.extend([f"## {session['id']} — {session['start']} to {session['end']}", ""])
        lines.extend(f"- `{item['path']}` ({item['source']})" for item in session["screenshots"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"
