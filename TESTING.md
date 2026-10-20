# Testing

## 1.2.0 — 2026-10-16

Synthetic image-byte fixtures force a split inside the gap and a join across the gap. Check default grouping parity, automatic/manual provenance, manifest agreement, source hashes, malformed/unknown/reversed/escaping/conflicting references and content changes before scan or copy. Confirm invalid reviews create no copy destination or staging directory.

Run `python -m pip install -e ".[dev]"`, `ruff format --check .`, `ruff check .`, `pytest` (90% branch-aware coverage floor), and `python -m build`. Fixtures contain synthetic bytes only; no screenshot content is inspected. Release completion requires the protected CI and CodeQL checks for the exact proposed head.

Race fixtures edit a later source from the first copy callback after preflight and edit an already-copied source before manifest creation. Require a staged-byte mismatch to abort with no final or temporary destination, require successful manifest hashes to equal staged bytes, and preserve all source bytes except the fixtures' explicit concurrent edits.

## Scan and output boundaries

Version 1.2.1 refuses selected symlink roots, skips descendant links and fails unreadable discovery instead of silently returning partial groups. Ancestor path aliases remain allowed. Hashing uses one MiB chunks and rejects metadata/byte-count changes; this remains sequential local evidence, not an atomic snapshot. Gap controls require positive integers; review versions require integer 1.

Copy export validates report structure/counts, unique session IDs and screenshot references before creating its exclusively owned staging directory. Empty scans produce an empty copy manifest. Basename collisions use Unicode NFC/case folding on every platform; sequence mode adds deterministic prefixes. Existing/dangling report and destination paths are preserved. These guards do not defend against hostile concurrent filesystem replacement. Copy export and report writing are separate operations: a later report I/O failure can leave an already completed copy export. Markdown filenames retain literal control-character escapes.

Windows reparse-point roots are refused and descendant reparse entries are skipped, including junctions; portable metadata fixtures verify rejection before recursion.

Relative direct-API report source paths are checked for links before canonicalization; nested copy destinations remain forbidden after canonicalization. Blank sources are invalid.
