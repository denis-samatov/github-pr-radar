# Changelog

## 0.2.0

- Fix overlapping pagination when the requested PR limit is not a multiple of 100.
- Add author/label filters and draft exclusion.
- Add optional check-run, commit-status and review signals with explicit partial-data warnings.
- Add suggested triage actions and Markdown output.
- Add `--fail-on-stale` for CI, preserve existing summary JSON fields, and include all matched PRs.
- Validate CLI arguments before network access; provide credential-safe API error messages.
- Split API access, report analysis and CLI presentation into separate modules.

## 0.1.0

- Initial read-only GitHub REST API CLI with inactivity and draft counts.
