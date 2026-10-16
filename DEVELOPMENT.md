# Development handoff

## 1.2.0 — 2026-10-16

`--boundary-overrides review.json` accepts a version 1 JSON object with a `boundaries` array. Each override contains `before`, `after`, `before_sha256`, `after_sha256` and `action` (`split` or `join`). Use relative paths and hashes from a fresh JSON scan; copy those five fields for the boundary being reviewed. The referenced screenshots must remain adjacent in current timestamp/path order and their contents must match the reviewed hashes. Unknown, reversed, duplicate/conflicting, escaping and stale references fail before export staging begins. Reports record each boundary's final action, automatic action and provenance; copy manifests include the same decisions. Unspecified boundaries retain the configured automatic gap behavior. Grouping and joining do not redact screenshots; reports, paths, timestamps, hashes and copied images can be sensitive. Originals remain copy-only and unchanged.
