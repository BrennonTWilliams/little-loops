---
id: BUG-2754
title: Verify PyPI publication status matches README install instructions
type: BUG
priority: P4
status: done
discovered_date: 2026-07-23
discovered_by: audit-docs
testable: false
confidence_score: 100
outcome_confidence: 95
score_complexity: 25
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 25
completed_at: '2026-07-24T03:31:14Z'
---

README.md presents `pip install little-loops` (README.md:32, 64, 228; also
docs/guides/GETTING_STARTED.md:29) as the primary install path, and the PyPI
badge (README.md:15-17) links to `https://pypi.org/project/little-loops/`.
A web search during a docs audit could not confirm a published release under
that name. `ENH-2256` (done) implies PyPI publishing is a real, intended
distribution channel — `pip install -e "./scripts[dev]"` (CONTRIBUTING.md:32)
is the only path confirmed to work today.

## Expected Behavior

Confirm whether `little-loops` is actually published on PyPI:

- If published: no doc change needed — close as verified.
- If not yet published: README's primary install instructions should lead
  with the editable-install path instead, with PyPI noted as
  forthcoming/aspirational (or the badge removed until publication).

## Acceptance Criteria

- [x] PyPI publication status confirmed (check `pypi.org/project/little-loops/`
      directly, or release/publish tooling in this repo).
- [x] README/GETTING_STARTED install instructions match actual status.

## Source

Found by `/ll:audit-docs readme` (2026-07-23).

## Verification Notes

Confirmed via `curl https://pypi.org/pypi/little-loops/json` (200, not 404):
`little-loops` is published on PyPI, currently at version `1.149.0` with a
long release history (`1.100.0` through `1.149.0` visible). Per this issue's
own Expected Behavior: "If published: no doc change needed — close as
verified." README's `pip install little-loops` instructions and PyPI badge
accurately reflect reality — no doc change required.

## Session Log
- `/ll:verify-issues` - 2026-07-24T03:31:20 - `830776b6-8e8e-4688-bb99-ecd84751534a.jsonl`
- `/ll:confidence-check` - 2026-07-23T00:00:00Z - `830776b6-8e8e-4688-bb99-ecd84751534a.jsonl`
