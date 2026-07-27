# Screenshot Session Grouper

[![CI](https://github.com/loganpendragonmultiverse/screenshot-session-grouper/actions/workflows/ci.yml/badge.svg)](https://github.com/loganpendragonmultiverse/screenshot-session-grouper/actions/workflows/ci.yml)

Screenshot Session Grouper organizes image timestamps into likely game sessions. It produces a reviewable Markdown or JSON manifest and can optionally copy screenshots into new session folders without moving or deleting the originals.

## Three-minute start

```bash
python -m pip install .
screenshot-sessions ~/Pictures/Game --gap-minutes 90 --output sessions.md
screenshot-sessions ~/Pictures/Game --timezone-offset=-04:00 --copy-to ~/Pictures/Game-Sessions --collision-mode sequence
```

Recognizable `YYYY-MM-DD_HH-MM-SS` filename timestamps take priority; other images use filesystem modification times. Use `--timezone-offset` to state the timezone encoded by filenames. A new session begins after the configured gap. Copy export stages a new destination, writes a SHA-256 copy manifest, and refuses existing, nested, or temporary targets. Duplicate basenames fail by default; `--collision-mode sequence` adds a stable numeric prefix.

Session boundaries are estimates. Edited timestamps, cloud downloads, copied files, and inconsistent clocks can produce misleading groups. The tool does not inspect image content or game metadata. Requires Python 3.10 or newer.

Part of the [Logan Pendragon Forge open-source collection](https://www.loganpendragonforge.com/open-source/). Licensed under the [MIT License](LICENSE).
