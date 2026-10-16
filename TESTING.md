# Testing

## 1.2.0 — 2026-10-16

Synthetic image-byte fixtures force a split inside the gap and a join across the gap. Check default grouping parity, automatic/manual provenance, manifest agreement, source hashes, malformed/unknown/reversed/escaping/conflicting references and content changes before scan or copy. Confirm invalid reviews create no copy destination or staging directory.

Run `python -m pip install -e ".[dev]"`, `ruff format --check .`, `ruff check .`, `pytest` (90% branch-aware coverage floor), and `python -m build`. Fixtures contain synthetic bytes only; no screenshot content is inspected. The required CodeQL workflow was disabled for inactivity during this change; its state was left unchanged.
