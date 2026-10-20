import copy
import json
import os
from pathlib import Path

import pytest

from screenshot_session_grouper import core
from screenshot_session_grouper.cli import main


def source(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "shot.png").write_bytes(b"synthetic")
    return root


@pytest.mark.parametrize("gap", [True, 1.5, "1", 0, -1])
def test_gap_types(tmp_path, gap):
    with pytest.raises(ValueError, match="integer"):
        core.scan(source(tmp_path), gap)


@pytest.mark.parametrize("zone", [None, [], 1])
def test_timezone_type(tmp_path, zone):
    with pytest.raises(TypeError, match="text"):
        core.scan(source(tmp_path), timezone_offset=zone)


@pytest.mark.parametrize("version", [True, 1.0])
def test_review_version_type(tmp_path, version):
    with pytest.raises(ValueError, match="version"):
        core.scan(source(tmp_path), boundary_overrides={"version": version, "boundaries": []})


def test_unreadable_discovery_fails_without_output(tmp_path, monkeypatch):
    root = source(tmp_path)
    denied = root / "denied"
    denied.mkdir()
    original = os.scandir

    def scandir(path):
        if Path(path) == denied:
            raise PermissionError("synthetic denied directory")
        return original(path)

    monkeypatch.setattr(os, "scandir", scandir)
    copies, report = tmp_path / "copies", tmp_path / "report"
    assert main([str(root), "--copy-to", str(copies), "--output", str(report)]) == 2
    assert not copies.exists() and not report.exists()


def test_hashing_is_chunked_and_stable(tmp_path, monkeypatch):
    root = source(tmp_path)

    def forbidden(*a, **kw):
        pytest.fail("whole-file byte read")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    assert core.scan(root)["screenshot_count"] == 1
    real = os.fstat
    calls = 0
    from types import SimpleNamespace

    def changed(fd):
        nonlocal calls
        calls += 1
        value = real(fd)
        return SimpleNamespace(
            st_mode=value.st_mode,
            st_size=value.st_size + (calls % 2 == 0),
            st_mtime_ns=value.st_mtime_ns,
            st_ctime_ns=value.st_ctime_ns,
        )

    monkeypatch.setattr(os, "fstat", changed)
    with pytest.raises(ValueError, match="changed"):
        core.scan(root)


def test_empty_scan_exports_manifest(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    destination = tmp_path / "copies"
    core.export_copies(core.scan(root), destination)
    assert json.loads((destination / "manifest.json").read_text())["copies"] == []


@pytest.mark.parametrize(
    "mutation",
    ["root", "session", "duplicate-session", "item", "duplicate-path", "hash", "count", "version"],
)
def test_malformed_exports_do_not_stage(tmp_path, mutation):
    report = core.scan(source(tmp_path))
    if mutation == "root":
        report = []
    elif mutation == "session":
        report["sessions"][0] = []
    elif mutation == "duplicate-session":
        report["sessions"].append(copy.deepcopy(report["sessions"][0]))
    elif mutation == "item":
        report["sessions"][0]["screenshots"][0] = None
    elif mutation == "duplicate-path":
        report["sessions"][0]["screenshots"].append(
            copy.deepcopy(report["sessions"][0]["screenshots"][0])
        )
    elif mutation == "hash":
        report["sessions"][0]["screenshots"][0]["sha256"] = True
    elif mutation == "count":
        report["screenshot_count"] = True
    elif mutation == "version":
        report["version"] = True
    destination = tmp_path / "copies"
    with pytest.raises((TypeError, ValueError)):
        core.export_copies(report, destination)
    assert not destination.exists() and not (tmp_path / ".copies.tmp").exists()


def test_portable_case_collisions(tmp_path):
    root = tmp_path / "source"
    for folder, name in [("one", "Shot.png"), ("two", "shot.PNG")]:
        (root / folder).mkdir(parents=True)
        (root / folder / name).write_bytes(b"synthetic")
    report = core.scan(root)
    with pytest.raises(ValueError, match="duplicate"):
        core.export_copies(report, tmp_path / "bad")
    core.export_copies(report, tmp_path / "good", "sequence")
    assert len(list((tmp_path / "good/session-001").iterdir())) == 2


def test_existing_report_prevents_copy(tmp_path):
    root = source(tmp_path)
    report = tmp_path / "report"
    report.write_text("keep")
    copies = tmp_path / "copies"
    assert main([str(root), "--copy-to", str(copies), "--output", str(report)]) == 2
    assert report.read_text() == "keep" and not copies.exists()


@pytest.mark.parametrize("kind", ["report", "destination", "temporary", "source"])
def test_dangling_and_root_links(tmp_path, kind):
    root = source(tmp_path)
    destination, report = tmp_path / "copies", tmp_path / "report"
    link = {
        "report": report,
        "destination": destination,
        "temporary": tmp_path / ".copies.tmp",
        "source": tmp_path / "linked-source",
    }[kind]
    target = root if kind == "source" else tmp_path / "missing"
    try:
        link.symlink_to(target, target_is_directory=kind != "report")
    except OSError:
        pytest.skip("symlink unavailable")
    assert (
        main(
            [
                str(link if kind == "source" else root),
                "--copy-to",
                str(destination),
                "--output",
                str(report),
            ]
        )
        == 2
    )
    assert link.is_symlink()
    if kind != "source":
        assert not target.exists()


def test_report_created_during_scan_is_preserved(tmp_path, monkeypatch):
    root = source(tmp_path)
    report = tmp_path / "report"
    real = core.scan

    def scan(*a, **kw):
        result = real(*a, **kw)
        report.write_text("raced")
        return result

    monkeypatch.setattr("screenshot_session_grouper.cli.scan", scan)
    assert main([str(root), "--output", str(report)]) == 2
    assert report.read_text() == "raced"


def test_markdown_literal_filename():
    assert core._filename("a```b\n# title") == "```` a```b\\u000a# title ````"


def test_selected_reparse_root_is_rejected(tmp_path, monkeypatch):
    import stat
    from types import SimpleNamespace

    root = source(tmp_path)
    real = Path.lstat

    def metadata(path, *a, **kw):
        if path == root:
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_file_attributes=0x400)
        return real(path, *a, **kw)

    monkeypatch.setattr(Path, "lstat", metadata)
    with pytest.raises(ValueError, match="reparse"):
        core.scan(root)


def test_descendant_reparse_is_not_traversed(tmp_path, monkeypatch):
    import stat
    from types import SimpleNamespace

    root = source(tmp_path)
    calls = []

    class Entry:
        name = "junction"
        path = str(root / "junction")

        def stat(self, **kw):
            assert kw == {"follow_symlinks": False}
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_file_attributes=0x400)

    class Listing:
        def __enter__(self):
            return iter([Entry()])

        def __exit__(self, *a):
            return None

    def scandir(path):
        calls.append(path)
        assert path == root
        return Listing()

    monkeypatch.setattr(os, "scandir", scandir)
    assert core.scan(root)["screenshot_count"] == 0
    assert calls == [root]


def test_relative_report_source_cannot_export_inside_itself(tmp_path, monkeypatch):
    root = source(tmp_path)
    report = core.scan(root)
    monkeypatch.chdir(tmp_path)
    report["source"] = "source"
    with pytest.raises(ValueError, match="inside"):
        core.export_copies(report, root / "nested")
    assert not (root / "nested").exists() and not (root / ".nested.tmp").exists()


def test_blank_report_source_rejected(tmp_path):
    report = core.scan(source(tmp_path))
    report["source"] = ""
    with pytest.raises(ValueError, match="report"):
        core.export_copies(report, tmp_path / "copies")
