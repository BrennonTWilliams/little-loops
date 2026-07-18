---
id: FEAT-2671
title: "F1-prereq (a) \u2014 Content-hash fragment store"
type: FEAT
priority: P2
status: done
captured_at: '2026-07-18T15:15:21Z'
completed_at: '2026-07-18T18:39:16Z'
discovered_date: 2026-07-18
discovered_by: capture-issue
parent: EPIC-2456
relates_to:
- FEAT-2672
- FEAT-2673
blocks:
- FEAT-2673
decision_needed: false
labels:
- token-cost
- caching
- tier-2
confidence_score: 96
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 18
size: Very Large
---

# FEAT-2671: F1-prereq (a) — Content-hash fragment store

## Summary

New `scripts/little_loops/prompts/fragment_store.py` (~40 LOC): compute a
SHA-256 content hash over the stable prompt fragments —
`(skill_body, system_prompt, tool_definitions)` — and skip re-serialization
when the key is stable across invocations. Adapted from
`BerriAI/litellm/litellm/caching/caching.py`. This is EPIC-2456 § Children
[TBD-8], the first of two cache-stability prerequisites that must land
before F1 (`cache_control: ephemeral`, FEAT-2673) is enabled: a cache
breakpoint is only worth paying the 1.25x write premium for if the block
under it is byte-stable, and the fragment store is what proves stability.

## Current Behavior

`PersistentExecutor._run_action()` (`scripts/little_loops/fsm/executor.py`)
re-interpolates and re-serializes the full action string on every invocation,
with no signal for whether the underlying skill body, system prompt, or tool
definitions were actually stable across the call. FEAT-2675's
`dedupe_stable_system_blocks()` produces `cache_control_candidates` for a
single call's message list but has no cross-call memory of which fragments
repeat — there is no `scripts/little_loops/prompts/` module and no
content-hash store anywhere in the codebase.

## Expected Behavior

A new `scripts/little_loops/prompts/fragment_store.py` module exposes
`fragment_key(skill_body, system_prompt, tool_definitions) -> str` (a
64-char SHA-256 hex digest) plus a small keyed store with `get`/`put` and a
hit-counter, wired read-only into `PersistentExecutor._run_action()` so
cross-call fragment stability can be measured without changing any emitted
prompt.

## Motivation

F1's savings model (0.1x reads vs 1.25x writes, ~12.5x differential per the
cookbook anchors in EPIC-2456) collapses if the marked blocks churn between
calls — every churn is a fresh 1.25x write with no read to amortize it. A
content-hash store gives the cache-marking oracle (FEAT-2673) a cheap,
deterministic stability signal, and independently saves re-serialization
work on the prompt-assembly path.

## Use Case

As the cache-marking oracle in FEAT-2673, I need a cheap, deterministic
signal for whether a prompt fragment was byte-identical to its prior
invocation, so I only pay the `cache_control: ephemeral` write premium on
fragments that are actually stable across calls.

## Impact

Blocks FEAT-2673 (`cache_control: ephemeral` marking) — without this
stability signal, F1's cache-marking oracle has no cheap way to tell stable
fragments from churning ones, risking paying the 1.25x write premium with no
read amortization. EPIC-2456 § Success Metrics tracks the F1 row this issue
is a prerequisite for.

## Implementation Steps

1. New module `scripts/little_loops/prompts/fragment_store.py` (~40 LOC):
   `fragment_key(skill_body, system_prompt, tool_definitions) -> str`
   (SHA-256 hex) plus a small keyed store with `get`/`put` and a
   hit-counter for measurement.
2. Hashing lives behind a small helper so F8's parent-prefix hoisting
   ([TBD-14]) can later share it via `lib/hashing.py` (EPIC-2456 Open
   Question #8 — share-or-duplicate decision is deferred to that capture;
   do not create `lib/hashing.py` speculatively here).
3. Wire into the prompt-assembly path — `PersistentExecutor._run_action()` in
   `fsm/executor.py` (~line 1487-1527), not `fsm/runners.py` — read-only
   first: record hit/miss, change no behavior.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

4. Create `scripts/little_loops/prompts/__init__.py` re-exporting `fragment_key`
   and the store class, mirroring `compression/__init__.py`'s `__all__` pattern.
5. **Resolved (2026-07-18):** the locked `tier0_traces` fixtures
   (`scripts/tests/fixtures/tier0_traces/*.json`, `usage_jsonl_v1` schema) are
   pure token-count/usage rows — `iteration`, `state`, `action_type`,
   `input_tokens`/`output_tokens`/`cache_read_tokens`/`cache_creation_tokens`,
   `model`, `timestamp`. No prompt content (`skill_body`/`system_prompt`/
   `tool_definitions`) exists in them to derive from, so an adapter over
   `state`/`action_type` would only synthesize placeholder strings from state
   names — not a genuine byte-stability signal. **Decision: build a new,
   purpose-built fixture set** (`scripts/tests/fixtures/fragment_store_traces/`)
   with actual `skill_body`/`system_prompt`/`tool_definitions`-shaped sample
   data modeling repeated-call patterns (same skill invoked across iterations
   with stable vs. churning fragments), not derived from `tier0_traces`. The
   hit-rate AC (see below) is reworded accordingly: "≥80% across the new
   `fragment_store_traces` fixture set modeling Tier 0-like repeated-call
   patterns," not literally replayed against the locked usage-only trace
   files.
6. Extend `scripts/tests/test_fsm_executor.py`'s `TestCompressionHook` (or add a
   sibling class) to assert the fragment-key call coexists with the ENH-2486
   guard and FEAT-2675 compression hook without altering the emitted `action`.
7. Add a `## little_loops.prompts` section to `docs/reference/API.md`.

## Files to Modify

- new `scripts/little_loops/prompts/fragment_store.py` (~40 LOC)
- new `scripts/little_loops/prompts/__init__.py` — re-exports `fragment_key` and
  the store class, mirroring `scripts/little_loops/compression/__init__.py`'s
  `__all__` re-export convention
- `scripts/little_loops/fsm/executor.py` — record-only wiring in
  `PersistentExecutor._run_action()` (~line 1487-1527, alongside the existing
  ENH-2486 prompt-size guard and FEAT-2675 compression hooks). Supersedes the
  earlier `fsm/runners.py` target: `DefaultActionRunner.run()` only sees the
  fully-interpolated action string and has no access to the pre-interpolation
  fragments, per this issue's own Codebase Research Findings below.
- new `scripts/tests/test_fragment_store.py`
- new `scripts/tests/fixtures/fragment_store_traces/` (manifest + sample
  fixture files with `skill_body`/`system_prompt`/`tool_definitions` fields,
  modeled on `scripts/tests/fixtures/tier0_traces/manifest.json`'s `_meta`
  shape — see fixture-gap resolution above)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` — `_run_action()` (line ~1466) is called
  internally by `_execute_learning_state()` (line 663), `_flush_pending_shell_state()`
  (line 1351), and `_run_action_or_route()` (line 1520); all callers are internal
  to `executor.py` — no external caller updates needed. [Agent 1 finding, confirmed
  via `ll-code callers-of` + Grep; codegraph index is stale as of 2026-06-02 so
  treated as a lead and verified]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — add a `## little_loops.prompts` section (there is
  currently only a `## little_loops.compression` section, ~line 7539, for the
  FEAT-2675 sibling); EPIC-2456's own Integration Map § Documentation already
  commits to this addition for the fragment store [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — extend `TestCompressionHook` (lines
  178-268) or add a sibling test class asserting the new record-only
  fragment-key call coexists with the ENH-2486 guard and FEAT-2675 compression
  hook without altering `runner.calls[0]` / the emitted `action` string and
  without double-firing, mirroring `test_guard_measures_uncompressed_size`
  (lines 250-268) [Agent 1 + Agent 3 finding]
- Fixture gap for the Tier 0 hit-rate AC — **resolved 2026-07-18** (see
  Implementation Steps Step 5): `scripts/tests/fixtures/tier0_traces/`
  (ENH-2518, `usage_jsonl_v1` rows: `state`/`action_type`/token counts) has no
  `skill_body`/`system_prompt`/`tool_definitions`-shaped fields to call
  `fragment_key()` on directly, and no adapter can derive real fragment
  content from it (the rows carry no prompt content at all). New fixture set
  `scripts/tests/fixtures/fragment_store_traces/` to be added by this issue,
  with a manifest mirroring `tier0_traces/manifest.json`'s `_meta` shape.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Wiring-target correction**: `fsm/runners.py`'s `DefaultActionRunner.run()`
  (`scripts/little_loops/fsm/runners.py:91`) only ever sees the
  fully-interpolated, already-compressed `action` string — it has no access
  to the pre-interpolation template or a structured message list. The actual
  single choke point for every action mode (prompt/shell/mcp/contract) is
  `PersistentExecutor._run_action()` in
  `scripts/little_loops/fsm/executor.py` (~line 1466), where the FEAT-2675
  heuristic compressor and the ENH-2486 prompt-size guard already hook in
  (lines ~1487-1527). The record-only fragment-key call in this issue's Step
  3 should live there, not in `runners.py` — `runners.py` can stay untouched
  unless `run/agent/tools` also need to flow into the key.
- **No `skill_body`/`system_prompt`/`tool_definitions` variables exist yet** —
  these are FEAT-2671/FEAT-2673 conceptual names, not current identifiers.
  The closest existing analogues are `state.agent` / `state.tools` on
  `StateConfig` (`scripts/little_loops/fsm/schema.py:564-565`, plain
  `str | None` / `list[str] | None` fields) and the interpolated `action`
  string itself (`fsm/executor.py:1484`, `interpolate(action_template, ctx)`).
- **Closest upstream stability signal**: FEAT-2675's
  `dedupe_stable_system_blocks()` (`scripts/little_loops/compression/heuristic.py:120`)
  already dedupes repeated `role == "system"` blocks and returns
  `cache_control_candidates` (output-list indices), with its `CompressedResult`
  docstring stating explicitly: *"Flagged for the separate F1 `cache_control`
  child to consume later — no `cache_control` marking happens in this
  module."* This is the direct precedent the fragment store's stability
  signal extends/generalizes.
- **SHA-256 keying convention** (model `fragment_key()` after this):
  `session_store._hash_args()` (`scripts/little_loops/session_store.py:1912-1918`)
  — `json.dumps(value, sort_keys=True, default=str)` (with `repr()` fallback
  for non-JSON-serializable input) piped into
  `hashlib.sha256(blob.encode("utf-8")).hexdigest()`. That call site truncates
  to `[:16]`; FEAT-2671's stated "SHA-256 hex" key should keep the full
  64-char digest since it's a stability/equality signal, not a storage key
  needing brevity.
- **Module/config precedent to follow** (sibling EPIC-2456 prereq,
  FEAT-2675, `status: done`): package layout is
  `scripts/little_loops/compression/{__init__.py, heuristic.py}` with
  `__init__.py` re-exporting the public surface. A parallel
  `scripts/little_loops/prompts/__init__.py` re-exporting `fragment_key`
  (and the store class) matches this convention. If a config gate is added
  (not required for a record-only first pass but likely needed for
  FEAT-2673), mirror `CompressionConfig`
  (`scripts/little_loops/config/features.py:528-558`): a `@dataclass` with
  `from_dict()` lenient-unknown-keys, wired at three sites —
  `config/core.py:226` (parse), `config/core.py:302-305` (property
  accessor), and `config/__init__.py` `__all__` re-export (a dedicated test,
  `test_config.py:2792-2796`, exists solely to catch a missing re-export).
- **No existing get/put + hit-counter store class** — searched for
  `class \w*Store\b`, `class \w*Cache\b`, `hit_count`, `self._hits`: no
  matches anywhere in `scripts/little_loops`. The closest analog is
  query-time aggregation over `history.db` rows in
  `scripts/little_loops/cli/ctx_stats.py:146-164` (`cache_hits` counter) and
  its hit-rate formula at `ctx_stats.py:294`:
  `cache_read / (cache_read + cache_write + uncached) * 100`. The in-memory
  `get`/`put`-with-counter class this issue specifies is a new shape for
  this codebase, not a pattern to copy — model the counter field names
  (`cache_hits`, `hit_rate_pct`) after `ctx_stats.py` for consistency when
  this feeds observability later.
- **Test-file precedent**: `scripts/tests/test_heuristic_compression.py`
  (FEAT-2675) is the direct model for `test_fragment_store.py` — one
  `Test<Behavior>` class per unit of behavior, loaders that `pytest.fail`
  (not `skip`) on a missing fixture so absence is a hard failure, and (for
  the Tier 0 hit-rate AC) fixture layout mirroring
  `scripts/tests/fixtures/heuristic_traces/manifest.json` /
  `scripts/tests/fixtures/tier0_traces/manifest.json`.
- **`scripts/little_loops/prompts/` does not exist yet** — this issue creates
  the directory from scratch, alongside its `__init__.py`.

## Acceptance Criteria

- [x] SHA-256 key stable across repeated serialization of identical inputs;
      changes when any of the three fragments changes (regression test).
- [x] Hit rate >= 80% across the new `fragment_store_traces` fixture set
      (purpose-built with `skill_body`/`system_prompt`/`tool_definitions`
      sample data modeling Tier 0-like repeated-call patterns — see Codebase
      Research Findings / fixture-gap resolution below; the locked
      `tier0_traces` set has no prompt-content fields to hash), per EPIC-2456
      Success Metrics (F1 row).
- [x] No behavior change to assembled prompts (record-only in this issue).

## Resolution

Implemented `scripts/little_loops/prompts/fragment_store.py` (`fragment_key()`
+ `FragmentStore`) and `scripts/little_loops/prompts/__init__.py`, wired
read-only into `PersistentExecutor._run_action()` (`fsm/executor.py`) ahead of
the ENH-2486 guard and FEAT-2675 compression hook, measured on the
pre-interpolation `action_template` plus `state.agent`/`state.tools` for
prompt-mode actions only. Added `scripts/tests/test_fragment_store.py`
(13 tests: key regression + store hit/miss + locked-trace hit-rate gate),
the purpose-built `scripts/tests/fixtures/fragment_store_traces/` fixture
set (81.8% hit rate over 22 modeled calls, clearing the 80% AC), a
`TestFragmentStoreHook` sibling class in `test_fsm_executor.py` asserting
coexistence with the guard/compression hooks without altering the emitted
action, and a `## little_loops.prompts` section in `docs/reference/API.md`.
No config gate added — record-only wiring needs none per this issue's own
Codebase Research Findings; a config gate is deferred to FEAT-2673 if needed.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-18_

**Readiness Score**: 96/100 → PROCEED
**Outcome Confidence**: 74/100 → Moderate

### Outcome Risk Factors
- Broad enumeration across 7 sites: new module, new package `__init__.py`,
  `fsm/executor.py` wiring, `test_fragment_store.py`, the new
  `fragment_store_traces/` fixture set, the `test_fsm_executor.py`
  extension, and the `docs/reference/API.md` section — the prior
  test-coverage gap (locked `tier0_traces` lacked fragment-shaped fields) is
  now resolved via the purpose-built fixture set (Implementation Steps Step
  5), but the site count itself keeps Complexity/Breadth in the moderate
  band even though each individual site is mechanical or local, not deep.

## Session Log
- `/ll:manage-issue` - 2026-07-18T18:38:52Z - `4c891f2d-0794-45eb-9d2e-bd5f91ef908b.jsonl`
- `/ll:ready-issue` - 2026-07-18T18:23:03 - `070da144-4d67-4cfd-824e-6a0f5da166d9.jsonl`
- `/ll:confidence-check` - 2026-07-18T17:30:00 - `34c9eeb7-5279-4efc-9db1-04ad53b7b69c.jsonl`
- `/ll:confidence-check` - 2026-07-18T17:20:00 - `44b1763f-b224-455d-ab1c-3555dbe27803.jsonl`
- `/ll:wire-issue` - 2026-07-18T17:16:00 - `a37bd5ea-7d88-4d25-a190-24efa6db05f2.jsonl`
- `/ll:refine-issue` - 2026-07-18T17:09:15 - `7ab4fd36-664c-4276-849d-42e519772d65.jsonl`
- `/ll:capture-issue` - 2026-07-18T15:15:21Z - captured from EPIC-2456 § Children [TBD-8] (source: thoughts/plans/2026-07-02-token-cost-reduction-architecture.md, Tier 2)

## Status

**Open** | Created: 2026-07-18 | Priority: P2
