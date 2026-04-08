"""CVE → public PoC link index.

Reads the cached ``trickest/cve`` repo (per-CVE markdown files grouped
by year) plus the secondary mirror ``Mr-xn/Penetration_Testing_POC``
and builds a single ``{cve_id: [poc_url, ...]}`` map.

The built index is persisted to a JSON file next to the trickest cache
so subsequent lookups skip the walk. Regenerate with ``build_index()``
or by deleting the cache file.

Callers use:

    from decepticon.references.cve_poc_index import lookup_poc
    urls = lookup_poc("CVE-2021-44228")

The function is safe to call when the cache is absent — it returns an
empty list instead of raising.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from decepticon.references.fetch import cache_path

TRICKEST_SLUG = "trickest-cve"
MRXN_SLUG = "penetration-testing-poc"

_CVE_ID_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s)>\]\"'`]+", re.IGNORECASE)
_INDEX_FILENAME = "poc_index.json"


@dataclass
class PoCIndex:
    """In-memory map of CVE ID to a de-duplicated list of PoC URLs."""

    entries: dict[str, list[str]] = field(default_factory=dict)

    def add(self, cve_id: str, url: str) -> None:
        key = cve_id.upper()
        bucket = self.entries.setdefault(key, [])
        if url not in bucket:
            bucket.append(url)

    def lookup(self, cve_id: str) -> list[str]:
        return list(self.entries.get(cve_id.upper(), ()))

    def size(self) -> int:
        return len(self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.size(),
            "entries": self.entries,
        }


def _iter_trickest_files(repo: Path) -> list[Path]:
    """Return every ``CVE-*.md`` file under year-numbered directories."""
    if not repo.is_dir():
        return []
    files: list[Path] = []
    for year_dir in sorted(repo.iterdir()):
        if not year_dir.is_dir():
            continue
        if not re.fullmatch(r"\d{4}", year_dir.name):
            continue
        files.extend(sorted(year_dir.glob("CVE-*.md")))
    return files


def _extract_cve_id(path: Path, text: str) -> str | None:
    stem = path.stem.upper()
    if _CVE_ID_RE.fullmatch(stem):
        return stem
    m = _CVE_ID_RE.search(text)
    return m.group(0).upper() if m else None


def _extract_urls(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;")
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _ingest_trickest(repo: Path, index: PoCIndex) -> int:
    added = 0
    for path in _iter_trickest_files(repo):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        cve_id = _extract_cve_id(path, text)
        if not cve_id:
            continue
        for url in _extract_urls(text):
            before = len(index.entries.get(cve_id, ()))
            index.add(cve_id, url)
            if len(index.entries[cve_id]) > before:
                added += 1
    return added


def _ingest_mrxn(repo: Path, index: PoCIndex) -> int:
    """Scan filenames and markdown in the Mr-xn mirror for CVE IDs + URLs."""
    if not repo.is_dir():
        return 0
    added = 0
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in {".md", ".txt", ".py"}:
            # Avoid blowing up on huge binary/sample files
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        name_ids = _CVE_ID_RE.findall(path.name)
        body_ids = _CVE_ID_RE.findall(text)
        ids = {i.upper() for i in (name_ids + body_ids)}
        if not ids:
            continue
        # Every CVE ID in scope claims the file path itself as a PoC
        rel = str(path.relative_to(repo))
        url = f"file://{rel}"
        for cve_id in ids:
            before = len(index.entries.get(cve_id, ()))
            index.add(cve_id, url)
            if len(index.entries[cve_id]) > before:
                added += 1
        for url in _extract_urls(text):
            for cve_id in ids:
                before = len(index.entries.get(cve_id, ()))
                index.add(cve_id, url)
                if len(index.entries[cve_id]) > before:
                    added += 1
    return added


def build_index(*, root: Path | None = None) -> PoCIndex:
    """Walk both caches and return a fresh ``PoCIndex``."""
    index = PoCIndex()
    trickest = cache_path(TRICKEST_SLUG, root=root)
    mrxn = cache_path(MRXN_SLUG, root=root)
    _ingest_trickest(trickest, index)
    _ingest_mrxn(mrxn, index)
    return index


def _index_file(root: Path | None) -> Path:
    trickest = cache_path(TRICKEST_SLUG, root=root)
    return trickest.parent / _INDEX_FILENAME


def save_index(index: PoCIndex, *, root: Path | None = None) -> Path:
    path = _index_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(index.to_dict(), indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def load_index(*, root: Path | None = None) -> PoCIndex:
    """Load persisted index if present; otherwise return empty ``PoCIndex``.

    Empty is the **safe default** — lookups quietly return no hits.
    """
    path = _index_file(root)
    if not path.is_file():
        return PoCIndex()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return PoCIndex()
    raw = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return PoCIndex()
    index = PoCIndex()
    for k, v in raw.items():
        if isinstance(v, list):
            for url in v:
                if isinstance(url, str):
                    index.add(str(k), url)
    return index


def lookup_poc(cve_id: str, *, root: Path | None = None) -> list[str]:
    """Convenience lookup that reads the persisted index lazily.

    Falls back to an on-the-fly build of the trickest cache if no
    persisted index exists yet. Returns ``[]`` when neither cache is
    present.
    """
    index = load_index(root=root)
    if index.size() == 0:
        # Try a live build in case the cache was hydrated but not
        # indexed yet.
        index = build_index(root=root)
        if index.size() > 0:
            try:
                save_index(index, root=root)
            except OSError:
                pass
    return index.lookup(cve_id)


__all__ = [
    "MRXN_SLUG",
    "PoCIndex",
    "TRICKEST_SLUG",
    "build_index",
    "load_index",
    "lookup_poc",
    "save_index",
]
