# Example

```bash
screenshot-sessions ~/Pictures/Game --gap-minutes 75 --output sessions.md
screenshot-sessions ~/Pictures/Game --format json --copy-to ~/Pictures/Game-Sessions
screenshot-sessions ~/Pictures/Game --timezone-offset=-04:00 --copy-to ~/Pictures/Game-Sessions --collision-mode sequence
```

Copy export is opt-in. The source screenshots are never moved or deleted, and each export includes `manifest.json` with source, destination, and SHA-256 evidence.
