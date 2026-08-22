---
id: ENH-3292
type: ENH
title: 'dead-code-cleanup.yaml hardcodes this repo''s scope: ["scripts/"]'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-22'
captured_at: '2026-08-22T19:53:19Z'
labels:
- loops
- gate
- hardcode
- follow-up
relates_to:
- ENH-3281
decision_needed: false
---

# ENH-3292: dead-code-cleanup.yaml hardcodes this repo's scope: ["scripts/"]

## Summary

`dead-code-cleanup.yaml:8-9` ships `scope: ["scripts/"]` — a this-repo layout default
baked into a generic built-in loop. `scripts/` is this repo's own source directory
(`.claude/CLAUDE.md` § Key Directories); any consuming project without a top-level
`scripts/` directory gets a loop that scopes itself to a path that doesn't exist.

## Current Behavior

`scripts/little_loops/loops/dead-code-cleanup.yaml` declares a hardcoded
`scope: ["scripts/"]` at the top level, guessing this repo's own layout rather than
deriving a project-appropriate scope or defaulting to an empty/override slot.

## Expected Behavior

`dead-code-cleanup.yaml`'s `scope:` should not hardcode `scripts/`. Resolve via a
context-first default (empty override slot) or another project-layout-agnostic
mechanism, consistent with how `context.test_cmd`/`context.lint_cmd` are resolved
elsewhere in the built-in loop corpus (BUG-3276, ENH-3277, ENH-3281).

## Motivation

Flagged during ENH-3281 (generalize the this-repo-hardcode gate across all built-in
loops). `scope:` list entries are deliberately **out of scope** for that gate — they
are not exec-time content in the same sense as a state's `action` body or a top-level
`context:` default (see ENH-3281 § Program Design → Decision Rules) — so this instance
was never caught and needed its own follow-up rather than silently expanding that
gate's scope. ENH-3281 Implementation Step 5 requires this capture.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-22 — based on codebase analysis:_

**Option A**: Change `dead-code-cleanup.yaml:9` from `scope: ["scripts/"]` to `scope: ["."]`. This matches the explicit repo-wide opt-in already shipping in the two sibling `category: code-quality` loops (`incremental-refactor.yaml:6`, `test-coverage-improvement.yaml:16`), requires no new mechanism, is a one-line change, and satisfies `test_all_have_scope_field` (`test_builtin_loops.py:139-158`) without any exemption. Tradeoff: the concurrency lock is whole-repo-tree-grained rather than subdirectory-grained — but that is the already-accepted tradeoff for both sibling loops in this same category.

> **Selected:** Option A — one-line change to `scope: ["."]` matches the convention already used verbatim by 19 built-in loops (including both cited code-quality siblings) with zero test friction, versus Option B's new, partially-specified cross-cutting infrastructure.

**Option B**: Introduce a Python-side context-seeding step (mirroring `seed_confidence_thresholds()`/`inject_design_context()`, `cli/loop/_helpers.py:1368-1430`) that populates `context.src_dir` from `BRConfig.project.src_dir` before `resolve_scope()` runs, wired into both `run.py:cmd_run()` (before line 363) and `_helpers.py:run_background()` (before line 1590), then change `scope:` to `["${context.src_dir}"]`. This resolves the value from `.ll/ll-config.json` per-project rather than hardcoding `"."`, but requires new cross-cutting infrastructure with no existing precedent for a user-context-sourced (non-`run_dir`) value inside any built-in loop's `scope:`, and duplicate wiring into two call sites to stay consistent between foreground and background pre-flight scope resolution.

**Recommended**: Option A — it is the minimal in-scope fix (per this issue's own Scope Boundaries, which explicitly exclude broader mechanism work), backed by two loops already shipping the identical value in the same loop category, and requires no new code path. Option B builds general-purpose infrastructure for a single call site with no other current consumer.

### Decision Rationale

**Selected**: Option A — change `scope: ["scripts/"]` to `scope: ["."]`.

**Reasoning**: Option A is a drop-in, precedent-consistent one-line change with zero test-compatibility friction. Nineteen built-in loops (including both cited `category: code-quality` siblings, `incremental-refactor.yaml` and `test-coverage-improvement.yaml`) already ship `scope: ["."]` verbatim, and no test in `test_builtin_loops.py` pins `dead-code-cleanup`'s current `["scripts/"]` value. Option B, while structurally modeled on the existing `seed_confidence_thresholds()`/`inject_design_context()` seed-function pattern, would introduce a genuinely new class of usage — no existing built-in loop currently resolves `scope:` from a config-sourced (non-`run_dir`) context key — and undercounts its own wiring surface: a third `resolve_scope()` call site at `info.py:1551` is unaddressed, and `_helpers.py:1590` targets a separately-built `scope_context` dict rather than `fsm.context` directly, so the two named call sites aren't a drop-in identical edit.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A: `scope: ["."]` | 3 | 3 | 3 | 3 | **12/12** |
| B: context-seeded `scope: ["${context.src_dir}"]` | 2 | 1 | 1 | 1 | 5/12 |

**Key evidence**:
- `scope: ["."]` is used verbatim by 19 built-in loops, including 5 other `category: code-quality` loops beyond the two cited siblings (`fix-quality-and-tests.yaml`, `evaluation-quality.yaml`, `worktree-health.yaml`, `rubric-refine.yaml`, plus the two named).
- No test in `scripts/tests/test_builtin_loops.py` asserts `dead-code-cleanup`'s scope value — a repo-wide grep for the literal `"scripts/"` in that file returns zero matches.
- `resolve_scope()` (`fsm/concurrency.py:35`) only substitutes `${context.<var>}`; no built-in loop currently sources a `scope:` template var from `BRConfig`, so Option B would be a first-of-its-kind usage with a third, unaddressed call site (`info.py:1551`).

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-22 — based on codebase analysis:_

Findings below trace `scope:` from the loop file through `resolve_scope()` to its callers and the tests that constrain valid values.

### Files to Modify
- `scripts/little_loops/loops/dead-code-cleanup.yaml:8-9` — the hardcoded `scope: ["scripts/"]` to change

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/concurrency.py:35-53` — `resolve_scope(scope, context)` substitutes `${context.<var>}` templates in `scope:` paths; unresolved template vars pass through as literal strings
- `scripts/little_loops/cli/loop/run.py:363` — `scope = resolve_scope(fsm.scope or ["."], fsm.context)`, called inside `cmd_run()` before `PersistentExecutor` is constructed (`run.py:573`) or any state runs (`run_foreground` at `run.py:593`) — i.e. scope is resolved strictly pre-execution
- `scripts/little_loops/cli/loop/_helpers.py:1590` — same `resolve_scope(fsm.scope or ["."], scope_context)` call inside `run_background()`'s pre-flight conflict check, using a locally rebuilt `scope_context` (`_helpers.py:1586-1589`), not the same `fsm.context` mutated in `run.py`
- `scripts/little_loops/cli/loop/info.py:1551` (`cmd_show`) — same call, for `ll-loop show`'s effective-scope display
- `scripts/little_loops/fsm/validation/structural_rules.py:1226` — `_validate_missing_scope()` (BUG-3107): emits a WARNING when `fsm.scope` is falsy, explicitly instructing loop authors to add `scope: ["."]` as the "explicit repo-wide opt-in" rather than relying on the `fsm.scope or ["."]` runtime fallback silently
- `scripts/tests/test_builtin_loops.py:139-158` — `TestBuiltinLoopFiles.test_all_have_scope_field`: asserts `fsm.scope` is truthy and produces no scope warning for every built-in loop except an explicit `_SCOPE_EXEMPT_STEMS` allowlist (`:125-137`, 11 `oracles/*` files). `dead-code-cleanup` is not on that allowlist — an empty/omitted `scope:` would fail this test.
- `scripts/tests/test_builtin_loop_hardcode_gate.py:13-20` — module docstring explicitly excludes `scope:` list entries from its hardcode scan and names this exact issue as the follow-up that must cover it separately

### Conventions in Force
- Built-in loops declare `scope:` explicitly rather than relying on the `fsm.scope or ["."]` runtime fallback — evidence: `_validate_missing_scope()` (`structural_rules.py:1226`) and `test_all_have_scope_field` (`test_builtin_loops.py:139-158`) both treat an implicit/omitted `scope:` as a defect for non-exempt built-in loops
- `scope: ["."]` is the established, currently-shipping literal for whole-project-scoped code-quality loops with no knowable-in-advance write footprint — evidence: `scripts/little_loops/loops/incremental-refactor.yaml:6` and `scripts/little_loops/loops/test-coverage-improvement.yaml:16`, both `category: code-quality` siblings of `dead-code-cleanup.yaml`
- Every `${context.<var>}` template appearing in any built-in loop's top-level `scope:` resolves `${context.run_dir}` — an executor-injected value (`scripts/little_loops/fsm/executor.py:902-903,978-980`), never a user-declared `context:` block default. No existing loop resolves `scope:` from a config-sourced context key.
- The `context.test_cmd`/`context.lint_cmd` config-first pattern (bare `ll-config get project.test_cmd` at `dead-code-cleanup.yaml:32,126`, or `if [ -n "${context.test_cmd}" ]` else `ll-config get` elsewhere) is a **bash-local, single-state** mechanism: `${context.test_cmd}` is interpolated by the FSM action-string engine when that specific state's action runs, and `ll-config get` executes as a live shell subprocess at that same moment — both strictly after scope has already been resolved and the concurrency lock already acquired (`run.py:371-373`). This mechanism cannot populate a `${context.<var>}` used inside `scope:`, since `resolve_scope()` runs once against the pre-assembled `fsm.context` dict before any state — including `check_preconditions` — exists to run a shell command.
- `project.src_dir` (`config-schema.json:20-24`, default `"src/"`) is never read via a shell-level `ll-config get project.src_dir` call in the loop corpus; its only usage under `scripts/little_loops/loops/` is a Python `ll_cfg.project.src_dir` attribute read inside an embedded Python heredoc in `auto-refine-and-implement.yaml:492,683`, unrelated to `scope:` resolution.

### Tests
- No existing test asserts `dead-code-cleanup.yaml`'s `scope:` value (confirmed by absence — no `test_scope_declared`-style method exists for it in `TestDeadCodeCleanupLoop`, `test_builtin_loops.py:12042`)
- Sibling per-loop `test_scope_declared` methods show the established assertion shape (membership check against the parsed `scope:` list) — e.g. `test_builtin_loops.py:1352` (issue-refinement), `:2967` (refine-to-ready-issue), `:8215` (autodev, `test_scope_field_uses_run_dir_template`), `:8664` (recursive-refine)
- `scripts/tests/test_concurrency.py:1058` — `TestResolveScope` covers `resolve_scope()`'s template-substitution behavior directly (static passthrough, context-var substitution, unresolved-var preservation)

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-22 — based on codebase analysis:_

No new type is introduced; the change is a value swap inside the existing `FSMLoop.scope` field.

### Types
- N/A — no new data shape; this is a single scalar value change (a string literal) inside an existing `list[str]` field

### Signatures
- `FSMLoop.scope: list[str] = field(default_factory=list)` — `scripts/little_loops/fsm/schema.py:1307`; the field being changed, falsy (empty/omitted) is disallowed for built-in loops by `test_all_have_scope_field`
- `resolve_scope(scope: list[str], context: dict[str, Any]) -> list[str]` — `scripts/little_loops/fsm/concurrency.py:35`; substitutes `${context.<var>}` templates against `context`, a static string (no template) passes through unchanged

### Call Path
`ll-loop run` (`cli/loop/run.py:cmd_run`) → `load_and_validate(path)` parses `dead-code-cleanup.yaml`'s `scope:` into `FSMLoop.scope` → `resolve_scope(fsm.scope or ["."], fsm.context)` (`run.py:363`) → `LockManager.acquire(fsm.name, scope, ...)` (`run.py:371-373`) — all of this happens before `PersistentExecutor` is constructed (`run.py:573`) or any state (including `check_preconditions`) executes (`run.py:593`). The parallel pre-flight path is `run_background()` → `resolve_scope(fsm.scope or ["."], scope_context)` (`_helpers.py:1590`).

### Decision Rules
N/A — no new decision logic, gate, or threshold is introduced; this changes an existing static configuration value.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Scope Boundaries

**In scope**: fixing `dead-code-cleanup.yaml`'s `scope: ["scripts/"]` hardcode.

**Out of scope**: widening ENH-3281's hardcode gate to cover `scope:` entries —
already considered and rejected there (`scope:` entries are not exec-time content).

## Related Key Documentation

- ENH-3281 — generalize the this-repo-hardcode gate; flagged this instance as
  out-of-scope-but-must-capture in its Known Instance section and Implementation Step 5
- BUG-3276 — the original single-loop this-repo-hardcode defect (a different loop,
  `incremental-refactor.yaml`, and a different surface, `context.test_cmd`)

## Status

**Open** | Created: 2026-08-22 | Priority: P3


## Session Log
- `/ll:decide-issue` - 2026-08-22T20:38:21 - `8a3822be-71d1-4b6b-bf90-c7a7081d28ae.jsonl`
- `/ll:refine-issue` - 2026-08-22T20:30:18 - `bc6653b6-fcc0-4790-89ae-8782900fae6c.jsonl`
