---
id: ENH-2771
title: Key history tables on the stable numeric issue id, not the mutable TYPE-NNN string
type: ENH
priority: P2
status: open
discovered_by: capture-issue
discovered_date: 2026-07-24
captured_at: '2026-07-24T22:09:37Z'
labels:
- history
- session-store
- data-integrity
- schema
relates_to:
- BUG-2769
decision_needed: false
parent: EPIC-2791
---

# ENH-2771: Key history tables on the stable numeric issue id, not the mutable `TYPE-NNN` string

## Summary

An issue's numeric ID is immutable and globally unique across types; its **type**
is mutable metadata (an ENH is routinely promoted to a FEAT, a BUG reframed as an
EPIC). Every history table keys on the composite `TYPE-NNN` string, so a retype
silently splits one issue's history into two unrelated keys. This has already
happened seven times.

## Current Behavior

Retypes split history. Each of these has exactly one file on disk but two keys in
`.ll/history.db` (`issue_events` ∪ `issue_snapshots`):

| Num | On disk | Keys in DB |
|-----|---------|-----------|
| 1378 | `BUG-1378` | `BUG-1378`, `ENH-1378` |
| 1821 | `FEAT-1821` | `ENH-1821`, `FEAT-1821` |
| 1864 | `EPIC-1864` | `ENH-1864`, `EPIC-1864` |
| 1978 | `EPIC-1978` | `BUG-1978`, `EPIC-1978` |
| 2576 | `FEAT-2576` | `ENH-2576`, `FEAT-2576` |
| 2689 | `ENH-2689` | `ENH-2689`, `FEAT-2689` |
| 2705 | `FEAT-2705` | `ENH-2705`, `FEAT-2705` |

Three (2576, 2689, 2705) are from the last few weeks, so this is an active
pattern rather than legacy residue. Any query using the current key sees roughly
half of each issue's real history and reports no error.

## Expected Behavior

An issue's history is retrievable by its number regardless of how many times its
type changed, and the pre-retype rows remain attributable to the same issue.

## Motivation

`ll-issues next-id` allocates numbers globally with no type argument, which
already encodes the invariant: **the number is the identity, the type is a
label**. The schema contradicts that, and the cost is invisible — a split issue
returns partial history rather than failing, so it looks like a low-effort issue
instead of a mis-keyed one. Every consumer that reasons about effort, cycle time,
or prior corrections (`issue_effort()`, `ll-history-context`, go/no-go) reads the
truncated half.

This also subsumes most of `BUG-2769`: with a numeric key, a malformed
`id: 2756` or `id: "1294"` extracts to the correct row instead of mis-keying it.

## Proposed Solution

Add `issue_num INTEGER` as the stable join key **alongside** the existing
`issue_id TEXT` display column — join on the number, render the string.

Numeric-*only* is the tempting simplification but loses two things:

1. **`TYPE-NNN` is not always reconstructable.** `issue_type` is NULL in 30/1931
   `issue_events` rows and 15/480 `issue_snapshots` rows (~1.6% / ~3%), so those
   rows could never be rendered back to a display label.
2. **`search_index.ref` degrades.** It is a namespace shared across kinds, and a
   bare `2756` is a poor FTS token — it collides with line numbers, scores, and
   timestamps appearing in indexed content.

Sketch:

1. Migration adds `issue_num INTEGER` to `issue_events` and `issue_snapshots`,
   backfilled by extracting trailing digits from `issue_id`; index it.
2. Repoint the `issue_sessions` VIEW and the 8 code sites that query by
   `issue_id` (`grep -rn "WHERE issue_id" scripts/little_loops`) to join on
   `issue_num`.
3. Reads accept either form: normalize a caller-supplied `TYPE-NNN` or bare
   number to an integer at the API boundary.
4. `search_index` keeps its `TYPE-NNN` ref for display and FTS quality; add the
   number as a separate indexed token if lookup-by-number is wanted.

### Migration hazard — retype collisions

The dedup index `idx_issue_snapshots_dedup(issue_id, transition)` becomes
`(issue_num, transition)`, at which point the seven split numbers can collide.
`FEAT-2705|open` and `ENH-2705|open` are currently two distinct rows with
different timestamps; under a numeric key `INSERT OR IGNORE` would silently drop
one. The merge needs an explicit rule (keep earliest `ts`? keep the row whose
`issue_type` matches the file on disk?) rather than whichever-lands-first. Decide
this before writing the migration, and log what was merged.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Migration mechanism**: `_MIGRATIONS` (`session_store.py:378`) is a flat
  `list[str]` of raw SQL — `_apply_migrations()` (`session_store.py:1158`)
  splits each entry on `;` and executes it inside one `BEGIN IMMEDIATE`
  transaction. There is **no per-migration Python callback hook**, so the
  `issue_num` backfill must be expressible as SQL, not a Python loop, unless
  routed through the separate `_backfill_issues()`/`_backfill_snapshots()`
  Python pass (`session_store.py:3133`/`:3196`, called from `backfill()` at
  `:4718`). Since the transform is a simple trailing-digit extraction, SQLite's
  `substr()`/`instr()` can do it inline in the migration itself, e.g.
  `CAST(substr(issue_id, instr(issue_id, '-') + 1) AS INTEGER)` — no regex
  needed. Closest precedent for "add column + index in one migration": v12
  (`summary_nodes.level` + `idx_summary_nodes_cross_dedup`); closest precedent
  for "add column, prefer it, fall back to a legacy view for pre-migration
  rows": v16 (`session_id` + rebuilt `issue_sessions` VIEW,
  `session_store.py:630-669`).
- **`ll-verify-kinds` is a no-op for this migration**: it only scans
  `_MIGRATIONS` for `CREATE TABLE` statements
  (`cli/verify_kinds.py:25`, `_CREATE_TABLE_RE`) and checks the table name
  against `_KIND_TABLE`/`_KINDLESS_TABLES`. An `ALTER TABLE ADD COLUMN`
  migration — all this issue needs, since no new table is created — is
  invisible to it. Implementation Step 6 ("Verify `ll-verify-kinds` still
  passes") will trivially pass with no registration action required.
- **No `normalize_issue_id` helper exists yet** — grepping for
  `normalize_issue_id` and `parse_issue_id` across `scripts/little_loops`
  returns no hits. The closest prior art is `issue_parser.py`'s
  `get_next_issue_number()` prefix-union regex (`issue_parser.py:453-502`,
  matches `(?:BUG|ENH|FEAT|EPIC)-(\d+)`), which can be adapted for the
  normalize-on-read boundary helper. This issue and `BUG-2769` are both
  introducing this helper for the first time, not reusing an existing one —
  whichever lands first should own it.
- **Root cause of the NULL `issue_type` rows** (the 1.6%/3% cited under
  Proposed Solution): write paths are asymmetric in whether they fall back to
  filename-derived type when frontmatter `type:` is absent.
  `_backfill_issues()` (`session_store.py:3133`) calls
  `_derive_type_priority()` (`:3110`), which falls back to
  `_FILENAME_TYPE_RE = re.compile(r"(BUG|ENH|FEAT|EPIC)-(\d+)")`
  (`:3106`) when frontmatter has no `type`. `_backfill_snapshots()`
  (`:3196`) does **not** call this fallback — it sets
  `issue_type = fm.get("type")` directly (`:3223`) even though it already
  computes `issue_id` via the same filename regex a few lines earlier
  (`:3213-3217`). The three live/direct write paths
  (`SQLiteTransport.send()`'s `issue.*` branch at `:3011-3042`,
  `record_issue_event()` at `:1414`, `record_issue_snapshot()` at `:1361`)
  have no derivation at all — they take `issue_type` verbatim from the
  caller/frontmatter and write `NULL` if absent. Fixing this asymmetry is
  optional for `issue_num` (which derives from `issue_id`, not `issue_type`)
  but worth noting since a NULL `issue_type` row is exactly the case where
  `TYPE-NNN` reconstruction from `issue_num` alone would fail — reinforcing
  the "keep `issue_id` TEXT alongside `issue_num`" decision already made
  above.
- **Two more history-DB tables carry `issue_id` and are arguably in-scope**,
  not just the 8 sites in `history_reader.py`/`cli/session.py`: `orchestration_runs`
  (`session_store.py:798`, `issue_id TEXT NOT NULL`, `idx_orchestration_runs_issue_id`
  at `:812`) and `commit_events` (`:684`, `idx_commit_events_issue_id` at `:687`).
  Both live in the same `.ll/history.db` this issue targets (unlike
  `.ll/queue.db`, which Scope Boundaries correctly excludes) and have the same
  retype-split exposure as `issue_events`/`issue_snapshots`. Worth an explicit
  scope call: include them in the migration/repoint pass, or add them to Scope
  Boundaries' "Out of scope" list with a reason (e.g. lower query volume, no
  known split evidence yet, same caveat given for `search_index`).
- **Precise `WHERE issue_id` site count**: `history_reader.py` has 4
  (`related_issue_events` at `:571` and its session_id-filtered branch at
  `:608`, `sessions_for_issue` at `:1909`, `issue_effort` at `:1939` — plus
  `find_session_for_issue_transition` at `:588` and `recent_issue_velocity`
  at `:1956`, which the issue's "8 sites" count likely folds in), and
  `cli/history_context.py:313` is a 5th outside `history_reader.py` not
  currently listed in the Integration Map's Dependent Files.

## API/Interface

- `sessions_for_issue(issue_id)`, `issue_effort(issue_id)`, and
  `related_issue_events(issue_id)` keep their `TYPE-NNN` string signatures;
  normalization happens inside, so no caller changes.
- No CLI surface change — `ll-session recent --issue BUG-2705` keeps working and
  starts returning the pre-retype rows too.

## Implementation Steps

1. Decide the retype-collision merge rule.
2. Add the migration (`_MIGRATIONS` in `session_store.py`) with the backfill.
3. Add the normalize-on-read boundary helper (shared with `BUG-2769`'s
   `normalize_issue_id`).
4. Repoint the `issue_sessions` VIEW and the 8 `issue_id` query sites.
5. Test: a retyped issue returns unified history across both former keys; a
   `TYPE-NNN` and a bare-number lookup return identical rows.
6. Verify `ll-verify-kinds` still passes for any new table registration.

## Scope Boundaries

**In scope**: the `issue_num` column, its backfill, the retype-collision merge
rule, the `issue_sessions` VIEW, and the read-side normalization boundary in
`history_reader.py`.

**Out of scope**:
- Renaming issue **files** or frontmatter `id:` to a numeric form — the
  `TYPE-NNN` convention stays the user-facing identity everywhere (filenames,
  CLI args, `parent:`/`relates_to:`, commit messages, GitHub sync).
- The frontmatter-`id` validation and `ll-issues format-check` rule — that is
  `BUG-2769`. This issue makes those defects harmless; it does not replace the
  lint.
- The missing-`issue_events`-rows gap (`BUG-2770`). Re-keying does not create
  rows that were never written; fix that first or the backfill inherits the hole.
- Other `issue_id`-keyed tables outside the history DB (`.ll/queue.db`,
  `decisions.d` fragments) — no retype-split evidence there yet.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — `_MIGRATIONS`, `issue_sessions` VIEW,
  ingest sites
- `scripts/little_loops/history_reader.py` — `sessions_for_issue`, `issue_effort`,
  `related_issue_events`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/session.py` — `recent --issue`, `related`
- `scripts/little_loops/cli/history_context.py:313` — snapshot body lookup by
  `issue_id`, not previously listed here (found via research)
- `ll-history-context`, `ll-history` — per-issue reads

### Tests
- `scripts/tests/test_session_store.py` — migration + backfill
- `scripts/tests/test_history_reader.py` — retype unification

## Impact

- **Priority**: P2 — silent partial-history loss on an invariant the rest of the
  system already assumes.
- **Effort**: Medium — one migration, one VIEW, 8 query sites, plus the
  collision-merge decision.
- **Risk**: Medium — a schema migration on a 4 GB DB; the backfill is a pure
  regex derivation, but the dedup-index change is destructive if the merge rule
  is wrong.
- **Breaking Change**: No — external signatures keep taking `TYPE-NNN`.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | history-db producer/consumer flow |
| `docs/reference/API.md#little_loopssession_store` | schema + `_MIGRATIONS` |

## Session Log
- `/ll:refine-issue` - 2026-07-25T03:58:52 - `1386fb28-a538-4cb4-8530-41254608bcd9.jsonl`
- `/ll:capture-issue` - 2026-07-24T22:09:37Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/65a565ab-fdff-4457-9611-217b87d7512a.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P2
