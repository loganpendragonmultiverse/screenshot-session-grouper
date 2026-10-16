from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from itertools import pairwise
from pathlib import Path
from typing import Any

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
FILENAME_TIME = re.compile(
    r"(?P<date>\d{4}[-_]?\d{2}[-_]?\d{2})[-_ ](?P<time>\d{2}[-_]?\d{2}[-_]?\d{2})"
)


def _parse_timezone(value: str) -> timezone:
    if value in {"Z", "+00:00", "-00:00"}:
        return timezone.utc
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", value)
    if not match:
        raise ValueError("timezone-offset must be Z or +/-HH:MM")
    hours, minutes = int(match.group(2)), int(match.group(3))
    if hours > 23 or minutes > 59:
        raise ValueError("timezone-offset is out of range")
    delta = timedelta(hours=hours, minutes=minutes)
    return timezone(delta if match.group(1) == "+" else -delta)


def _filename_timestamp(path: Path, source_timezone: timezone) -> datetime | None:
    match = FILENAME_TIME.search(path.stem)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group("date") + match.group("time"))
    try:
        return datetime.strptime(digits, "%Y%m%d%H%M%S").replace(tzinfo=source_timezone)
    except ValueError:
        return None


def _relative_reference(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or any(character in value for character in ("\\", ":"))
    ):
        raise ValueError("boundary references must be relative screenshot paths")
    return value


def _boundaries(
    screenshots: list[dict[str, Any]], gap_minutes: int, overrides: dict[str, Any] | None
) -> list[dict[str, Any]]:
    boundaries: list[dict[str, Any]] = []
    for before, after in pairwise(screenshots):
        seconds = (
            datetime.fromisoformat(after["timestamp"]) - datetime.fromisoformat(before["timestamp"])
        ).total_seconds()
        action = "split" if seconds > gap_minutes * 60 else "join"
        boundaries.append(
            {
                "before": before["path"],
                "after": after["path"],
                "before_sha256": before["sha256"],
                "after_sha256": after["sha256"],
                "automatic_action": action,
                "action": action,
                "provenance": "automatic",
            }
        )
    if overrides is None:
        return boundaries
    if (
        not isinstance(overrides, dict)
        or set(overrides) != {"version", "boundaries"}
        or overrides["version"] != 1
        or not isinstance(overrides["boundaries"], list)
    ):
        raise ValueError("boundary overrides must be a version 1 object with a boundaries array")
    by_pair = {(b["before"], b["after"]): b for b in boundaries}
    seen: set[tuple[str, str]] = set()
    for item in overrides["boundaries"]:
        if not isinstance(item, dict) or set(item) != {
            "before",
            "after",
            "before_sha256",
            "after_sha256",
            "action",
        }:
            raise ValueError("boundary override requires paths, hashes and action")
        pair = (_relative_reference(item["before"]), _relative_reference(item["after"]))
        if pair in seen:
            raise ValueError("duplicate or conflicting boundary override")
        seen.add(pair)
        if pair not in by_pair:
            raise ValueError(
                "unknown or stale boundary: references must be adjacent in current order"
            )
        boundary = by_pair[pair]
        if item["action"] not in ("split", "join"):
            raise ValueError("boundary action must be split or join")
        if any(item[key] != boundary[key] for key in ("before_sha256", "after_sha256")):
            raise ValueError("stale boundary: screenshot hashes changed")
        boundary["action"] = item["action"]
        boundary["provenance"] = "manual"
    return boundaries


def scan(
    source: Path,
    gap_minutes: int = 90,
    timezone_offset: str = "+00:00",
    *,
    boundary_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not source.is_dir():
        raise ValueError("source must be a directory")
    if gap_minutes <= 0:
        raise ValueError("gap-minutes must be positive")
    source_timezone = _parse_timezone(timezone_offset)
    screenshots = []
    for path in source.rglob("*"):
        if not path.is_file() or path.is_symlink() or path.suffix.casefold() not in EXTENSIONS:
            continue
        parsed = _filename_timestamp(path, source_timezone)
        timestamp = parsed or datetime.fromtimestamp(path.stat().st_mtime, source_timezone)
        screenshots.append(
            {
                "path": path.relative_to(source).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "timestamp": timestamp.isoformat(timespec="seconds"),
                "source": "filename" if parsed else "modified-time",
            }
        )
    screenshots.sort(key=lambda item: (item["timestamp"], item["path"]))
    boundaries = _boundaries(screenshots, gap_minutes, boundary_overrides)
    sessions: list[dict[str, Any]] = []
    for index, item in enumerate(screenshots):
        if index == 0 or boundaries[index - 1]["action"] == "split":
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
        "timezone_offset": timestamp_offset(source_timezone),
        "screenshot_count": len(screenshots),
        "session_count": len(sessions),
        "sessions": sessions,
        "boundaries": boundaries,
    }


def timestamp_offset(value: timezone) -> str:
    offset = value.utcoffset(None) or timedelta()
    sign = "+" if offset >= timedelta() else "-"
    minutes = abs(int(offset.total_seconds() // 60))
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def export_copies(report: dict[str, Any], destination: Path, collision_mode: str = "error") -> None:
    source = Path(report["source"])
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("copy destination already exists")
    if source == destination or source in destination.parents:
        raise ValueError("copy destination cannot be inside the screenshot source")
    temporary = destination.with_name(f".{destination.name}.tmp")
    if temporary.exists():
        raise ValueError("temporary export path already exists")
    if collision_mode not in {"error", "sequence"}:
        raise ValueError("collision-mode must be error or sequence")
    # Validate every source reference and reviewed hash before creating the staging directory.
    for session in report["sessions"]:
        if not re.fullmatch(r"session-[0-9]+", session["id"]):
            raise ValueError("invalid session identifier")
        for item in session["screenshots"]:
            relative = _relative_reference(item["path"])
            path = source / relative
            if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
                raise ValueError("screenshot reference escapes source")
            if "sha256" in item and hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("stale screenshot: source changed since review")
    manifest: list[dict[str, str]] = []
    try:
        for session in report["sessions"]:
            folder = temporary / session["id"]
            folder.mkdir(parents=True, exist_ok=True)
            for sequence, item in enumerate(session["screenshots"], start=1):
                source_file = source / item["path"]
                target = folder / source_file.name
                if target.exists():
                    if collision_mode == "error":
                        raise ValueError(
                            f"duplicate screenshot filename in {session['id']}: {target.name}"
                        )
                    target = folder / f"{sequence:04d}-{source_file.name}"
                    while target.exists():
                        sequence += 1
                        target = folder / f"{sequence:04d}-{source_file.name}"
                shutil.copy2(source_file, target)
                manifest.append(
                    {
                        "source": item["path"],
                        "destination": target.relative_to(temporary).as_posix(),
                        "sha256": hashlib.sha256(source_file.read_bytes()).hexdigest(),
                    }
                )
        (temporary / "manifest.json").write_text(
            json.dumps(
                {"version": 1, "copies": manifest, "boundaries": report.get("boundaries", [])},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
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
    if report.get("boundaries"):
        lines.extend(["## Boundary decisions", ""])
        lines.extend(
            f"- `{item['before']}` → `{item['after']}`: {item['action']} ({item['provenance']}; automatic: {item['automatic_action']})"
            for item in report["boundaries"]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"
