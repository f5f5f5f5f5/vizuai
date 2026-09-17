"""Load allowed furniture labels from a text file."""
from __future__ import annotations

import ast
import json
from pathlib import Path


def load_label_set(path: str | Path) -> set[str]:
    labels_path = Path(path)
    if not labels_path.exists():
        raise FileNotFoundError(f"Labels file not found: {labels_path}")
    content = labels_path.read_text(encoding="utf-8").strip()
    if not content:
        return set()

    if content.lstrip().startswith("["):
        parsed = _parse_list_content(content)
        if parsed:
            return parsed

    labels = set()
    for line in content.splitlines():
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("#"):
            labels.add(cleaned)
    return labels


def load_furniture_labels(path: str | Path) -> set[str]:
    return load_label_set(path)


def _parse_list_content(content: str) -> set[str]:
    for parser in (_parse_json_list, _parse_python_list):
        parsed = parser(content)
        if parsed:
            return parsed
    return set()


def _parse_json_list(content: str) -> set[str]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return set()
    if isinstance(data, list):
        return {str(item).strip().lower() for item in data if str(item).strip()}
    return set()


def _parse_python_list(content: str) -> set[str]:
    try:
        data = ast.literal_eval(content)
    except (ValueError, SyntaxError):
        return set()
    if isinstance(data, (list, tuple, set)):
        return {str(item).strip().lower() for item in data if str(item).strip()}
    return set()
