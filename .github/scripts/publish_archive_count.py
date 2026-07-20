#!/usr/bin/env python3
"""Publish archive-count.json to the browser-readable archive-count branch."""

from __future__ import annotations

import argparse
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable


TRANSIENT_HTTP_STATUSES = {408, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5


def github_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "ufo-files-archive-count-publisher",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def request_json(
    url: str,
    *,
    token: str,
    method: str = "GET",
    payload: dict[str, str] | None = None,
    allow_not_found: bool = False,
    urlopen: Callable[..., object] = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object] | None:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers=github_headers(token),
        method=method,
    )

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urlopen(request, timeout=30) as response:
                content = response.read()
            return json.loads(content) if content else {}
        except urllib.error.HTTPError as error:
            error.close()
            if error.code == 404 and allow_not_found:
                return None
            if error.code not in TRANSIENT_HTTP_STATUSES or attempt == MAX_ATTEMPTS:
                raise
            delay = min(2 ** (attempt - 1), 16)
            print(
                f"GitHub API returned HTTP {error.code}; retrying in {delay}s "
                f"(attempt {attempt + 1}/{MAX_ATTEMPTS}).",
                flush=True,
            )
            sleep(delay)
        except urllib.error.URLError:
            if attempt == MAX_ATTEMPTS:
                raise
            delay = min(2 ** (attempt - 1), 16)
            print(
                f"GitHub API connection failed; retrying in {delay}s "
                f"(attempt {attempt + 1}/{MAX_ATTEMPTS}).",
                flush=True,
            )
            sleep(delay)

    raise AssertionError("unreachable")


def publish(path: Path, *, repository: str, revision: str, token: str) -> None:
    api_root = f"https://api.github.com/repos/{repository}"
    branch = "archive-count"
    encoded_branch = urllib.parse.quote(branch, safe="")

    reference = request_json(
        f"{api_root}/git/ref/heads/{encoded_branch}",
        token=token,
        allow_not_found=True,
    )
    if reference is None:
        request_json(
            f"{api_root}/git/refs",
            token=token,
            method="POST",
            payload={"ref": f"refs/heads/{branch}", "sha": revision},
        )

    existing = request_json(
        f"{api_root}/contents/archive-count.json?ref={encoded_branch}",
        token=token,
        allow_not_found=True,
    )
    payload = {
        "message": "Update live archive count",
        "branch": branch,
        "content": base64.b64encode(path.read_bytes()).decode("ascii"),
    }
    if existing is not None and isinstance(existing.get("sha"), str):
        payload["sha"] = str(existing["sha"])

    request_json(
        f"{api_root}/contents/archive-count.json",
        token=token,
        method="PUT",
        payload=payload,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, nargs="?", default=Path("archive-count.json"))
    args = parser.parse_args()
    publish(
        args.path,
        repository=os.environ["GITHUB_REPOSITORY"],
        revision=os.environ["GITHUB_SHA"],
        token=os.environ["GH_TOKEN"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
