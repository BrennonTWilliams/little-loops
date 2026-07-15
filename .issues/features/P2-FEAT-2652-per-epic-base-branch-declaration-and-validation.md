---
discovered_commit: 6f81ca029f3c40a05520d5f1d8536fdd0a8723cc
discovered_branch: main
discovered_date: 2026-07-15 00:00:00+00:00
discovered_by: capture-issue
status: open
relates_to:
- ENH-2653
- BUG-2651
depends_on:
- ENH-2656
labels:
- epic-branches
- parallel
- worktree
- sprint
confidence_score: 100
outcome_confidence: 82
score_complexity: 21
score_test_coverage: 23
score_ambiguity: 20
score_change_surface: 18
spike_attempted: true
spike_completed: true
---

# FEAT-2652: Per-EPIC base-branch declaration + sprint-creation validation

## Summary

An EPIC integration branch is **always** forked from the global
`parallel.base_branch` (default `main`). There is no way for an EPIC whose child
issues reference symbols living on an unmerged feature branch (e.g.
`refactor/tableau-third-revision`) to declare that branch as its base. When such
an EPIC is sprinted from the wrong base, every child that cites the not-yet-merged
symbols fails readiness *correctly-but-misleadingly* — the symbols really are
absent from the worktree, but they exist exactly where the EPIC intends them.
The loop then degrades silently to `verdict: partial` and holds the epic merge
open, with no signal the base was wrong.

Add an optional `base_branch:` / `target_branch:` frontmatter field to EPIC
issues, teach worktree creation to honor it, and validate at sprint-creation time
that the declared base exists (and, ideally, that the EPIC's cited symbols
resolve there) — refusing to dispatch a wrong-base EPIC rather than letting it
degrade to `partial`.

## Current Behavior

- `worker_pool.py:_ensure_epic_branch()` (~line 1739) hardcodes the fork point:

  ```python
  self._git_lock.run(
      ["branch", branch, self.parallel_config.base_branch],
      cwd=self.repo_path, timeout=30,
  )
  ```

- `_resolve_branch_targets()` returns either `parallel.base_branch` (standalone)
  or `epic/<EPIC-ID>-<slug>` (EPIC child) — and the EPIC branch itself was created
  off `parallel.base_branch`. No per-EPIC override anywhere in the call chain.
- `config-schema.json` exposes `parallel.base_branch` as a **global** setting only.
- The EPIC template (`epic-sections.json`) declares Goal / Scope / Children /
  Success Metrics plus common sections — **no branch field**.
- `epic_branches.verify_before_merge: true` only enforces the *merge-time*
  contract (lint/coverage on the EPIC branch before merge-back); it does **not**
  check the *sprint-creation-time* contract "does the child content exist on the
  branch this EPIC was sprinted against?"

Result: an EPIC created while the user is on `main` (or whenever the sprint logic
picks `main`) produces a worktree lacking any unmerged-branch symbols, and the
false readiness rejections are only visible in the per-issue verifier transcript.

## Expected Behavior

- An EPIC may declare its intended base, e.g.:

  ```yaml
  base_branch: refactor/tableau-third-revision
  ```

- `_ensure_epic_branch()` forks the EPIC integration branch from the EPIC's
  declared `base_branch` when present, falling back to `parallel.base_branch`
  when absent (fully backward-compatible — no field means today's behavior).
- Sprint creation (`sprint-refine-and-implement` → `auto-refine-and-implement`
  path, i.e. the orchestrator/WorkerPool that reads the EPIC) **validates** the
  declared base:
  - the ref exists (local or remote); if not, refuse to dispatch with a clear
    error naming the missing branch.
  - optionally, spot-check that a sample of the EPIC's children's cited symbols
    resolve on that base (via `git show <base>:<file>`); if the base is clearly
    wrong, abort rather than emit a run-full of false `NOT_READY`s and finish
    `partial`.
- Escalation: a wrong-base condition should be a **hard stop**, not folded into a
  soft `partial`. (Absorbs the "partial masks a false NOT_READY" side-finding —
  the mismatch was noticed and classified as a `concern`, then swallowed.)

## Use Case

A developer is iterating a large redesign on a long-lived feature branch
(`refactor/tableau-third-revision`) that has not yet merged to `main`. They scope
an EPIC whose child issues cite symbols introduced by that redesign, then run
`sprint-refine-and-implement`. Today, if the sprint is created off `main`, every
redesign-referencing child is falsely rejected as `NOT_READY` and the run ends
`partial` with the epic merge held open. With this feature, the EPIC declares
`base_branch: refactor/tableau-third-revision`; the worktree forks from the right
tree, children reach `READY`, and a genuinely wrong/missing base is rejected up
front with a clear error instead of a silent degrade.

## Acceptance Criteria

- [ ] EPIC issues accept an optional `base_branch:` (alias `target_branch:`)
      frontmatter field, documented in the EPIC section schema.
- [ ] When an EPIC declares `base_branch`, its integration branch is forked from
      that ref; when absent, it forks from `parallel.base_branch` (unchanged
      today's behavior — verified by test).
- [ ] Sprint dispatch validates that a declared base ref exists (local or
      remote); a missing ref aborts dispatch with an error naming the branch, and
      does **not** produce a `partial` verdict.
- [ ] A wrong-base condition is surfaced as a hard stop, not folded into a soft
      `partial`.
- [ ] Tests cover: valid declared base forks correctly; missing base ref aborts;
      no field preserves `parallel.base_branch` behavior.

## Implementation Steps

1. Add `base_branch` (alias `target_branch`) to the EPIC section schema
   (`epic-sections.json`) as an optional frontmatter field; document it.
2. Thread the EPIC's declared base into `WorkerPool._ensure_epic_branch()` /
   `_resolve_branch_targets()`; fall back to `parallel.base_branch` when unset.
3. Add a validation step at sprint dispatch: assert the declared base ref exists;
   optionally sample-check cited symbols via `git show <base>:<file>`.
4. On validation failure, abort the dispatch (hard error), do not degrade to
   `partial`.
5. Tests: EPIC with a valid declared base forks from it; EPIC with a missing
   base ref aborts; EPIC with no field preserves current `parallel.base_branch`
   behavior.

## Integration Map

- `scripts/little_loops/parallel/worker_pool.py` — `_ensure_epic_branch()`,
  `_resolve_branch_targets()`
- `scripts/little_loops/parallel/orchestrator.py` — EPIC-aware base resolution
  (already switches comparison base for EPIC children, FEAT-2562)
- `scripts/little_loops/templates/.../epic-sections.json` — new field
- `config-schema.json` — document interaction with global `parallel.base_branch`
- Pairs with ENH-2653 (`ready-issue` should also learn the target branch so its
  symbol checks run against the right tree).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Where the base_branch field hangs off (no new type needed):**
- `IssueInfo` (`scripts/little_loops/issue_parser.py:551`) is the *single*
  dataclass used for every issue type including EPICs — there is no `EpicInfo`
  subclass. Add a `base_branch: str | None = None` field here (dataclass
  currently ends at `status: str = "open"`).
- Frontmatter alias precedent (`base_branch` / `target_branch`): follow the
  `parent` / `parent_issue` pattern in `IssueParser.parse_file()`
  (`issue_parser.py:844-864`) — check the canonical key first, fall back to the
  alias only when absent, and `logger.warning` naming both keys. Document both
  names on the field's docstring (as `parent`'s docstring does at line 578).

**Fork seam (worker_pool.py):**
- The hardcoded fork is `_ensure_epic_branch()` at `worker_pool.py:1739`
  (`["branch", branch, self.parallel_config.base_branch]`). The method
  (1707-1743) already does local (`rev-parse --verify`) then remote
  (`ls-remote --heads`) existence checks before creating — thread the EPIC's
  declared base in as the fork point here.
- `_resolve_branch_targets()` (`worker_pool.py:1615-1641`) is where the EPIC
  ancestor is resolved and the branch name built; it calls `_ensure_epic_branch`.
- `_load_epic_slug()` (`worker_pool.py:1682-1705`) is the exact precedent for a
  new `_load_epic_base_branch(epic_id)` helper — it globs `P?-{epic_id}-*.md`,
  parses via `IssueParser`, and falls back to a default on parse failure.

**Second, independent base derivation to keep in sync (orchestrator.py):**
- The FEAT-2562 comparison-base block (`orchestrator.py:435-464`) **re-derives**
  the EPIC branch name independently (`base = f"{prefix}{epic_id.lower()}-{slug}"`)
  rather than reading a stored value, and uses it as the diff base for
  `git rev-list --count {base}..{branch}`. A per-EPIC base override must be
  applied here too or the comparison base will diverge from the fork base.

**Sprint-dispatch validation seam (hard-stop precedent):**
- Insert the base-existence check in `scripts/little_loops/cli/sprint/run.py`
  right after `issue_infos = manager.load_issue_infos(...)` (line 351), mirroring
  the existing `_run_learning_gate_preflight()` gate
  (`run.py:166-230`, called at 367-369). That gate returns an `int` exit code
  (0 pass / 1 block), logs `logger.error` naming the blocking cause, and the
  caller early-`return`s **before** the worker pool is constructed (line 625) —
  exactly the "abort dispatch, name the missing branch, no `partial`" shape the
  AC requires. Use this return-code style at the CLI level, not a raised
  `RuntimeError`.

**Reusable ref-existence primitive:**
- `worktree_utils.setup_worktree()` (`worktree_utils.py:111-118`) already does
  `git rev-parse --verify <base_branch>` and raises `RuntimeError` on
  non-resolution — the closer template for "validate ref, hard-stop on missing."
  All git calls in these paths go through `GitLock.run([...], cwd=, timeout=)`
  (`parallel/git_lock.py:28-60`); do not add bare `subprocess.run(["git",...])`.

**New-code gaps (no existing precedent):**
- The optional "spot-check cited symbols resolve on the base" step has **no**
  analog: `git show <ref>:<file>` (blob-at-ref read) is used nowhere in
  `scripts/little_loops/`. This is net-new code following the
  `GitLock.run([...])` + `.returncode`/`.stdout` convention.
- `epic-sections.json` has **no frontmatter-only field entries** today — every
  entry is a markdown `##` section schema. Documenting `base_branch` there
  (per Implementation Step 1) introduces a new category; the natural existing
  home for frontmatter-key docs is the `IssueInfo` docstring. Consider whether
  the schema entry is worth the precedent, or document in the docstring only.

**Test targets:**
- No direct Python unit test of `_ensure_epic_branch` exists today; coverage is
  indirect via the loop-YAML mirroring test
  `test_builtin_loops.py:test_checkout_epic_branch_reuses_ensure_epic_branch_shape`
  (line 2097). New tests should land in `scripts/tests/test_worker_pool.py`
  (fork behavior) and `scripts/tests/test_cli_sprint.py` /
  `test_sprint_integration.py` (dispatch validation abort).
- Parent EPIC: `EPIC-2451` (per-epic integration-branch strategy). Related
  hardcoded-base bug: `BUG-2323`.

### Post-ENH-2656 Update (re-refine 2026-07-15)

_Added by `/ll:refine-issue` — the `depends_on: ENH-2656` precursor has now landed
(commit `5e780e7c`). Several anchors above were written pre-ENH-2656 and are now
STALE. The implementation scope collapses dramatically. This addendum supersedes
the "three/four independent derivation paths must stay in lockstep" framing in
**Current Behavior**, **Confidence Check Notes → Outcome Risk Factors**, and the
per-path bullets in **Codebase Research Findings** above._

**The single seam now exists — extend ONE function body:**
- ENH-2656 added `resolve_epic_base(epic_id, base_branch)` and
  `resolve_epic_branch_name(epic_id, prefix, slug)` to
  `scripts/little_loops/worktree_utils.py:65-107`. `resolve_epic_base` returns
  `base_branch` verbatim today and its docstring **explicitly reserves itself as
  the FEAT-2652 seam**: _"FEAT-2652 extends **only this function** to prefer a
  per-EPIC `base_branch:` declaration ... no caller changes required, retiring
  the four hand-synced derivation paths this resolver consolidates."_ The
  `epic_id` param is already accepted (unused today) precisely so the per-EPIC
  lookup needs no signature change.
- **Implementation reduces to**: (1) add `base_branch: str | None = None` to
  `IssueInfo` + alias parse; (2) extend `resolve_epic_base`'s body to look up the
  EPIC's declared `base_branch` by `epic_id` and prefer it over the passed
  default; (3) add the sprint-dispatch validation gate. Steps 2/6/7/10 of the
  original Implementation Steps / Wiring Phase (threading the base through
  `_ensure_epic_branch`, the second call site, the FSM state, the
  `test_builtin_loops` substring assertions) are **already done by ENH-2656** —
  do not re-thread them.

**STALE anchors (corrected):**
- ⚠ **Current Behavior** claims `_ensure_epic_branch()` (~1739) "hardcodes the
  fork point" via `["branch", branch, self.parallel_config.base_branch]`. No
  longer true. The method is now `_ensure_epic_branch(self, branch, base)`
  (`worker_pool.py:1713`); the fork reads the `base` **parameter**. The caller
  `_resolve_branch_targets()` (`worker_pool.py:1615-1647`) resolves the base via
  `resolve_epic_base(epic_id, self.parallel_config.base_branch)` at line 1645 and
  passes it in at 1646.
- ⚠ **orchestrator.py** re-derivation moved from an inline `f"{prefix}..."` to a
  `resolve_epic_branch_name()` call (`orchestrator.py:462-466`). This site needs
  only the branch **name** (it diffs against the already-created EPIC branch), so
  it does **not** call `resolve_epic_base` and needs **no** per-EPIC-base wiring.
- ⚠ **FSM `checkout_epic_branch`** state now imports both resolvers directly
  (`auto-refine-and-implement.yaml:180-184, 226-228`) — no longer an independent
  path; it inherits the override automatically once `resolve_epic_base` is
  extended.
- ✓ Still accurate: the second `_resolve_branch_targets()` call site at
  `worker_pool.py:360` (pass-through — inherits the change, no edit).

**Reduced-scope test targets:**
- `scripts/tests/test_worktree_utils.py::TestResolveEpicBase` (added by ENH-2656)
  is now the primary unit-test home for the per-EPIC override — extend it with
  "declared base preferred over default" / "no field falls back to default" cases
  rather than adding fork tests in `test_worker_pool.py`.
- Sprint-dispatch gate: still `test_sprint_integration.py::TestSprintPreflightGate`
  shape (unchanged by ENH-2656).
- The `test_builtin_loops.py` substring assertions were already converted by
  ENH-2656 to resolver import/call checks — the "likely to break" warning above
  no longer applies.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/worker_pool.py:360` — a **second** call site of
  `_resolve_branch_targets()` (outside the primary 1637-1640 chain). Any signature
  change to thread the declared base must preserve this call too [Agent 2 finding].
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — the FSM
  `checkout_epic_branch` state is a **third, independent** base-branch derivation
  path (mirrors `_ensure_epic_branch`'s `rev-parse`/`ls-remote`/`git branch <name>
  <base>` shape inline). If the fork point becomes per-EPIC, this state's shell
  action must read the declared base too, or it diverges from the Python fork
  [Agent 1 + Agent 3 finding].
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — sprint entry
  loop that dispatches through the orchestrator; confirm it surfaces the new
  hard-stop abort rather than swallowing it [Agent 1 finding].
- `IssueInfo` is consumed read-only by ~35 CLI/consumer sites (issues/*.py,
  `sync.py`, `dependency_graph.py`, `learning_tests/extractor.py`,
  `hooks/sweep_stale_refs.py`). Additive field is safe, but any consumer doing
  strict frontmatter-key validation or `dataclasses.fields()`/`asdict()` snapshotting
  could reject/expose the new key — spot-check `sync.py` and the parser fuzz tests
  [Agent 2 finding].

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` (~462-495) — states the EPIC branch "forks from and merges
  back to `parallel.base_branch`"; this global claim becomes conditionally false
  [Agent 2 finding].
- `docs/development/MERGE-COORDINATOR.md` (~149-165) — merge-target decision + 4-step
  lifecycle assumes merge-back to the global base; needs a per-EPIC-base caveat
  [Agent 2 finding].
- `docs/reference/CONFIGURATION.md` (~370-374) — documents `base_branch` as the
  single global setting and `epic_branches.merge_to_base_on_complete`; add the
  per-EPIC override + interaction note [Agent 2 finding].
- `docs/guides/SPRINT_GUIDE.md` (~308-352) — "What changes when per-EPIC branches
  are enabled" describes fork from `parallel.base_branch`; add the frontmatter
  override + new dispatch-validation/hard-stop behavior [Agent 2 finding].
- `docs/reference/API.md` — enumerates `IssueInfo` dataclass fields; add
  `base_branch` entry [Agent 1 finding].
- `config-schema.json` inline `description` strings for `epic_branches` (~412-414)
  and `merge_to_base_on_complete` (~426-429) assert unconditional-global-base
  semantics — same caveat as the prose docs [Agent 2 finding].
- `commands/create-sprint.md` / `skills/ll-create-sprint/SKILL.md` /
  `skills/scope-epic/SKILL.md` — user-facing text on sprint dispatch + EPIC
  scoping; mention the new `base_branch:` field and validation gate [Agent 1 finding].
- `CHANGELOG.md` — release note for the new opt-in field [Agent 1 finding].

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_worker_pool.py::TestResolveBranchTargets` (lines 3448-3604)
  — **likely to break**: all 5 tests build issues with a fixed attribute set and
  assert exact branch tuples. Add `base_branch=None` defaults to the `_make_issue_file`
  helper (line 3425) and each mock issue so the no-field path still resolves to
  `parallel.base_branch` [Agent 3 finding].
- `scripts/tests/test_issue_parser.py` — mimic the `parent`/`parent_issue` alias
  precedent: `test_parse_parent_from_frontmatter` (1881) for the happy path and
  `test_parse_parent_issue_alias_emits_warning` (1903) for the `target_branch`
  alias + warning [Agent 3 finding].
- `scripts/tests/test_sprint_integration.py::TestSprintPreflightGate` (1932) — the
  exact template for the new dispatch gate: happy-path (ref exists → 0), abort-on-
  missing-ref (→ 1, hard stop, **not** `partial`), skip-flag bypass, disabled-config
  skip; follows `_run_learning_gate_preflight`'s return-code shape [Agent 3 finding].
- `scripts/tests/test_cli_loop_worktree.py::test_base_branch_invalid_raises_runtime_error`
  (292) — closest ref-existence pattern (mock `git_lock.run`, branch on
  `"--verify" in args`, return non-zero + stderr, assert on the failure) [Agent 3 finding].
- `scripts/tests/test_builtin_loops.py` — `test_checkout_epic_branch_reuses_ensure_epic_branch_shape`
  (2097) and `..._gated_on_epic_scope_and_config` (2083) assert literal substrings
  (`'"branch", branch, base'`, `rev-parse`, `ls-remote`) in the loop YAML; **likely
  to break** if the fork-point arg changes [Agent 3 finding].
- `scripts/tests/test_orchestrator.py` — covers the FEAT-2562 comparison-base block
  (orchestrator.py:435-464); per-EPIC base threading there needs matching test
  updates [Agent 2 finding].

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation:_

6. Update the **second** `_resolve_branch_targets()` call site at
   `worker_pool.py:360` in lockstep with the primary chain (signature parity).
7. Thread the declared base into the FSM `checkout_epic_branch` state in
   `auto-refine-and-implement.yaml` (third derivation path) so the loop's inline
   fork matches the Python fork; verify `sprint-refine-and-implement.yaml` surfaces
   the hard-stop.
8. Update `test_worker_pool.py::TestResolveBranchTargets` + `_make_issue_file`
   helper for the new `base_branch` field (no-field path preserved).
9. Add parser tests mirroring the `parent`/`parent_issue` alias pair for
   `base_branch`/`target_branch`; add a `TestSprintPreflightGate`-style gate test
   class for the dispatch validation.
10. Sync the `test_builtin_loops.py` substring assertions if the fork-point arg
    changes; update `test_orchestrator.py` for the comparison-base threading.
11. Update the doc network (ARCHITECTURE, MERGE-COORDINATOR, CONFIGURATION,
    SPRINT_GUIDE, API), the `config-schema.json` inline descriptions, the sprint/
    epic skills+command, and CHANGELOG.

## Impact

High. This is the root cause of the wrong-base false-negative class. Without it,
any EPIC whose children reference unmerged-branch symbols will keep silently
degrading to `partial` and holding merges open, and the only diagnosis path is
reading per-issue transcripts. Backward-compatible (opt-in field).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-15_

**Readiness Score**: 96/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- Three independent base-branch derivation paths must stay in lockstep — deep per-site complexity: `worker_pool.py`'s `_ensure_epic_branch()`/`_resolve_branch_targets()` (two call sites), `orchestrator.py`'s FEAT-2562 comparison-base re-derivation, and the FSM `checkout_epic_branch` state in `auto-refine-and-implement.yaml`. Missing any one leaves a stale global-base assumption.
- Several test files assert literal substrings/exact tuples (`test_builtin_loops.py`'s `checkout_epic_branch` shape tests, `test_worker_pool.py::TestResolveBranchTargets`) that are likely to break and require synchronized updates alongside the implementation, not just additive coverage.

## Spike Results

_Added by `/ll:spike` on 2026-07-15_

Proves the one net-new, no-precedent mechanism in this issue: the optional
"spot-check that a sample of the EPIC's children's cited symbols resolve on the
declared base" step (`git show <ref>:<path>` blob-at-ref read — used nowhere in
`scripts/little_loops/` today).

**Retired risks**

| Risk | Proven by | Result |
|------|-----------|--------|
| Reading a file's content at an arbitrary ref via `GitLock.run(["show", f"{ref}:{path}"])` + `.returncode`/`.stdout` | `test_reads_blob_present_on_ref` | ✓ pass |
| A missing path-at-ref returns non-zero (not an exception) → classifiable as "symbol absent on base" | `test_missing_path_at_ref_returns_nonzero`, `test_missing_path_on_base_but_present_on_feature` | ✓ pass |
| A nonexistent ref returns non-zero cleanly | `test_nonexistent_ref_returns_nonzero` | ✓ pass |
| Routes git through `GitLock` (no bare subprocess) — AST regression guard | `test_uses_gitlock_no_bare_subprocess` | ✓ pass |

**Spike location**: `scripts/tests/spike/git_show_blob_at_ref/`
**Verification**: 5 tests pass (`python -m pytest scripts/tests/spike/git_show_blob_at_ref/ -v`).
**Promotion**: move to `scripts/little_loops/spike/git_show_blob_at_ref/` in a separate PR.

The dominant fan-out-drift risk (four independent base derivations) is addressed
structurally by the precursor **ENH-2656** (single source-of-truth EPIC base
resolver), which this issue now `depends_on`.

## Status

open — captured from consumer-project run findings. Root-cause fix; pairs with
ENH-2653 (guardrail) and BUG-2651 (independent triage bug surfaced in same run).


## Session Log
- `/ll:confidence-check` - 2026-07-15T23:59:00 - `35707e3e-676f-4f72-b932-da80a7362563.jsonl`
- `/ll:refine-issue` - 2026-07-15T23:55:52 - `80f3560e-5b13-43a5-8a20-af13c7fc2332.jsonl`
- `/ll:spike` - 2026-07-15T23:22:40 - `d6eae4b5-b439-4617-9ac1-9a6b401a46c6.jsonl`
- `/ll:decide-issue` - 2026-07-15T23:17:31 - `d6eae4b5-b439-4617-9ac1-9a6b401a46c6.jsonl`
- `/ll:confidence-check` - 2026-07-15T23:20:00 - `7285c640-59d1-431f-84f9-29111bbcaa9d.jsonl`
- `/ll:wire-issue` - 2026-07-15T23:14:48 - `58678dfa-9825-4b94-9e6a-4216d0846bde.jsonl`
- `/ll:refine-issue` - 2026-07-15T23:09:39 - `d59da632-f9e0-4c3a-b52b-fd5930e8885f.jsonl`
