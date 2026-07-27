---
id: FEAT-2850
type: FEAT
priority: P2
status: open
parent: FEAT-2846
discovered_date: 2026-07-26
discovered_by: issue-size-review
blocked_by:
- FEAT-2849
labels:
- issues-cli
- dependency-graph
- linting
decision_needed: true
---

# FEAT-2850: Repo-wide prose-dependency sweep gated in pytest

## Summary

Add a repo-wide sweep mode that reports every issue with prose-dependency
drift, gated in `python -m pytest scripts/tests/` per the project's
no-hosted-CI policy, and fix the 9 issues in this repo already known to
drift. Decomposed from FEAT-2846; depends on FEAT-2849's extractor and gap
taxonomy.

## Parent Issue

Decomposed from FEAT-2846: Detect prose dependency claims that are missing
from frontmatter. Covers Implementation Steps 4 and 7 of the parent.

## Decision Needed

The parent issue left the sweep's entry-point route as an open decision:
either a `format-check --all` mode (no new command surface, per the
parent's stated preference — "Reusing the existing taxonomy means no new
command surface and free integration with every consumer of
format-check") or a new standalone `ll-verify-prose-deps` entry point
following the `ll-verify-*` family's conventions. Resolve this before
implementation — it determines which of the two file lists below applies.

## Expected Behavior

A sweep over the active issue categories (`bugs`, `features`,
`enhancements`, `epics`) that reports every `prose_dep_drift`/
`stale_prose_dep` gap found, wired into the pytest suite so it fails CI
(this repo's local suite) if any issue drifts. Once built, fix this repo's
9 currently-drifting issues so the gate passes clean:

```
EPIC-2149→ENH-2148   FEAT-2414→FEAT-2413   ENH-2580→ENH-2581
ENH-2582→ENH-2581    EPIC-2457→ENH-2581    EPIC-2575→FEAT-2576
EPIC-2765→ENH-2762   FEAT-2416→FEAT-2413   EPIC-2257→BUG-2266
```

## Integration Map

### If the standalone `ll-verify-prose-deps` route is chosen
- `scripts/little_loops/cli/verify_prose_deps.py` — **NEW**: follow
  `scripts/little_loops/cli/verify_cli_allowlist.py`'s `_run()`/
  `main_verify_*()` shape
- `scripts/little_loops/cli/__init__.py:90-144` — add
  `main_verify_prose_deps` to the `main_verify_*` export list
- `scripts/little_loops/cli/doctor.py:455-489` — `ll-doctor --full`'s
  `_FULL_CHECKS` registry is hand-registered, not auto-discovering; add a
  dedicated `@register_full_check`-decorated adapter (model:
  `_full_docs_check` at `doctor.py:486-489`) or `--full` silently won't run
  it
- `skills/configure/areas.md` ("All ll- commands" preset) and
  `writers._LL_PERMISSIONS` — `ll-verify-cli-allowlist` asserts every
  `ll-` entry point in `scripts/pyproject.toml` is mirrored in both; a new
  registration without matching entries here fails that existing gate
- `scripts/pyproject.toml:69-102` — `[project.scripts]` `ll-verify-*`
  registration
- `docs/reference/CLI.md` — new subcommand docs
- `.claude/CLAUDE.md` CLI Tools list — new bullet

### If the `format-check --all` mode is chosen instead
- `scripts/little_loops/cli/issues/format_check.py` — add an `--all` flag
  that walks all active categories instead of a single issue path
- No new entry point, no `doctor.py`/`verify_cli_allowlist`/
  `pyproject.toml` changes

### Tests
- `scripts/tests/test_verify_cli_allowlist.py` — in-process gate-test
  pattern to follow if the standalone route is chosen (call `_run()` /
  `main_verify_*()` directly, assert `exit_code == 0`) — not
  `test_policy_builder_node_gate.py`'s subprocess-wrap style, which is
  reserved for a different-toolchain (Node) gate
- New test module following that three-tier shape: pure-function unit
  tests → `_run()` with `patch(...)` for the dirty-state branch →
  `main_verify_*()` with `patch("sys.argv", ...)` asserting exit code +
  `capsys` stderr

### Behavioral Side Effect
- `scripts/little_loops/loops/rn-remediate.yaml:98-113` — the
  `ensure_formatted` gate checks `check_format_gaps(...).has_gaps` via
  `exit_code` only (not per-category), so any issue with prose-dependency
  drift will start routing to `format_issue` remediation once the new gap
  kinds land (from FEAT-2849) — an intentional but repo-wide behavior
  change worth calling out in this issue's PR description, not a file to
  edit.

## Implementation Steps

1. Resolve the route decision (standalone entry point vs. `--all` mode).
2. Build the sweep using `scripts/little_loops/issues/anchor_sweep.py`'s
   `sweep_issues()` (lines 100-120) as the driver template — walks
   `_ACTIVE_CATEGORIES`, isolates per-file `OSError`s so one bad file
   doesn't abort the sweep.
3. Wire the sweep into `python -m pytest scripts/tests/` per the
   no-hosted-CI policy.
4. Fix this repo's 9 drifting issues so the gate passes.

## Acceptance Criteria

- [ ] The repo-wide sweep runs under `python -m pytest scripts/tests/` and
      passes once this repo's 9 drifting issues are corrected.
- [ ] No GitHub Actions workflow is added.
- [ ] The route decision is resolved and reflected consistently (no
      leftover conditional file lists in code or docs).

## Impact

- **Users**: backlog owners adopting this on an existing project get an
  upfront report of which issues drifted before the rule existed, instead
  of discovering them one mis-scheduled issue at a time.
- **Risk**: Low. Purely additive to the pytest suite.
- **Effort**: Small-Medium, once FEAT-2849 lands.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.claude/CLAUDE.md` § Testing & CI Policy | Gate belongs in the local pytest suite |
| `scripts/little_loops/issues/anchor_sweep.py` | Repo-wide walk driver to reuse |
| `scripts/little_loops/cli/verify_cli_allowlist.py` | `ll-verify-*` convention, if that route is chosen |

## Context

Decomposed from FEAT-2846 by `/ll:issue-size-review` (score 11/11, Very
Large), split out from FEAT-2849 (extractor + gap taxonomy) since the sweep
is independently shippable once the gap kinds exist.

## Session Log
- `/ll:issue-size-review` - 2026-07-26T00:00:00 - `52f8c37a-8768-4813-8704-c3364dbd6e28.jsonl`

---

## Status

open
