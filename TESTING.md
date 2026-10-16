# Testing

## 1.2.0 — 2026-10-16

Synthetic image-byte fixtures force a split inside the gap and a join across the gap. Check default grouping parity, automatic/manual provenance, manifest agreement, source hashes, malformed/unknown/reversed/escaping/conflicting references and content changes before scan or copy. Confirm invalid reviews create no copy destination or staging directory.

Run `python -m pip install -e ".[dev]"`, `ruff format --check .`, `ruff check .`, `pytest` (90% branch-aware coverage floor), and `python -m build`. Fixtures contain synthetic bytes only; no screenshot content is inspected. Release completion requires the protected CI and CodeQL checks for the exact proposed head.

Race fixtures edit a later source from the first copy callback after preflight and edit an already-copied source before manifest creation. Require a staged-byte mismatch to abort with no final or temporary destination, require successful manifest hashes to equal staged bytes, and preserve all source bytes except the fixtures' explicit concurrent edits.
