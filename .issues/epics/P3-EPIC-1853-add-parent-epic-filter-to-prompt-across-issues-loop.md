---
id: EPIC-1853
title: Add parent-epic filter to prompt-across-issues loop
type: EPIC
priority: P3
captured_at: '2026-06-01T17:06:21Z'
completed_at: '2026-06-01T18:33:17Z'
discovered_date: 2026-06-01
discovered_by: capture-issue
status: done
relates_to:
- ENH-1643
decision_needed: false
confidence_score: 100
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# EPIC-1853: Add parent-epic filter to prompt-across-issues loop

## Summary

`prompt-across-issues` supports type filtering (`--context type=BUG`) via ENH-1643, but has no way to scope a sweep to all issues belonging to a specific epic. A user running a prompt across all children of EPIC-1773 must manually enumerate issue IDs or run the full-backlog sweep. Add an optional `parent` context variable that narrows the pending list to issues whose `parent:` frontmatter matches a given epic ID.

## Current Behavior

`prompt-across-issues` builds its pending list from `ll-issues list --json` with an optional `--type` flag (ENH-1643). There is no `--parent` flag on `ll-issues list` and no `parent` context variable on the loop. Users wanting to sweep all children of an epic have no supported path.

## Expected Behavior

```bash
# Sweep all open issues under EPIC-1773
ll-loop run prompt-across-issues "/ll:ready-issue {issue_id}" --context parent=EPIC-1773
```

When `parent` is supplied, the `init` state filters the pending list to issues whose `parent:` frontmatter field matches the given ID. When omitted, behavior is identical to today.

## Motivation

Wave-based epic work (e.g., EPIC-1773) produces a set of child issues that need the same sweep applied — readiness checks, refinement, verification. Today there's no idiomatic way to run `prompt-across-issues` scoped to those children without manually listing IDs or sweeping the entire backlog. This is the natural sibling to type filtering (ENH-1643): type narrows by category, parent narrows by ownership.

## Proposed Solution

Two options for the filtering mechanism:

**(a) Post-filter in `init`** — run `ll-issues list --json`, then filter the JSON in Python to keep only issues where `parent == context.parent`. No changes to `ll-issues list` CLI.

> **Selected:** (a) Post-filter in `init` — self-contained to one YAML file; `parent` is already in `ll-issues list --json` output, directly mirrors the existing `context.type` pattern in the same `init` state.

**(b) Add `--parent` flag to `ll-issues list`** — extend the CLI to support `ll-issues list --parent EPIC-1773 --json`, then pass `--parent ${context.parent}` conditionally in `init` (same pattern as `--type`).

Option (a) is self-contained to the loop YAML. Option (b) is more reusable but requires a Python CLI change.

### Changes (Option a — loop-only)

1. Add `context: { parent: "" }` block above `states:` in `prompt-across-issues.yaml`
2. In `init`, after `ll-issues list --json`, pipe through a Python filter that drops issues where `parent != context.parent` when `context.parent` is non-empty
3. Update loop `description:` to document the new flag

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-01.

**Selected**: (a) Post-filter in `init`

**Reasoning**: Option (a) is self-contained to `prompt-across-issues.yaml` (~10 lines, one file), directly mirrors the existing `context.type` → shell-variable → Python-filter chain already in the same `init` state, and requires no new infrastructure since `parent` is already emitted in `ll-issues list --json` output (list_cmd.py:121). Option (b)'s added CLI reusability is not justified here — no other loop callers use the conditional `TYPE_ARG` pattern that would benefit from a native `--parent` CLI flag.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| (a) Post-filter in `init` | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| (b) Add `--parent` CLI flag | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:
- (a): `parent` field already in `ll-issues list --json` output (list_cmd.py:121); `context.type` pattern in same `init` state is a direct template (prompt-across-issues.yaml:40-49); `test_init_supports_type_filter` at test_builtin_loops.py:1186 is the direct test analog
- (b): `--milestone` in list_cmd.py:47-57 and __init__.py:184-189 are structural templates; requires 4 files changed vs 1; `issues_dir_with_epic_children` fixture already exists but additional CLI test scope adds maintenance surface

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/prompt-across-issues.yaml` — add `parent` context var and filter logic in `init`
- *(Option b only)* `scripts/little_loops/cli/issues/__init__.py` — add `--parent` argument

### Similar Patterns
- `scripts/little_loops/loops/prompt-across-issues.yaml` init state lines 40-49 — exact `TYPE_ARG` / `[ -n "${context.type}" ]` pattern and Python one-liner (`python3 -c "import json, sys; ..."`) to mirror
- `scripts/little_loops/loops/test-coverage-improvement.yaml:20-22` — empty-string default for optional context vars with `[ -n ... ]` guard in shell action

### Dependent Files (Callers/Importers)
- N/A — loop YAML is not a Python module; invoked directly via `ll-loop run prompt-across-issues`

### Tests
- `scripts/tests/test_builtin_loops.py:1092` — `TestPromptAcrossIssuesLoop` class; add `test_init_supports_parent_filter` mirroring `test_init_supports_type_filter` at line 1186 (validates `context.parent` default is `""` and init action body references `${context.parent}`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issues_cli.py` — *(Option b only)* add `test_list_filter_by_parent_match` and `test_list_filter_by_parent_no_match` in `TestIssuesCLIList` class, mirroring `test_list_filter_by_milestone_match` (line 619); create an issue with `parent: EPIC-001` frontmatter, invoke `ll-issues list --parent EPIC-001` and assert it appears, invoke with `--parent EPIC-999` and assert it doesn't

### Documentation
- `docs/guides/LOOPS_GUIDE.md:560` — `prompt-across-issues` table row; add `--context parent=EPIC-NNN` to capability description
- `scripts/little_loops/loops/README.md:27` — same table row; parallel update required

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — *(Option b only)* `ll-issues list` flag table (~line 793); add `--parent EPIC-NNN` row mirroring the `--milestone` entry

### Configuration
- N/A

## Implementation Steps

1. Add `parent: ""  # Optional: EPIC-NNN. When set, restricts sweep to issues with matching parent: field.` to the `context:` block in `scripts/little_loops/loops/prompt-across-issues.yaml` (alongside the existing `type: ""` entry)
2. In the `init` state (lines 40-49 of `prompt-across-issues.yaml`), add a `PARENT_ARG` guard below the existing `TYPE_ARG` block:
   - **Option (a) — post-filter in Python**: extend the existing `python3 -c` one-liner to add `if "${context.parent}": issues = [i for i in issues if i.get('parent') == "${context.parent}"]` before the `for` loop (the `parent` field is already present in `ll-issues list --json` output at `list_cmd.py:121`)
   - **Option (b) — CLI flag**: add `--parent "${context.parent}"` argument to `ll-issues list` call; register the arg in `scripts/little_loops/cli/issues/__init__.py` (lines 126-197) and add filter in `scripts/little_loops/cli/issues/list_cmd.py` (lines 42-56, matching `type_filter` pattern)
3. Update loop `description:` field in `prompt-across-issues.yaml` to document `--context parent=EPIC-NNN` usage
4. Update documentation table rows:
   - `docs/guides/LOOPS_GUIDE.md:560` — append `--context parent=EPIC-NNN` to capability column
   - `scripts/little_loops/loops/README.md:27` — same update
5. Add `test_init_supports_parent_filter` test method to `scripts/tests/test_builtin_loops.py:TestPromptAcrossIssuesLoop` (line 1092), mirroring `test_init_supports_type_filter` at line 1186 — validate `context.parent` default is `""` and init action body references `${context.parent}`
6. Run `ll-loop validate prompt-across-issues`
7. Dry-run: `ll-loop run prompt-across-issues "/ll:ready-issue {issue_id}" --context parent=EPIC-1773` and confirm pending list matches `ll-issues list --json | python3 -c "import json,sys; [print(i['id']) for i in json.load(sys.stdin) if i.get('parent')=='EPIC-1773']"`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation (Option b path only):_

8. *(Option b only)* Add `test_list_filter_by_parent_match` and `test_list_filter_by_parent_no_match` to `scripts/tests/test_issues_cli.py` in `TestIssuesCLIList` — mirror `test_list_filter_by_milestone_match` (line 619); write a temp issue file with `parent: EPIC-001` frontmatter, invoke `ll-issues list --parent EPIC-001`, assert it appears; invoke with `--parent EPIC-999`, assert it doesn't
9. *(Option b only)* Update `docs/reference/CLI.md` `ll-issues list` flag table (~line 793) — add `--parent EPIC-NNN` row with description mirroring the `--milestone` entry

## API/Interface

```yaml
context:
  parent: ""  # Optional: EPIC-NNN. When set, restricts sweep to issues with matching parent: field.
```

```bash
ll-loop run prompt-across-issues "<prompt>"                          # all open issues (unchanged)
ll-loop run prompt-across-issues "<prompt>" --context parent=EPIC-1773  # children of EPIC-1773 only
ll-loop run prompt-across-issues "<prompt>" --context type=ENH --context parent=EPIC-1773  # both filters
```

## Scope Boundaries

- **Out of scope**: multi-parent selection
- **Out of scope**: filtering by any attribute other than `parent` (priority, label, etc.)
- **Out of scope**: changes to `ll-loop run` itself — uses existing `--context KEY=VALUE` mechanism

## Success Metrics

- `ll-loop validate prompt-across-issues` exits 0
- `--context parent=EPIC-1773` pending list matches `ll-issues list --json` filtered to `parent == "EPIC-1773"`
- Default invocation (no `--context parent`) is bit-for-bit identical to pre-change

## Impact

- **Priority**: P3 — Quality-of-life for epic-scoped sweep workflows
- **Effort**: Small — mirrors ENH-1643 pattern exactly; ~10 lines in one YAML file (Option a)
- **Risk**: Low — empty-string default preserves current behavior; post-filter logic is simple Python
- **Breaking Change**: No

## Labels

`enhancement`, `loops`, `fsm`

## Session Log
- `/ll:ready-issue` - 2026-06-01T18:31:17 - `08b37632-8612-4103-9d09-928ebcf3d023.jsonl`
- `/ll:decide-issue` - 2026-06-01T18:27:22 - `ead2516b-025f-48fe-a5f9-3dcf77ecea5d.jsonl`
- `/ll:wire-issue` - 2026-06-01T18:20:06 - `188f6aed-9b5a-476d-b0ec-814b0c9ef6c1.jsonl`
- `/ll:refine-issue` - 2026-06-01T18:16:07 - `82ca77a3-3757-46eb-bd70-4bbff3c8fb0e.jsonl`
- `/ll:format-issue` - 2026-06-01T17:14:33 - `96043361-acea-4c7e-bf4e-4bf536eb0898.jsonl`
- `/ll:capture-issue` - 2026-06-01T17:06:21Z - `1781e718-7f06-4b5d-95f3-141040199f61.jsonl`
- `/ll:confidence-check` - 2026-06-01T19:00:00Z - `494ad2ed-0ef5-43fe-bde9-a221baa7ae4c.jsonl`
- `/ll:confidence-check` - 2026-06-01T20:00:00Z - `fcb37dcb-bab8-4c41-bfb1-b4884a0855e9.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P3
