# Development handoff

## 1.2.0 — 2026-10-16

`--boundary-overrides review.json` accepts a version 1 JSON object with a `boundaries` array. Each override contains `before`, `after`, `before_sha256`, `after_sha256` and `action` (`split` or `join`). Use relative paths and hashes from a fresh JSON scan; copy those five fields for the boundary being reviewed. The referenced screenshots must remain adjacent in current timestamp/path order and their contents must match the reviewed hashes. Unknown, reversed, duplicate/conflicting, escaping and stale references fail before export staging begins. Reports record each boundary's final action, automatic action and provenance; copy manifests include the same decisions. Unspecified boundaries retain the configured automatic gap behavior. Grouping and joining do not redact screenshots; reports, paths, timestamps, hashes and copied images can be sensitive. Originals remain copy-only and unchanged.

For current scan reports, each staged file is hashed after copying and must match its reviewed scan hash before the final destination is published. Copy-manifest hashes describe the staged bytes, even if a source changes after its copy. A mismatch aborts the export and removes staging without altering source files. Legacy reports without scan hashes retain copy support, with manifest hashes still derived from staged bytes.

## Scan and output boundaries

Version 1.2.1 refuses selected symlink roots, skips descendant links and fails unreadable discovery instead of silently returning partial groups. Ancestor path aliases remain allowed. Hashing uses one MiB chunks and rejects metadata/byte-count changes; this remains sequential local evidence, not an atomic snapshot. Gap controls require positive integers; review versions require integer 1.

Copy export validates report structure/counts, unique session IDs and screenshot references before creating its exclusively owned staging directory. Empty scans produce an empty copy manifest. Basename collisions use Unicode NFC/case folding on every platform; sequence mode adds deterministic prefixes. Existing/dangling report and destination paths are preserved. These guards do not defend against hostile concurrent filesystem replacement. Copy export and report writing are separate operations: a later report I/O failure can leave an already completed copy export. Markdown filenames retain literal control-character escapes.

Windows reparse-point roots are refused and descendant reparse entries are skipped, including junctions; portable metadata fixtures verify rejection before recursion.

Relative direct-API report source paths are checked for links before canonicalization; nested copy destinations remain forbidden after canonicalization. Blank sources are invalid.
