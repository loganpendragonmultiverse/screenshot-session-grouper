import json
import os
from datetime import datetime, timezone

import pytest

from screenshot_session_grouper.cli import main
from screenshot_session_grouper.core import export_copies, render_markdown, scan


def test_grouping_uses_filename_and_modified_time(tmp_path):
    first = tmp_path / "Game_2026-07-26_10-00-00.png"
    second = tmp_path / "plain.jpg"
    third = tmp_path / "Game_2026-07-26_14-00-00.png"
    for path in (first, second, third):
        path.write_bytes(b"image")
    timestamp = datetime(2026, 7, 26, 10, 30, tzinfo=timezone.utc).timestamp()
    os.utime(second, (timestamp, timestamp))
    report = scan(tmp_path, 60)
    assert report["session_count"] == 2
    assert report["timezone_offset"] == "+00:00"
    assert report["sessions"][0]["screenshots"][0]["source"] == "filename"
    assert "session-001" in render_markdown(report)


def test_export_and_safety(tmp_path):
    source = tmp_path / "shots"
    source.mkdir()
    (source / "Shot_2026-07-26_10-00-00.png").write_bytes(b"image")
    report = scan(source)
    destination = tmp_path / "organized"
    export_copies(report, destination)
    assert (destination / "session-001" / "Shot_2026-07-26_10-00-00.png").exists()
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["copies"][0]["destination"].startswith("session-001/")
    assert len(manifest["copies"][0]["sha256"]) == 64
    with pytest.raises(ValueError, match="exists"):
        export_copies(report, destination)
    with pytest.raises(ValueError, match="inside"):
        export_copies(report, source / "organized")


def test_cli_json_and_validation(tmp_path, capsys):
    (tmp_path / "shot.png").write_bytes(b"image")
    assert main([str(tmp_path), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["screenshot_count"] == 1
    assert main([str(tmp_path), "--gap-minutes", "0"]) == 2


def test_invalid_filename_falls_back_and_ignores_other_files(tmp_path):
    (tmp_path / "Shot_2026-99-99_10-00-00.png").write_bytes(b"image")
    (tmp_path / "notes.txt").write_text("not a screenshot", encoding="utf-8")
    report = scan(tmp_path)
    assert report["screenshot_count"] == 1
    assert report["sessions"][0]["screenshots"][0]["source"] == "modified-time"
    with pytest.raises(ValueError, match="directory"):
        scan(tmp_path / "missing")


def test_export_rejects_temporary_path_and_duplicate_names(tmp_path):
    source = tmp_path / "shots"
    (source / "one").mkdir(parents=True)
    (source / "two").mkdir()
    for folder in ("one", "two"):
        (source / folder / "Shot_2026-07-26_10-00-00.png").write_bytes(b"image")
    report = scan(source)
    destination = tmp_path / "organized"
    temporary = tmp_path / ".organized.tmp"
    temporary.mkdir()
    with pytest.raises(ValueError, match="temporary"):
        export_copies(report, destination)
    temporary.rmdir()
    with pytest.raises(ValueError, match="duplicate"):
        export_copies(report, destination)
    assert not temporary.exists()
    export_copies(report, destination, "sequence")
    copied = list((destination / "session-001").glob("*.png"))
    assert len(copied) == 2
    assert any(path.name.startswith("0002-") for path in copied)


def test_cli_copy_and_safe_report_output(tmp_path):
    source = tmp_path / "shots"
    source.mkdir()
    (source / "shot.png").write_bytes(b"image")
    destination = tmp_path / "copies"
    output = tmp_path / "report.md"
    assert main([str(source), "--copy-to", str(destination), "--output", str(output)]) == 0
    assert destination.is_dir()
    assert output.is_file()
    assert main([str(source), "--output", str(output)]) == 2


def test_explicit_filename_timezone_and_invalid_offset(tmp_path):
    (tmp_path / "Shot_2026-07-26_10-00-00.png").write_bytes(b"image")
    report = scan(tmp_path, timezone_offset="-04:00")
    assert report["timezone_offset"] == "-04:00"
    assert report["sessions"][0]["start"].endswith("-04:00")
    with pytest.raises(ValueError, match="timezone-offset"):
        scan(tmp_path, timezone_offset="local")
