import argparse
import asyncio
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from config import Settings
from services.storage import S3Storage


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _slug(value: str, max_len: int = 80) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9а-яё]+", "-", value, flags=re.IGNORECASE)
    value = value.strip("-")
    if not value:
        return "q"
    return value[:max_len]


def _read_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _iter_images(inputs_dir: Path) -> list[Path]:
    images: list[Path] = []
    for path in sorted(inputs_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in IMAGE_SUFFIXES:
            images.append(path)
    return images


def _load_q_sets(inputs_dir: Path) -> dict[str, list[str]]:
    q_files = sorted([p for p in inputs_dir.glob("*.txt") if p.is_file()])
    sets: dict[str, list[str]] = {}
    for qf in q_files:
        name = qf.stem
        lines = _read_lines(qf)
        if not lines:
            continue
        # de-dup while preserving order
        seen: set[str] = set()
        qs: list[str] = []
        for q in lines:
            if q in seen:
                continue
            seen.add(q)
            qs.append(q)
        sets[name] = qs
    return sets


@dataclass(frozen=True)
class ParamCombo:
    search_type: str
    hl: str | None
    country: str | None
    device: str | None
    safe_search: str | None

    def to_extra_params(self) -> dict[str, str]:
        params: dict[str, str] = {"search_type": self.search_type}
        if self.hl:
            params["hl"] = self.hl
        if self.country:
            params["country"] = self.country
        if self.device:
            params["device"] = self.device
        if self.safe_search:
            params["safe_search"] = self.safe_search
        return params

    def slug(self) -> str:
        parts = [f"st-{self.search_type}"]
        if self.hl:
            parts.append(f"hl-{self.hl}")
        if self.country:
            parts.append(f"ct-{self.country}")
        if self.device:
            parts.append(f"dev-{self.device}")
        if self.safe_search:
            parts.append(f"safe-{self.safe_search}")
        return "__".join(parts)


def _build_param_grid(
    search_types: Iterable[str],
    hls: list[str],
    countries: list[str],
    devices: list[str],
    safe_searches: list[str],
) -> list[ParamCombo]:
    combos: list[ParamCombo] = []
    for st in search_types:
        st = st.strip()
        if not st:
            continue
        for hl in (hls or [None]):
            for country in (countries or [None]):
                for device in (devices or [None]):
                    if st == "exact_matches":
                        for safe in (safe_searches or [None]):
                            combos.append(
                                ParamCombo(
                                    search_type=st,
                                    hl=hl,
                                    country=country,
                                    device=device,
                                    safe_search=safe,
                                )
                            )
                    else:
                        combos.append(
                            ParamCombo(
                                search_type=st,
                                hl=hl,
                                country=country,
                                device=device,
                                safe_search=None,
                            )
                        )
    # de-dup
    unique: dict[tuple, ParamCombo] = {}
    for c in combos:
        key = (c.search_type, c.hl, c.country, c.device, c.safe_search)
        unique[key] = c
    return list(unique.values())


async def _upload_for_lens(storage: S3Storage, settings: Settings, image_path: Path) -> str:
    data = image_path.read_bytes()
    suffix = image_path.suffix.lower()
    # Keep content-type sane for the common cases; SearchAPI just needs a fetchable URL.
    if suffix == ".png":
        out_suffix = ".png"
    else:
        out_suffix = ".jpg"
    key_prefix = f"searchapi-test/{image_path.stem}-{_hash_bytes(data)}"
    if settings.S3_PRESIGN_INPUTS:
        return storage.upload_bytes_presigned(data, out_suffix, key_prefix, settings.S3_PRESIGN_EXPIRES)
    return storage.upload_bytes(data, out_suffix, key_prefix)


async def _searchapi_lens(
    *,
    settings: Settings,
    image_url: str,
    q: str,
    extra_params: dict[str, str],
) -> dict:
    params: dict[str, str] = {
        "api_key": settings.SEARCHAPI_KEY,
        "engine": settings.SEARCHAPI_ENGINE,
        "search_type": settings.SEARCHAPI_SEARCH_TYPE,
        "url": image_url,
        "q": q,
    }
    params.update({str(k): str(v) for k, v in extra_params.items()})
    url = f"{settings.SEARCHAPI_BASE_URL}?{urlencode(params)}"

    def _fetch() -> dict:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=settings.TIMEOUT) as resp:
            raw = resp.read()
        return json.loads(raw.decode("utf-8"))

    return await asyncio.to_thread(_fetch)


async def run(
    inputs_dir: Path,
    outputs_dir: Path,
    concurrency: int,
    default_q: str | None,
    search_types: list[str],
    hls: list[str],
    countries: list[str],
    devices: list[str],
    safe_searches: list[str],
) -> None:
    settings = Settings()
    outputs_dir.mkdir(parents=True, exist_ok=True)

    images = _iter_images(inputs_dir)
    if not images:
        raise SystemExit(f"No images found under {inputs_dir}")

    q_sets = _load_q_sets(inputs_dir)
    if not q_sets:
        if default_q:
            q_sets = {"q": [default_q]}
        else:
            raise SystemExit(
                f"No .txt files with q-values found in {inputs_dir}. "
                "Add e.g. inputs/q.txt with one q per line."
            )

    search_types_final = search_types or [settings.SEARCHAPI_SEARCH_TYPE]
    grid = _build_param_grid(
        search_types=search_types_final,
        hls=hls,
        countries=countries,
        devices=devices,
        safe_searches=safe_searches,
    )

    storage = S3Storage(settings, prefix="searchapi-test/")
    sem = asyncio.Semaphore(max(1, concurrency))

    manifest_path = outputs_dir / "_manifest.jsonl"
    # Always append: multiple test runs can accumulate.
    manifest_f = manifest_path.open("a", encoding="utf-8")

    async def _one_request(
        *,
        image_path: Path,
        image_url: str,
        q_set_name: str,
        q: str,
        combo: ParamCombo,
    ) -> None:
        out_dir = outputs_dir / image_path.stem / q_set_name / _slug(q)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{combo.slug()}.json"
        if out_path.exists():
            return
        async with sem:
            extra = combo.to_extra_params()
            try:
                payload = await _searchapi_lens(
                    settings=settings,
                    image_url=image_url,
                    q=q,
                    extra_params=extra,
                )
                out_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                rec = {
                    "status": "ok",
                    "image": str(image_path),
                    "image_url": image_url,
                    "q_set": q_set_name,
                    "q": q,
                    "params": extra,
                    "out": str(out_path),
                }
            except Exception as e:
                rec = {
                    "status": "error",
                    "image": str(image_path),
                    "image_url": image_url,
                    "q_set": q_set_name,
                    "q": q,
                    "params": extra,
                    "error": repr(e),
                    "out": str(out_path),
                }
            manifest_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            manifest_f.flush()

    # Upload each image once per run.
    image_urls: dict[Path, str] = {}
    for img in images:
        image_urls[img] = await _upload_for_lens(storage, settings, img)

    tasks: list[asyncio.Task] = []
    for img in images:
        img_url = image_urls[img]
        for q_set_name, qs in q_sets.items():
            for q in qs:
                for combo in grid:
                    tasks.append(
                        asyncio.create_task(
                            _one_request(
                                image_path=img,
                                image_url=img_url,
                                q_set_name=q_set_name,
                                q=q,
                                combo=combo,
                            )
                        )
                    )
    await asyncio.gather(*tasks)
    manifest_f.close()
    print(f"Done. Raw responses in {outputs_dir}")
    print(f"Manifest: {manifest_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Batch-test SearchAPI Google Lens with different q/params. "
            "Place images + one or more *.txt files (each line is a q) into inputs."
        )
    )
    parser.add_argument(
        "--inputs",
        type=Path,
        default=Path("DUMP/research/searchapi_test/inputs"),
        help="Inputs directory (images + *.txt with q values).",
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        default=Path("DUMP/research/searchapi_test/outputs"),
        help="Outputs directory (raw JSON responses + _manifest.jsonl).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Max concurrent SearchAPI requests.",
    )
    parser.add_argument(
        "--default-q",
        type=str,
        default=None,
        help="Fallback q if no *.txt files are present in inputs.",
    )

    # Params from SearchAPI docs (google_lens)
    parser.add_argument(
        "--search-types",
        type=str,
        default=None,
        help="Comma-separated search_type values to test (e.g. products,visual_matches,exact_matches,all).",
    )
    parser.add_argument(
        "--hl",
        type=str,
        default=None,
        help="Comma-separated hl values (e.g. ru,en).",
    )
    parser.add_argument(
        "--country",
        type=str,
        default=None,
        help="Comma-separated country values (e.g. RU,US).",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Comma-separated device values (desktop,mobile).",
    )
    parser.add_argument(
        "--safe-search",
        type=str,
        default=None,
        help="Comma-separated safe_search values for exact_matches only (blur,off).",
    )

    args = parser.parse_args()
    search_types = _parse_csv(args.search_types)
    hls = _parse_csv(args.hl)
    countries = _parse_csv(args.country)
    devices = _parse_csv(args.device)
    safe_searches = _parse_csv(args.safe_search)

    # Normalize common country casing.
    countries = [c.upper() for c in countries]
    asyncio.run(
        run(
            inputs_dir=args.inputs,
            outputs_dir=args.outputs,
            concurrency=args.concurrency,
            default_q=args.default_q,
            search_types=search_types,
            hls=hls,
            countries=countries,
            devices=devices,
            safe_searches=safe_searches,
        )
    )


if __name__ == "__main__":
    main()
