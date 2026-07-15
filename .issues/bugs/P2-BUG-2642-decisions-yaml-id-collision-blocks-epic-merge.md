---
id: BUG-2642
title: Concurrent `.ll/decisions.yaml` appends collide on ARCHITECTURE-NNN id and
  block EPIC merges
type: BUG
status: open
priority: P2
discovered_date: '2026-07-15'
discovered_by: capture-issue
captured_at: '2026-07-15T02:26:46Z'
decision_needed: false
labels:
- decisions
- data-integrity
- epic-merge
- concurrency
confidence_score: 96
outcome_confidence: 68
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 18
score_change_surface: 13
size: Very Large
---

# BUG-2642: Concurrent `.ll/decisions.yaml` appends collide on ARCHITECTURE-NNN id and block EPIC merges

## Summary

When work happens on an EPIC integration branch and on `main` in parallel, both
sides append decision entries to `.ll/decisions.yaml` using the same monotonic
`ARCHITECTURE-NNN` counter and the same tail of the YAML `entries:` list. On
merge-back (`epic → base`), git reports a content conflict in
`.ll/decisions.yaml`, and the auto-refine/sprint loop's merge step
(`merge_epic_branch_to_base`) aborts with `epic_merge_verdict=merge_failed` — a
green feature branch (verify gate passed) is silently blocked by a decisions-log
data conflict unrelated to the feature.

## Current Behavior

Divergent branches both append decision entries to the single shared
`entries:` list in `.ll/decisions.yaml`, each minting the same next
`ARCHITECTURE-NNN` id. On `epic → base` merge-back, git cannot auto-resolve the
overlapping tail edits and the loop's merge step aborts with
`epic_merge_verdict=merge_failed`, giving no diagnostic.

## Steps to Reproduce

Observed live during `ll-loop run sprint-refine-and-implement --context sprint_name=EPIC-2370` (2026-07-14):

1. `main` appended two decisions: `ARCHITECTURE-154` (BUG-2640) and
   `ARCHITECTURE-155` (ENH-2641).
2. The epic branch `epic/epic-2370-…` independently appended `ARCHITECTURE-154`
   (FEAT-2337) — the **same id** for a different decision.
3. `git merge --no-ff epic` into `main` → `CONFLICT (content): Merge conflict in
   .ll/decisions.yaml` (both branches edited the same list tail; ids collide).
4. `merge_epic_branch_to_base` runs `git merge --abort` and returns False →
   loop reports `merge_failed`, EPIC not closed out.

Manual resolution required unioning all three entries and renumbering the epic's
`ARCHITECTURE-154` → `ARCHITECTURE-156`.

## Root Cause

The `ARCHITECTURE-NNN` id is allocated from a repo-global monotonic counter and
new entries are appended to the end of a single shared list. Two branches that
each add a decision necessarily pick the same next id and edit the same region,
so a text merge cannot auto-resolve. This is structural: any parallel/epic
branch that logs a decision races here. See [[project_verify_gate_pythonpath_test_self_contamination]]
for the run this surfaced in.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Id-minting site**: `scripts/little_loops/cli/issues/decisions.py` in `_cmd_add()`
  (~line 441): `entry_id = f"{prefix}-{len(existing) + 1:03d}"` where
  `existing = list_entries(path=path, type=entry_type)` and `prefix =
  args.category.upper()` (so `category: architecture` → `ARCHITECTURE-`). The id
  is a **count of on-disk entries + 1**, recomputed per worktree with no persisted
  counter, lock, or cross-branch coordination — two diverged worktrees see the
  same historical count and mint the identical id. The same shape recurs at
  `_cmd_extract_from_completed()` (~line 862).
- **Append/serialize site**: `scripts/little_loops/decisions.py` in `add_entry()`
  (line 310) → `entries.append(entry)` → `save_decisions()` (line 297), which
  re-serializes the **entire** list via `yaml.dump(..., sort_keys=False)` +
  `atomic_write()`. Every add is a full-file read-modify-write landing the new
  entry at the list tail, so both branches edit the same end-of-file region → a
  single-line content conflict git cannot auto-resolve.
- **No id-uniqueness guard**: neither `load_decisions()` (line 284),
  `_entry_from_dict()`, nor `add_entry()` rejects duplicate ids; duplicates are
  silently accepted on read and write. `ll-verify-decisions`
  (`scripts/little_loops/cli/verify_decisions.py`) validates parse/schema only and
  is not invoked on the add or merge paths.
- **Merge-abort site**: `scripts/little_loops/worktree_utils.py` in
  `merge_epic_branch_to_base()` (lines 384–435) runs a single `git merge --no-ff`;
  on any non-zero returncode it logs one `logger.warning` with raw `result.stderr`,
  runs `git merge --abort`, and returns `False` (→ `epic_merge_verdict=merge_failed`).
  No per-file conflict inspection, no `.gitattributes`/merge-driver
  (none exists anywhere in the repo), and no structured diagnostic artifact
  (the observability half is BUG-2643). Thin caller:
  `ParallelOrchestrator._merge_epic_branch_to_base()`
  (`scripts/little_loops/parallel/orchestrator.py`, ~line 1353).
- **Prior art — structurally identical race**: `ll-issues next-id`
  (`scripts/little_loops/cli/issues/next_id.py` `cmd_next_id()`) uses the same
  "read max + 1" allocation and has its own documented concurrency bug, BUG-1364,
  whose A/B/C option analysis is directly reusable here. Note BUG-1364 rejected an
  in-CLI reservation write because `get_next_issue_number()` is called from
  read-only parsing — the same read-vs-write hazard applies to `list_entries()` /
  `load_decisions()` here (both called from read-only `_cmd_list` /
  `load_coupling_entries`), so any lock/reservation fix must not fire on reads.

## Expected Behavior

Decision-log appends from divergent branches should merge without a hand-resolved
conflict and without id collisions.

## Candidate Approaches (not yet decided)

- **Per-branch / namespaced ids** (e.g. embed a branch or uuid component) so two
  branches never mint the same id.
- **Custom git merge driver** (`.gitattributes` `merge=` for `.ll/decisions.yaml`)
  that unions `entries:` and renumbers collisions deterministically.
- **Append-only fragment files** (one file per decision, id from uuid/timestamp)
  merged by directory union instead of editing one shared YAML list.
- **UUID-based ids** with the human `ARCHITECTURE-NNN` label demoted to display-only.

### Codebase Research Findings

_Added by `/ll:refine-issue` — decision point (pick one for v1):_

**Option A**: **Append-only fragment files** — one file per decision under a
directory (e.g. `.ll/decisions.d/<uuid>.json`), id from `uuid.uuid4()`, merged by
directory union. Real precedent exists: the loop run-queue
(`scripts/little_loops/cli/loop/run.py` ~line 357 writes `.queue/<uuid>.json`;
`read_queue_entries()` in `cli/loop/_helpers.py` globs + unions). Collision-proof
by construction — distinct filenames never conflict on merge. Cost: a compaction/
read layer to present the union as one logical log, plus migration of the existing
flat `entries:` list.

**Option B**: **UUID-based ids**, keep the single shared `entries:` list, demote
`ARCHITECTURE-NNN` to a display-only label. Removes id *collisions* but does **not**
remove the git *content conflict* — both branches still append to the same list
tail, so `merge_epic_branch_to_base` still aborts. Weakest on its own.

**Option C**: **Custom git merge driver** — `.gitattributes` `merge=` for
`.ll/decisions.yaml` that unions `entries:` and renumbers colliding ids
deterministically. No `.gitattributes` or merge driver exists anywhere in the repo
today (new territory), and it must be installed per-clone (`git config
merge.<driver>.driver ...`) — brittle for a hook/loop that runs on fresh
worktrees.

**Option D**: **Atomic/namespaced id allocation** — mirror the flock reservation
pattern from `LockManager.acquire()` (`scripts/little_loops/fsm/concurrency.py`
~lines 114–142) or namespace ids by branch/issue (cf. `generate_from_completed()`
which already uses `id=f"DEC-{issue.issue_id}"` to sidestep the counter). Note the
BUG-1364 precedent: a reservation *write* cannot live in `list_entries()` /
`load_decisions()` because those run in read-only contexts. Solves collisions but,
like Option B, does not by itself resolve the shared-list-tail merge conflict.

**Recommended**: **Option A (append-only fragment files)** for v1 — it is the only
option that removes *both* the id collision *and* the git merge conflict at once,
and it reuses an existing, tested in-repo pattern (`.queue/<uuid>.json`) rather
than introducing merge-driver plumbing (Option C) or leaving the list-tail conflict
unaddressed (Options B/D).

> **Selected:** Option A (append-only fragment files) — only option that resolves both the id collision and the git merge conflict, reusing the tested `.queue/<uuid>.json` write + glob-union pattern.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-14.

**Selected**: Option A — Append-only fragment files

**Reasoning**: Option A is the only candidate that removes *both* failure modes at once — id collisions (distinct `uuid.uuid4()` filenames never collide) and the git content conflict (each decision is a distinct path, so `merge_epic_branch_to_base` never sees an overlapping `entries:` list tail). It ports a working, in-repo precedent — the loop run-queue's `.queue/<uuid>.json` write (`scripts/little_loops/cli/loop/run.py:355`) + `read_queue_entries()` glob-union (`cli/loop/_helpers.py:172`), an idiom that recurs across 7+ modules — and can reuse `atomic_write_json()` (`file_utils.py:35`). Options B and D only re-scheme the id and leave the shared-list-tail merge conflict — the actual reported symptom — unresolved; Option C has zero repo footprint (no `.gitattributes`/merge driver exists) and requires brittle per-worktree `git config` that `setup_worktree()` does not propagate.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — Append-only fragment files | 3/3 | 2/3 | 2/3 | 2/3 | 9/12 |
| B — UUID-based ids only | 2/3 | 3/3 | 2/3 | 1/3 | 8/12 |
| D — Atomic/namespaced id allocation | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |
| C — Custom git merge driver | 0/3 | 1/3 | 1/3 | 0/3 | 2/12 |

**Key evidence**:
- **Option A**: Working precedent in-tree (`.queue/<uuid>.json` write + `read_queue_entries()` glob-union); `atomic_write_json()` reusable. New glue in `decisions.py` (no directory-union code today) + migration of the flat `entries:` list is the only real cost (reuse score 2).
- **Option B**: Small, well-precedented id-minting edit (uuid idiom, `DEC-{issue_id}` shows non-counter ids already tolerated), but `save_decisions()` still rewrites the same shared list tail — the merge conflict is untouched by construction. Issue's own verdict: "weakest on its own" (reuse score 1).
- **Option D**: Reuses `LockManager.acquire()` flock sentinel + `atomic_write()`, but BUG-1364 evaluated this exact shape for the id-race and rejected it (3/12) because reservation writes leak into read-only `list_entries()`/`load_decisions()` callers; also leaves the git conflict unresolved (reuse score 2).
- **Option C**: No `.gitattributes`, merge driver, or `%O`/`%A`/`%B` usage anywhere in the repo; `setup_worktree()` propagates only `user.email`/`user.name`, so a driver would not travel to fresh worktrees/clones (reuse score 0).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/decisions.py` — `_cmd_add()` (~line 441) and
  `_cmd_extract_from_completed()` (~line 862): replace `len(existing) + 1` id
  minting with the chosen collision-free scheme.
- `scripts/little_loops/decisions.py` — `add_entry()` / `save_decisions()` /
  `load_decisions()` (lines 284–314): for Option A, add fragment-file write +
  directory-union read; keep the flat-file path as a compatibility/compaction target.
- `scripts/little_loops/worktree_utils.py` — `merge_epic_branch_to_base()`
  (lines 384–435): for Option C, or to add a `.ll/decisions.yaml`-specific
  auto-resolve/retry before the blanket `merge --abort`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/decisions.py` — `_cmd_list`, `generate` (via
  `generate_from_completed`), `sync`, `promote`, `suggest-rules` all read through
  `load_decisions()`/`list_entries()`.
- `scripts/little_loops/decisions_sync.py` — `sync_to_local_md()` consumes entries.
- `scripts/little_loops/cli/verify_decisions.py` — `ll-verify-decisions` loads via
  `load_decisions()`; must accept the new storage layout.
- `scripts/little_loops/parallel/orchestrator.py` —
  `_merge_epic_branch_to_base()` (~line 1353) thin caller of the merge helper.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `merge_epic_branch`
  state (the loop where `merge_failed` surfaces).
- `hooks/scripts/check-decisions-yaml.sh` — pre-commit / PreToolUse validator that
  inspects candidate `.ll/decisions.yaml` writes (ENH-2592).

### Similar Patterns (reuse)
- `scripts/little_loops/cli/loop/run.py` ~line 357 + `cli/loop/_helpers.py`
  `read_queue_entries()` — fragment-file write/union (Option A template).
- `scripts/little_loops/fsm/concurrency.py` `LockManager.acquire()` — flock
  reservation (Option D template).
- `scripts/little_loops/cli/issues/next_id.py` `cmd_next_id()` +
  `.issues/bugs/P2-BUG-1364-*.md` — the structurally identical id-race and its
  A/B/C option analysis (prior art).
- `scripts/little_loops/file_utils.py` `atomic_write()` — reusable atomic write.

### Tests
- Existing: `scripts/tests/test_decisions.py` (isolated `.ll/decisions.yaml`
  fixture), `scripts/tests/test_cli_decisions.py`, `scripts/tests/test_verify_decisions.py`,
  `scripts/tests/test_worktree_utils.py`, `scripts/tests/test_merge_coordinator.py`
  (`temp_git_repo` real-repo fixture, `pytest.mark.integration`).
- **New coverage needed** (none exists today): a dual-branch id-collision → merge
  repro using the `temp_git_repo` fixture (init → branch → diverge both
  `.ll/decisions.yaml` → merge → assert no conflict / distinct ids), and/or a
  `threading.Barrier(2)` in-process allocator-race test (idiom from
  `scripts/tests/test_concurrency.py`).

### Documentation
- `docs/guides/DECISIONS_LOG_GUIDE.md` — storage-layout / id-scheme change.
- `docs/development/MERGE-COORDINATOR.md`, `docs/ARCHITECTURE.md`,
  `docs/reference/API.md` — if the merge path or decisions API changes.
- `.claude/CLAUDE.md` — the `ll-issues` / `ll-verify-decisions` surface notes.

## Impact

- **Priority**: P2 — recurring; silently blocks EPIC merge-back for any epic that
  also logs a decision (which FEAT/EPIC captures do by default). Requires manual
  YAML conflict resolution each time, and the loop gives no diagnostic (see the
  companion observability gap, BUG-2643).
- **Risk of ignoring**: EPIC close-out stalls look like verify failures but are
  data conflicts; easy to misdiagnose.

## Related

- BUG-2643 — merge-step failures persist no diagnostic artifact (same run).
- ENH-2589 / `ll-verify-decisions` — decisions-log validation surface.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-14_

**Readiness Score**: 96/100 → GREENLIGHT
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- Moderate change surface: `load_decisions()`/`list_entries()` have 8+ call sites
  across `_cmd_list`/`generate`/`sync`/`promote`/`suggest-rules`,
  `decisions_sync.sync_to_local_md()`, `ll-verify-decisions`,
  `ParallelOrchestrator._merge_epic_branch_to_base()`, and the
  `auto-refine-and-implement.yaml` loop state — all must tolerate the new
  fragment-file storage layout without behavior drift.
- Moderate per-site depth: introducing a directory-union read layer plus
  migration/compaction of the existing flat `entries:` list is a shared-state
  change, not a mechanical substitution — no directory-union code exists in
  `decisions.py` today.
- Residual ambiguity: the compaction/read-layer design and the migration path
  for pre-existing flat-list entries are not fully specified in the issue —
  left to implementation-time design.

## Status

**Open** | Created: 2026-07-15 | Priority: P2

## Session Log
- `/ll:confidence-check` - 2026-07-14T00:00:00 - `f8f6ee6c-782e-4e4f-9f42-2985a2df8c9f.jsonl`
- `/ll:decide-issue` - 2026-07-15T02:38:03 - `e9655459-9230-48dc-8037-23646a30a6af.jsonl`
- `/ll:refine-issue` - 2026-07-15T02:33:51 - `cdf638ed-77f6-4e7d-bf02-35f33fa437d7.jsonl`
- `/ll:capture-issue` - 2026-07-15T02:26:46Z - session: sprint-refine-and-implement EPIC-2370 review
