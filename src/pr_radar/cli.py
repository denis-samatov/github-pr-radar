"""Summarize public repository pull requests through the GitHub REST API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

API = "https://api.github.com"


def fetch_prs(repository: str, state: str = "open", limit: int = 30, token: str | None = None) -> list[dict]:
    """Retrieve up to ``limit`` PRs from the GitHub REST API, including pagination."""
    if not (1 <= limit <= 500):
        raise ValueError("limit must be between 1 and 500")
    try:
        owner, repo = repository.split("/")
    except ValueError as exc:
        raise ValueError("repository must use OWNER/REPO format") from exc
    if not owner or not repo or any(ch.isspace() for ch in repository):
        raise ValueError("repository must use OWNER/REPO format")
    if state not in {"open", "closed", "all"}:
        raise ValueError("invalid state")
    result: list[dict] = []
    while len(result) < limit:
        page_size = min(100, limit - len(result))
        query = urlencode({"state": state, "sort": "updated", "direction": "desc", "per_page": page_size, "page": len(result) // 100 + 1})
        url = f"{API}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/pulls?{query}"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "github-pr-radar/0.1.0"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        with urlopen(Request(url, headers=headers), timeout=15) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise ValueError("unexpected API response")
        result.extend(batch)
        if len(batch) < page_size:
            break
    return result[:limit]


def summarize(prs: list[dict], days: int = 14, now: datetime | None = None) -> dict:
    """Aggregate PR information; a stale PR has not been updated for ``days`` days."""
    if days < 0:
        raise ValueError("days must be non-negative")
    now = now or datetime.now(timezone.utc)
    stale = []
    draft_count = 0
    for pr in prs:
        draft_count += bool(pr.get("draft", False))
        updated_at = datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00"))
        age = (now - updated_at).total_seconds() / 86400
        if age >= days:
            stale.append({"number": pr["number"], "title": pr["title"], "url": pr["html_url"], "days_since_update": round(age, 1)})
    stale.sort(key=lambda item: item["days_since_update"], reverse=True)
    return {"total": len(prs), "draft": draft_count, "stale": stale, "stale_count": len(stale)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect GitHub pull request activity")
    parser.add_argument("repository", help="GitHub repository as OWNER/REPO")
    parser.add_argument("--state", choices=["open", "closed", "all"], default="open")
    parser.add_argument("--limit", type=int, default=30, help="Maximum PRs to inspect (1-500)")
    parser.add_argument("--stale-days", type=int, default=14)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args(argv)
    try:
        prs = fetch_prs(args.repository, args.state, args.limit, os.getenv("GITHUB_TOKEN"))
        report = summarize(prs, args.stale_days)
    except (ValueError, HTTPError, URLError, TimeoutError) as exc:
        if isinstance(exc, HTTPError) and exc.code in {403, 429}:
            print("GitHub API rate limit or access restriction. Try again later or set GITHUB_TOKEN.", file=sys.stderr)
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"repository": args.repository, **report}, indent=2))
    else:
        print(f"{args.repository}: {report['total']} PR(s), {report['draft']} draft(s), {report['stale_count']} stale (≥{args.stale_days} days)")
        for item in report["stale"]:
            print(f"  #{item['number']} ({item['days_since_update']} days) {item['title']}\n    {item['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
