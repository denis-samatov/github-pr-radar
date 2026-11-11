"""Deterministic triage signals; no claims about mergeability or code quality."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.error import HTTPError, URLError

from .github import GitHubClient


def summarize(prs: list[dict], days: int = 14, now: datetime | None = None) -> dict:
    if days < 0:
        raise ValueError("days must be non-negative")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    items = []
    for pr in prs:
        updated = datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00"))
        age = max(0, (now - updated).total_seconds() / 86400)
        items.append({
            "number": pr["number"], "title": pr["title"], "url": pr["html_url"],
            "author": (pr.get("user") or {}).get("login", "unknown"),
            "labels": [label["name"] for label in pr.get("labels", [])],
            "draft": bool(pr.get("draft", False)), "state": pr.get("state", "open"),
            "days_since_update": round(age, 1), "stale": age >= days,
        })
    items.sort(key=lambda item: (-item["days_since_update"], item["number"]))
    stale = [item.copy() for item in items if item["stale"]]
    return {"total": len(items), "draft": sum(item["draft"] for item in items),
            "stale": stale, "stale_count": len(stale), "pull_requests": items}


def review_signal(reviews: list[dict]) -> str:
    latest = {}
    for review in sorted(reviews, key=lambda row: (row.get("submitted_at") or "", row.get("id", 0))):
        state = review.get("state")
        login = (review.get("user") or {}).get("login")
        if login and state in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            latest[login] = state
    if "CHANGES_REQUESTED" in latest.values():
        return "changes_requested"
    if "APPROVED" in latest.values():
        return "approval_present"
    return "no_decisive_review"


def ci_signal(checks: list[dict], statuses: list[dict]) -> str:
    signals = []
    for check in checks:
        if check.get("status") != "completed":
            signals.append("pending")
        elif check.get("conclusion") in {"success", "neutral", "skipped"}:
            signals.append("passed")
        elif check.get("conclusion") in {"failure", "cancelled", "timed_out", "action_required", "startup_failure", "stale"}:
            signals.append("failed")
        else:
            signals.append("unknown")
    # GitHub returns statuses newest first; retain the latest for each context.
    latest = {}
    for status in statuses:
        latest.setdefault(status["context"], status.get("state"))
    signals.extend({"success": "passed", "pending": "pending", "failure": "failed", "error": "failed"}.get(state, "unknown") for state in latest.values())
    for signal in ("failed", "pending", "unknown"):
        if signal in signals:
            return signal
    return "passed" if signals else "no_checks"


def enrich(report: dict, prs: list[dict], repository: str, client: GitHubClient) -> None:
    by_number = {pr["number"]: pr for pr in prs}
    for item in report["pull_requests"]:
        source = by_number[item["number"]]
        base = f"/repos/{repository}"
        item.update(ci="unknown", review="unknown", warnings=[])
        # Keep independently available signals if another endpoint is forbidden.
        try:
            reviews = client.items(f"{base}/pulls/{item['number']}/reviews")
            item["review"] = review_signal(reviews)
        except (HTTPError, URLError, TimeoutError, ValueError):
            item["warnings"].append("Review data unavailable; check token permissions or rate limits.")
        try:
            sha = source["head"]["sha"]
            checks = client.items(f"{base}/commits/{sha}/check-runs", key="check_runs", filter="latest")
            statuses = client.items(f"{base}/commits/{sha}/statuses")
            item["ci"] = ci_signal(checks, statuses)
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError):
            item["warnings"].append("CI data unavailable; check token permissions or rate limits.")
        reasons = []
        if item["state"] != "open":
            reasons.append("closed")
        elif item["draft"]:
            reasons.append("draft")
        else:
            if item["ci"] == "failed":
                reasons.append("fix_ci")
            if item["review"] == "changes_requested":
                reasons.append("address_review")
            if item["stale"]:
                reasons.append("follow_up")
            if item["review"] == "no_decisive_review":
                reasons.append("needs_review")
        item["actions"] = reasons or ["monitor"]
    report["stale"] = [item.copy() for item in report["pull_requests"] if item["stale"]]
    report["warnings"] = sum(bool(item["warnings"]) for item in report["pull_requests"])


def _cell(value) -> str:
    # Titles are untrusted text, not Markdown/HTML.
    text = str(value).replace("\n", " ").replace("\r", " ")
    for char in ("\\", "`", "*", "_", "[", "]", "<", ">", "|"):
        text = text.replace(char, "\\" + char)
    return text


def markdown(repository: str, report: dict) -> str:
    lines = [f"# PR Radar: {repository}", "", f"Scanned: {report['scanned']} PRs; matched: {report['total']}; drafts: {report['draft']}; stale: {report['stale_count']}.",
             "", "Results cover only the fetched sample, sorted by last update (oldest first).", "",
             "| PR | Title | Author | Inactive days | CI | Review | Suggested actions |",
             "| --- | --- | --- | ---: | --- | --- | --- |"]
    for item in report["pull_requests"]:
        url = f"https://github.com/{repository}/pull/{item['number']}"
        actions = item.get("actions", ["draft"] if item["draft"] else ["follow_up"] if item["stale"] else ["monitor"])
        lines.append(f"| [#{item['number']}]({url}) | {_cell(item['title'])} | {_cell(item['author'])} | {item['days_since_update']} | {item.get('ci', 'not_requested')} | {item.get('review', 'not_requested')} | {', '.join(actions)} |")
    if report.get("warnings"):
        for item in report["pull_requests"]:
            for warning in item.get("warnings", []):
                lines.extend(["", f"- #{item['number']}: {warning}"])
        lines.extend(["", f"Warning: incomplete detail data for {report['warnings']} PR(s); unknown does not mean passed."])
    return "\n".join(lines) + "\n"
