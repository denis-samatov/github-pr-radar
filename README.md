# GitHub PR Radar

A dependency-free Python CLI for **read-only pull request triage** through the GitHub REST API. Find inactive PRs, filter your review queue, inspect CI and review signals, and export a report for humans or automation.

## What it reports

- PR number, title, author, labels, draft status and days since last update
- Configurable inactivity threshold and oldest-first output
- Optional CI signal combining check runs and the latest commit status per context
- Optional review signal based on each reviewer's latest decisive review
- Suggested next actions: `fix_ci`, `address_review`, `follow_up`, `needs_review`, `monitor`, `draft`, or `closed`
- Plain text, JSON and Markdown output; optional nonzero exit when stale PRs exist

No runtime dependencies, no LLM account, and no repository writes.

## Quick start

Requires Python 3.10+.

```bash
python -m pip install -e .
pr-radar python/cpython --limit 50 --stale-days 30
pr-radar owner/repo --author denis-samatov --exclude-drafts
pr-radar owner/repo --label bug --label backend --details
pr-radar owner/repo --details --markdown > pr-report.md
pr-radar owner/repo --json > pr-report.json
```

Or without installation:

```bash
PYTHONPATH=src python -m pr_radar owner/repo --limit 10
```

Filters apply **after fetching** the latest `--limit` PRs. Repeating `--label` requires all specified labels; label matching is exact and author matching is case-insensitive. The limit is 1–500 (default 30). `--state open|closed|all` defaults to `open`; `--stale-days` defaults to 14.

`--json` and `--markdown` are mutually exclusive. Existing `total`, `draft`, `stale`, and `stale_count` JSON fields remain available; `pull_requests` contains every matched PR, while `scanned` counts fetched PRs before filtering.

## Authentication and API costs

Anonymous access works for public repositories. Set `GITHUB_TOKEN` in your environment or CI secrets for higher rate limits and authorized private repository access. Never place tokens in command arguments or tracked files.

Use read-only permissions: **Pull requests** for PRs and reviews; **Checks** and **Commit statuses** for `--details`. Tokens must also have access to the repository. GitHub Actions tokens are scoped to their repository.

The basic report uses one request per page of up to 100 PRs. `--details` adds at least three requests per matched PR (reviews, check runs and commit statuses), with pagination where needed. Start with `--limit 10` on large repositories. Details are fetched sequentially with a 15-second timeout per request.

Unavailable detail endpoints produce `unknown` and a warning, preserving independently available signals. JSON includes warnings per PR and a count of affected PRs; text prints warnings to stderr; Markdown includes them below the table. A partial detail report can still exit successfully: inspect warnings if your automation needs complete data.

## CI integration

```bash
pr-radar owner/repo --exclude-drafts --stale-days 30 --json --fail-on-stale > report.json
```

| Exit code | Meaning |
| --- | --- |
| `0` | Report produced; no stale-policy failure |
| `1` | API, network, or data error prevented the report |
| `2` | `--fail-on-stale` found matching stale PRs, or CLI arguments were invalid |

An invalid CLI invocation produces no report. With `--state all`, the stale policy also includes closed PRs. Use the default open state for a pending-work policy.

To add Markdown to an existing GitHub Actions job after installation:

```yaml
permissions:
  contents: read
  pull-requests: read
  checks: read
  statuses: read
steps:
  # Check out the repository and install github-pr-radar first.
  - name: Summarize pull requests
    env:
      GITHUB_TOKEN: ${{ github.token }}
      RADAR_REPOSITORY: ${{ github.repository }}
    run: pr-radar "$RADAR_REPOSITORY" --limit 10 --details --markdown >> "$GITHUB_STEP_SUMMARY"
```

## Interpreting signals

| Signal | Meaning |
| --- | --- |
| CI `passed` | All returned checks/statuses passed, were neutral, or were skipped |
| CI `failed` | At least one failed, errored, cancelled, timed out, or requires action |
| CI `pending` | No failure found, but at least one check/status is unfinished |
| CI `no_checks` | Both endpoints succeeded but returned no checks/statuses |
| CI `unknown` | Data is unavailable or an outcome is unrecognized |
| Review `changes_requested` | At least one reviewer's latest decisive review requests changes |
| Review `approval_present` | An approval exists and no latest decisive review requests changes |
| Review `no_decisive_review` | No current decisive approval/change request was found |

Comment-only reviews do not erase an earlier decision. Dismissed reviews clear that reviewer's decision. These signals do **not** reproduce GitHub's branch protection or required-review rules. An approval may concern an older commit. CI uses the PR's current **head SHA**, not its synthetic merge commit, and does not identify which checks are required.

## Limitations

- Reports describe the fetched sample, not the entire repository or an atomic snapshot. Concurrent GitHub updates can shift page boundaries.
- Inactivity is measured from `updated_at`; a stale PR is not necessarily abandoned. The threshold includes drafts and closed PRs if selected.
- Suggested actions are transparent metadata heuristics, not code-quality judgments or merge recommendations. They do not analyze diffs, unresolved review threads, Issues, or LLM summaries.
- No retries or automatic waiting on rate limits. Initial fetch errors stop the report; optional detail errors produce warnings.
- Check-run listing follows GitHub's REST endpoint limits, including its check-suite scope.

## Development

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

Tests use mocked API responses for pagination, auth headers, filters, exit codes, stale boundaries, review decisions, CI aggregation and partial failures. CI runs on Python 3.10, 3.12 and 3.13.

## API references

- [Pull requests](https://docs.github.com/en/rest/pulls/pulls#list-pull-requests)
- [Reviews](https://docs.github.com/en/rest/pulls/reviews#list-reviews-for-a-pull-request)
- [Check runs](https://docs.github.com/en/rest/checks/runs#list-check-runs-for-a-git-reference)
- [Commit statuses](https://docs.github.com/en/rest/commits/statuses#list-commit-statuses-for-a-reference)
- [Rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)

## License

MIT
