# GitHub PR Radar

A small, dependency-free Python CLI that integrates with the **GitHub REST API** to inspect pull request activity in public repositories. It reports total PRs, drafts, and PRs that have not been updated for a configurable number of days.

## Features

- Real GitHub REST API integration (`GET /repos/{owner}/{repo}/pulls`)
- Anonymous read access to public repositories (no token required)
- Optional `GITHUB_TOKEN` for higher rate limits or authorized private-repository access
- `open`, `closed`, and `all` PR filters; pagination up to 500 PRs
- JSON output for scripting and CI pipelines
- Standard-library runtime with no external dependencies

## Quick start

Requires Python 3.10+.

```bash
python -m pip install -e .
pr-radar python/cpython --limit 20 --stale-days 30
pr-radar python/cpython --limit 10 --json
```

Or without installation:

```bash
PYTHONPATH=src python -m pr_radar python/cpython --limit 10
```

## Authentication (optional)

For public repositories, authentication is not required, but GitHub applies lower rate limits to anonymous requests. If you need a token, supply it as an environment variable (never commit a token):

```bash
export GITHUB_TOKEN=YOUR_TOKEN
pr-radar owner/repo
```

Use a fine-grained token with minimal permissions and read-only Pull requests access when needed.

## Example output

```text
owner/repo: 4 PR(s), 1 draft(s), 2 stale (≥14 days)
  #12 (20.3 days) Improve documentation
    https://github.com/owner/repo/pull/12
```

This is illustrative output, not a live API result.

## Development

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## GitHub API reference

- [List pull requests](https://docs.github.com/en/rest/pulls/pulls#list-pull-requests)
- [Rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)

## Limitations

- Only analyzes the latest `--limit` PRs, not necessarily all repository history.
- A "stale" PR is defined solely by its last update timestamp; it is not necessarily abandoned.
- The report does not evaluate code quality or review status.

## License

MIT
