---
discovered_commit: 6f81ca029f3c40a05520d5f1d8536fdd0a8723cc
discovered_branch: main
discovered_date: 2026-07-15 00:00:00+00:00
discovered_by: decide-issue
completed_at: '2026-07-15T23:43:06Z'
status: done
decision_needed: false
parent: EPIC-2451
relates_to:
- FEAT-2652
- ENH-2653
labels:
- epic-branches
- parallel
- worktree
- refactor
confidence_score: 88
outcome_confidence: 75
score_complexity: 20
score_test_coverage: 20
score_ambiguity: 15
score_change_surface: 20
---

# ENH-2656: Single source-of-truth EPIC base-branch resolver

## Summary

The EPIC integration-branch base is derived **independently in four places** today,
all hardcoding `parallel.base_branch` as the fork point. FEAT-2652 (per-EPIC
`base_branch:` declaration) requires all four to honor a per-EPIC override in
lockstep — the dominant outcome-confidence risk on that issue (72/100). This
enhancement extracts a single resolver so FEAT-2652 becomes "1 tested function + N
callers" instead of "4 hand-synced derivation paths."

This is a **pure refactor**: it introduces the seam and routes every existing
site through it with **no behavior change** (all four still resolve to
`parallel.base_branch` until FEAT-2652 adds the per-EPIC field). It should land
**before** FEAT-2652.

## Current Behavior

Four independent base derivations, none reading a shared value:

1. `worker_pool.py:_ensure_epic_branch()` (~1739) — the real fork:
   `["branch", branch, self.parallel_config.base_branch]`.
2. `worker_pool.py:_resolve_branch_targets()` (~1615-1641) — builds the branch
   name; **two** call sites (primary chain ~1637-1640 and a second at
   `worker_pool.py:360`).
3. `orchestrator.py:435-464` (FEAT-2562 comparison-base block) — **re-derives**
   the EPIC branch name as a string (`base = f"{prefix}{epic_id.lower()}-{slug}"`)
   and uses `parallel.base_branch` semantics for the diff base.
4. `auto-refine-and-implement.yaml` `checkout_epic_branch` state — inline FSM
   shell action mirroring the `rev-parse`/`ls-remote`/`git branch <name> <base>`
   shape.

Because the FSM state (4) is a shell action, it cannot call Python directly — so
today it re-implements the fork inline, guaranteeing drift risk the moment the
fork point becomes conditional.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-07-15):_

**Anchors verified, line numbers refreshed:**

- Site 1 — `worker_pool.py:_ensure_epic_branch()` is `worker_pool.py:1707-1743`;
  the real fork is at `worker_pool.py:1739`
  (`["branch", branch, self.parallel_config.base_branch]`).
- Site 2 — `_resolve_branch_targets()` is `worker_pool.py:1615-1641`, base read at
  `worker_pool.py:1631`; the second call site is `worker_pool.py:360`
  (`fork_point, _ = self._resolve_branch_targets(issue)`, with a
  `fork_point != base_branch` no-op normalization at ~362).
- Site 3 — the FEAT-2562 comparison-base block lives **inside**
  `orchestrator.py:_inspect_worktree()` (method starts `orchestrator.py:417`),
  baseline `base = self.parallel_config.base_branch` at `orchestrator.py:438`,
  independent EPIC-name re-derivation at `orchestrator.py:462-464`.
- Site 4 — `checkout_epic_branch` is `auto-refine-and-implement.yaml:162-233`;
  base derived at line 220 (`cfg.parallel.base_branch or detect_default_branch(...)`
  — the **only** site with a `detect_default_branch()` fallback), fork at line 230.

**The issue undercounts `base_branch` reads (six, not four).** Two additional
direct reads exist but are correctly **out of scope** — they are non-EPIC
fallback paths, not EPIC fork points:

- `worker_pool.py:1124` (`_get_changed_files`, `diff_base`) — used only when the
  worker has **no** cached epic branch.
- `worker_pool.py:1166` (`_update_branch_base`) — remote-fetch/rebase target for
  **standalone** issues (the `else` branch when no epic branch is cached).

These consume `self._worker_epic_branches` when an EPIC branch is set, so they
need no resolver routing; note them so a future pass doesn't mistake them for
missed fork sites.

**Two duplicated concerns, not one.** Beyond the fork-**base** string, the EPIC
branch-**name** format `f"{prefix}{epic_id.lower()}-{slug}"` is independently
hand-written at `worker_pool.py:1639`, `orchestrator.py:464`, and
`auto-refine-and-implement.yaml:219`, and the slug-loading walk
(`IssueParser` + `slugify(info.title)`) is duplicated between
`worker_pool.py:_load_epic_slug()` (`worker_pool.py:1682-1705`) and the FSM
heredoc (`auto-refine-and-implement.yaml:203-217`). For FEAT-2652's per-EPIC
override to land safely, the **name** derivation is as much a drift risk as the
base. Consider a companion `resolve_epic_branch_name(epic_id)` alongside the base
resolver (or a single helper returning `(name, base)`).

**Site 4 is inline _Python_, not a bash shell action.** The
`checkout_epic_branch` action is an inline Python heredoc
(`auto-refine-and-implement.yaml:171-244`, `action_type: shell` +
`capture: epic_branch`) that **already imports from `little_loops`** — including
`from little_loops.worktree_utils import detect_default_branch` at line 180. This
materially changes the "thin CLI subcommand" plan (see decision point below): the
FSM can `import` a resolver directly rather than shelling out to a new CLI. A
sibling `merge_epic_branch` state (`auto-refine-and-implement.yaml:583-586`) has
its own `cfg.parallel.base_branch or "main"` fallback but already reads the
persisted `base-branch-name.txt` (BUG-2614), so it is a downstream consumer, not
a fifth fork site.

## Expected Behavior

- A single Python helper — e.g. `_resolve_epic_base(epic_id) -> str` (or a
  module-level function in a shared location both `worker_pool.py` and
  `orchestrator.py` import) — returns the fork base for an EPIC. Post-ENH it
  simply returns `parallel.base_branch`; FEAT-2652 changes only this function's
  body to prefer a declared `base_branch`.
- All Python sites (1, 2×2, 3) call the resolver instead of reading
  `self.parallel_config.base_branch` directly for EPIC forks.
- The FSM `checkout_epic_branch` state (4) shells out to a thin CLI subcommand
  (e.g. `ll-issues epic-base <EPIC-ID>` or an `ll-loop`/`ll-parallel` helper) that
  prints the resolved base, instead of re-deriving it inline. FEAT-2652 then
  needs to touch **only the resolver + the CLI subcommand**, not the YAML logic.

### Codebase Research Findings

_Added by `/ll:refine-issue` — how the FSM state consumes the resolver:_

Because Site 4 is an inline Python heredoc that already imports from
`little_loops` (see Current Behavior findings), there are two viable ways to feed
it the resolved base. This is a real fork worth deciding before implementation:

**Option A**: Add a thin CLI subcommand (as originally scoped) — e.g.
`ll-issues epic-base <EPIC-ID>` — and have `checkout_epic_branch` shell out to it.
Follows the `ll-issues` subcommand convention: new file
`scripts/little_loops/cli/issues/epic_base.py` exporting `cmd_epic_base(config, args)`,
registered in `scripts/little_loops/cli/issues/__init__.py` (parser block ~152,
dispatch ~831) modeled on the `next-id`/`path` subcommands; tested via
`scripts/tests/test_issues_cli.py::TestIssuesCLINextId` shape (patch `sys.argv`,
call `main_issues()`, assert `capsys` stdout). `ll-parallel` has **no** subparser
layer, so `ll-issues` is the correct home.

**Option B**:
> **Selected:** Option B (FSM imports resolver directly) — the heredoc already imports `worktree_utils`; a CLI subcommand adds a process-spawn and parallel surface for no benefit.

Have the FSM heredoc import the resolver directly —
`from little_loops.worktree_utils import resolve_epic_base` — mirroring its
existing `from little_loops.worktree_utils import detect_default_branch` at
`auto-refine-and-implement.yaml:180`. No new CLI surface; FEAT-2652 touches
**only** the resolver function. The brittle `test_builtin_loops.py` assertions
convert to "asserts the import + resolver call" instead of "asserts the CLI
invocation."

**Recommended**: Option B — the FSM state is already Python importing
`worktree_utils`, so a CLI subcommand adds a process-spawn and a parallel
surface for no benefit here. A CLI subcommand is only warranted if a genuinely
non-Python consumer of the resolved base appears later; none exists today.
(If chosen, keep Option A's CLI test pattern on file for that future need.)

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-15.

**Selected**: Option B — FSM heredoc imports the resolver directly.

**Reasoning**: The `checkout_epic_branch` state is already an in-process Python
heredoc that imports `from little_loops.worktree_utils import detect_default_branch`
(auto-refine-and-implement.yaml:180) and computes the base inline at line 220 — every
sibling state in the file imports `little_loops.*` directly (e.g. autodev.yaml's
`check_open_question_progress` even imports a private CLI helper). Adding
`resolve_epic_base()` to the already-shared leaf module `worktree_utils.py` requires no
new file, parser wiring, dispatch branch, or subprocess/stdout-parsing, so FEAT-2652
touches only the resolver function. A CLI subcommand is warranted only if a non-Python
consumer appears; none exists today.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (CLI subcommand) | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |
| Option B (direct import) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- Option A: `ll-issues` file-per-subcommand scaffolding (`next_id.py`, `TestIssuesCLINextId`) is directly reusable, but at this call site it replaces a simpler already-working direct-import path with a new subprocess consumption path (reuse 2/3).
- Option B: Mirrors the `detect_default_branch` import at the exact same line (auto-refine-and-implement.yaml:180); `worktree_utils.py` is a leaf module already imported by `orchestrator.py` and 11 loop YAMLs — lowest-friction, no new infrastructure (reuse 3/3).

## Acceptance Criteria

- [ ] A single resolver function returns the EPIC fork base; all Python fork/
      comparison-base sites route through it.
- [ ] The `checkout_epic_branch` FSM heredoc imports the resolver directly
      (`from little_loops.worktree_utils import resolve_epic_base`, mirroring its
      existing `detect_default_branch` import) instead of re-deriving the base
      inline. No new CLI surface (Option B, decided 2026-07-15).
- [ ] **No behavior change**: every site still resolves to `parallel.base_branch`
      (verified by the existing `TestResolveBranchTargets` suite passing
      unchanged in behavior, and the loop-shape tests updated to assert the
      resolver import/call rather than the inline literal).
- [ ] Brittle literal-substring assertions in `test_builtin_loops.py`
      (`checkout_epic_branch` shape tests, ~2083/2097) are converted to
      behavioral/CLI-call assertions so they stop tripping on arg changes.
- [ ] A single unit test pins the resolver's fallback contract (no per-EPIC field
      → `parallel.base_branch`), giving FEAT-2652 a red-first seam to extend.

## Implementation Steps

1. Add `_resolve_epic_base(epic_id)` (shared location importable by both
   `worker_pool.py` and `orchestrator.py`); body returns `parallel.base_branch`.
2. Route `_ensure_epic_branch()`, both `_resolve_branch_targets()` call sites, and
   the `orchestrator.py:435-464` comparison-base derivation through it.
3. Repoint the `checkout_epic_branch` FSM heredoc to
   `from little_loops.worktree_utils import resolve_epic_base` and call it,
   dropping the inline base re-derivation (Option B — no CLI subcommand).
4. Convert `test_builtin_loops.py` literal-substring assertions to
   behavioral/CLI-call assertions; add the resolver fallback unit test.
5. Confirm the full `TestResolveBranchTargets` suite passes with no expected-value
   changes (behavior parity).

## Integration Map

- `scripts/little_loops/parallel/worker_pool.py` — `_ensure_epic_branch()`,
  `_resolve_branch_targets()` (×2), the new resolver seam.
- `scripts/little_loops/parallel/orchestrator.py` — FEAT-2562 comparison-base
  block (435-464).
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` —
  `checkout_epic_branch` state → direct `resolve_epic_base` import (Option B).
- `scripts/little_loops/worktree_utils.py` — new `resolve_epic_base()` resolver
  (shared leaf module, already imported by orchestrator + FSM).

### Codebase Research Findings

_Added by `/ll:refine-issue` — resolver placement + exact anchors:_

- **Resolver home** — `scripts/little_loops/worktree_utils.py`. It is a leaf
  module (zero `little_loops.*` internal imports), already hosts the EPIC-branch
  git-mechanics helpers (`detect_default_branch()` ~23, `verify_epic_branch_before_merge()`
  ~274, `merge_epic_branch_to_base()` ~396, `open_pr_for_epic_branch()` ~476), and
  is **already imported** by `orchestrator.py:38` and the FSM YAML
  (`auto-refine-and-implement.yaml:180`). `worker_pool.py` does not import it today
  but can without a cycle. (`parallel/types.py` is the alternative leaf home but is
  a pure config module — `worktree_utils.py` is the better semantic fit.)
- **Fork/base sites to route** — `worker_pool.py:1631`, `worker_pool.py:1739`,
  `orchestrator.py:438`+`462-464`, `auto-refine-and-implement.yaml:220`.
- **Slug helper to reuse/relocate** — `worker_pool.py:_load_epic_slug()`
  (`worker_pool.py:1682-1705`); the FSM heredoc duplicates it at
  `auto-refine-and-implement.yaml:203-217`.
- **CLI pattern (only if Option A)** — subcommand file under
  `scripts/little_loops/cli/issues/`, wired in that dir's `__init__.py`; entry point
  `ll-issues = "little_loops.cli:main_issues"` (`scripts/pyproject.toml:68`).
- **Brittle test assertions to convert** — `test_builtin_loops.py:2090`
  (`'"branch", branch, base' in action`), `:2100-2102`
  (`rev-parse`/`ls-remote` in action), and the ENH-2601 end-to-end assertion at
  `test_builtin_loops.py:2857`.

## Tests

- `scripts/tests/test_worker_pool.py::TestResolveBranchTargets` — must pass with
  unchanged expected branch tuples (behavior parity).
- `scripts/tests/test_builtin_loops.py` — `checkout_epic_branch` shape tests
  converted to assert the `resolve_epic_base` import/call (Option B) rather than
  the inline literal.
- New resolver fallback unit test (no field → `parallel.base_branch`).

## Impact

Medium. No user-facing behavior change on its own, but it retires the dominant
execution risk on FEAT-2652 by collapsing four hand-synced derivation paths into
one tested function. Sequence **before** FEAT-2652.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-15_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 75/100

### Concerns
- Acceptance Criteria (line 192-193) and Implementation Steps (step 3) still
  mandate "a thin CLI subcommand" and route the FSM state to shell out to it —
  but the Decision Rationale section (decided 2026-07-15 by `/ll:decide-issue`)
  explicitly selected **Option B** (FSM heredoc imports `resolve_epic_base()`
  directly from `worktree_utils.py`, no new CLI surface). These two sections
  contradict each other; an implementer following the AC/Steps literally would
  build the CLI subcommand the decision rejected. Update AC line 192-193 and
  Implementation Step 3 to match Option B before implementing.

### Outcome Risk Factors
- Ambiguity: the AC/Implementation Steps text was left pointing at the CLI
  subcommand approach even though `/ll:decide-issue` already picked Option B
  (direct import) — sync the stale text to Option B first so implementation
  doesn't build the discarded CLI surface.

## Resolution

Implemented 2026-07-15 (Option B). Added two shared leaf-module resolvers to
`worktree_utils.py`:

- `resolve_epic_base(epic_id, base_branch)` — returns `base_branch` verbatim
  today; the single FEAT-2652 seam (per-EPIC override lands here).
- `resolve_epic_branch_name(epic_id, prefix, slug)` — single-sources the
  `<prefix><epic-id-lower>-<slug>` format previously hand-written at 3 sites.

Routed every Python fork/comparison-base/name site through them:
`worker_pool._resolve_branch_targets` + `_ensure_epic_branch(branch, base)`
(now takes the resolved base), `orchestrator._inspect_worktree` (branch-name
derivation), and the `checkout_epic_branch` FSM heredoc (Option B — imports the
resolvers directly, mirroring its existing `detect_default_branch` import; no
CLI subcommand). No behavior change — all sites still resolve to
`parallel.base_branch`.

Tests: new `TestResolveEpicBase`/`TestResolveEpicBranchName` unit tests pin the
fallback contract; `test_builtin_loops.py` brittle literal-substring assertion
converted to a `resolve_epic_base`/`resolve_epic_branch_name` import+call check;
`TestResolveBranchTargets` passes with unchanged expected tuples. Full suite:
15072 passed, 36 skipped. ruff + mypy clean; `ll-loop validate` passes.

## Status

done — precursor refactor split from FEAT-2652 to de-risk its per-EPIC
base-branch threading. Unblocks FEAT-2652.

## Session Log
- `/ll:manage-issue` - 2026-07-15T23:42:36 - `94563b11-a9f7-40a4-8a2b-00330dffee45.jsonl`
- `/ll:ready-issue` - 2026-07-15T23:35:04 - `7ea91453-80a8-4d93-8938-e8b4b6763cb7.jsonl`
- `/ll:decide-issue` - 2026-07-15T23:31:05 - `793cec70-586f-4fc4-a369-c7841ae83277.jsonl`
- `/ll:refine-issue` - 2026-07-15T23:28:16 - `6c540f7a-bb19-4d27-b451-c8f12038547f.jsonl`
- `/ll:confidence-check` - 2026-07-15T00:00:00 - `b5329306-08f2-4888-9be6-2ea39e864cdf.jsonl`
