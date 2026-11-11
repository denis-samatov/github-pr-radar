"""Read-only GitHub REST API client with bounded, consistent pagination."""

from __future__ import annotations

import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api.github.com"


def validate_repository(repository: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repository must use OWNER/REPO format")
    if repository.split("/")[1] in {".", ".."}:
        raise ValueError("repository must use OWNER/REPO format")
    return repository


class GitHubClient:
    def __init__(self, token: str | None = None):
        self.token = token

    def get(self, path: str, **params):
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-pr-radar/0.2.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        url = f"{API}{path}"
        if params:
            url += "?" + urlencode(params)
        with urlopen(Request(url, headers=headers), timeout=15) as response:
            return json.load(response)

    def items(self, path: str, *, limit: int | None = None, key: str | None = None, **params) -> list[dict]:
        # Keep per_page constant: changing it changes page offsets on GitHub.
        page_size = min(100, limit) if limit is not None else 100
        result = []
        page = 1
        while True:
            data = self.get(path, **params, per_page=page_size, page=page)
            batch = data.get(key) if key and isinstance(data, dict) else data
            if not isinstance(batch, list) or any(not isinstance(item, dict) for item in batch):
                raise ValueError("unexpected API response")
            result.extend(batch)
            if limit is not None and len(result) >= limit:
                return result[:limit]
            if len(batch) < page_size:
                return result
            page += 1


def fetch_prs(repository: str, state: str = "open", limit: int = 30, token: str | None = None) -> list[dict]:
    validate_repository(repository)
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    if state not in {"open", "closed", "all"}:
        raise ValueError("invalid state")
    return GitHubClient(token).items(
        f"/repos/{repository}/pulls", limit=limit, state=state, sort="updated", direction="desc"
    )
