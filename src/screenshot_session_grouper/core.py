from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import unicodedata
from datetime import datetime, timedelta, timezone
from itertools import pairwise
from pathlib import Path
from typing import Any

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
FILENAME_TIME = re.compile(
    r"(?P<date>\d{4}[-_]?\d{2}[-_]?\d{2})[-_ ](?P<time>\d{2}[-_]?\d{2}[-_]?\d{2})"
)


def _parse_timezone(value: str) -> timezone:
    if not isinstance(value, str):
        raise TypeError("timezone-offset must be text")
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
        or type(overrides["version"]) is not int
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


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        initial = os.fstat(stream.fileno())
        if not stat.S_ISREG(initial.st_mode):
            raise ValueError("screenshot must be a regular file")
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            count += len(chunk)
        final = os.fstat(stream.fileno())
    if count != initial.st_size or (initial.st_size, initial.st_mtime_ns, initial.st_ctime_ns) != (
        final.st_size,
        final.st_mtime_ns,
        final.st_ctime_ns,
    ):
        raise ValueError("screenshot changed during hashing")
    return digest.hexdigest()


def _screenshots(directory: Path):
    with os.scandir(directory) as iterator:
        entries = sorted(iterator, key=lambda entry: entry.name)
    for entry in entries:
        metadata = entry.stat(follow_symlinks=False)
        if getattr(metadata, "st_file_attributes", 0) & 0x400:
            continue
        mode = metadata.st_mode
        if stat.S_ISDIR(mode):
            yield from _screenshots(Path(entry.path))
        elif stat.S_ISREG(mode) and Path(entry.name).suffix.casefold() in EXTENSIONS:
            yield Path(entry.path)


def scan(
    source: Path,
    gap_minutes: int = 90,
    timezone_offset: str = "+00:00",
    *,
    boundary_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if source.is_symlink():
        raise ValueError("source must be a directory, not a symlink")
    try:
        metadata = source.lstat()
        mode = metadata.st_mode
    except FileNotFoundError as exc:
        raise ValueError("source must be a directory") from exc
    if not stat.S_ISDIR(mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
        raise ValueError("source must be a directory without reparse links")
    if type(gap_minutes) is not int or gap_minutes <= 0:
        raise ValueError("gap-minutes must be a positive integer")
    source_timezone = _parse_timezone(timezone_offset)
    screenshots = []
    for path in _screenshots(source):
        parsed = _filename_timestamp(path, source_timezone)
        timestamp = parsed or datetime.fromtimestamp(path.stat().st_mtime, source_timezone)
        screenshots.append(
            {
                "path": path.relative_to(source).as_posix(),
                "sha256": _hash_file(path),
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
    if (
        not isinstance(report, dict)
        or type(report.get("version")) is not int
        or report["version"] != 1
        or not isinstance(report.get("source"), str)
        or not report["source"]
        or not isinstance(report.get("sessions"), list)
    ):
        raise ValueError("export requires a version 1 scan report")
    source = Path(report["source"])
    metadata = source.lstat()
    if (
        source.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or getattr(metadata, "st_file_attributes", 0) & 0x400
    ):
        raise ValueError("report source must be a regular directory without links")
    source = source.resolve()
    if destination.is_symlink():
        raise ValueError("copy destination already exists")
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("copy destination already exists")
    if source == destination or source in destination.parents:
        raise ValueError("copy destination cannot be inside the screenshot source")
    temporary = destination.with_name(f".{destination.name}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError("temporary export path already exists")
    if not isinstance(collision_mode, str) or collision_mode not in {"error", "sequence"}:
        raise ValueError("collision-mode must be error or sequence")
    # Validate every source reference and reviewed hash before creating the staging directory.
    seen_sessions, seen_paths = set(), set()
    for session in report["sessions"]:
        if (
            not isinstance(session, dict)
            or not isinstance(session.get("id"), str)
            or not isinstance(session.get("screenshots"), list)
        ):
            raise TypeError("invalid export session")
        if session["id"] in seen_sessions:
            raise ValueError("duplicate session identifier")
        seen_sessions.add(session["id"])
        if not re.fullmatch(r"session-[0-9]+", session["id"]):
            raise ValueError("invalid session identifier")
        for item in session["screenshots"]:
            if not isinstance(item, dict) or "path" not in item:
                raise ValueError("invalid screenshot item")
            relative = _relative_reference(item["path"])
            if relative in seen_paths:
                raise ValueError("duplicate screenshot reference")
            seen_paths.add(relative)
            if "sha256" in item and (
                not isinstance(item["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
            ):
                raise ValueError("invalid screenshot SHA-256")
            path = source / relative
            if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
                raise ValueError("screenshot reference escapes source")
            if "sha256" in item and _hash_file(path) != item["sha256"]:
                raise ValueError("stale screenshot: source changed since review")
    for field, count in (
        ("session_count", len(seen_sessions)),
        ("screenshot_count", len(seen_paths)),
    ):
        if field in report and (type(report[field]) is not int or report[field] != count):
            raise ValueError("export report count mismatch")
    manifest: list[dict[str, str]] = []
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary.mkdir()
    try:
        for session in report["sessions"]:
            folder = temporary / session["id"]
            folder.mkdir()
            used_names: set[str] = set()
            for sequence, item in enumerate(session["screenshots"], start=1):
                source_file = source / item["path"]
                target = folder / source_file.name
                if unicodedata.normalize("NFC", target.name).casefold() in used_names:
                    if collision_mode == "error":
                        raise ValueError(
                            f"duplicate screenshot filename in {session['id']}: {target.name}"
                        )
                    target = folder / f"{sequence:04d}-{source_file.name}"
                    while unicodedata.normalize("NFC", target.name).casefold() in used_names:
                        sequence += 1
                        target = folder / f"{sequence:04d}-{source_file.name}"
                used_names.add(unicodedata.normalize("NFC", target.name).casefold())
                shutil.copy2(source_file, target)
                copied_sha256 = _hash_file(target)
                if "sha256" in item and copied_sha256 != item["sha256"]:
                    raise ValueError("stale screenshot: copied bytes differ from reviewed scan")
                manifest.append(
                    {
                        "source": item["path"],
                        "destination": target.relative_to(temporary).as_posix(),
                        "sha256": copied_sha256,
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
        if destination.exists() or destination.is_symlink():
            raise ValueError("copy destination appeared during export")
        os.replace(temporary, destination)
    except Exception:
        if temporary.exists() or temporary.is_symlink():
            shutil.rmtree(temporary)
        raise


def _filename(value: str) -> str:
    literal = "".join(
        f"\\u{ord(char):04x}" if ord(char) < 32 or ord(char) == 127 else char for char in value
    )
    fence = "`" * (max((len(x) for x in re.findall(r"`+", literal)), default=0) + 1)
    return fence + " " + literal + " " + fence


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Screenshot Sessions",
        "",
        f"**{report['screenshot_count']} screenshots · {report['session_count']} likely sessions · {report['gap_minutes']} minute gap**",
        "",
    ]
    for session in report["sessions"]:
        lines.extend([f"## {session['id']} — {session['start']} to {session['end']}", ""])
        lines.extend(
            f"- {_filename(item['path'])} ({item['source']})" for item in session["screenshots"]
        )
        lines.append("")
    if report.get("boundaries"):
        lines.extend(["## Boundary decisions", ""])
        lines.extend(
            f"- {_filename(item['before'])} → {_filename(item['after'])}: {item['action']} ({item['provenance']}; automatic: {item['automatic_action']})"
            for item in report["boundaries"]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"
