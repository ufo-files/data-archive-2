#!/usr/bin/env python3
"""Count source records across every public UFO Files data-archive shard."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import tempfile
import urllib.request
from collections import Counter
from pathlib import Path, PurePosixPath


OWNER = "ufo-files"
SHARD_RE = re.compile(r"^data-archive(?:-(\d+))?$")
TYPE_EXTENSIONS = {
    "documents": {
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".rtf", ".txt", ".csv", ".tsv", ".html", ".htm", ".xml",
    },
    "images": {
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".jp2",
        ".tif", ".tiff",
    },
    "videos": {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".wmv", ".webm"},
    "audio": {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"},
}
NON_SOURCE_ROOTS = {".github", "manifest", "scripts"}


def command(*arguments: str, cwd: Path | None = None) -> bytes:
    return subprocess.check_output(arguments, cwd=cwd)


def shard_sort_key(name: str) -> tuple[int, int]:
    match = SHARD_RE.fullmatch(name)
    if not match:
        raise ValueError(name)
    return (0, 0) if match.group(1) is None else (1, int(match.group(1)))


def github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ufo-files-archive-count",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def discover_shards() -> list[str]:
    names: set[str] = set()
    page = 1
    while True:
        request = urllib.request.Request(
            f"https://api.github.com/users/{OWNER}/repos?type=public&per_page=100&page={page}",
            headers=github_headers(),
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            repositories = json.load(response)
        if not repositories:
            break
        names.update(str(repository["name"]) for repository in repositories)
        if len(repositories) < 100:
            break
        page += 1
    return sorted(
        {name for name in names if SHARD_RE.fullmatch(name)},
        key=shard_sort_key,
    )


def tracked_paths(repo: Path) -> list[PurePosixPath]:
    output = command("git", "ls-tree", "-r", "-z", "--name-only", "HEAD", cwd=repo)
    return [
        PurePosixPath(raw.decode("utf-8", "surrogateescape"))
        for raw in output.split(b"\0")
        if raw
    ]


def classify(path: PurePosixPath) -> str | None:
    for kind, extensions in TYPE_EXTENSIONS.items():
        if path.suffix.lower() in extensions:
            return kind
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("archive-count.json"))
    args = parser.parse_args()

    shards = discover_shards()
    if not shards:
        raise RuntimeError("No data-archive shards were found")

    by_type: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    excluded_zip = 0
    excluded_non_archive = 0
    seen: set[str] = set()
    revisions: dict[str, str] = {}

    with tempfile.TemporaryDirectory(prefix="ufo-files-archive-count-") as temporary:
        root = Path(temporary)
        for shard in shards:
            checkout = root / shard
            subprocess.run(
                [
                    "git", "clone", "--filter=blob:none", "--no-checkout", "--depth=1",
                    f"https://github.com/{OWNER}/{shard}.git", str(checkout),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            revisions[shard] = command("git", "rev-parse", "HEAD", cwd=checkout).decode().strip()
            for path in tracked_paths(checkout):
                relative = path.as_posix()
                if relative in seen:
                    continue
                seen.add(relative)
                if len(path.parts) < 2 or path.parts[0] in NON_SOURCE_ROOTS:
                    excluded_non_archive += 1
                    continue
                if path.suffix.lower() == ".zip":
                    excluded_zip += 1
                    continue
                kind = classify(path)
                if kind is None:
                    excluded_non_archive += 1
                    continue
                by_type[kind] += 1
                by_source[path.parts[0]] += 1

    total = sum(by_type.values())
    payload = {
        "schema_version": 2,
        "repository": "ufo-files/data-archive shards",
        "shards": shards,
        "revisions": revisions,
        "generated_utc": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "count": total,
        "total_files": total,
        "by_type": {kind: by_type.get(kind, 0) for kind in TYPE_EXTENSIONS},
        "by_source": dict(sorted(by_source.items())),
        "excluded": {
            "zip_files": excluded_zip,
            "non_archive_files": excluded_non_archive,
        },
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Counted {total} archive file(s) across {len(shards)} shard(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
