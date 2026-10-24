#!/usr/bin/env python3
"""Create a per-task STATUS.md / REASONING.md documentation bundle."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
TEMPLATES = ("STATUS.md", "REASONING.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold docs/<TASK-ID>/{STATUS.md,REASONING.md,assets/}.",
    )
    parser.add_argument("--root", default="docs", help="Docs root (default: docs)")
    parser.add_argument("--task-id", required=True, help="Task id, e.g. EPARSE-4")
    parser.add_argument("--title", required=True, help="Human-readable task title")
    parser.add_argument(
        "--project",
        default=str(Path.cwd()),
        help="Project path written into STATUS.md (default: current directory)",
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Date in YYYY-MM-DD (default: today)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task_id = args.task_id.strip()
    title = args.title.strip()
    if not TASK_ID_RE.match(task_id):
        print(
            "error: task id must match [A-Za-z0-9][A-Za-z0-9._-]*",
            file=sys.stderr,
        )
        return 2
    if not title:
        print("error: title must not be empty", file=sys.stderr)
        return 2

    skill_root = Path(__file__).resolve().parent.parent
    template_dir = skill_root / "templates"
    target = Path(args.root).expanduser().resolve() / task_id
    if target.exists():
        print(f"error: {target} already exists; refusing to overwrite", file=sys.stderr)
        return 1
    for name in TEMPLATES:
        if not (template_dir / name).is_file():
            print(f"error: missing template {template_dir / name}", file=sys.stderr)
            return 1

    replacements = {
        "{{TASK_ID}}": task_id,
        "{{TITLE}}": title,
        "{{DATE}}": args.date,
        "{{PROJECT}}": str(Path(args.project).expanduser().resolve()),
    }

    target.mkdir(parents=True)
    assets = target / "assets"
    assets.mkdir()
    (assets / ".gitkeep").write_text("", encoding="utf-8")

    for name in TEMPLATES:
        text = (template_dir / name).read_text(encoding="utf-8")
        for placeholder, value in replacements.items():
            text = text.replace(placeholder, value)
        (target / name).write_text(text, encoding="utf-8")

    print(f"created {target / 'STATUS.md'}")
    print(f"created {target / 'REASONING.md'}")
    print(f"created {assets}/")
    print(
        "next: fill the placeholders, add evidence, then verify links and test counts"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
