---
id: BUG-2754
title: Verify PyPI publication status matches README install instructions
type: BUG
priority: P4
status: open
discovered_date: 2026-07-23
discovered_by: audit-docs
testable: false
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

- [ ] PyPI publication status confirmed (check `pypi.org/project/little-loops/`
      directly, or release/publish tooling in this repo).
- [ ] README/GETTING_STARTED install instructions match actual status.

## Source

Found by `/ll:audit-docs readme` (2026-07-23).
