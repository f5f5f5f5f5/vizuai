"""Apply managed GCS lifecycle rules for the product bucket."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from google.cloud import storage
from google.oauth2 import service_account

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from config import Settings


DEFAULT_POLICY_PATH = ROOT_DIR / "scripts" / "gcs_lifecycle_policy.json"


def _load_policy(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("Lifecycle policy file must be a non-empty JSON array")
    normalized: list[dict] = []
    for entry in raw:
        prefix = str(entry.get("prefix") or "").strip()
        age_days = int(entry.get("age_days") or 0)
        if not prefix:
            raise ValueError("Every lifecycle rule must define a non-empty 'prefix'")
        if age_days <= 0:
            raise ValueError("Every lifecycle rule must define a positive 'age_days'")
        normalized.append(
            {
                "action": {"type": "Delete"},
                "condition": {"age": age_days, "matchesPrefix": [prefix]},
            }
        )
    return normalized


def _managed_prefixes(rules: list[dict]) -> set[str]:
    prefixes: set[str] = set()
    for rule in rules:
        condition = rule.get("condition") or {}
        for prefix in condition.get("matchesPrefix") or []:
            if prefix:
                prefixes.add(str(prefix))
    return prefixes


def _is_managed_rule(rule: dict, managed_prefixes: set[str]) -> bool:
    condition = rule.get("condition") or {}
    rule_prefixes = {str(prefix) for prefix in (condition.get("matchesPrefix") or []) if prefix}
    return bool(rule_prefixes & managed_prefixes)


def _serialize_rules(rules: list[dict]) -> str:
    return json.dumps(rules, ensure_ascii=False, indent=2, sort_keys=True)


def main() -> None:
    settings = Settings()
    parser = argparse.ArgumentParser(
        description="Apply managed GCS lifecycle rules to the product bucket without overwriting unrelated rules."
    )
    parser.add_argument(
        "--policy-file",
        type=Path,
        default=DEFAULT_POLICY_PATH,
        help=f"Path to lifecycle policy JSON (default: {DEFAULT_POLICY_PATH}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the merged lifecycle rules without applying them.",
    )
    args = parser.parse_args()

    managed_rules = _load_policy(args.policy_file)
    managed_prefixes = _managed_prefixes(managed_rules)

    credentials = None
    if settings.GCS_CREDENTIALS_PATH:
        credentials = service_account.Credentials.from_service_account_file(
            settings.GCS_CREDENTIALS_PATH
        )

    client = storage.Client(
        project=settings.VERTEX_PROJECT_ID,
        credentials=credentials,
    )
    bucket = client.bucket(settings.GCS_BUCKET)
    bucket.reload()

    existing_rules = list(bucket.lifecycle_rules or [])
    preserved_rules = [
        rule for rule in existing_rules
        if not _is_managed_rule(rule, managed_prefixes)
    ]
    merged_rules = preserved_rules + managed_rules

    print("Bucket:", bucket.name)
    print("Managed prefixes:", ", ".join(sorted(managed_prefixes)))
    print("Existing managed rules removed:", len(existing_rules) - len(preserved_rules))
    print("Final lifecycle rules:")
    print(_serialize_rules(merged_rules))

    if args.dry_run:
        print("Dry run only, bucket was not modified.")
        return

    bucket.lifecycle_rules = merged_rules
    bucket.patch()
    print("Lifecycle rules applied successfully.")


if __name__ == "__main__":
    main()
