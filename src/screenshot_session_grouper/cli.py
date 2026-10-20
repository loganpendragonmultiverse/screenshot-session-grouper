from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import export_copies, render_json, render_markdown, scan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Group screenshots into likely timestamp sessions."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--gap-minutes", type=int, default=90)
    parser.add_argument("--timezone-offset", default="+00:00", help="Z or +/-HH:MM")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--copy-to", type=Path)
    parser.add_argument("--collision-mode", choices=("error", "sequence"), default="error")
    parser.add_argument(
        "--boundary-overrides", type=Path, help="Reviewed version 1 split/join boundary JSON"
    )
    args = parser.parse_args(argv)
    try:
        if args.output and (args.output.exists() or args.output.is_symlink()):
            raise ValueError(f"output already exists: {args.output}")
        overrides = (
            json.loads(args.boundary_overrides.read_text(encoding="utf-8"))
            if args.boundary_overrides
            else None
        )
        if args.boundary_overrides and not isinstance(overrides, dict):
            raise ValueError("boundary overrides must contain an object")
        report = scan(
            args.source, args.gap_minutes, args.timezone_offset, boundary_overrides=overrides
        )
        if args.copy_to:
            export_copies(report, args.copy_to, args.collision_mode)
        rendered = render_json(report) if args.format == "json" else render_markdown(report)
        if args.output:
            if args.output.exists() or args.output.is_symlink():
                raise ValueError(f"output already exists: {args.output}")
            with args.output.open("x", encoding="utf-8") as output:
                output.write(rendered)
        else:
            sys.stdout.write(rendered)
    except (OSError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0
