---
id: BUG-2427
title: '`project_digest` treats `sections=[]` as "render nothing", silently emptying
  the session-start project-context digest'
type: BUG
priority: P2
status: done
captured_at: '2026-07-01T18:43:12Z'
completed_at: '2026-07-01T18:43:12Z'
discovered_date: 2026-07-01
discovered_by: user
labels:
- bug
- history-db
- session-digest
- silent-failure
- contract-mismatch
- test-hygiene
relates_to:
- ENH-1907
- ENH-2040
decision_needed: false
confidence_score: 100
---

# BUG-2427: `project_digest` treats `sections=[]` as "render nothing", silently emptying the session-start project-context digest

## Summary

`project_digest()` in `scripts/little_loops/history_reader.py` violates its own
documented contract. The docstring states that `sections=None` **or**
`sections=[]` both render all registered providers, but the implementation only
special-cased `None`. An empty list `[]` fell through to the `else` branch and
became the (empty) provider list, so **zero** sections were queried — yielding an
empty `ProjectDigest` (`empty == True`), which makes `render_project_context()`
return `""` and drops the `<project_context>` block entirely.

The bug was masked in production because the two call sites each carried an
identical defensive band-aid (`_sd.sections if _sd.sections else None`) to map
the empty-list config default to `None`. That workaround is the tell that the API
contract was broken: any caller passing `_sd.sections` (the config default `[]`,
per `config/features.py:809`) directly would silently get no digest.

While fixing this, a second, independent defect surfaced in the module's test
suite: `TestProjectDigest` fixtures hardcoded `ts="2026-06-01T10:00:00Z"`, which —
with today being 2026-07-01 — fell at/outside the `days=30` window, so 7 "fresh
row" tests began failing purely due to the wall-clock date (a latent time-bomb).

## Steps to Reproduce

1. Call `project_digest(db, sections=[])` against a populated `history.db`.
2. **Observe:** `digest.empty is True` and `render_project_context(digest) == ""`,
   even though the DB has recent file events / completed issues / corrections.
3. Separately: run `pytest scripts/tests/test_history_reader.py::TestProjectDigest`
   on any date ≥ ~30 days after 2026-06-01 and observe 7 unrelated failures from
   the hardcoded fixture timestamps aging out of the digest window.

## Root Cause

`scripts/little_loops/history_reader.py`, in `project_digest()`:

```python
# before — only None is treated as "all providers"
provider_keys: list[str] = list(SECTION_PROVIDERS.keys()) if sections is None else sections
```

`[]` is falsy but `is not None`, so it was used verbatim as the (empty) provider
list. The docstring, the config default (`sections=[]`), and both caller
workarounds all agree that "unconfigured / empty" should mean "render all" — only
the code and one test disagreed.

The test-suite time-bomb was a separate cause: `TestProjectDigest._insert_file_event`
/ `_insert_issue_event` defaulted `ts` to a fixed calendar date instead of a
recent-relative timestamp.

## Resolution

_Resolved 2026-07-01 (direct fix, TDD-adjacent: red fixtures observed first)._

1. **Contract fix** — `history_reader.py`, `project_digest()`:
   ```python
   # after — both None and [] mean "all providers"
   provider_keys: list[str] = list(SECTION_PROVIDERS.keys()) if not sections else sections
   ```
   A non-empty list still restricts/orders output. The docstring already described
   this behavior, so no doc edit was needed.

2. **Test corrected** — `scripts/tests/test_history_reader.py`: the test that
   encoded the buggy behavior (`test_empty_sections_list_returns_empty_digest`,
   which asserted `sections=[]` → empty) was repurposed to
   `test_empty_sections_list_renders_all_sections`, asserting `[]` renders all
   sections against a populated DB.

3. **Caller cleanup (behavior-preserving)** — removed the now-redundant
   `_sd.sections if _sd.sections else None` band-aid in both call sites, passing
   `_sd.sections` directly:
   - `scripts/little_loops/hooks/session_start.py` (session-start digest injection)
   - `scripts/little_loops/cli/history_context.py` (`ll-history-context` CLI)

4. **Test-suite time-bomb fix** — `TestProjectDigest._insert_file_event` /
   `_insert_issue_event` now default `ts` to `now - 1 day`
   (`datetime.now(UTC) - timedelta(days=1)`) instead of a fixed `2026-06-01`, so
   "fresh row" assertions stay inside the digest window on any run date. Tests that
   deliberately exercise staleness still pass explicit old timestamps and are
   unaffected.

## Impact

- **Priority**: P2 — the affected feature (`session_digest`) is **default-on**
  (ENH-2040), and the module's own test class was actively red as of 2026-07-01
  from the fixture time-bomb. Production user-facing impact from the contract bug
  alone was masked by the caller band-aids, but the API was a latent footgun and
  the suite (this project's sole CI gate) was failing.
- **Effort**: Small — one-token predicate change, one test rewrite, two caller
  simplifications, and two fixture-default edits.
- **Risk**: Low — the contract fix is behavior-preserving for the default (`[]` →
  all) and for explicit non-empty lists; graceful empty-digest degradation on a
  missing/empty/stale DB is unchanged.

## Verification

- `pytest scripts/tests/test_history_reader.py scripts/tests/test_hook_session_start.py scripts/tests/test_history_context_cli.py`
  → **155 passed**.
- `TestProjectDigest` alone → **14 passed** (previously 7–8 failing on this date).
- End-to-end smoke against the real `.ll/history.db`: `project_digest(..., sections=[])`
  now returns the same non-empty sections as the `None` default, and
  `render_project_context(...)` starts with `<project_context>`.
- `ruff check` + `ruff format --check` clean on all four changed files.
- Full suite (`python -m pytest scripts/tests/`): **13304 passed, 23 skipped,
  1 failed in 427s**. The single failure —
  `test_enh494_skill_companions.py::TestSkillLineLimit::test_all_skills_within_limit`
  (a SKILL.md line-count limit) — is **pre-existing and unrelated**: this change
  touched no skill files (only `history_reader.py`, `test_history_reader.py`,
  `session_start.py`, `history_context.py`). Same standing failure recorded in
  [[BUG-2423]]'s resolution.

## Files Changed

- `scripts/little_loops/history_reader.py` — `project_digest()` predicate fix.
- `scripts/tests/test_history_reader.py` — repurposed empty-sections test; fixture
  timestamps made recent-relative.
- `scripts/little_loops/hooks/session_start.py` — removed caller band-aid.
- `scripts/little_loops/cli/history_context.py` — removed caller band-aid.

## Similar Patterns

- Same silent-failure family as other "empty result vs. failure are the same
  signal" bugs (e.g. [[BUG-2423]] swallowing CLI errors). Here the false-clean
  signal was an empty provider list rather than a swallowed exit code.

## Status

**Done** | Created: 2026-07-01 | Completed: 2026-07-01 | Priority: P2


## Session Log
- `hook:posttooluse-status-done` - 2026-07-01T18:44:54 - `771898ce-5217-4c16-8aa1-2394b36bffd0.jsonl`
