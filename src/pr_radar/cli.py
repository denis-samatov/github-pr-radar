"""Command-line interface for read-only pull request triage."""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError

from .github import GitHubClient, fetch_prs
from .report import enrich, markdown, summarize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect GitHub pull request activity")
    parser.add_argument("repository", help="GitHub repository as OWNER/REPO")
    parser.add_argument("--state", choices=["open", "closed", "all"], default="open")
    parser.add_argument("--limit", type=int, default=30, help="Maximum PRs to fetch before filtering (1-500)")
    parser.add_argument("--stale-days", type=int, default=14)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    output.add_argument("--markdown", action="store_true", help="Print a Markdown report")
    parser.add_argument("--author", help="Filter fetched PRs by author (case-insensitive)")
    parser.add_argument("--label", action="append", default=[], help="Require label; repeat to require multiple labels")
    parser.add_argument("--exclude-drafts", action="store_true")
    parser.add_argument("--details", action="store_true", help="Fetch reviews, check runs and commit statuses (extra API requests)")
    parser.add_argument("--fail-on-stale", action="store_true", help="Exit 2 if matching stale PRs exist")
    args = parser.parse_args(argv)
    if args.stale_days < 0:
        parser.error("--stale-days must be non-negative")
    if not 1 <= args.limit <= 500:
        parser.error("--limit must be between 1 and 500")
    try:
        token = os.getenv("GITHUB_TOKEN")
        prs = fetch_prs(args.repository, args.state, args.limit, token)
        matched = [pr for pr in prs if
                   (not args.author or (pr.get("user") or {}).get("login", "").lower() == args.author.lower())
                   and (not args.exclude_drafts or not pr.get("draft"))
                   and set(args.label).issubset({label["name"] for label in pr.get("labels", [])})]
        report = {"repository": args.repository, "state": args.state, "scanned": len(prs),
                  "limit": args.limit, "stale_days": args.stale_days, **summarize(matched, args.stale_days)}
        if args.details:
            enrich(report, matched, args.repository, GitHubClient(token))
    except (ValueError, HTTPError, URLError, TimeoutError) as exc:
        if isinstance(exc, HTTPError):
            messages = {401: "Authentication failed; check GITHUB_TOKEN.",
                        403: "GitHub denied access or rate limit exceeded; check token permissions and rate limits.",
                        404: "Repository not found or not accessible to this token.",
                        429: "GitHub rate limit exceeded; try again later."}
            message = messages.get(exc.code, f"GitHub API returned HTTP {exc.code}.")
        elif isinstance(exc, (URLError, TimeoutError)):
            message = "Could not reach GitHub API; check your connection and try again."
        else:
            message = str(exc)
        print(f"Error: {message}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.markdown:
        print(markdown(args.repository, report), end="")
    else:
        print(f"{args.repository}: {report['total']} PR(s), {report['draft']} draft(s), {report['stale_count']} stale (≥{args.stale_days} days); scanned {len(prs)}")
        for item in report["pull_requests"]:
            flags = [flag for flag, enabled in (("draft", item["draft"]), ("stale", item["stale"])) if enabled]
            if args.details:
                flags += [f"CI: {item['ci']}", f"review: {item['review']}", "actions: " + ", ".join(item["actions"])]
            print(f"  #{item['number']} ({item['days_since_update']} days) {item['title']} [{'; '.join(flags)}]\n    {item['url']}")
            for warning in item.get("warnings", []):
                print(f"Warning: #{item['number']}: {warning}", file=sys.stderr)
    return 2 if args.fail_on_stale and report["stale_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
