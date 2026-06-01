---
id: ENH-1860
type: ENH
priority: P4
status: open
captured_at: '2026-06-01T17:35:32Z'
discovered_date: '2026-06-01'
discovered_by: capture-issue
relates_to: [FEAT-1737]
parent: EPIC-1864
---

# ENH-1860: EPIC cascade lifecycle — propagate close/cancel to children

## Summary

When an EPIC's status is set to `cancelled` or `done`, optionally cascade the status change to its active children. Add `--cascade` and `--cascade-to <status>` flags to `ll-issues set-status` so that closing an EPIC can mark its open children `deferred` (default) or `cancelled` in one call. Default behavior remains non-cascading.

## Current Behavior

Setting `ll-issues set-status EPIC-1622 done` only updates the EPIC's frontmatter. Its active children remain `open` / `in_progress` / `blocked`, even though they are now orphans of a closed initiative. Users either leave them as stale orphans, manually close each one, or run `/ll:link-epics` later to reparent them.

`/ll:capture-issue` flips `status: done → open` when reopening, but there is no equivalent flow for "this EPIC is no longer relevant — defer its children."

## Expected Behavior

```
$ ll-issues set-status EPIC-1622 cancelled --cascade
EPIC-1622: marked cancelled
  Cascading to 4 active children (default: deferred):
    ENH-1311 → deferred
    ENH-1312 → deferred
    BUG-1320 → deferred
    FEAT-1335 → deferred
  (5 children already done/cancelled — unchanged)

$ ll-issues set-status EPIC-1622 done --cascade --cascade-to done
# closes all open children as well
```

Without `--cascade`, behavior is unchanged.

## Motivation

EPICs that get cancelled (priority shift, scope change, deprecated direction) leave a tail of stale orphan issues that pollute `ll-issues list` and confuse scan tools. Today this requires N manual `set-status` calls. The cascade flag makes the cleanup atomic and auditable.

This is a lower-leverage gap (EPICs are rarely cancelled), captured at P4 to track but not prioritize.

## Proposed Solution

1. Add `--cascade` (bool) and `--cascade-to <status>` (default: `deferred`) flags to `ll-issues set-status`.
2. Reject `--cascade` if the target status is not `done` or `cancelled` (cascade only makes sense on closure).
3. Resolve children via FEAT-1737 union path.
4. Filter to active statuses (`open`, `in_progress`, `blocked`).
5. Apply the target cascade status to each, in a transaction-style loop with per-file logging.
6. Print summary; exit non-zero if any individual file update fails (but continue the rest).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/set_status.py` (or wherever `set-status` lives) — add `--cascade` flags and child-resolution path
- `scripts/little_loops/cli/issues/__init__.py` — argparse wiring

### Dependent Files (Callers/Importers)
- `scripts/little_loops/sprint.py` — reuse `SprintManager.load_or_resolve()` union for child resolution
- `skills/capture-issue/SKILL.md` — adjacent reopen-issue flow; pattern reference

_Wiring pass added by `/ll:wire-issue`:_
- `skills/review-epic/SKILL.md` — recommends per-child `ll-issues set-status CHILD_ID deferred` calls that `--cascade` replaces; skill workflow should be updated post-implementation [Agent 1 + 2 finding]
- `skills/manage-issue/SKILL.md` — recommends `ll-issues set-status ISSUE_ID done` for completion; should mention `--cascade` for EPIC closure [Agent 1 + 2 finding]

### Similar Patterns
- `ll-issues set-status` existing single-file update — model cascade as N independent updates with shared logging
- FEAT-1737 union resolution — exact same children set

### Tests
- `scripts/tests/test_set_status_cli.py:TestIssuesCLISetStatus` — extend (5 existing tests for basic transitions, error handling)
  - `--cascade` with no children → no-op, exit 0
  - `--cascade` with mix of active/done children → only active ones change
  - `--cascade --cascade-to done` → closes all open children
  - `--cascade` rejected when target status is not done/cancelled
  - One-file failure does not abort the rest

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_progress.py:TestComputeEpicProgress` — tests `compute_epic_progress()` child resolution logic (14 tests); `_make_issue()` helper at line 15 is the canonical test fixture pattern for parent/child relationships [Agent 3 finding]
- `scripts/tests/test_frontmatter.py:TestUpdateFrontmatter` — tests `update_frontmatter()` (10 tests) which the cascade calls per-child; existing coverage confirms the per-file update path is solid [Agent 3 finding]
- `scripts/tests/test_issues_cli.py:issues_dir_with_epic_progress` fixture (line 4419) — closest model for creating EPIC+children test fixtures in CLI integration tests [Agent 3 finding]
- Additional cascade test cases identified (beyond the 5 listed above): default `--cascade-to deferred`, non-EPIC issue skips cascade, resolves via `relates_to:` forward, resolves via `parent:` backward, union dedup [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` — `ll-issues set-status --cascade` flag row
- `.claude/CLAUDE.md` — Issue File Format section may mention cascade in status enum docs

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — references `set-status` usage generically; add cascade flag example [Agent 2 finding]
- `skills/review-epic/SKILL.md` — 4 references (lines 212, 234, 249, 258) recommend individual per-child `set-status` calls; should recommend `--cascade` instead when cascade ships [Agent 2 finding]
- `skills/manage-issue/SKILL.md` — lines 451-457 recommend `set-status` for completion; should mention `--cascade` for EPIC closure [Agent 2 finding]

### Configuration
- `epics.cascade.default_status` (default `deferred`) — overridable (key does not yet exist in `.ll/ll-config.json`)

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` has `additionalProperties: false` at top level — adding `epics` requires explicit declaration in `properties`. Currently no `epics` section exists; closest EPIC keys are `issues.categories.epics` (line 96) and `commands.review_epic` (line 490). [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **set_status.py** (`scripts/little_loops/cli/issues/set_status.py`): 40 lines. Currently reads frontmatter with `parse_frontmatter()`, updates with `update_frontmatter()`, writes back. No cascade or child-awareness. The `_resolve_issue_id()` helper comes from `show.py`.
- **Child resolution (FEAT-1737 pattern)**: `compute_epic_progress()` at `issue_progress.py:67` uses union of forward (`relates_to:`) + backward (`parent:`) lookups, deduplicated (lines 85–87). This is the preferred resolution function for the cascade — simpler than `sprint.py:load_or_resolve()` which adds dependency ordering we don't need.
- **Active statuses**: `_OPEN_STATUSES = frozenset({"open", "in_progress", "blocked"})` at `issue_progress.py:13`. Terminal statuses: `_TERMINAL_STATUSES = frozenset({"done", "cancelled"})` at line 14.
- **Frontmatter update**: `update_frontmatter(content, {"status": new_status})` at `frontmatter.py:190` — already used by `set_status.py:36`.
- **CLI wiring**: `set-status` subparser registered at `__init__.py:583–595`, dispatched at line 692. Add `--cascade` and `--cascade-to` arguments here.
- **Docs**: `set-status` documented at `docs/reference/CLI.md:1203–1217`. Will need a flag row for `--cascade` / `--cascade-to`.
- **Tests**: `scripts/tests/test_set_status_cli.py:TestIssuesCLISetStatus` — extend (5 existing tests for basic transitions, error handling, field preservation). Follow test patterns from `test_issue_progress.py` for child resolution testing.

## Implementation Steps

1. **Argparse extension** — Add `--cascade` (bool, `store_true`) and `--cascade-to` (str, `choices=STATUS_CHOICES`, `default="deferred"`) to the `set-status` subparser at `__init__.py:583–595`. Follow the existing `add_argument` pattern (positional `status` uses `choices=[...]` at line 591).
2. **Validation** — In `cmd_set_status()` at `set_status.py:13`, after resolving the issue path, check: if `--cascade` is set but `args.status` is not `done` or `cancelled`, print error to stderr and return 1.
3. **Child resolution** — Use the union pattern from `compute_epic_progress()` at `issue_progress.py:85–87`: forward (`relates_to:`) + backward (`parent:`) lookups. Call `find_issues(config, status_filter=_OPEN_STATUSES)` to get active children only (filter to `{"open", "in_progress", "blocked"}`). Use `_OPEN_STATUSES` from `issue_progress.py:13` or define locally.
4. **Apply cascade** — Loop over resolved `IssueInfo` children. For each: read file, `update_frontmatter(content, {"status": args.cascade_to})` (from `frontmatter.py:190`), write back. Wrap each update in try/except; accumulate successes/failures. Continue on individual failure (do not abort).
5. **Render summary** — Print EPIC transition line (existing), then a summary block: total children, how many cascaded, how many skipped (already terminal), how many failed. Use the format from the issue's Expected Behavior section.
6. **Tests** — Extend `TestIssuesCLISetStatus` in `scripts/tests/test_set_status_cli.py`. Use `_make_issue()` pattern from `test_issue_progress.py:15` for creating parent/child fixtures. Test cases: no children → no-op, mixed active/done, `--cascade-to done`, rejected for non-closing target, individual failure doesn't abort.
7. **Docs** — Add `--cascade` and `--cascade-to` rows to the set-status table at `docs/reference/CLI.md:1207–1210`. Add config key `epics.cascade.default_status` to `config-schema.json` under the `epics` category.
8. **Config** — Optionally add `epics.cascade.default_status` to `.ll/ll-config.json` with default `deferred`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. **Update `skills/review-epic/SKILL.md`** — Replace individual per-child `ll-issues set-status CHILD_ID deferred` recommendations with `ll-issues set-status EPIC_ID done --cascade` at lines 212, 234, 249, 258. This is the highest-impact skill coupling — cascade makes its primary recommendation pattern obsolete.
10. **Update `skills/manage-issue/SKILL.md`** — Add `--cascade` mention to the `set-status` completion recommendation at lines 451-457 for when the completed issue is an EPIC.
11. **Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`** — Add cascade flag example alongside existing `set-status` usage references.
12. **Config schema validation** — `config-schema.json` has `additionalProperties: false` at top level; the new `epics` top-level key must be declared in `properties` alongside the existing `issues` and `commands` sections.
13. **Use `_OPEN_STATUSES` from `issue_progress.py:13`** — Avoid defining a third copy of the active-status set. `_OPEN_STATUSES` and `sprint.py:_ACTIVE_STATUSES` are identical; prefer the one already imported in the resolution path.

## Impact

- **Priority**: P4 — Low frequency (EPIC cancellation is rare); cleanup ergonomics.
- **Effort**: Small — Reuses resolution; adds a flag + loop.
- **Risk**: Low–Medium — Mass status updates, but only when explicitly opted in via flag. Default behavior preserved.
- **Breaking Change**: No

## Success Metrics

- Cancelling an EPIC with N active children completes in 1 command instead of N+1.
- No accidental cascades — flag is required.

## Scope Boundaries

- Cascade only on `done` / `cancelled` (not `open`, `in_progress`, etc.).
- Cascade does not edit child issue body or remove them — only status frontmatter.
- No automatic reparenting of children to a successor EPIC (out of scope).
- No reverse cascade (child status changes do not propagate up).

## API/Interface

```
ll-issues set-status EPIC-NNN done --cascade
ll-issues set-status EPIC-NNN cancelled --cascade --cascade-to cancelled
```

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `epics`, `cli`, `lifecycle`, `captured`

## Session Log
- `/ll:wire-issue` - 2026-06-01T21:57:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7792ec77-ca5f-4918-82dc-00025e2d1ee3.jsonl`
- `/ll:refine-issue` - 2026-06-01T21:50:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c9e18a4f-1421-454e-946b-7d7f53cf8dc6.jsonl`
- `/ll:format-issue` - 2026-06-01T17:45:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ac3a8d0e-1e74-47b1-9d58-b8dbb8f453b4.jsonl`
- `/ll:capture-issue` - 2026-06-01T17:35:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/277dd3c5-ffef-46cb-bcc6-124409ce1225.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P4
