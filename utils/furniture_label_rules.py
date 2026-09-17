"""Helpers for furniture search label/type rules."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FurnitureTypeRule:
    type_name: str
    search_enabled: bool
    query_terms: tuple[str, ...]
    include_tokens: tuple[str, ...]
    exclude_tokens: tuple[str, ...]


@dataclass(frozen=True)
class FurnitureLabelRules:
    version: str | None
    notes: tuple[str, ...]
    vision_label_to_type: dict[str, str]
    type_rules: dict[str, FurnitureTypeRule]

    def resolve_type_name(self, label: str) -> str:
        normalized = _normalize_key(label)
        if not normalized:
            return ""
        mapped = self.vision_label_to_type.get(normalized)
        if mapped:
            return mapped
        return normalized.replace(" ", "_")

    def resolve_type_rule(self, label: str) -> FurnitureTypeRule:
        type_name = self.resolve_type_name(label)
        rule = self.type_rules.get(type_name)
        if rule:
            return rule
        fallback_tokens = _split_terms(label)
        return FurnitureTypeRule(
            type_name=type_name,
            search_enabled=True,
            query_terms=tuple(fallback_tokens),
            include_tokens=tuple(fallback_tokens),
            exclude_tokens=(),
        )


def load_furniture_label_rules(path: str | Path) -> FurnitureLabelRules:
    rules_path = Path(path)
    if not rules_path.exists():
        raise FileNotFoundError(f"Furniture label rules file not found: {rules_path}")
    raw = json.loads(rules_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Furniture label rules file is invalid: {rules_path}")

    version = raw.get("version")
    notes = tuple(str(item) for item in raw.get("notes", []) if isinstance(item, str))
    raw_map = raw.get("vision_label_to_type")
    raw_types = raw.get("types")
    if not isinstance(raw_map, dict) or not isinstance(raw_types, dict):
        raise ValueError(f"Furniture label rules file is invalid: {rules_path}")

    label_to_type: dict[str, str] = {}
    for raw_label, raw_type in raw_map.items():
        if not isinstance(raw_label, str) or not isinstance(raw_type, str):
            continue
        label_key = _normalize_key(raw_label)
        type_key = _normalize_key(raw_type)
        if label_key and type_key:
            label_to_type[label_key] = type_key

    type_rules: dict[str, FurnitureTypeRule] = {}
    for raw_type_name, payload in raw_types.items():
        if not isinstance(raw_type_name, str) or not isinstance(payload, dict):
            continue
        type_key = _normalize_key(raw_type_name)
        if not type_key:
            continue
        query_terms = _extract_terms(payload.get("query_terms"))
        include_tokens = _extract_terms(payload.get("include_tokens"))
        exclude_tokens = _extract_terms(payload.get("exclude_tokens"))
        search_enabled = bool(payload.get("search_enabled", True))
        type_rules[type_key] = FurnitureTypeRule(
            type_name=type_key,
            search_enabled=search_enabled,
            query_terms=query_terms,
            include_tokens=include_tokens,
            exclude_tokens=exclude_tokens,
        )

    return FurnitureLabelRules(
        version=str(version) if isinstance(version, str) else None,
        notes=notes,
        vision_label_to_type=label_to_type,
        type_rules=type_rules,
    )


def _extract_terms(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    terms: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = _normalize_text(item)
        if normalized and normalized not in seen:
            seen.add(normalized)
            terms.append(normalized)
    return tuple(terms)


def _split_terms(value: str) -> list[str]:
    normalized = _normalize_text(value)
    if not normalized:
        return []
    return [part for part in normalized.replace("_", " ").split() if part]


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _normalize_key(value: str) -> str:
    return _normalize_text(value).replace(" ", "_")

