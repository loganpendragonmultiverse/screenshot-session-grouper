import hashlib
import json

import pytest

from screenshot_session_grouper.cli import main
from screenshot_session_grouper.core import export_copies, scan


def fixture(tmp_path):
    source = tmp_path / "shots"
    source.mkdir()
    for time in ["10-00-00", "10-05-00", "15-00-00"]:
        (source / ("Shot_2026-10-01_" + time + ".png")).write_bytes(time.encode())
    paths = sorted(source.glob("*.png"))
    return source, paths


def overrides(paths, action, index=0):
    before, after = paths[index : index + 2]
    return {
        "version": 1,
        "boundaries": [
            {
                "before": before.name,
                "after": after.name,
                "before_sha256": hashlib.sha256(before.read_bytes()).hexdigest(),
                "after_sha256": hashlib.sha256(after.read_bytes()).hexdigest(),
                "action": action,
            }
        ],
    }


@pytest.mark.parametrize("action,index,count", [("split", 0, 3), ("join", 1, 1)])
def test_reviewed_boundary_and_copy_manifest(tmp_path, action, index, count):
    source, paths = fixture(tmp_path)
    hashes = {p: p.read_bytes() for p in paths}
    policy = overrides(paths, action, index)
    report = scan(source, boundary_overrides=policy)
    assert report["session_count"] == count
    boundary = report["boundaries"][index]
    assert boundary["provenance"] == "manual" and boundary["action"] == action
    assert report["boundaries"][1 - index]["provenance"] == "automatic"
    destination = tmp_path / "copies"
    export_copies(report, destination)
    manifest = json.loads((destination / "manifest.json").read_text())
    assert manifest["boundaries"] == report["boundaries"]
    assert all(p.read_bytes() == raw for p, raw in hashes.items())
    policy_path = tmp_path / "review.json"
    policy_path.write_text(json.dumps(policy))
    assert main([str(source), "--boundary-overrides", str(policy_path), "--format", "json"]) == 0


@pytest.mark.parametrize(
    "mutation", ["unknown", "stale", "conflict", "escaping", "reverse", "bad-action", "bad-shape"]
)
def test_bad_overrides_fail_before_copy(tmp_path, mutation):
    source, paths = fixture(tmp_path)
    policy = overrides(paths, "split")
    item = policy["boundaries"][0]
    if mutation == "unknown":
        item["after"] = "unknown.png"
    if mutation == "stale":
        item["before_sha256"] = "0" * 64
    if mutation == "conflict":
        policy["boundaries"].append({**item, "action": "join"})
    if mutation == "escaping":
        item["before"] = "../outside.png"
    if mutation == "reverse":
        item["before"], item["after"] = item["after"], item["before"]
    if mutation == "bad-action":
        item["action"] = "delete"
    if mutation == "bad-shape":
        policy["boundaries"] = None
    policy_path = tmp_path / "review.json"
    policy_path.write_text(json.dumps(policy))
    destination = tmp_path / "copies"
    assert (
        main([str(source), "--boundary-overrides", str(policy_path), "--copy-to", str(destination)])
        == 2
    )
    assert not destination.exists()
    assert not (tmp_path / ".copies.tmp").exists()


def test_default_parity_and_stale_review(tmp_path):
    source, paths = fixture(tmp_path)
    default = scan(source)
    assert (
        scan(source, boundary_overrides={"version": 1, "boundaries": []})["sessions"]
        == default["sessions"]
    )
    assert default["session_count"] == 2
    assert all(b["provenance"] == "automatic" for b in default["boundaries"])
    policy = overrides(paths, "join", 1)
    paths[2].write_bytes(b"changed")
    with pytest.raises(ValueError, match="stale"):
        scan(source, boundary_overrides=policy)


@pytest.mark.parametrize(
    "root", [None, [], {"version": 2, "boundaries": []}, {"version": 1, "boundaries": [{}]}]
)
def test_invalid_review_root(tmp_path, root):
    source, _ = fixture(tmp_path)
    review = tmp_path / "review.json"
    review.write_text(json.dumps(root))
    destination = tmp_path / "copies"
    assert (
        main([str(source), "--boundary-overrides", str(review), "--copy-to", str(destination)]) == 2
    )
    assert not destination.exists()


def test_changed_source_before_export(tmp_path):
    source, paths = fixture(tmp_path)
    report = scan(source, boundary_overrides=overrides(paths, "split"))
    paths[0].write_bytes(b"edited after scan")
    destination = tmp_path / "copies"
    with pytest.raises(ValueError, match="stale"):
        export_copies(report, destination)
    assert not destination.exists()
    assert not (tmp_path / ".copies.tmp").exists()


def test_legacy_scan_report_still_exports(tmp_path):
    source, _ = fixture(tmp_path)
    report = scan(source)
    report.pop("boundaries")
    for session in report["sessions"]:
        for item in session["screenshots"]:
            item.pop("sha256")
    destination = tmp_path / "copies"
    export_copies(report, destination)
    assert len(json.loads((destination / "manifest.json").read_text())["copies"]) == 3


def test_source_changed_after_preflight_is_not_published(tmp_path, monkeypatch):
    from screenshot_session_grouper import core

    source, paths = fixture(tmp_path)
    original = {path: path.read_bytes() for path in paths}
    report = scan(source, boundary_overrides=overrides(paths, "join", 1))
    real_copy = core.shutil.copy2
    changed = False

    def concurrent_copy(src, dst):
        nonlocal changed
        result = real_copy(src, dst)
        if src == paths[0]:
            paths[2].write_bytes(b"synthetic concurrent edit before later copy")
            changed = True
        return result

    monkeypatch.setattr(core.shutil, "copy2", concurrent_copy)
    destination = tmp_path / "copies"
    with pytest.raises(ValueError, match="stale"):
        export_copies(report, destination)
    assert changed
    assert not destination.exists()
    assert not (tmp_path / ".copies.tmp").exists()
    assert paths[0].read_bytes() == original[paths[0]]
    assert paths[1].read_bytes() == original[paths[1]]
    assert paths[2].read_bytes() == b"synthetic concurrent edit before later copy"


def test_manifest_hashes_staged_bytes_when_source_changes_after_copy(tmp_path, monkeypatch):
    from screenshot_session_grouper import core

    source, paths = fixture(tmp_path)
    original = {path: path.read_bytes() for path in paths}
    report = scan(source, boundary_overrides=overrides(paths, "split"))
    real_copy = core.shutil.copy2

    def concurrent_copy(src, dst):
        result = real_copy(src, dst)
        if src == paths[0]:
            paths[0].write_bytes(b"synthetic concurrent edit after copy")
        return result

    monkeypatch.setattr(core.shutil, "copy2", concurrent_copy)
    destination = tmp_path / "copies"
    export_copies(report, destination)
    manifest = json.loads((destination / "manifest.json").read_text())
    for item in manifest["copies"]:
        copied = destination / item["destination"]
        expected = hashlib.sha256(original[source / item["source"]]).hexdigest()
        assert item["sha256"] == hashlib.sha256(copied.read_bytes()).hexdigest() == expected
    assert paths[0].read_bytes() == b"synthetic concurrent edit after copy"
    assert paths[1].read_bytes() == original[paths[1]]
    assert paths[2].read_bytes() == original[paths[2]]
