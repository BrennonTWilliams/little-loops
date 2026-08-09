---
id: BUG-3110
type: BUG
title: '`auto-refine-and-implement` silently ignores its positional scope arg and
  works the whole backlog instead'
priority: P2
status: done
captured_at: '2026-08-08T00:00:00Z'
completed_at: '2026-08-09T01:11:46Z'
discovered_date: 2026-08-08
discovered_by: loop-run-review
testable: true
labels:
- loop-authoring
- issue-management
- silent-failure
relates_to:
- ENH-2601
- ENH-2615
confidence_score: 100
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 23
---

# BUG-3110: `auto-refine-and-implement` silently ignores its positional scope arg

## Summary

`ll-loop run auto-refine-and-implement EPIC-3041` accepts the EPIC id, reports
no error, and then refines and implements an entirely different set of issues —
the priority-ranked backlog. The run in
`.loops/runs/auto-refine-and-implement-20260808T002107/` spent 8h25m and $23.24
closing 11 backlog issues while doing zero work on EPIC-3041's seven children.

This is a silent-wrong-work defect, not a crash: every state reports success,
the run looks healthy in the terminal, and the divergence is only visible by
diffing `autodev-input.txt` against the EPIC's child set after the fact.

## Current Behavior

`auto-refine-and-implement.yaml` declares no `input_key`, so it inherits the
FSM default `input_key: "input"` (`fsm/schema.py:1292`, `:1558`).

In `cli/loop/run.py:162-175` the positional arg is JSON-parsed first; only a
JSON **dict** whose keys intersect `fsm.context` is splatted into context.
`"EPIC-3041"` is not JSON, so it falls to the else branch:

```python
fsm.context[fsm.input_key] = raw   # → context["input"] = "EPIC-3041"
```

Nothing in the loop reads `context.input` — its sole mention is a comment on
line 111 describing the *autodev sub-loop's* input. The loop's actual knob is
`context.scope`, which stays `""`, so `resolve_set` takes the else branch:

```sh
LIST=$(ll-issues next-issues 2>/dev/null | head -n ${context.max_issues} | paste -sd ',' -)
```

Knock-on effects, all silent — every EPIC-specific state no-ops on an empty scope:

- `checkout_epic_branch` — `re.fullmatch(r"EPIC-\d+", scope)` fails → no epic
  branch, so `delegate`'s `worktree: ${captured.epic_branch.output}` is a no-op
  and commits land directly on the base branch (ENH-2601/ENH-2609 bypassed).
- `recheck_set` — `grep -qE '^EPIC-[0-9]+$' || exit 1` → mid-run decompositions
  never cycle back for a second delegate pass (ENH-2615 bypassed).
- `merge_epic_branch` — nothing to merge (BUG-2614 path bypassed).

The same defect makes the invocation documented in
`sprint-refine-and-implement.yaml:6-7` wrong:

```
ll-loop run auto-refine-and-implement 'scope=<sprint-name|EPIC-NNN>'
```

`"scope=EPIC-3041"` is not valid JSON either, so it also lands in
`context.input`. Only `--context scope=EPIC-3041` works today.

## Expected Behavior

`ll-loop run auto-refine-and-implement EPIC-3041` binds `EPIC-3041` to
`context.scope` and resolves that EPIC's descendant set, exactly as
`ll-loop run sprint-refine-and-implement EPIC-3041` already does via its
`input_key: sprint_name`.

A bare `ll-loop run auto-refine-and-implement` with no argument must keep
working — empty scope is the supported "rank the backlog" mode, so
`required_inputs` must NOT be added.

## Steps to Reproduce

1. `ll-loop run auto-refine-and-implement EPIC-3041 -q`
2. Inspect `<run_dir>/autodev-input.txt`.
3. Observe it contains the ranked backlog (37 unrelated ids), not the EPIC's
   children. No warning is emitted at any point.

## Root Cause

Missing `input_key: scope` declaration. The sibling loop
`sprint-refine-and-implement.yaml:8-9` gets this right
(`input_key: sprint_name` + `required_inputs`);
`auto-refine-and-implement` is the only built-in loop that declares a `scope: ""`
context knob without a matching `input_key`.

## Proposed Solution

Declare `input_key: scope` on `auto-refine-and-implement.yaml`, without
`required_inputs`. One line, no state-machine changes; the
`sprint-refine-and-implement` alias is unaffected because it binds `scope:`
explicitly through `with:` rather than through the positional arg.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — declare `input_key: scope` (already applied in the working tree, uncommitted, at line 64, with a BUG-3110 comment above it)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — correct the documented invocation in its `description:` block (already applied, uncommitted)
- `docs/guides/LOOPS_REFERENCE.md` — `auto-refine-and-implement`'s "Required context variables" table (around line 937-941) lists only `max_issues`; it has no row for `scope` and no `(populated from positional CLI arg via input_key: scope)` phrasing, unlike the sibling `sprint-refine-and-implement` entry immediately above it (`:911-914`) and unlike other `input_key`-binding loops' rows (`rn-plan`, `rn-refine`, `rn-stepwise`). This table was not updated by the in-tree fix and is not covered by Implementation Steps 1-4.

### Dependent Files (Callers/Consumers of `context.scope`)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` states `resolve_set`, `checkout_epic_branch`, `recheck_set`, and `merge_epic_branch` all interpolate `${context.scope}` directly into embedded Python/shell — the FSM executor substitutes the value before the block runs, so whatever `cli/loop/run.py` writes into `fsm.context["scope"]` at binding time is what these four states see verbatim.
- `scripts/little_loops/cli/loop/run.py:161-175` — the positional-arg injection block; all three write paths (JSON-dict-splat's `else`, non-dict-JSON, and the `except JSONDecodeError` fallback) resolve to `fsm.context[fsm.input_key] = raw`, so this code needed no change — only `fsm.input_key` needed to change, which the YAML edit does.
- `scripts/little_loops/fsm/schema.py:1292` (`FSMLoop.input_key` dataclass default `"input"`) and `:1558` (`input_key=data.get("input_key", "input")` load path) — confirm the mechanism the fix relies on; neither line needed to change.
- `scripts/little_loops/fsm/validation/structural_rules.py:1197-1219` (`_validate_input_key_without_guard`) — fires a WARNING whenever `fsm.input_key != "input"` and `fsm.required_inputs` is empty; fires unconditionally for this loop's fix, since `required_inputs` is deliberately left unset.

### Conventions in Force
- A loop declaring a custom `input_key` (differing from the FSM default `"input"`) is, in every other case in `scripts/little_loops/loops/*.yaml` (~33 loops), paired with `required_inputs: ["<same key>"]` — evidence: `deep-research.yaml:3-4`, `rn-stepwise.yaml:4,26`, `rn-refine.yaml:3,37`, `sprint-refine-and-implement.yaml:11-12`, and 20+ others. `auto-refine-and-implement` is the only loop with a genuinely custom `input_key` that deliberately omits `required_inputs`.
- Where a loop's positional-arg binding is documented per-context-var, the convention is an inline comment on the default-value line reading `# populated from positional CLI arg via input_key: <key>` (`deep-research.yaml:19`, `rn-stepwise.yaml:29`, `rn-plan.yaml:21`) or the `# populated from loop_input via input_key: <key>` variant (`generative-art.yaml:26` and 10+ others) — both phrasings coexist with no documented rule for which applies; a contested convention, not a single canonical form.
- `TestValidatorWarningBudget.ALLOWLIST` entries in `scripts/tests/test_builtin_loops.py` (the mechanism suppressing this fix's expected `required-inputs` warning) follow a consistent three-part comment shape immediately above each entry: cite the owning issue ID, name the validator rule that fired, and explain why the warning is a false positive/accepted tradeoff for that specific loop — evidence: `test_builtin_loops.py:13562-13574` (ENH-2903), `:13575-13590` (BUG-3107), `:13591-13598` (this fix's own entry, BUG-3110). A header block at `:13550-13560` documents the migration path away from allowlisting once a rule gains an in-YAML suppress flag (citing ENH-2748 and BUG-2112 as precedent).
- Structural regression tests for "sibling loop declares X correctly, this loop doesn't" bugs live as a dedicated `test_*` method inside the affected loop's own `TestXxxLoop` class, with a docstring citing the bug ID and asserting both the positive requirement (field present/correct) and, where relevant, the negative requirement (a field that must stay absent) — evidence: `test_scope_declared` (BUG-3087, `test_builtin_loops.py:4082-4095`) and this fix's own `test_input_key_binds_positional_arg_to_scope` (`test_builtin_loops.py:4097-4117`), both inside `TestAutoRefineAndImplementLoop`. The sibling `TestSprintRefineAndImplementLoop` class carries the mirror-image assertion, `test_sprint_name_is_required_input` (`:4146-4149`), testing for the presence of what this fix's test asserts must be absent.

### Tests
- `scripts/tests/test_builtin_loops.py::TestAutoRefineAndImplementLoop::test_input_key_binds_positional_arg_to_scope` — already added, uncommitted; asserts `input_key == "scope"`, `"scope"` is declared under `context:`, and `required_inputs` stays unset.
- `scripts/tests/test_builtin_loops.py::TestValidatorWarningBudget` — already gained the allowlist entry `("auto-refine-and-implement", "required-inputs"): {"required_inputs"}`, consumed by `test_deterministic_warning_categories_do_not_regrow` and cross-checked for staleness by `test_allowlist_entries_are_not_stale`.
- No test currently asserts the end-to-end CLI behavior (`ll-loop run auto-refine-and-implement EPIC-3041` actually produces `fsm.context["scope"] == "EPIC-3041"` through `cli/loop/run.py`'s binding block) — the existing test is structural (YAML-shape only), not behavioral.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_commands.py` — new end-to-end test needed; no existing test combines real CLI-arg parsing with an observable context assertion against the actual `auto-refine-and-implement.yaml` loop. Closest pattern to extend: `test_required_input_supplied_proceeds` (`:5094`, patches `sys.argv` + calls the real `main_loop()` entry point rather than replicating the injection logic) combined with the capsys-on-dry-run-stdout style of `test_dry_run_with_show_diagrams_renders_diagram` (`:4826`) / `test_dry_run_without_show_diagrams_no_diagram` (`:4863`) — `cmd_run`'s `--dry-run` path prints the post-injection `Context:` block via `print_execution_plan` (`cli/loop/_helpers.py:1499-1502`), so `--dry-run` output is the observable signal without needing a code-level hook. Shape: `sys.argv = ["ll-loop", "run", "--dry-run", "auto-refine-and-implement", "EPIC-3041"]` → `main_loop()` → assert `"scope: 'EPIC-3041'"` in `capsys.readouterr().out`. [Agent 3 finding]

### Documentation
- `docs/guides/LOOPS_GUIDE.md:92-94` documents the generic `input_key`/`required_inputs`/validator-warning mechanism once; no loop-specific update needed there.
- `docs/guides/LOOPS_REFERENCE.md` — see Files to Modify above; the per-loop table row for `auto-refine-and-implement` is stale relative to the fix and is not addressed by the current Implementation Steps.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Types
N/A — no new data shape introduced; the fix is a single scalar YAML field (`input_key: scope`), and `context.scope` already existed as a declared `str` context var (`auto-refine-and-implement.yaml`, `context:` block).

### Signatures
- `input_key: str` — `FSMLoop` dataclass field, defaults to `"input"` (`scripts/little_loops/fsm/schema.py:1292`); `auto-refine-and-implement.yaml` overrides it to `"scope"`.
- `_validate_input_key_without_guard(fsm: FSMLoop) -> list[ValidationError]` — fires a WARNING when `input_key` is non-default and `required_inputs` is empty (`scripts/little_loops/fsm/validation/structural_rules.py:1197-1219`).

### Call Path
`ll-loop run auto-refine-and-implement EPIC-3041` (argparse captures `EPIC-3041` as `args.input`)
→ `scripts/little_loops/fsm/schema.py` loop-construction (`input_key=data.get("input_key", "input")`, line 1558) resolves `fsm.input_key = "scope"` from the YAML
→ `scripts/little_loops/cli/loop/run.py:161-175` positional-arg injection block: `raw = "EPIC-3041"`; `json.loads(raw)` raises `JSONDecodeError` (bare identifier, not valid JSON) → `except` branch → `fsm.context[fsm.input_key] = raw` → `fsm.context["scope"] = "EPIC-3041"`
→ `--context scope=...`, if supplied, would override this afterward (lines 183-187, "so --context can override")
→ `resolve_set` state reads `${context.scope}` = `"EPIC-3041"`, takes the non-empty branch (`if [ -n "${context.scope}" ]`), resolves via `SprintManager(...).load_or_resolve("EPIC-3041")` instead of falling through to `ll-issues next-issues`
→ `checkout_epic_branch`/`recheck_set`/`merge_epic_branch` each independently re-read `${context.scope}` and recognize it as an EPIC id via their own `re.fullmatch(r"EPIC-\d+", scope)` / `grep -qE '^EPIC-[0-9]+$'` checks.

`sprint-refine-and-implement.yaml`'s alias path is structurally separate: its own `input_key: sprint_name` binds the CLI positional arg to `context.sprint_name`, then its `delegate` state's `with: scope: "${context.sprint_name}"` passes that value into `auto-refine-and-implement` directly — this path never touches `cli/loop/run.py`'s positional-arg binding block at all, since it enters through sub-loop `with:` wiring, not a fresh `ll-loop run` invocation.

### Decision Rules
N/A — no new decision logic; the fix is a routing/binding correction (which context key an already-existing positional argument lands in), not a new gap kind, gate, or threshold.

## Implementation Steps

1. Add `input_key: scope` to `scripts/little_loops/loops/auto-refine-and-implement.yaml`.
2. Add a structural regression test asserting `input_key == "scope"` and that
   `required_inputs` stays unset (`TestAutoRefineAndImplementLoop`).
3. Fix the wrong invocation in `sprint-refine-and-implement.yaml`'s description
   (`'scope=<sprint-name|EPIC-NNN>'` → the positional form, now that it works).
4. Audit the remaining built-in loops for the same class of defect: any loop
   declaring a context knob it expects from the positional arg but no
   `input_key` (see Follow-up).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- Update `docs/guides/LOOPS_REFERENCE.md`'s `auto-refine-and-implement` "Required context variables" table (currently lists only `max_issues`, around line 937-941) to add a `scope` row with the `(populated from positional CLI arg via input_key: scope)` phrasing used by sibling entries (e.g. `sprint-refine-and-implement` at `:911-914`, `rn-plan`/`rn-refine`/`rn-stepwise`). This table was not touched by the in-tree fix and none of the existing four Implementation Steps cover it.

_Wiring pass added by `/ll:wire-issue`:_
- The same doc's "Invocation" code block for `auto-refine-and-implement` (lines 943-950) shows only the bare form and `--context max_issues=10` — it has no example of the positional-scope form (`ll-loop run auto-refine-and-implement EPIC-3041`) that this bug fixes. Add that example alongside the table-row fix so the doc actually demonstrates the newly-working invocation. [Agent 2 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add an end-to-end behavioral test in `scripts/tests/test_ll_loop_commands.py` that invokes the real `main_loop()` CLI entry with `ll-loop run --dry-run auto-refine-and-implement EPIC-3041` and asserts `scope: 'EPIC-3041'` appears in the dry-run `Context:` stdout block — closing the structural-only gap the issue itself flags in its Tests subsection.
- Add the missing positional-scope invocation example to `docs/guides/LOOPS_REFERENCE.md`'s "Invocation" code block for `auto-refine-and-implement`, not just the table row.

## Follow-up

Two adjacent hardening items, deliberately out of scope here:

- **Class-wide lint.** `ll-loop validate` cannot currently detect
  "declares a knob but binds the positional arg elsewhere." A rule flagging
  loops whose `context:` has exactly one obvious scalar knob while `input_key`
  is left at the default would catch this shape generally, in the spirit of
  BUG-3107's `no-scope` warning.
- **Timeout reporting.** The same run also surfaced that a `timeout`
  termination prints `Loop completed: <state>` plus a *stale* `Failure reason`
  from an unrelated earlier state (`cli/loop/_helpers.py:1868-1884`), and skips
  `finalize` so no `summary.json` is written for a run that closed 11 issues.

## Impact

- **Severity**: high — burns hours of wall clock and real API spend on the wrong
  work, with no error signal. Also silently bypasses epic-branch isolation, so
  commits intended for an integration branch land on the base branch instead.
- **Blast radius**: one YAML line plus one test; the alias loop and the
  backlog-ranking mode are both unaffected.

## Status

open


## Session Log
- `/ll:manage-issue` - 2026-08-09T01:11:39 - `2c1d7c76-6c59-4873-a2b3-cbd3c6d7ab5a.jsonl`
- `/ll:confidence-check` - 2026-08-08T17:26:47 - `0746a600-67e0-4eeb-88c7-015609fa694e.jsonl`
- `/ll:wire-issue` - 2026-08-08T17:19:22 - `422e30b6-5b50-4f9d-ab32-5ca05586e8ad.jsonl`
- `/ll:refine-issue` - 2026-08-08T17:11:15 - `73ca0bfa-eade-4557-92e6-107ab4dcd85a.jsonl`
