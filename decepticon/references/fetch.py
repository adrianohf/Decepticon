"""Reference repository fetcher + local search.

Clones (or pulls) any of the catalogued repositories into the sandbox
workspace under ``/workspace/.references/<slug>/`` so agents can grep
through the full contents offline after the first fetch.

The fetcher uses git via subprocess; the actual clone happens through
the bash tool, NOT directly here — this module is pure metadata + a
path manager so tests can cover logic without requiring network.

Search is a ripgrep / grep wrapper via subprocess that the agent
invokes through bash; we just produce the right command line here.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from decepticon.references.catalog import REFERENCES, ReferenceEntry


CACHE_ROOT = Path(os.environ.get("DECEPTICON_REFERENCES_ROOT", "/workspace/.references"))


@dataclass
class ReferenceCache:
    """State of a reference repo's local checkout."""

    slug: str
    url: str
    path: Path
    present: bool
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "url": self.url,
            "path": str(self.path),
            "present": self.present,
            "size_bytes": self.size_bytes,
        }


def _entry(slug: str) -> ReferenceEntry:
    for ref in REFERENCES:
        if ref.slug == slug:
            return ref
    raise KeyError(f"unknown reference slug: {slug}")


def cache_path(slug: str, *, root: Path | None = None) -> Path:
    """Resolve the local checkout path for a reference slug."""
    base = root or CACHE_ROOT
    _entry(slug)  # validate
    return base / slug


def cache_status(slug: str, *, root: Path | None = None) -> ReferenceCache:
    """Check whether a reference is cached and how large it is."""
    entry = _entry(slug)
    path = cache_path(slug, root=root)
    present = path.exists()
    size = _dir_size(path) if present else 0
    return ReferenceCache(
        slug=slug, url=entry.url, path=path, present=present, size_bytes=size
    )


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    continue
    except OSError:
        return 0
    return total


def ensure_cached(
    slug: str,
    *,
    root: Path | None = None,
    depth: int = 1,
    run: bool = True,
) -> ReferenceCache:
    """Clone or update the reference repo if missing.

    When ``run`` is True (default), spawn ``git`` via subprocess; when
    False, just return the projected status (used by tests).
    """
    entry = _entry(slug)
    base = root or CACHE_ROOT
    base.mkdir(parents=True, exist_ok=True)
    path = base / slug
    if run and entry.fetch_hint == "git":
        if path.exists() and (path / ".git").exists():
            subprocess.run(
                ["git", "-C", str(path), "pull", "--ff-only"],
                check=False,
                capture_output=True,
                timeout=120,
            )
        else:
            subprocess.run(
                ["git", "clone", "--depth", str(depth), entry.url, str(path)],
                check=False,
                capture_output=True,
                timeout=300,
            )
    return cache_status(slug, root=root)


def search_cache(
    slug: str,
    pattern: str,
    *,
    root: Path | None = None,
    max_results: int = 60,
) -> list[tuple[str, int, str]]:
    """Grep the cached repo for ``pattern``. Returns ``(file, line, snippet)``.

    Uses ripgrep if available, falling back to ``grep -r``. Pure Python
    walk is used when neither binary is installed (slowest path).
    """
    status = cache_status(slug, root=root)
    if not status.present:
        return []
    # Prefer rg, then grep, then Python
    for binary in ("rg", "grep"):
        if _which(binary):
            cmd = (
                [binary, "-n", "--max-count", "3", pattern, str(status.path)]
                if binary == "rg"
                else [
                    "grep",
                    "-rn",
                    "--include=*",
                    pattern,
                    str(status.path),
                ]
            )
            try:
                res = subprocess.run(
                    cmd, capture_output=True, timeout=30, text=True, errors="replace"
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                break
            lines = res.stdout.splitlines()[:max_results]
            out: list[tuple[str, int, str]] = []
            for ln in lines:
                parsed = _parse_grep_line(ln)
                if parsed:
                    out.append(parsed)
            return out
    return _pyfind(status.path, pattern, max_results)


def _which(binary: str) -> bool:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        candidate = Path(directory) / binary
        if candidate.exists() and os.access(candidate, os.X_OK):
            return True
    return False


def _parse_grep_line(line: str) -> tuple[str, int, str] | None:
    # Format: /path/to/file:42:content
    parts = line.split(":", 2)
    if len(parts) < 3:
        return None
    path = parts[0]
    try:
        line_no = int(parts[1])
    except ValueError:
        return None
    return (path, line_no, parts[2][:240])


def _pyfind(root: Path, pattern: str, max_results: int) -> list[tuple[str, int, str]]:
    """Pure-Python fallback when rg/grep aren't installed."""
    needle = pattern.lower()
    hits: list[tuple[str, int, str]] = []
    try:
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            try:
                with p.open("r", encoding="utf-8", errors="replace") as fh:
                    for i, line in enumerate(fh, start=1):
                        if needle in line.lower():
                            hits.append((str(p), i, line.rstrip()[:240]))
                            if len(hits) >= max_results:
                                return hits
            except OSError:
                continue
    except OSError:
        pass
    return hits
