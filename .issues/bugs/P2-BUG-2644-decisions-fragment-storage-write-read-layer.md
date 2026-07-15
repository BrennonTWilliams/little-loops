---
id: BUG-2644
title: Add append-only fragment storage (write + directory-union read) for `.ll/decisions.yaml`
  to remove id/merge collisions
type: BUG
status: done
priority: P2
parent: BUG-2642
discovered_date: '2026-07-15'
completed_at: '2026-07-15T14:47:29Z'
discovered_by: issue-size-review
confidence_score: 96
outcome_confidence: 75
score_complexity: 18
score_test_coverage: 21
score_ambiguity: 20
score_change_surface: 16
---

# BUG-2644: Add append-only fragment storage (write + directory-union read) for `.ll/decisions.yaml`

## Summary

Decomposed from BUG-2642 (Option A: append-only fragment files). This child
lands the **core storage layer**: id minting switches from a shared
"count on disk + 1" counter to `uuid.uuid4()`-based fragment files under
`.ll/decisions.d/<uuid>.json`, and reads go through a directory-union layer
so two divergent branches never write the same id or the same list-tail
region, eliminating both the id collision and the git merge conflict at the
source.

## Parent Issue

Decomposed from BUG-2642: Concurrent `.ll/decisions.yaml` appends collide on
ARCHITECTURE-NNN id and block EPIC merges.

## Current Behavior

`_cmd_add()` mints ids as `f"{prefix}-{len(existing) + 1:03d}"` (a recomputed
count with no persisted counter or cross-branch coordination), and
`save_decisions()` re-serializes the entire `entries:` list on every add. Two
divergent branches therefore mint the same id and edit the same end-of-file
region, producing both id collisions and a git merge conflict on
`.ll/decisions.yaml`.

## Expected Behavior

Id minting uses `uuid.uuid4()`-based fragment files under
`.ll/decisions.d/<uuid>.json`, and reads go through a directory-union layer that
presents the fragments (plus the legacy flat `entries:` list, for back-compat)
as one logical log. Two divergent branches never write the same id or the same
file region, so appends from different branches merge cleanly with no conflict
and no colliding ids.

## Steps to Reproduce

1. `git init` a repo with `.ll/decisions.yaml` containing N entries.
2. Branch, then on each of two branches run `ll-issues decisions add ...` so
   both mint `ARCHITECTURE-{N+1}` and append to the same list tail.
3. Merge one branch into the other.
4. Observe a git merge conflict on `.ll/decisions.yaml` and two entries sharing
   the same `ARCHITECTURE-{N+1}` id.

## Impact

Any two branches (e.g. concurrent epic children) that each append a decision
collide on both the minted id and the file region, blocking EPIC merges and
silently duplicating decision ids. This is the storage-layer root fix that
unblocks the collision reported in BUG-2642.

## Root Cause (from parent)

`scripts/little_loops/cli/issues/decisions.py::_cmd_add()` (~line 441) mints
`entry_id = f"{prefix}-{len(existing) + 1:03d}"` — a recomputed count with no
persisted counter, lock, or cross-branch coordination. `add_entry()` /
`save_decisions()` (`scripts/little_loops/decisions.py`, lines 284–314)
re-serialize the **entire** `entries:` list on every add, so both branches
edit the same end-of-file region.

## Scope

- `scripts/little_loops/cli/issues/decisions.py` — `_cmd_add()` (~line 441)
  and `_cmd_extract_from_completed()` (~line 862): replace `len(existing) + 1`
  id minting with `uuid.uuid4()`-based fragment ids.
- `scripts/little_loops/decisions.py` — `add_entry()` / `save_decisions()` /
  `load_decisions()` (lines 284–314): add fragment-file write (one file per
  decision under `.ll/decisions.d/`) and a directory-union read that presents
  the union as one logical log; keep the flat-file path readable for
  back-compat (legacy `entries:` list still loads).
- Migration/compaction of the pre-existing flat `entries:` list into fragments
  (or a dual-read that unions legacy file + fragment dir), keeping
  `load_decisions()` back-compat for `test_decisions.py`'s legacy-format
  fixtures. (Wiring Phase item 4 from parent.)

## Out of Scope (covered by sibling issues)

- In-place entry mutation (`set_outcome()`, `_cmd_promote()`) — BUG-2645.
- PreToolUse/pre-commit gate + `ll-verify-decisions` fragment awareness —
  BUG-2646.
- Docs/config updates — BUG-2647.

## Reuse Template

- `scripts/little_loops/cli/loop/run.py` ~line 357 (fragment write) +
  `cli/loop/_helpers.py::read_queue_entries()` (glob-union read) — Option A's
  in-repo precedent for both write and read sides.
- `scripts/little_loops/file_utils.py::atomic_write_json()` — reusable atomic
  write for fragment files.

## Tests

- New dual-branch id-collision → merge repro using the `temp_git_repo` fixture
  (init → branch → diverge both `.ll/decisions.yaml` → merge → assert no
  conflict / distinct ids) — mirrors `test_merge_coordinator.py`'s
  `pytest.mark.integration` style.
- Directory-union reader tests mirroring
  `scripts/tests/test_cli_loop_queue.py::TestReadQueueEntries` (lines 260–352):
  missing dir → `[]`, empty dir → `[]`, multi-fragment merge-sorted, malformed
  fragment skipped, plus a BUG-2642-specific fifth case — two fragments with
  duplicate/colliding `id` must not silently overwrite in the merged result.
  Fragment-write helper to copy: `TestQueueRemoveCommand._write_entry`
  (~line 358).
- `scripts/tests/test_decisions.py` — update legacy-format assertions: line
  164 `assert isinstance(data, list)`, lines 126/135/144 (raw `entries:` YAML
  corruption fixtures), `test_save_decisions_preserves_unmodeled_keys`
  (~line 197), `test_save_decisions_does_not_strip_unrelated_entry_extras`
  (~line 210) — re-expressed as `.ll/decisions.d/*.json` fragments.
- `scripts/tests/test_cli_decisions.py` — `test_add_decision`/
  `test_add_exception` (assert only `result == 0`) and
  `test_add_coupling_id_prefix` (~line 769) — review for id-generation
  call-signature change.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current source:_

### Files to Modify

- `scripts/little_loops/decisions.py` — write + read layer:
  - `load_decisions()` **lines 284–294** (cited range accurate). Already dual-shape
    aware: line 293 does `entries = data if isinstance(data, list) else
    data.get("entries", [])`, so a bare top-level list *and* an `entries:`-wrapped
    mapping both load. Extend to also glob-union `.ll/decisions.d/*.json` fragments
    onto the legacy-file entries.
  - `save_decisions()` **lines 297–307** — currently dumps the whole list as a bare
    top-level YAML list via `atomic_write(resolved, content)` (the **string**
    atomic writer, not `atomic_write_json`). New fragment write should use
    `atomic_write_json()` per the Reuse Template.
  - `add_entry()` **lines 310–314** — classic read-all → append → rewrite-all; this
    is the whole-file-rewrite the fragment write replaces.
- `scripts/little_loops/cli/issues/decisions.py` — id minting:
  - `_cmd_add()` def at **line 408**; id-mint at **line 441**
    (`entry_id = f"{prefix}-{len(existing) + 1:03d}"`, `existing` filtered at line
    434). Cited "~line 441" is exact.
  - `_cmd_extract_from_completed()` — **discrepancy flagged**: the id-mint statement
    `entry_id = f"{cat_prefix}-{len(existing_rules_typed) + 1:03d}"` is exactly
    **line 862** (matches the issue), but the function `def` is at **line 694**,
    ~168 lines earlier. The "~line 862" anchor points at the statement, not the def.

### Similar Patterns (Reuse — verified)

- Fragment WRITE: `scripts/little_loops/cli/loop/run.py` — `entry_id =
  str(uuid.uuid4())` at **line 357**, `queue_dir / f"{entry_id}.json"` at line 368,
  written line 369. Note: this precedent uses plain `write_text(json.dumps(...))`
  (non-atomic); prefer `atomic_write_json()` for decisions.
- Directory-union READ: `scripts/little_loops/cli/loop/_helpers.py::read_queue_entries()`
  **lines 172–200** — `if not queue_dir.exists(): return []`, globs `*.json`, per-file
  `try/except (json.JSONDecodeError, KeyError, FileNotFoundError, OSError): continue`
  (malformed-skip), then `entries.sort(key=lambda d: d.get("enqueuedAt", ""))`.
  `uuid.uuid4()` fragment naming currently exists *only* in this queue subsystem —
  BUG-2644 is the second adopter.
- Atomic write: `scripts/little_loops/file_utils.py::atomic_write_json(path, data)`
  **line 35** — mkdir parent, `json.dumps(data, indent=2, allow_nan=False)`,
  `json.loads` round-trip validation (raises `ValueError`), tempfile + `os.replace`.

### Tests (patterns verified)

- Union-reader tests to mirror: `scripts/tests/test_cli_loop_queue.py::TestReadQueueEntries`
  **lines 260–352** — writes raw fragments with `.write_text(json.dumps(...))`
  (decoupled from writer), reverse-write-then-assert-sorted-order idiom, literal
  `bad.json` malformed case. Write helper `TestQueueRemoveCommand._write_entry`
  **lines 362–378** (`@staticmethod`, returns `Path`).
- Dual-branch merge repro: `scripts/tests/test_merge_coordinator.py` — module-level
  `pytestmark = pytest.mark.integration`, `temp_git_repo` fixture (lines 18–56),
  `_setup_conflict_repo` (lines 2286–2334) diverges the *same file* on main vs a
  `git worktree add -b` branch. Direct analogue for the id-collision → merge repro.
- `test_decisions.py` legacy assertions to re-express, and `test_cli_decisions.py`
  id-generation call sites — as cited in the Tests section above (unchanged).

### Configuration

- `scripts/little_loops/config-schema.json` — `decisions.log_path` at **line 577**
  (default `.ll/decisions.yaml`). Fragment dir can be *derived* (`.ll/decisions.d/`)
  from `log_path` rather than adding a new schema key. (Config/docs edits are
  BUG-2647 scope; recorded here only for the read/write layer's path resolution.)
- `scripts/little_loops/config/features.py` — **`DecisionsConfig` dataclass, `log_path`
  field ~line 509** (`from_dict` default ~line 523). This is the *Python model* the
  schema key maps to and the value `generate_from_completed()` / CLI handlers resolve
  the log path from; the derived `.ll/decisions.d/` path must come off this field. The
  issue previously cited only the JSON schema — the runtime resolution goes through this
  dataclass. [Agent finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue` — in-scope read/write-layer consumers not yet
listed (sibling-owned consumers deliberately excluded, see note below):_

- `scripts/little_loops/decisions_sync.py` — **direct importer of the private
  `_DEFAULT_LOG_PATH`** from `little_loops.decisions`, and its `_resolve_path()`
  **duplicates `decisions.py::_resolve_path()` verbatim**. `sync_to_local_md()` reads
  active rules via `list_entries()` / `resolve_active()`, so it must see the fragment
  union, not just the legacy flat file. When the read layer learns `.ll/decisions.d/`,
  this second copy of path-resolution must be updated in lockstep (or resolution
  centralized in `decisions.py` and imported). [Agent 1 + Agent 2 finding]
- `scripts/little_loops/decisions.py::generate_from_completed()` — **in-file caller**
  that computes `log_path = project_root / config.decisions.log_path` and passes it
  into `load_decisions()` / `add_entry()`; its `existing_issue_ids` dedup depends on
  the union view being visible. Must consume the directory-union read, not the flat
  file alone. Same-file change but a distinct call site from `_cmd_add()`. [Agent 2 finding]

_Out-of-scope consumers confirmed (do NOT edit here — sibling issues own them):_
`cli/verify_decisions.py` (its own `_resolve_log_path()` re-declares `_DEFAULT_LOG_PATH`;
malformed-fragment `json.JSONDecodeError` is outside its `(yaml.YAMLError, KeyError,
ValueError)` catch tuple) → **BUG-2646**; `hooks/scripts/check-decisions-yaml.sh` +
`.pre-commit-config.yaml` regex `^\.ll/decisions\.yaml$` (won't match fragment files) →
**BUG-2646**; all docs (`DECISIONS_LOG_GUIDE.md`, `CONFIGURATION.md`, `API.md`,
`ARCHITECTURE.md`, `.claude/CLAUDE.md`, `.gitignore` comment) → **BUG-2647**.
CLI-boundary-insulated (JSON output only, no change if format preserved):
`skills/wire-issue/static-coupling-layer.md`, `.loops/distill-decisions.yaml`.

### Tests (wiring pass additions)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_wire_issue_static_layer.py` — **calls `save_decisions()`** directly
  to seed coupling entries for `load_coupling_entries()` filtering tests; will exercise
  the new fragment-write path. Review/update its `save_decisions()` fixtures once writes
  emit fragments. [Agent 1 + Agent 3 finding]
- `scripts/tests/test_cli_decisions.py` — beyond the already-listed cases, **assert
  uuid-shape ids** (`re.match(r"^[0-9a-f-]{36}$", entry_id)`) on any `add` /
  `extract-from-completed` invocation that omits `--id` and lets the code mint the id.
  Tests that pass `id=` explicitly (`_make_decision("ARCH-001", ...)`) are unaffected.
  [Agent 3 finding]

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation of the read/write layer:_

1. Derive the `.ll/decisions.d/` fragment dir from
   `config/features.py::DecisionsConfig.log_path` (not a hardcoded literal), so a
   custom `log_path` still lands its fragments in a sibling dir.
2. Route `decisions_sync.py`'s read path (`list_entries()` / `resolve_active()` in
   `sync_to_local_md()`) through the directory-union reader, and reconcile its
   duplicated `_resolve_path()` / `_DEFAULT_LOG_PATH` import with the new resolution
   (centralize in `decisions.py` or update both copies together).
3. Ensure `generate_from_completed()`'s `existing_issue_ids` dedup reads the union view
   (legacy file + fragments), not the flat file alone.
4. Union reader must **skip malformed fragments** (mirror `read_queue_entries()`'s
   `try/except (json.JSONDecodeError, KeyError, FileNotFoundError, OSError): continue`)
   so a bad `.ll/decisions.d/*.json` does not propagate an uncaught `json.JSONDecodeError`
   out of `load_decisions()`. (Gate/verify awareness of that skip is BUG-2646.)
5. Update `test_wire_issue_static_layer.py` `save_decisions()` fixtures and add
   uuid-shape id assertions in `test_cli_decisions.py` (see Tests section).

## Status

**Done** | Created: 2026-07-15 | Completed: 2026-07-15 | Priority: P2

## Resolution

Implemented the append-only fragment storage layer:

- `decisions.py`: `add_entry()` now writes one `.ll/decisions.d/<uuid>.json`
  fragment via `atomic_write_json()` instead of rewriting the flat file;
  `load_decisions()` unions the legacy flat `entries:` list with the fragment
  dir (derived from `log_path` via `_fragments_dir()`), skipping malformed
  fragments (mirrors `read_queue_entries()`); colliding ids are both preserved.
  `save_decisions()` became the compaction point — it folds the union into the
  flat file and clears the fragment dir so loads never double-count.
- `cli/issues/decisions.py`: `_cmd_add()` and `_cmd_extract_from_completed()`
  mint `uuid.uuid4()` ids instead of `len(existing)+1`, eliminating the
  cross-branch id collision.
- `decisions_sync.py` / `generate_from_completed()` see the union automatically
  (they read through `load_decisions()`/`list_entries()`), so no lockstep change
  was needed.
- Tests: new `test_decisions_fragments.py` (union-reader cases + dual-branch
  git-merge repro proving no conflict / distinct ids); updated `test_cli_decisions.py`
  id-shape and flat-file assertions.

Sibling issues BUG-2645/2646/2647 cover in-place mutation, gate awareness, and docs.

## Session Log
- `/ll:manage-issue` - 2026-07-15T14:46:51 - `3ef06488-c663-4245-b1b5-81db09e39bcf.jsonl`
- `/ll:ready-issue` - 2026-07-15T14:34:05 - `6ed6367f-5af8-43e0-9def-0b1bcb62c9a2.jsonl`
- `/ll:wire-issue` - 2026-07-15T14:31:12 - `499b3278-6e00-4861-99a3-95fd0966aa5d.jsonl`
- `/ll:refine-issue` - 2026-07-15T14:25:14 - `65c44868-244f-47bb-9e94-6a5d9a86bee0.jsonl`
- `/ll:issue-size-review` - 2026-07-15T00:00:00 - `1e8c4ff4-aeb1-4a0e-ae31-59bf29c066dd.jsonl`
