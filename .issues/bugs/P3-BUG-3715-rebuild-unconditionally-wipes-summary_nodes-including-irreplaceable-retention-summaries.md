---
id: BUG-3715
type: BUG
title: rebuild() unconditionally wipes summary_nodes including irreplaceable retention
  summaries
priority: P3
status: open
relates_to:
- ENH-3698
- ENH-3666
- ENH-3678
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T17:46:14Z'
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3715: rebuild() unconditionally wipes summary_nodes including irreplaceable retention summaries

## Summary

`rebuild()` in `little_loops.session_store.lifecycle` deletes all `summary_nodes`, including `kind='retention'` rows that `compact()` created before `prune()` deleted their source `raw_events`. These retention records cannot be replayed after pruning. On compacted-but-unpruned stores, the same deletion leaves surviving `raw_events.summary_node_id` values dangling, and another `compact()` skips those already-compacted rows.

Preserve every retention row unchanged, continue rebuilding the other summary kinds and all spans, and make the derivation fingerprint detect non-usage deletion-predicate changes. This is a retention-preservation fix; transaction restructuring remains with ENH-3666.

## Current Behavior

- The wipe loop uses `_REBUILD_TABLE_PREDICATES`, but its only entry is the live-usage exception. Both summary tables are fully deleted inside `BEGIN IMMEDIATE`.
- Manual `ll-session rebuild`, `backfill --rebuild`, and `refresh --rebuild` can trigger this loss today. Automatic replay can also run when `rebuild_needed()` reports a stale store. The absence of a derive-version bump does not make the bug wholly latent.
- Hook/refresh rebuilds pass `config=None`, so leaf/condensed summaries are deleted without regeneration. Manual rebuild/backfill load raw project JSON and regenerate these summaries only when `history.compaction.enabled` is true.
- Enabled history compaction can make blocking host calls and launch the soft-threshold background summarizer while the rebuild write transaction is open. Handled host timeouts, nonzero exits, and parse failures escalate to deterministic truncation; only an unhandled exception rolls back the rebuild.
- `compute_fingerprint()` does not hash `_REBUILD_TABLE_PREDICATES`, so adding a retention predicate currently changes deletion semantics without changing the digest.

## Expected Behavior

- All retention nodes survive every successful rebuild with their IDs and every column unchanged, whether their raw rows remain, were pruned, or have a NULL session ID. Surviving raw rows retain their `compacted` flags and valid retention-node links.
- Leaf/condensed nodes and all `summary_spans` continue to be deleted and regenerated under the existing config gate. A span contains a `message_event_id`; retaining it across replacement of `message_events` would retain an obsolete reference.
- Hook, refresh, manual rebuild, and backfill paths agree on retention preservation. Document their existing conditional difference in derived-summary regeneration and the write-lock/LLM behavior.
- Non-usage predicate changes affect the derivation fingerprint without rewriting frozen historical provenance or triggering a derive bump before the size gate is available.

## Acceptance Criteria

- [ ] `compact(db, config=..., and_prune=True)` followed by two `rebuild(db)` calls preserves the complete retention-row snapshot, including `id`, `content`, timestamps, `level`, and all other columns. The fixture actually prunes source rows and includes multiple sessions, multiple retention ranges for one session, and a NULL-session retention row.
- [ ] `compact(..., and_prune=False)` followed by rebuild preserves the complete raw-event snapshot and retention snapshot; every non-NULL retention link still resolves to the original retention ID. A subsequent `compact()` creates no new summaries and compacts no additional rows when no raw data was added.
- [ ] Mixed retention, leaf, and condensed fixtures prove that only retention nodes survive unchanged. With `config=None`, old leaf/condensed nodes and all old spans are absent. With compaction enabled and deterministic stubs, leaf/condensed nodes are regenerated and all new span endpoints and parent links resolve to the correct regenerated nodes/messages. No new span or parent link targets a retention node.
- [ ] Repeated config-enabled rebuilds have equivalent logical derived summaries and graph structure under deterministic stubs. Compare retention rows exactly; normalize regenerated IDs/parent links/span links and exclude regenerated `created_at`. Production LLM content and regenerated IDs/timestamps are not promised to be identical.
- [ ] Config-enabled and config-omitted rebuilds leave identical retention snapshots. Cover the hook worker's `backfill_incremental(..., also_rebuild=True, config=None)` route with source discovery stubbed and the CLI's config forwarding using existing CLI tests. Stub host summarization and `_maybe_soft_threshold_summary` in config-enabled lifecycle tests; never spawn a real host.
- [ ] An injected failure after derived replacements and at least one metadata write, before commit, rolls back the summary tables, raw data, other rebuilt tables, and schema/derive/usage metadata together.
- [ ] Fingerprint tests prove that adding/changing a non-usage predicate changes the digest, usage-only predicate changes do not, and plain/annotated literal definitions are handled. Frozen legacy literal/digest pins remain unchanged; the historical source at `9cb4467d6` still recomputes to the existing frozen digest.
- [ ] The current fingerprint snapshot is regenerated in the same change. Follow the sequencing rule below: no `REBUILD_DERIVE_VERSION` bump before ENH-3698 lands; remove only a temporary BUG-3715 equality pin if the size gate is already present and preservation is proven.
- [ ] Update the rebuild docstring and CLI/API/architecture/history documentation with the retention exception, config-dependent regeneration, residual loss of derived summaries whose raw data was pruned, and current transaction behavior. Remove implemented ENH-3698 retention-loss warnings only after preservation is proven; retain write-lock and applicable LLM warnings.
- [ ] Focused regression/guard tests and the authoritative `python -m pytest scripts/tests/` suite pass.

## Motivation

Once raw rows are pruned, their retention records cannot be re-derived. These are deterministic count/session/time-range summaries, not copies of the original transcript. Losing them is permanent without an external backup. Preserving their IDs also prevents dangling pointers before pruning. Fixing this is a prerequisite for safe future derive-version bumps, and immediately protects explicit maintenance commands.

## Root Cause

`rebuild()` treats both summary tables as replayable caches. `compact()` writes a separate retention kind that does not participate in replay. `prune()` deletes only compacted raw rows, leaving cache cleanup to rebuild. The unconditional summary wipe therefore removes data that the replay path never writes.

### Invariants

| Data | Source / regeneration | Rebuild contract after this fix |
| --- | --- | --- |
| `kind='retention'` nodes | Deterministic `compact()` output; raw rows may no longer exist | Preserve all columns and IDs |
| `raw_events.compacted` / `summary_node_id` | Set by `compact()`; links target retention nodes | Leave unchanged |
| `kind='leaf'` / `kind='condensed'` nodes | History compaction over replayed messages; only reproducible logically while raw sources survive | Delete; regenerate only with enabled config |
| `summary_spans` | Written only for leaf nodes and current `message_events` IDs | Delete all; recreate with regenerated leaf/message IDs |
| `parent_id` edges | Written only among leaf/condensed nodes | Recreate with the derived graph |

Retention nodes have no spans or parent edges under the existing writers. Foreign-key enforcement is disabled and there are no cascades, so rebuild must clear derived references itself. AUTOINCREMENT sequences are not reset by `DELETE`; regenerated nodes cannot collide with retained IDs. Preserve all retention rows rather than selecting only those with missing raw sources. A new summary kind must declare whether it is replayable before being added to this contract.

## Proposed Solution

Add exactly the retention exception to the existing predicate dictionary:

```python
_REBUILD_TABLE_PREDICATES = {
    "usage_events": "channel IS NOT 'live'",
    "summary_nodes": "kind IS NOT 'retention'",
}
```

Keep the existing unconditional `summary_spans` wipe and transaction shape. No schema migration, new summary kind, new count key, or repair of previously lost nodes is needed. Do not add a span predicate: retention nodes have no spans to preserve, and message rows are replaced.

In `scripts/tests/rebuild_fingerprint.py`, include a stable, sorted serialization of `_REBUILD_TABLE_PREDICATES` excluding `usage_events` in the fingerprint payload **only when that filtered mapping is nonempty**. The legacy source already has the usage-only dictionary, so this rule preserves its existing digest. Extend `_literal()` to accept literal `ast.AnnAssign` definitions as well as `ast.Assign`, and fail clearly for a missing required constant. Update synthetic fingerprint fixtures to define the required mapping. Regenerate only the current snapshot; never regenerate `frozen_legacy_digest`.

## Program Design

### Types

- `_REBUILD_TABLE_PREDICATES: dict[str, str]` — existing mapping gains the `summary_nodes` predicate; adding an annotation is optional and supported by the fingerprint reader.
- Fingerprint payload — retains existing functions/tables/search-kind/DDL inputs and adds nonempty non-usage predicates in deterministic key order.

### Signatures

- `rebuild(db: Path | str = DEFAULT_DB_PATH, *, config: dict | None = None, max_sessions: int | None = None) -> dict[str, int]` — unchanged; existing wipe loop consumes the added predicate.
- `compute_fingerprint(sources: dict[str, str], manifest: dict[str, Any]) -> dict[str, Any]` — unchanged interface; include the predicate mapping in its digest input.
- `_literal(tree: ast.Module, name: str) -> Any` — support plain and annotated literal assignments; missing names remain errors.

### Call Path

- `hooks.session_start.handle` → detached `cli.backfill_worker.main` → `lifecycle.backfill_incremental(also_rebuild=True)` → `lifecycle.rebuild(config=None)`.
- `cli.session.main_session` rebuild/backfill branches → `lifecycle.rebuild(config=<raw project JSON>)`; refresh branch → `lifecycle.rebuild(config=None)`.
- `TestDeriveFingerprint` → `compute_fingerprint()` → `_literal()` / reachable function discovery → current digest comparison.

## Scope Boundaries

- Keep LLM calls and background-thread behavior unchanged; document them and leave restructuring with ENH-3666. This removes the earlier "move or document" implementation choice.
- Leaf/condensed summaries for fully pruned periods remain unrecoverable through replay and will still be deleted. Hook/refresh rebuilds still omit enabled history-compaction config. ENH-3666 already calls for deciding whether these summaries leave `_REBUILD_TABLES` and for taking `_compact_sessions` out of rebuild; these remain explicit residual concerns, not additional blockers on this fix.
- Do not restore already-deleted retention nodes, reset raw flags, preserve arbitrary corrupt graph edges, or change pruning/re-ingestion/dedup semantics. SQLite's retention index does not enforce uniqueness for NULL-session keys; this fix promises no new duplicates when repeating compact/rebuild without adding raw data.
- `cli.history.main_history` currently chooses a NULL-session root without filtering by kind, so a retention node can already be selected as a root. This pre-existing reader issue is outside the retention-wipe fix.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/lifecycle.py` — predicate dictionary, `_REBUILD_TABLES` comment, `rebuild()` docstring, derive-version safety comment if sequencing permits.
- `scripts/tests/rebuild_fingerprint.py` — `compute_fingerprint()` predicate input and `_literal()` annotated-literal support.
- `scripts/tests/test_enh3678_rebuild_derive_gate.py` — guard mutation/legacy tests, synthetic fixtures, snapshot regeneration guidance, conditional temporary-pin cleanup.
- `scripts/little_loops/session_store/rebuild_fingerprint.json` — current digest snapshot; preserve frozen legacy digest.
- `scripts/tests/test_session_store_lifecycle.py` — retention/rebuild regressions in `TestRebuild`, using `TestCompact` setup patterns and existing rollback patterns.
- `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/ARCHITECTURE.md`, `docs/guides/HISTORY_SESSION_GUIDE.md` — correct summary wipe lists and describe the current config/transaction contract.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/session.py` — rebuild/backfill config forwarding and refresh without config; update help wording only if needed for the documented contract.
- `scripts/little_loops/cli/backfill_worker.py` and `scripts/little_loops/hooks/session_start.py` — config-omitted automatic route inherits preservation; remove only implemented interim retention-loss warnings if ENH-3698 has landed.
- `scripts/little_loops/cli/doctor.py` — conditional cleanup of ENH-3698 retention-loss guidance if present; retain lock/compaction guidance.
- `scripts/little_loops/session_store/usage_refresh.py` — respects compacted-source flags/links; no behavior change.
- `scripts/little_loops/session_store/__init__.py` — no new export required; predicates are internal.
- Summary readers/exports retain access to preserved nodes; no new DAG integration for retention records.

### Similar Patterns

- The live-only `usage_events` exception (BUG-3530) preserves rows that cannot be replayed. Use the same existing predicate mechanism.

### Tests

- `scripts/tests/test_session_store_lifecycle.py` — `TestRebuild`, `TestCompact`, config-enabled compaction tests, and rollback/live-usage preservation patterns.
- `scripts/tests/test_enh3678_rebuild_derive_gate.py` — fingerprint changes, legacy pins, derive stamps, and hook routing.
- `scripts/tests/test_session_store_schema.py` — schema/index compatibility and existing dangling-link assertions; no DDL change expected.
- `scripts/tests/test_ll_session.py` — CLI forwarding/count contract; existing success totals keep their nine count keys.
- The current reachable-function count of 23 is a snapshot observation, not a design constraint. A predicate-only production fix need not change it; update function-set expectations deliberately if implementation changes reachability.

### Documentation

Update all four named documentation files and the rebuild docstring together. Enabled config regenerates only summaries supported by surviving replayed messages; config omitted/disabled clears non-retention summaries. Describe the existing long write transaction and possible host calls rather than claiming this fix removes them.

### Configuration

No new key or default. Manual commands currently load raw `.ll/ll-config.json` without local-override merging; preserve that behavior here. Keep the `rebuild()` signature and count keys unchanged.

## Implementation Steps

1. Add the retention-node predicate and update comments/docstring; keep the full span wipe and atomic replay.
2. Add non-usage predicate fingerprint coverage with the nonempty-only legacy-compatible rule, literal support, and guard mutation tests.
3. Add pruned/unpruned, mixed-kind, NULL-session/multiple-range, logical-repeatability, caller-parity, and late-failure rollback regressions. Use deterministic summary/thread stubs only where compaction is enabled.
4. Regenerate the current snapshot and apply the sequencing rule; preserve all frozen historical pins.
5. Update documentation and any already-implemented ENH-3698 warning surfaces. Run the focused lifecycle/fingerprint/schema/CLI tests, then the authoritative full suite.

### Sequencing

- ENH-3698 is open at review time. BUG-3715 may land first; it does not depend on the size gate to preserve rows during explicit or existing automatic rebuilds. In that order, regenerate the current fingerprint **without a derive-version bump**, retaining the existing size-gate equality pin.
- If ENH-3698 has landed first and re-anchored the temporary equality pin to BUG-3715, remove only that temporary pin in the proven preservation change and follow the normal bump rule for the changed non-usage selection. Keep the permanent frozen literal/digest pins.
- A derive-version bump requires both the size gate and retention preservation. A deletion-predicate change counts as changed selection semantics; the no-bump exception above is temporal, not an assertion that preservation is outside derivation.
- Remove ENH-3698's interim retention-loss warning from implemented hook/doctor/docs surfaces when this fix lands. If the size gate lands later, its implementation must check BUG-3715's resolved state and omit that now-obsolete warning. Neither issue blocks the other's implementation. Keep warnings about write locks, enabled LLM compaction, and the separate derived-summary limitations.

## Impact

- **Priority:** P3 — irreversible retention loss through existing maintenance/rebuild paths, and a prerequisite for future derive bumps.
- **Effort:** Medium — localized production fix plus fingerprint/legacy compatibility tests and documentation.
- **Risk:** Low-Medium — preserve one existing kind while retaining current replay behavior; fingerprint provenance and sequencing need deliberate verification.

## Steps to Reproduce

1. Create a temporary store with old raw events and retention gates set to zero; run `compact(db, config=..., and_prune=True)` and verify source rows were deleted.
2. Run `rebuild(db)` and observe that retention rows disappear.
3. Repeat with `and_prune=False`; observe that `raw_events.summary_node_id` points to missing nodes after rebuild and another `compact()` does not repair it.

Use temporary/copy stores for reproduction; do not rebuild a live project store to verify this bug.

## Pre-Implementation Review — 2026-10-03

Inspected `main` in the little-loops repository. Consolidated the accumulated research into the explicit contract above; earlier requirements to preserve retention spans, compare all summary rows exactly, and optionally restructure transactions are replaced.

- Temporary pruned fixture: retention count **1 → 0** after rebuild, with the source raw row already deleted.
- Temporary compacted-but-unpruned fixture: retention count **1 → 0**, leaving **one dangling raw-event summary link**.
- Temporary two-predicate experiment: preserving a synthetic retention span left **one dangling message endpoint**, confirming why the full span wipe must remain. Real retention writers create no spans.
- Two enabled rebuilds over the same short, deterministic input produced identical leaf content but IDs **1 → 2**; exact whole-table equality is an invalid requirement.
- Source mutation experiment: adding the retention predicate left the existing fingerprint unchanged. A temporary nonempty-only non-usage hashing experiment detected the predicate and preserved both the working-tree pre-fix digest and the legacy digest from `9cb4467d6`.
- Baseline: `python -m pytest scripts/tests/test_session_store_lifecycle.py scripts/tests/test_enh3678_rebuild_derive_gate.py -q` → **182 passed**. These are existing tests, not proof of the unimplemented fix.
- `/ll:advise` with `claude-opus-5-5` endorsed the retention-only fix, full span wipe, test-contract corrections, in-scope fingerprint repair, and documentation-only transaction criterion (**confidence 0.82**). Adopted its nonempty-only hashing rule after verifying legacy compatibility. Its dissent favored a separate predicate literal pin as a lower-risk guard alternative; the fingerprint repair is retained because it directly closes the unguarded selection input.
- Advisor proposals to add another bump prerequisite for config-omitted derived summaries were not adopted: this route and derived-summary loss already exist, and their contract/redesign is explicitly tracked with ENH-3666. The advisor's suggestion that the soft-threshold worker writes spans is unsupported by `_maybe_soft_threshold_summary`, which writes only condensed-node content/rows; tests still stub it to avoid asynchronous summary changes.

## Confidence Check Notes

_Reassessed by `/ll:confidence-check` on 2026-10-03 against the revised scope (fingerprint repair, full span wipe, test contract)._

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 75/100 → MODERATE

No gaps. Program Design gate, dependencies, parity/claim/structure/decision checks all clean; cited symbols (`_REBUILD_TABLE_PREDICATES`, `_literal`, `compute_fingerprint`, `rebuild`) resolve. Residual outcome risk is moderate breadth (~9 files incl. four docs) and the ENH-3698 sequencing rule, which depends on landing order at implementation time.

## Related

ENH-3698 (size gate and conditional warning cleanup), ENH-3666 (summary/transaction restructuring), ENH-3678 (landed derive gate), BUG-3530 (live-usage preservation precedent).

## Related Key Documentation

- `docs/reference/CLI.md` — `ll-session rebuild`.
- `docs/reference/API.md` — raw-event/rebuild/compact lifecycle.
- `docs/ARCHITECTURE.md` — summary/cache schema contract.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — session storage and summary tables.

## Session Log
- `/ll:confidence-check` - 2026-10-03T18:33:39 - `29c0951b-ecba-44fc-9c7a-bae598ad6c00.jsonl`
- `/ll:ready-issue` - 2026-10-03T18:31:01 - `93d9237c-0107-40d4-8cc6-a4173db603d9.jsonl`
- `/ll:advise` - 2026-10-03T18:31:01 - `93d9237c-0107-40d4-8cc6-a4173db603d9.jsonl`
- `/ll:confidence-check` - 2026-10-03T18:18:32 - `3953e906-c2cf-43f6-92f4-86a32eec7a1b.jsonl`
- `/ll:verify-issues` - 2026-10-03T18:17:24 - `d567e7da-49d1-4d07-b0d8-a9ed32fbd7f3.jsonl`
- `/ll:wire-issue` - 2026-10-03T18:14:21 - `ec3229f4-6ba4-4dad-bae3-1bd17c071032.jsonl`
- `/ll:refine-issue` - 2026-10-03T18:07:17 - `a59b3881-619f-461a-a4fb-79f07d2aebe7.jsonl`
- `/ll:format-issue` - 2026-10-03T18:01:26 - `6b27c7de-5d33-4c17-b3b7-3a7c6b15361b.jsonl`
- `/ll:capture-issue` - 2026-10-03T17:46:28 - `32f52444-a659-4ef8-933a-2361ae6c6aff.jsonl`

## Status

**Open** | Created: 2026-10-03 | Priority: P3
