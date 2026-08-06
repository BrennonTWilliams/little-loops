---
id: BUG-3087
type: BUG
title: Scope the issue-lifecycle loops so they stop locking the repo root
priority: P2
status: done
parent: BUG-3083
captured_at: '2026-08-06T16:17:02Z'
completed_at: '2026-08-06T19:00:41Z'
discovered_date: 2026-08-06
discovered_by: capture-issue
labels:
- fsm-concurrency
- learning-gate
- ll-auto
- loop-authoring
relates_to:
- BUG-2864
- BUG-3083
- BUG-3088
verify_verdict: VALID
confidence_score: 95
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# BUG-3087: Scope the issue-lifecycle loops so they stop locking the repo root

## Summary

This is the minimum fix half of BUG-3083 ("Unscoped issue-management loops
lock the whole repo, false-conflicting every narrowly-scoped loop"). A loop
YAML that omits `scope:` acquires a lock on the repository root
(`run.py:363` — `resolve_scope(fsm.scope or ["."], fsm.context)`). Because
`_paths_overlap()` treats "one path contains the other" as an overlap
(`concurrency.py:398-415`), a repo-root lock conflicts with *every* other
loop regardless of how narrowly that loop scoped itself.

`refine-to-ready-issue.yaml` declares no `scope:`, and it is the loop most
likely to run concurrently with `ll-auto` — the two are halves of the same
backlog workflow (refine to ready → implement). This issue gives it, and the
other issue-lifecycle loops, real scopes. It does **not** address the
broader "stop silently defaulting to `["."]`" policy question — see
[[BUG-3088]] for that.

## Parent Issue

Decomposed from [BUG-3083](P2-BUG-3083-unscoped-loops-lock-whole-repo-false-gate-conflicts.md):
Unscoped issue-management loops lock the whole repo, false-conflicting every
narrowly-scoped loop.

## Steps to Reproduce

1. In one shell: `ll-loop run refine-to-ready-issue --context issue_file=<any issue>`
   and leave it running (it declares no `scope:`, so it locks `.`).
2. In a second shell: run `ll-auto --only <ID>` on an issue that has
   `learning_tests_required` in its frontmatter (so the learning gate actually
   fires — `issue_manager.py:1105-1112`).
3. Observe the gate subprocess exit 1 with
   `Scope conflict with running loop: refine-to-ready-issue` /
   `Conflicting scope: ['<repo root>']`, and `ll-auto` report
   `IMPLEMENT_FAILED <ID>` without attempting implementation.

## Root Cause

`refine-to-ready-issue.yaml` has no `scope:` key, and it is the loop most
likely to run concurrently with `ll-auto`. With no explicit `scope:`,
`cmd_run()` (`run.py:363`) falls back to `["."]`, so it locks the entire
repo root and conflicts with any other concurrent loop.

Audit against `grep -l '^scope:' scripts/little_loops/loops/*.yaml` (per
BUG-3083's Codebase Research Findings) confirms six issue-lifecycle loops
currently lack `scope:`: `refine-to-ready-issue.yaml`,
`issue-refinement.yaml`, `issue-staleness-review.yaml`,
`recursive-refine.yaml`, `auto-refine-and-implement.yaml`,
`issue-discovery-triage.yaml`.

## Current Behavior

Any of the six named issue-lifecycle loops blocks all concurrent loops
repo-wide, even loops that touch entirely disjoint files.

## Expected Behavior

Each of the six issue-lifecycle loops declares a real, narrow `scope:`
covering only `.issues/` plus its own run dir, so it no longer conflicts
with unrelated concurrent loops.

## Proposed Solution

Give the issue-lifecycle loops real scopes. They operate on `.issues/` plus
their own run dir, not the whole repo:

```yaml
scope:
  - ".issues/"
  - "${context.run_dir}"
```

Apply this to all six loops confirmed scope-less:
`refine-to-ready-issue.yaml`, `issue-refinement.yaml`,
`issue-staleness-review.yaml`, `recursive-refine.yaml`,
`auto-refine-and-implement.yaml`, `issue-discovery-triage.yaml`.

Note (from BUG-3083's refinement pass): no existing loop declares `.issues/`
in its scope today — the closest precedent (`autodev.yaml`,
`prompt-across-issues.yaml`, `ready-to-implement-gate.yaml`,
`proof-first-task.yaml`, `dead-code-cleanup.yaml`) uses
`scope: ["${context.run_dir}"]` alone. Adding `.issues/` is a new scope
shape here and should be justified on its own: these loops read/write issue
files outside their own run_dir, which `${context.run_dir}`-only scoping
would not cover.

## Integration Map

| File | Anchor | Change |
|------|--------|--------|
| `scripts/little_loops/loops/refine-to-ready-issue.yaml` | top-level keys | Add `scope:` |
| `scripts/little_loops/loops/issue-refinement.yaml` | top-level keys | Add `scope:` |
| `scripts/little_loops/loops/issue-staleness-review.yaml` | top-level keys | Add `scope:` |
| `scripts/little_loops/loops/recursive-refine.yaml` | top-level keys | Add `scope:` |
| `scripts/little_loops/loops/auto-refine-and-implement.yaml` | top-level keys | Add `scope:` |
| `scripts/little_loops/loops/issue-discovery-triage.yaml` | top-level keys | Add `scope:` |
| `scripts/little_loops/learning_tests/gate.py` | lines 127-133 | Update stale inline comment once `refine-to-ready-issue.yaml` is scoped |
| `scripts/little_loops/loops/README.md` | lines 28-34 | Document the issue-lifecycle loops' scope rationale alongside `autodev`'s |

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — § "Scope-Based Concurrency" (lines 786-816) is the primary reference doc explaining the `scope:` field; its only examples today are `["src/", "tests/"]` and `["${context.run_dir}"]` alone. Since `.issues/` + `${context.run_dir}` combined is a new scope shape (per this issue's own Codebase Research Findings), consider adding it as a second worked example here so the fixed-directory-plus-run_dir pattern has a canonical reference alongside the `loops/README.md` autodev-row precedent. [Agent 2 finding]

### Tests

- `scripts/tests/test_concurrency.py::TestMultiInstanceSameName` — new pair
  `test_refine_to_ready_issue_with_run_dir_scopes_both_acquire_concurrently` /
  `test_refine_to_ready_issue_with_dot_scope_still_conflicts`, mirroring the
  existing `autodev`/`ready-to-implement-gate` pairs at lines 605-667/669-730
  exactly (real `LockManager(tmp_loops)`, two `threading.Thread`s +
  `threading.Barrier(2)`).
- `scripts/tests/test_builtin_loops.py` — add `test_scope_declared` to:
  `TestRefineToReadyIssueSubLoop` (line 1242), `TestIssueRefinementSubLoop`
  (line 1144), `TestIssueStalenessReviewLoop` (line 10534),
  `TestRecursiveRefineLoop` (line 7085), `TestAutoRefineAndImplementLoop`
  (line 2867). `issue-discovery-triage.yaml` has no dedicated test class yet
  (only a string entry in `TestBuiltinLoopFiles.test_expected_loops_exist`,
  line 125) — add a new small class for it.

  _Wiring pass added by `/ll:wire-issue`:_ all four existing `scope`-declared
  precedents (`TestPromptAcrossIssuesLoop.test_scope_declared` line 2837,
  `TestReadyToImplementGateLoop.test_scope_declared` line 9713,
  `TestProofFirstTaskLoop.test_scope_declared` line 9938,
  `test_scope_field_uses_run_dir_template` for autodev line 7014) assert only
  a **single** `"${context.run_dir}" in scope` membership check. Because this
  fix's `scope:` is two entries (`[".issues/", "${context.run_dir}"]`), the
  six new `test_scope_declared` tests must assert **both** memberships
  (`".issues/" in scope` and `"${context.run_dir}" in scope`) — there is no
  existing precedent for a compound-scope assertion, so don't copy the
  single-path shape verbatim. [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- **Naming collision in `auto-refine-and-implement.yaml`**: this loop's `context:` block (line 63) already declares a context variable named `scope: ""` (sprint name or `EPIC-NNN`, used elsewhere in the loop body as `${context.scope}` for `SprintManager`/epic-branch resolution). Adding a top-level FSM `scope:` key is a structurally distinct YAML path (document-root `scope:` vs. `context.scope`) and does not conflict on parse, but an implementer editing this file must add the lock-scope key at the document root, not inside the existing `context:` block, and should not confuse the two when reading/editing.
- **`.issues/` is a new scope shape**: confirmed by codebase-pattern-finder — no loop YAML under `scripts/little_loops/loops/` (including `oracles/`) currently declares `.issues/` or any subpath inside a top-level `scope:` list. `.issues/` appears elsewhere only as a path used inside shell/prompt actions, never as a lock-scope entry. The two existing fixed-directory precedents are `dead-code-cleanup.yaml:8-9` (`scope: ["scripts/"]`) and `docs-sync.yaml:10-12` (`scope: ["docs/", "*.md"]`, the only existing multi-entry example combining a directory and a glob) — these establish that fixed-directory (non-`run_dir`) scopes are an accepted pattern, just not yet applied to `.issues/`.
- **Existing `test_scope_declared` shape to copy** (`scripts/tests/test_builtin_loops.py`): three near-identical instances already assert `scope` is a non-`None` list containing `"${context.run_dir}"` — `TestPromptAcrossIssuesLoop` (line 2837, cites ENH-2500), `TestReadyToImplementGateLoop` (line 9713, cites BUG-2864), `TestProofFirstTaskLoop` (line 9938, cites BUG-2864); a differently-named but identical-bodied variant is `test_scope_field_uses_run_dir_template` for `autodev` (line 7014, cites FEAT-1789). None of these assert `scope` contains *only* `${context.run_dir}` — a multi-entry list containing it plus `.issues/` still satisfies the pattern's `in scope` check.
- **`loops/README.md` scope-rationale convention**: only one row (the `autodev` entry, line 34) documents its scope choice in prose, inline in the description cell: `"Uses per-instance ${context.run_dir} for temp files and scope: ["${context.run_dir}"] to allow concurrent instances with disjoint issue sets."` No dedicated "why this scope" subsection exists; other scoped loops (`dead-code-cleanup`, `docs-sync`, `ready-to-implement-gate`, `proof-first-task`, `prompt-across-issues`) don't explain scope in the README at all — rationale for those lives only in YAML-file comments and test docstrings. A new entry for the issue-lifecycle loops should follow the `autodev` row's inline-prose convention rather than inventing a new subsection.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Types
- No new types. `scope` is an existing field: `scope: list[str] = field(default_factory=list)` (`scripts/little_loops/fsm/schema.py:1278`).

### Signatures
- `resolve_scope(scope: list[str], context: dict[str, Any]) -> list[str]` — `scripts/little_loops/fsm/concurrency.py:35-53`. Substitutes `${context.<var>}` templates via `_CONTEXT_VAR_RE`; a literal non-templated entry (e.g. `.issues/`) passes through unchanged.
- `LockManager.acquire(self, loop_name: str, scope: list[str], instance_id: str | None = None, *, singleton: bool = False) -> bool` — `concurrency.py:142-200`. Normalizes each scope path via `_normalize_path` (`Path(path).resolve()`, lines 425-427) before checking `find_conflict()`.
- `LockManager.find_conflict(self, scope: list[str], *, caller_loop_name: str | None = None, caller_singleton: bool = False) -> ScopeLock | None` — `concurrency.py:212-291`. Compares the candidate's normalized scope against every live lock's normalized scope via `_scopes_overlap()`.
- `LockManager._paths_overlap(self, path1: str, path2: str) -> bool` — `concurrency.py:398-423`. Exact-match or `Path.relative_to()` containment in either direction; both inputs must already be normalized absolute-path strings.

### Call Path
`ll-loop run` (`scripts/little_loops/cli/loop/run.py:363`, and the background pre-flight check at `scripts/little_loops/cli/loop/_helpers.py:1552`) both call `resolve_scope(fsm.scope or ["."], fsm.context)` -> `LockManager.acquire(fsm.name, scope, instance_id=instance_id, singleton=fsm.singleton)` -> `LockManager.find_conflict(scope, ...)` -> `_scopes_overlap()` -> `_paths_overlap()`. On conflict, `run.py:428` / `_helpers.py:1559` surface `"Scope conflict with running loop: <name>"` and the run aborts (or queues, if `--queue`). `context.run_dir` is guaranteed present before scope resolution — `run.py:197` injects it unconditionally if absent — so `${context.run_dir}` template entries always resolve.

### Decision Rules
N/A — no new decision logic. This issue only changes the declared `scope:` value in six existing loop YAML files; it does not add a new gap kind, gate, threshold, or classification rule. `resolve_scope`/`LockManager` behavior is unchanged.

## Implementation Steps

1. Audit the six named issue-lifecycle loops and confirm each is safe to
   scope to `.issues/` + `${context.run_dir}` (i.e. they don't touch files
   outside those paths).
2. Add `scope:` to all six loops.
3. Add the regression test pair in `test_concurrency.py` asserting
   `refine-to-ready-issue` and `ready-to-implement-gate` can hold locks
   simultaneously once scoped.
4. Add `test_scope_declared` to each affected loop's test class (new class
   for `issue-discovery-triage.yaml`).
5. Update the stale inline comment in `learning_tests/gate.py` (lines
   127-133) and the rationale note in `loops/README.md`.

## Impact

- **Severity**: silent, non-deterministic loss of automated work. ENH-3073
  was marked `IMPLEMENT_FAILED` with no implementation attempted, and the
  failure reason surfaced as "implementation failed" — actively misleading.
- **Blast radius**: any concurrent `ll-auto` + refine workflow. Only issues
  carrying `learning_tests_required` hit the gate, so it presents as an
  intermittent, issue-specific failure rather than an obvious concurrency
  bug.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM concurrency / scope-lock design |
| `.claude/CLAUDE.md` § Loop Authoring | Where a `scope:` authoring rule would live |

---

## Resolution

- **Action**: fix
- **Completed**: 2026-08-06
- **Status**: Completed

### Changes Made
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`: added `scope: [".issues/", "${context.run_dir}"]`
- `scripts/little_loops/loops/issue-refinement.yaml`: added `scope: [".issues/", "${context.run_dir}"]`
- `scripts/little_loops/loops/issue-staleness-review.yaml`: added `scope: [".issues/", "${context.run_dir}"]`
- `scripts/little_loops/loops/recursive-refine.yaml`: added `scope: [".issues/", "${context.run_dir}"]`
- `scripts/little_loops/loops/auto-refine-and-implement.yaml`: added `scope: [".issues/", "${context.run_dir}"]` (top-level lock scope, distinct from the pre-existing `context.scope` variable)
- `scripts/little_loops/loops/issue-discovery-triage.yaml`: added `scope: [".issues/", "${context.run_dir}"]`
- `scripts/little_loops/learning_tests/gate.py`: updated the stale inline comment (lines ~122-133) to reflect that `refine-to-ready-issue` is now scoped, not repo-root
- `scripts/little_loops/loops/README.md`: added scope-rationale prose to each of the six issue-lifecycle loop rows, following the `autodev` row's inline-prose convention
- `scripts/tests/test_concurrency.py`: added `test_refine_to_ready_issue_instances_still_conflict_on_shared_issues_scope`, `test_refine_to_ready_issue_with_dot_scope_still_conflicts`, and `test_refine_to_ready_issue_and_ready_to_implement_gate_acquire_simultaneously` to `TestMultiInstanceSameName`
- `scripts/tests/test_builtin_loops.py`: added `test_scope_declared` to `TestIssueRefinementSubLoop`, `TestRefineToReadyIssueSubLoop`, `TestAutoRefineAndImplementLoop`, `TestRecursiveRefineLoop`, `TestIssueStalenessReviewLoop`, and a new `TestIssueDiscoveryTriageLoop` class

### Verification Results
- Tests: PASS (`python -m pytest scripts/tests/` — 1505+ passed)
- Lint: PASS (`ruff check` on touched files)
- Loop validation: PASS (`ll-loop validate` on all six loops — pre-existing warnings unrelated to this change)

## Status

open


## Session Log
- `/ll:manage-issue` - 2026-08-06T19:00:35 - `74391729-5d5f-4f39-800d-29d2ce941af3.jsonl`
- `/ll:ready-issue` - 2026-08-06T18:28:32 - `e4e3d836-0f5a-404f-86b4-472963d98a40.jsonl`
- `/ll:confidence-check` - 2026-08-06T18:26:15 - `c6f9506d-468c-4c3e-a502-42686a1640e3.jsonl`
- `/ll:verify-issues` - 2026-08-06T18:23:51 - `b120f4f0-cbf0-49c0-9986-80a6f8eaddbd.jsonl`
- `/ll:verify-issues` - 2026-08-06T17:18:54 - `a5dc412a-dfaf-48c4-97ff-e79aaf559ba8.jsonl`
- `/ll:wire-issue` - 2026-08-06T17:16:55 - `52d0c931-e024-4921-8fa9-d5d15e1b5612.jsonl`
- `/ll:refine-issue` - 2026-08-06T17:08:02 - `605e232f-8b33-4cb7-9b5e-758db1444177.jsonl`
- `/ll:issue-size-review` - 2026-08-06T16:59:24 - `23212449-a121-4dca-9bc5-bc0a0164c75f.jsonl`
