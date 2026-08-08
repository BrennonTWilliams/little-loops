---
id: BUG-3119
type: BUG
title: Document the `scope:` authoring convention, the `["."]` fallback, and the new
  no-scope lint
priority: P3
status: open
parent: BUG-3088
captured_at: '2026-08-08T00:00:00Z'
discovered_date: 2026-08-08
discovered_by: issue-size-review
reconcile_attempted: true
labels:
- loop-authoring
- documentation
relates_to:
- BUG-3088
- BUG-3107
confidence_score: 95
outcome_confidence: 82
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 25
---

# BUG-3108: Document the `scope:` authoring convention, the `["."]` fallback, and the new no-scope lint

## Summary

Documentation deliverable of [BUG-3088](P3-BUG-3088-audit-unscoped-loops-and-warn-on-missing-scope.md).
Several docs currently tell loop authors that omitting `scope:` is fine —
directly contradicting the new lint added in [[BUG-3107]] — and no doc
explains the `["."]` runtime fallback that makes the lint worth having.
Depends on [[BUG-3107]] landing first, since these docs describe that rule's
behavior and remedy message.

## Parent Issue

Decomposed from [BUG-3088](P3-BUG-3088-audit-unscoped-loops-and-warn-on-missing-scope.md):
Audit unscoped loops and warn at validate time when `scope:` is missing.

## Proposed Solution

- `skills/create-loop/reference.md:631` currently says "Most users can
  omit this field... Single-loop use cases do not require scope
  declaration." Rewrite to tell authors to always declare `scope:`, using
  `["."]` for genuinely repo-wide loops. (Line 575's existing "An empty
  `scope` (or omitting it) is treated as the whole project" text is accurate
  and should stay.)
- `skills/create-loop/loop-types.md:986` (reference table: `scope | list[str]
  | *(entire repo)* | ...`) and the four commented `scope:` template lines
  (159, 274, 388, 498: `# scope: ["src/"]  # Optional: declare paths...`) —
  un-comment the `scope:` line in each of the four templates and drop
  "Optional" from the comment, so scaffolded loops start lint-clean.
- `docs/guides/LOOPS_GUIDE.md:786-816,848-849` — "Scope-Based Concurrency"
  documents `scope:` mechanics but not the `["."]` default-when-absent
  behavior; the "Notes" bullet at line 849 ("Loops with non-overlapping
  scopes run concurrently") is inaccurate for any unscoped loop. Document the
  fallback explicitly and point at `scope: ["."]` as the way to declare
  repo-wide intent.
- `docs/development/TROUBLESHOOTING.md:812-827,1285` — existing "Scope
  conflict" entries describe stale-lock symptoms only, not the
  false-conflict-from-unscoped-loop mechanism. Add that mechanism.
- `docs/reference/CLI.md:789-812` — enumerates every `ll-loop validate`
  structural/meta-loop lint rule in a fixed format (severity, trigger,
  rationale, suppression flag). Add the new no-scope WARNING rule in the same
  format.
- `scripts/little_loops/fsm/fsm-loop-schema.json:30-35` — the `scope`
  property's `description` ("Paths this loop operates on (for concurrency
  control)") does not mention the new validate-time nudge; update it to stay
  in sync with the lint message.
- `docs/reference/API.md:5179,6162-6207` — mirrors `FSMLoop.scope` field
  docstring and the `LockManager`/`resolve_scope` reference block. Confirm no
  change is needed (the fallback's shape is unchanged) and note that
  explicitly if so.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Files to Modify
- `skills/create-loop/reference.md:631` — rewrite "Most users can omit this field..." guidance to require declaring `scope:` explicitly
- `skills/create-loop/loop-types.md:159,274,388,498` — un-comment `# scope: ["src/"]` template lines, drop "Optional" wording
- `docs/guides/LOOPS_GUIDE.md:786-816,848-849` — document the `["."]` fallback in "Scope-Based Concurrency"; fix inaccurate Notes bullet at line 849
- `docs/development/TROUBLESHOOTING.md:812-827` — add the false-conflict-from-unscoped-loop mechanism to the existing "Scope conflict" entry
- `scripts/little_loops/fsm/fsm-loop-schema.json:30-35` (`scope` property, line 32 `description`) — update to mention the validate-time WARNING
- `docs/reference/API.md:5181` (not 5179 — the `FSMLoop.scope` field comment has drifted two lines since the issue was captured) — confirm/update field docstring
- `docs/reference/API.md:6162-6207` — `ScopeLock`/`LockManager`/`resolve_scope` reference block; confirmed accurate as-is (prose already correctly states templates pass through, says nothing false about empty-list handling)

### Dependent Files (Callers/Importers of the mechanism being documented)
- `scripts/little_loops/cli/loop/run.py:373` — `resolve_scope(fsm.scope or ["."], fsm.context)`, the primary fallback call site
- `scripts/little_loops/cli/loop/_helpers.py:1552` — same `fsm.scope or ["."]` idiom, pre-flight conflict check before spawning a detached/worktree loop
- `scripts/little_loops/fsm/concurrency.py:162-165` (`LockManager.acquire()`) — independently re-applies `if not scope: scope = ["."]` as a defensive fallback
- `scripts/little_loops/fsm/validation/structural_rules.py:1222` (`_validate_missing_scope()`) — the BUG-3107 lint itself; fires when `fsm.scope` is falsy (`[]`), `WARNING` severity, no suppression flag exists
- `scripts/little_loops/fsm/schema.py:1278,1544` — `FSMLoop.scope` dataclass default is `field(default_factory=list)`; YAML load uses `data.get("scope", [])` — an omitted key and an explicit `scope: []` are indistinguishable in-memory

### Tests
- `scripts/tests/test_concurrency.py` (`TestResolveScope`, lines ~1064-1140) — covers `resolve_scope()` template substitution, including `test_empty_scope` (empty list passes through empty; the `["."]` substitution is NOT inside `resolve_scope`)
- `scripts/tests/test_fsm_validation_structural.py` (`TestMissingScopeValidation`) — covers the BUG-3107 lint trigger/non-trigger cases

### Corrections to the Proposed Solution's cited targets (from Step 3 research)
- `skills/create-loop/loop-types.md:986` documents a **different** `scope` field — `EvaluateConfig.scope` for the `diff_stall` convergence evaluator (a per-state option limiting `git diff --stat`), not the loop-level `scope:` this issue is about. Updating that row would conflate two unrelated fields with the same name.
- `docs/reference/CLI.md:789-812` — the "No-scope (WARNING)" row already exists at line 810 (added by the BUG-3107 commit itself), quoting `resolve_scope(fsm.scope or ["."], fsm.context)` and both fix options. This part of the Proposed Solution is already done.
- `docs/development/TROUBLESHOOTING.md:1285` — this line no longer relates to scope (it's inside an unrelated "Check configuration" snippet). The only scope-relevant section in this file is at lines 812-829.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Types
N/A — no new data types; this is a documentation-only issue.

### Signatures
- `resolve_scope(scope: list[str], context: dict[str, Any]) -> list[str]` — in `scripts/little_loops/fsm/concurrency.py:35`; template substitution only, does NOT itself apply the `["."]` fallback (confirmed by `test_empty_scope`: `resolve_scope([], ...) == []`)
- `_validate_missing_scope(fsm: FSMLoop) -> list[ValidationError]` — in `scripts/little_loops/fsm/validation/structural_rules.py:1222`; the BUG-3107 lint, `if fsm.scope: return []`, else emits one WARNING with no suppression flag

### Call Path
`ll-loop run` (`cli/loop/run.py:373`) / background pre-flight (`cli/loop/_helpers.py:1552`) -> `fsm.scope or ["."]` -> `resolve_scope()` -> `LockManager.find_conflict()` / `.acquire()` (repo-root fallback re-applied defensively inside `acquire()`)

### Decision Rules
N/A — no new decision logic; this issue documents existing lint/fallback behavior, it does not introduce a gap kind, gate, or threshold.

## Implementation Steps

1. Confirm [[BUG-3107]] has landed so the lint's exact message/behavior is
   final.
2. Rewrite `skills/create-loop/reference.md:631`.
3. Un-comment `scope:` and drop "Optional" in the four `skills/create-loop/loop-types.md`
   template lines (159, 274, 388, 498). (Line 986's reference table documents
   a different `scope` field — `EvaluateConfig.scope` for the `diff_stall`
   evaluator, not the loop-level field this issue covers — so it is out of
   scope for this step.)
4. Update `docs/guides/LOOPS_GUIDE.md`'s Scope-Based Concurrency section
   (786-816, 848-849) with the `["."]` fallback and its Notes-bullet fix.
5. Add the false-conflict-from-unscoped-loop mechanism to
   `docs/development/TROUBLESHOOTING.md`'s existing "Scope conflict" entry
   (812-827). (Line 1285 is inside an unrelated "Check configuration" snippet
   and no longer relates to scope.)
6. Confirm `docs/reference/CLI.md:789-812`'s lint-rule table already
   documents the No-scope WARNING rule at line 810 (added by the BUG-3107
   commit itself, quoting `resolve_scope(fsm.scope or ["."], fsm.context)`
   and both fix options) — no change needed.
7. Update `scripts/little_loops/fsm/fsm-loop-schema.json:30-35`'s `scope`
   description.
8. Confirm `docs/reference/API.md:5181` (not 5179 — the `FSMLoop.scope`
   field comment has drifted two lines) and `6162-6207` need no change (or
   make the minimal change if they do).

## Impact

- **Severity**: without this, authoring docs actively contradict the new
  lint, so new loop authors get conflicting guidance.
- **Blast radius**: doc-only changes across 6 files plus one JSON schema
  description string. No code or test changes.

## Status

open


## Session Log
- `/ll:confidence-check` - 2026-08-08T18:16:36 - `47f42065-4220-4c09-974b-7fd99cd15eb2.jsonl`
- `/ll:confidence-check` - 2026-08-08T17:37:15 - `102c803e-68ba-4b70-826e-9d87622f3b54.jsonl`
- `/ll:reconcile-issue` - 2026-08-08T17:34:58 - `fb850fdf-cc95-448f-b74b-37536665ad19.jsonl`
- `/ll:refine-issue` - 2026-08-08T17:31:36 - `0746a600-67e0-4eeb-88c7-015609fa694e.jsonl`
- `/ll:issue-size-review` - 2026-08-08T12:31:14 - `252cabd4-42b7-43f3-becc-2330b53bf3d0.jsonl`
