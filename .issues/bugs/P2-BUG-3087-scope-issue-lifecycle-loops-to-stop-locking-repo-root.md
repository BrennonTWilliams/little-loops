---
id: BUG-3087
type: BUG
title: Scope the issue-lifecycle loops so they stop locking the repo root
priority: P2
status: open
parent: BUG-3083
captured_at: '2026-08-06T16:17:02Z'
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

### Dependent Files (Callers/Importers)

_Wiring pass (second) added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml:385` — invokes `loop: refine-to-ready-issue` as a sub-loop. `_execute_sub_loop` (`fsm/executor.py:820`) never resolves/acquires a lock for the nested `loop:` call itself, so narrowing `refine-to-ready-issue`'s own top-level `scope:` does not change `autodev`'s existing lock behavior — informational only, no code change required here. [Agent 1 finding, confirmed by direct grep]
- `scripts/little_loops/loops/rn-build.yaml:477` and `scripts/little_loops/loops/sprint-build-and-validate.yaml:80,163` — invoke `loop: recursive-refine` as a sub-loop. Same no-lock-extension caveat as above applies. [Agent 1 finding, confirmed]
- `scripts/little_loops/loops/scan-and-implement.yaml:32` — invokes `loop: issue-discovery-triage` as a sub-loop. Same caveat applies. [Agent 1 finding, confirmed]
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml:26` — invokes `loop: auto-refine-and-implement` as a sub-loop. Same caveat applies. [Agent 1 finding, confirmed]
- `scripts/little_loops/loops/eval-driven-development.yaml:125` — invokes `loop: issue-refinement` as a sub-loop. Same caveat applies. [Agent 1 finding, confirmed]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — § "Scope-Based Concurrency" (lines 786-816) is the primary reference doc explaining the `scope:` field; its only examples today are `["src/", "tests/"]` and `["${context.run_dir}"]` alone. Since `.issues/` + `${context.run_dir}` combined is a new scope shape (per this issue's own Codebase Research Findings), consider adding it as a second worked example here so the fixed-directory-plus-run_dir pattern has a canonical reference alongside the `loops/README.md` autodev-row precedent. [Agent 2 finding]

_Wiring pass (second) added by `/ll:wire-issue`:_
- `scripts/tests/test_learning_tests_gate.py:266` — `test_invocation_passes_queue_flag`'s docstring narrates: "ENH-3073 follow-up: --queue lets ready-to-implement-gate wait out a scope-lock held by an unrelated concurrently running loop (e.g. refine-to-ready-issue, which locks the whole repo)...". This is a second, independent copy of the same stale claim as the `learning_tests/gate.py` inline comment already in this Integration Map — the test body only asserts `"--queue" in cmd` so nothing breaks functionally, but the docstring should be updated alongside the `gate.py` comment so it doesn't keep citing "locks the whole repo" once this fix ships. [Agent 2 + Agent 3 finding, independently confirmed by both]

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

  _Wiring pass (second) added by `/ll:wire-issue`:_ for the new
  `issue-discovery-triage.yaml` test class, `TestBacklogFlowOptimizerLoop`
  (`scripts/tests/test_builtin_loops.py:10508-10531`) is the smallest
  existing structural-test class in the file (`LOOP_FILE` + `data` fixture +
  `test_required_top_level_fields`/`test_required_states_exist` style
  assertions) and the closest template to copy — `issue-discovery-triage.yaml`
  has `initial: count_baseline`. At the `resolve_scope()` unit level (not
  loop-YAML level), `scripts/tests/test_concurrency.py::TestResolveScope::
  test_mixed_static_and_template` (lines 951-955) already generically
  exercises one literal path + one template path in the same scope list,
  confirming the mechanism works — it just hasn't been exercised against a
  real loop YAML with `.issues/` + `${context.run_dir}` specifically, which
  is what the new `test_scope_declared` tests supply. No existing test
  asserts the *absence* of `scope` for any of the six loops, so adding
  `scope:` breaks nothing. [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- **Naming collision in `auto-refine-and-implement.yaml`**: this loop's `context:` block (line 63) already declares a context variable named `scope: ""` (sprint name or `EPIC-NNN`, used elsewhere in the loop body as `${context.scope}` for `SprintManager`/epic-branch resolution). Adding a top-level FSM `scope:` key is a structurally distinct YAML path (document-root `scope:` vs. `context.scope`) and does not conflict on parse, but an implementer editing this file must add the lock-scope key at the document root, not inside the existing `context:` block, and should not confuse the two when reading/editing.
- **`.issues/` is a new scope shape**: confirmed by codebase-pattern-finder — no loop YAML under `scripts/little_loops/loops/` (including `oracles/`) currently declares `.issues/` or any subpath inside a top-level `scope:` list. `.issues/` appears elsewhere only as a path used inside shell/prompt actions, never as a lock-scope entry. The two existing fixed-directory precedents are `dead-code-cleanup.yaml:8-9` (`scope: ["scripts/"]`) and `docs-sync.yaml:10-12` (`scope: ["docs/", "*.md"]`, the only existing multi-entry example combining a directory and a glob) — these establish that fixed-directory (non-`run_dir`) scopes are an accepted pattern, just not yet applied to `.issues/`.
- **Existing `test_scope_declared` shape to copy** (`scripts/tests/test_builtin_loops.py`): three near-identical instances already assert `scope` is a non-`None` list containing `"${context.run_dir}"` — `TestPromptAcrossIssuesLoop` (line 2837, cites ENH-2500), `TestReadyToImplementGateLoop` (line 9713, cites BUG-2864), `TestProofFirstTaskLoop` (line 9938, cites BUG-2864); a differently-named but identical-bodied variant is `test_scope_field_uses_run_dir_template` for `autodev` (line 7014, cites FEAT-1789). None of these assert `scope` contains *only* `${context.run_dir}` — a multi-entry list containing it plus `.issues/` still satisfies the pattern's `in scope` check.
- **`loops/README.md` scope-rationale convention**: only one row (the `autodev` entry, line 34) documents its scope choice in prose, inline in the description cell: `"Uses per-instance ${context.run_dir} for temp files and scope: ["${context.run_dir}"] to allow concurrent instances with disjoint issue sets."` No dedicated "why this scope" subsection exists; other scoped loops (`dead-code-cleanup`, `docs-sync`, `ready-to-implement-gate`, `proof-first-task`, `prompt-across-issues`) don't explain scope in the README at all — rationale for those lives only in YAML-file comments and test docstrings. A new entry for the issue-lifecycle loops should follow the `autodev` row's inline-prose convention rather than inventing a new subsection.

_Wiring pass (second) added by `/ll:wire-issue`:_
- **Prior decision precedent for this exact fix shape**: `.ll/decisions.yaml` entry `ARCHITECTURE-106` (issue ENH-2500, 2026-07-06) records the decision that migrated `prompt-across-issues` off a fixed `.loops/tmp/` path and declared `scope: ["${context.run_dir}"]` "so concurrent instances are isolated by LockManager" — the same lock-isolation rationale this issue applies to the six issue-lifecycle loops. No standing repo-wide policy exists ("all loops must declare non-repo-root scope by default"); each fix has been applied reactively per loop (ENH-2500, FEAT-1789 for `autodev`, this issue). [Agent 2 finding]
- **`cli/loop/info.py` scope display**: `cmd_show()` (lines ~1540-1541) already displays a loop's `scope:` field when present, so once these six loops declare `scope:`, `ll-loop show <name>` output changes for them automatically — informational only, no code change needed. `cmd_list()`'s JSON output does not include a scope field at all, so no JSON-consumer coupling exists. [Agent 1 finding]

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- **`learning_tests/gate.py` citation is stale**: the Integration Map's row for this file cites "lines 127-133" for the stale inline comment referencing unscoped issue-management loops. As of `c501c839 fix(learning-tests): forward configured queue-wait budget to gate subprocess` (already on `main`), that commit inserted a `BUG-3085` comment block plus `BRConfig`/`_queue_wait_budget` lines above the `cmd = [...]` list, pushing the target comment down. The comment now sits at **lines 137-142**, not 127-133.
- **`docs/guides/LOOPS_GUIDE.md` § "Scope-Based Concurrency" confirmed unchanged**: research-triage flagged this file as changed after the last refine pass, but the section content and line range (786-816) are unchanged — the file edit that triggered staleness touched an unrelated part of the document. No correction needed for that citation.
- **`auto-refine-and-implement.yaml` is not fully covered by "operate on `.issues/` plus their own run dir"**: unlike the other five loops, its `delegate` state runs `loop: autodev` in-process, which shells out to `ll-auto --only` (writes arbitrary source files repo-wide) and runs raw `git`/`worktree_utils` branch operations. `_execute_sub_loop` (`scripts/little_loops/fsm/executor.py:820`) never calls `LockManager`/`resolve_scope` for a nested `loop:` invocation, and `ll-auto` as a subprocess has no `LockManager` integration at all (`grep -rl LockManager` returns only `cli/loop/run.py`, `cli/loop/_helpers.py`, `fsm/concurrency.py`, `fsm/__init__.py`). Narrowing this loop's own top-level `scope:` is still correct and safe — its own action-level writes stay inside `.issues/` + run_dir — but it does not extend lock protection to the `autodev`/`ll-auto` work it delegates to, which was unprotected before this fix and remains so after. Worth a one-line callout in the loop's own YAML comment so a future reader doesn't assume the narrowed scope covers the delegated implementation work too.
- **Scope-shape catalog** (confirms the "new scope shape" claim with specifics): 7 existing loops declare top-level `scope:` — `autodev.yaml`, `ready-to-implement-gate.yaml`, `proof-first-task.yaml`, `prompt-across-issues.yaml` (Shape A: single `${context.run_dir}` template, each preceded by a bug-ID rationale comment), `rn-refine.yaml` (Shape B: single non-run_dir template, `${context.plan_file}`), `docs-sync.yaml` (Shape C: two fixed entries, `docs/` + `*.md`), `dead-code-cleanup.yaml` (Shape D: single fixed directory, `scripts/`). No `oracles/` loop declares `scope:`. No existing loop combines a fixed directory with a `${context.run_dir}` template in the same list — confirmed novel.
- **Test coverage gap among existing scope-declared loops**: only 4 of the 7 (`autodev`, `ready-to-implement-gate`, `proof-first-task`, `prompt-across-issues`) have a dedicated `test_scope_declared`-style test in `test_builtin_loops.py`; `rn-refine`, `docs-sync`, and `dead-code-cleanup` have no scope-specific test anywhere in the suite. The shared assertion shape (verbatim, ready-to-implement-gate variant) checks `scope is not None`, `isinstance(scope, list)`, and `"${context.run_dir}" in scope` — membership, not exact-list equality, so a compound list satisfies existing precedent's assertion style once extended to check both entries.

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
   > ⚠ Superseded — comment is now at lines 137-142, not 127-133; see § Codebase Research Findings under Integration Map

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

## Status

open


## Session Log
- `/ll:wire-issue` - 2026-08-06T18:21:59 - `b36d1b0a-2e6c-4d11-87b3-323eabb6bc31.jsonl`
- `/ll:refine-issue` - 2026-08-06T18:13:56 - `2714e173-0113-42e1-b8e8-e7f650c61db7.jsonl`
- `/ll:verify-issues` - 2026-08-06T17:18:54 - `a5dc412a-dfaf-48c4-97ff-e79aaf559ba8.jsonl`
- `/ll:wire-issue` - 2026-08-06T17:16:55 - `52d0c931-e024-4921-8fa9-d5d15e1b5612.jsonl`
- `/ll:refine-issue` - 2026-08-06T17:08:02 - `605e232f-8b33-4cb7-9b5e-758db1444177.jsonl`
- `/ll:issue-size-review` - 2026-08-06T16:59:24 - `23212449-a121-4dca-9bc5-bc0a0164c75f.jsonl`
