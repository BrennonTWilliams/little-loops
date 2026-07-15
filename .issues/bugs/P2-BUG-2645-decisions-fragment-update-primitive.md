---
id: BUG-2645
title: Add a fragment-update primitive for in-place decision mutation (`set_outcome`,
  `_cmd_promote`)
type: BUG
status: done
priority: P2
parent: BUG-2642
discovered_date: '2026-07-15'
completed_at: '2026-07-15T15:06:45Z'
discovered_by: issue-size-review
decision_needed: false
confidence_score: 98
outcome_confidence: 86
score_complexity: 20
score_test_coverage: 20
score_ambiguity: 24
score_change_surface: 22
---

# BUG-2645: Add a fragment-update primitive for in-place decision mutation

## Summary

Decomposed from BUG-2642 (Option A: append-only fragment files). Depends on
BUG-2644 (fragment storage layer) landing first. Two call sites bypass
`add_entry()` and instead do `load_decisions()` → mutate one entry in place →
`save_decisions(entries, path)`, which assumes a single flat writable list.
Once entries live in per-uuid fragments (BUG-2644), that "rewrite the whole
log" shape is a hard compat break — this issue adds a targeted
fragment-update primitive so these two sites can mutate a single entry
without rewriting the entire log.

## Parent Issue

Decomposed from BUG-2642: Concurrent `.ll/decisions.yaml` appends collide on
ARCHITECTURE-NNN id and block EPIC merges.

## Depends On

BUG-2644 must land first — this issue requires the fragment storage layer
(`.ll/decisions.d/<uuid>.json` write + directory-union read) to exist before
a fragment-update primitive is meaningful.

## Scope

- `scripts/little_loops/decisions.py` — `set_outcome()` (~line 346): bypasses
  `add_entry()` — does `load_decisions()` → mutate one entry →
  `save_decisions(entries, path)` (~line 366). Add a targeted
  fragment-update (or legacy-file) primitive instead of a full-list rewrite.
- `scripts/little_loops/cli/issues/decisions.py` — `_cmd_promote()`
  (~line 891): same pattern — indexes and overwrites the full list
  (`entries[idx] = rule` ~line 928) then `save_decisions(entries, path)`.
  Same fix as `set_outcome()`.

## Tests

- `scripts/tests/test_wire_issue_static_layer.py` — 18 `save_decisions(...)`
  call sites (lines 113, 129, 137, …) plus its `decisions_path` fixture
  round-trip through the flat single-file shape; update to exercise the
  fragment-update primitive.
- Add coverage for `set_outcome()` and `_cmd_promote()` mutating a single
  fragment without touching sibling fragments.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Fragment storage layer (BUG-2644) has already landed

Commit `f5a97da9` ("append-only fragment storage for decisions log") is present
in the current tree, so the **Depends On** precondition is satisfied. Available
primitives in `scripts/little_loops/decisions.py` a fragment-update primitive
would build on:

- `_fragments_dir(log_path)` (`decisions.py:29`) — derives `.ll/decisions.d`
  from the flat path via `log_path.with_suffix(".d")`.
- `_load_fragments(frag_dir)` (`decisions.py:39`) — globs `*.json`, skips
  malformed fragments, sorts union by `(timestamp, filename)`, preserves
  duplicate ids (BUG-2642 collision surfacing).
- `load_decisions(path)` (`decisions.py:321`) — returns
  `legacy + _load_fragments(...)` (line 337): the flat-file ∪ fragment-dir union.
- `save_decisions(entries, path)` (`decisions.py:340`) — **the compaction
  point**: rewrites the whole flat YAML *and then deletes every fragment file*
  in `frag_dir` (lines 359–362).
- `add_entry(entry, path)` (`decisions.py:365`) — append-only single-fragment
  writer: `atomic_write_json(frag_dir / f"{uuid.uuid4()}.json", entry.to_dict())`
  (line 374). Closest analog to a per-fragment *update*, but writes a fresh uuid
  filename, not an existing one.

**No fragment-update primitive exists yet** (grep for `update_entry` /
`update_fragment` / `fragment_update` returns nothing).

### Corrected line references (issue body cites a pre-fragment-layer revision)

The fragment-layer code inserted at lines 29–61 shifted the two call sites down:

- `set_outcome()` — signature `decisions.py:406`; `load_decisions(path)` at
  **line 416**; mutation `entry.outcome = ...` at **line 425**;
  `save_decisions(entries, path)` at **line 426**. (Issue says "~line 346/366".)
- `_cmd_promote()` — signature `cli/issues/decisions.py:885`;
  `load_decisions(path)` at **line 889**; `entries[idx] = rule` at **line 922**;
  `save_decisions(entries, path)` at **line 923**. (Issue says "~line 891/928".)
  Note `load_decisions`, `save_decisions`, `RuleEntry`, `DecisionEntry` are
  **injected as parameters** (bound at the `cmd_decisions()` call site,
  `cli/issues/decisions.py:327–329`), not imported inside the function.

### Core design challenge

Fragments have **anonymous uuid filenames**; an entry returned by
`load_decisions()` carries no record of which fragment file (if any) backs it,
and an entry may live in the **flat file** (with no per-entry file to target)
*or* in a fragment. A fragment-update primitive must therefore: (a) locate the
`*.json` fragment whose deserialized `id` matches `entry_id`; (b) if found,
`atomic_write_json` only that file; (c) if the entry lives in the flat file
only, fall back to a flat-file rewrite. This id→fragment-file lookup is the new
capability neither `add_entry()` nor `save_decisions()` provides.

### Decision point — how to mutate a single entry

> **Selected:** Option A — a fragment-targeted `update_entry()` primitive preserves the append-only/merge-clean property; Option B is the unfixed status quo that reintroduces the BUG-2642 collision surface.

**Option A** — Add a fragment-targeted `update_entry(entry_id, mutate_fn, path)`
primitive: scan `.ll/decisions.d/*.json` for the fragment whose `id` matches,
apply the mutation, `atomic_write_json` **only that fragment** (sibling
fragments untouched); if the id resolves to the flat file instead, rewrite just
the flat file without clearing pending fragments. Preserves the append-only /
merge-clean property BUG-2642 exists to protect. More code + the flat-vs-fragment
branch.

**Option B** — Route both call sites through the existing `save_decisions()`
(status quo). Zero new code, but every `set_outcome`/`_cmd_promote` **collapses
all pending fragments into the flat file** (save_decisions clears `frag_dir`),
reintroducing the exact `.ll/decisions.yaml` merge-collision surface BUG-2642 /
the parent epic was created to eliminate — whenever a mutation on one branch
races a concurrent append on another.

**Recommended**: Option A — Option B defeats the parent issue's purpose;
mutations must not force a compaction that re-flattens divergent branches.

### Integration Map

**Files to Modify**
- `scripts/little_loops/decisions.py` — add `update_entry()` (or equivalent)
  primitive near `add_entry()` (`~line 365`); rewrite `set_outcome()`
  (`line 416–426`) to use it instead of `load_decisions()` → `save_decisions()`.
- `scripts/little_loops/cli/issues/decisions.py` — `_cmd_promote()`
  (`line 885–929`): replace `entries[idx] = rule; save_decisions(...)`
  (`lines 922–923`) with the new primitive (thread it through the injected-deps
  signature, or import it directly).

**Tests**
- `scripts/tests/test_wire_issue_static_layer.py` — `decisions_path` fixture
  (`lines 25–29`) returns the flat path only; ~16 `save_decisions([...],
  decisions_path)` seeding call sites (113, 129, 137, 144, 158, 173, 193, 201,
  210, 224, 238, 253, 258, 263, 273, 288). These exercise coupling-entry
  read-back and remain valid, but none exercise a fragment-resident mutation.
- **New coverage needed**: seed an entry via `add_entry()` (fragment-resident),
  then assert `set_outcome()` / promote mutates only its backing fragment and
  leaves sibling fragments byte-identical (no `frag_dir` clear).

### Implementation Steps

1. In `decisions.py`, add `update_entry(entry_id, mutate, path)` (Option A):
   iterate `_fragments_dir(path).glob("*.json")`, parse each, match on `id`,
   apply `mutate(entry)`, `atomic_write_json` that file; on flat-file-only
   residence fall back to a flat rewrite that does **not** clear `frag_dir`.
2. Rewrite `set_outcome()` (`decisions.py:416–426`) to locate + mutate via the
   new primitive, preserving the `TypeError` / `already has an outcome` guards.
3. Rewrite `_cmd_promote()` (`cli/issues/decisions.py:922–923`) to build the
   `RuleEntry` then persist via the new primitive.
4. Add fragment-isolation tests (see Tests above).
5. Run `python -m pytest scripts/tests/test_wire_issue_static_layer.py
   scripts/tests/ -k "decision" -v`.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-15.

**Selected**: Option A — fragment-targeted `update_entry(entry_id, mutate_fn, path)` primitive

**Reasoning**: Option A reuses the codebase's existing append-only primitives
(`atomic_write_json`, `_fragments_dir`, and `_load_fragments`'s parse/skip logic) and
its two mutation call sites (`set_outcome`, `_cmd_promote`) are structurally uniform, so
one primitive replaces both cleanly. Option B is not a real alternative — it is the current
*unfixed* code: both call sites already route through `save_decisions()`, whose contract
(asserted by `test_save_folds_fragments_and_clears_dir`) unconditionally wipes `frag_dir`,
concretely reproducing the exact BUG-2642 merge-collision window the parent epic exists to
eliminate. Option A's added cost (an id→fragment provenance lookup and a non-compacting
flat-file write path) is contained to two call sites and fully unit-testable.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (`update_entry` primitive) | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |
| Option B (route via `save_decisions`) | 1/3 | 3/3 | 2/3 | 0/3 | 6/12 |

**Key evidence**:
- Option A: `add_entry()` (`decisions.py:365-374`) is a direct precedent for single-fragment
  `atomic_write_json` writes; `_fragments_dir()`/`_load_fragments()` supply the scan/parse
  logic. New work is limited to id→source provenance and a fragment-preserving flat write.
- Option B: both call sites already call `save_decisions()` today; its fragment-clearing
  compaction (`decisions.py:359-362`, guarded by `test_save_folds_fragments_and_clears_dir`)
  destroys concurrently-appended fragments — i.e. "Option B" means "do not fix BUG-2645".

## Resolution

Added `update_entry(entry_id, mutate, path)` to `decisions.py` (Option A): a
fragment-targeted in-place mutation primitive that searches `.ll/decisions.d/*.json`
first (rewriting only the matching fragment via `atomic_write_json`), falling back
to a non-compacting flat-file rewrite that leaves pending fragments intact. Both
`set_outcome()` and `_cmd_promote()` now route through it instead of
`load_decisions()` → `save_decisions()`, so mutations no longer clear `frag_dir`
and reintroduce the BUG-2642 merge-collision window. Fragment-isolation coverage
added in `test_decisions_fragments.py` (`TestUpdateEntry`,
`TestSetOutcomeFragmentIsolation`).

## Status

**Done** | Created: 2026-07-15 | Completed: 2026-07-15 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-07-15T15:06:20 - `16ef4c6d-0dbb-4b52-8338-3f635c1e9fe8.jsonl`
- `/ll:ready-issue` - 2026-07-15T14:56:08 - `16ef4c6d-0dbb-4b52-8338-3f635c1e9fe8.jsonl`
- `/ll:decide-issue` - 2026-07-15T14:53:49 - `6958dabb-0e00-4c8c-8fcb-68b709b956b3.jsonl`
- `/ll:refine-issue` - 2026-07-15T14:50:56 - `de85b44b-b3b5-4561-9ab1-2406e6d079db.jsonl`
- `/ll:issue-size-review` - 2026-07-15T00:00:00 - `1e8c4ff4-aeb1-4a0e-ae31-59bf29c066dd.jsonl`
