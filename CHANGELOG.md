# Changelog

## 1.2.1 - 2026-10-20

- Fail unreadable screenshot discovery and hash in bounded chunks with stable metadata checks.
- Validate scan/export controls and manifests; support empty export and portable case/Unicode collisions.
- Protect report/destination paths and exclusively own staging before cleanup.
- Render literal Markdown filenames and document sequential output boundaries.

## 1.2.0 - 2026-10-16

- Verify staged copied bytes against reviewed hashes before publishing; derive manifest hashes from staged bytes.

- Allow reviewed split/join decisions at named adjacent screenshot boundaries, with automatic and manual provenance.
- Add synthetic regression coverage and packaged development/testing documentation.

## 1.1.0 - 2026-07-27

- Added explicit filename timezone offsets and normalized modification-time reporting.
- Added a SHA-256 copy manifest mapping every source path to its emitted destination.
- Added opt-in collision-safe sequence prefixes for duplicate basenames.

## 1.0.0 - 2026-07-26

- Added filename and modification-time screenshot grouping.
- Added configurable session gaps and Markdown or JSON manifests.
- Added opt-in staged copy export that preserves source screenshots.
