# Example

```bash
screenshot-sessions ~/Pictures/Game --gap-minutes 75 --output sessions.md
screenshot-sessions ~/Pictures/Game --format json --copy-to ~/Pictures/Game-Sessions
screenshot-sessions ~/Pictures/Game --timezone-offset=-04:00 --copy-to ~/Pictures/Game-Sessions --collision-mode sequence
```

Copy export is opt-in. The source screenshots are never moved or deleted, and each export includes `manifest.json` with source, destination, and SHA-256 evidence.

A directory with no supported images is a valid empty scan and can export an empty copy manifest. Use `--collision-mode sequence` for portable case/Unicode duplicate basenames. Existing report outputs are checked before copy export starts.
