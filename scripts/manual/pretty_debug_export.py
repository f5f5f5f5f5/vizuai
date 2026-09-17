#!/usr/bin/env python3
"""Pretty-print debug_json from a DB export JSON file.

Usage:
  python3 scripts/manual/pretty_debug_export.py C:\\Users\\me\\Downloads\\export.json

The script writes <input>_debug_pretty.json next to the input file.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_record(obj: object) -> dict:
    if isinstance(obj, list):
        if not obj:
            raise ValueError("Export JSON is an empty list.")
        if not isinstance(obj[0], dict):
            raise ValueError("Export JSON list does not contain objects.")
        return obj[0]
    if isinstance(obj, dict):
        if "rows" in obj and isinstance(obj["rows"], list) and obj["rows"]:
            if not isinstance(obj["rows"][0], dict):
                raise ValueError("Export JSON rows do not contain objects.")
            return obj["rows"][0]
        return obj
    raise ValueError("Unsupported JSON structure.")


def _parse_debug(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    raise ValueError(f"Unsupported debug_json type: {type(value).__name__}")


def _normalize_input_path(raw: str) -> Path:
    """Accept both Linux and Windows-style paths when running from WSL."""
    text = raw.strip()

    # Windows absolute path: C:\Users\... or C:/Users/...
    m = re.match(r"^([A-Za-z]):[\\\\/](.+)$", text)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2).replace("\\", "/")
        return Path(f"/mnt/{drive}/{rest}")

    return Path(text).expanduser()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Path to JSON export file")
    args = parser.parse_args()

    input_path = _normalize_input_path(args.input)
    if not input_path.exists():
        raise SystemExit(
            "File not found: "
            f"{input_path}\n"
            "Tip for WSL: use '/mnt/c/Users/...' or quote Windows path, e.g. "
            "'C:\\Users\\YOUR_USER\\Downloads\\file.json'."
        )

    data = _load_json(input_path)
    record = _extract_record(data)
    if "debug_json" not in record:
        raise SystemExit("debug_json field not found in export.")

    debug_parsed = _parse_debug(record["debug_json"])
    out_path = input_path.with_name(f"{input_path.stem}_debug_pretty.json")
    out_path.write_text(
        json.dumps(debug_parsed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
