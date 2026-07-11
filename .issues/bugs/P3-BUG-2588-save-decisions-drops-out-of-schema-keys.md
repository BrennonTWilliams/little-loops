---
id: BUG-2588
title: save_decisions() silently drops entry keys not declared on the dataclass
type: BUG
status: open
priority: P3
discovered_date: '2026-07-10'
discovered_by: user-report
captured_at: '2026-07-10T21:08:10Z'
labels:
- decisions
- data-integrity
- serialization
- latent
decision_needed: true
confidence_score: 97
outcome_confidence: 86
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 22
---

# BUG-2588: `save_decisions()` silently drops entry keys not declared on the dataclass

## Summary

In `scripts/little_loops/decisions.py`, each entry dataclass
(`RuleEntry`, `DecisionEntry`, `ExceptionEntry`, `CouplingEntry`) implements
`from_dict`/`to_dict` with **fixed field lists**. `save_decisions()` does a full
load-mutate-dump (`load_decisions()` -> `to_dict()` -> `yaml.dump`) of the entire
file on every append. Any top-level key present in the YAML but not enumerated on
the matching dataclass is read into nothing by `from_dict` and never re-emitted by
`to_dict` — so it is **silently deleted on the next rewrite**.

Because `add_entry()` calls `save_decisions()`, adding one entry can quietly strip
extra fields from *unrelated* entries elsewhere in the file.

## Impact

- **Priority**: P3 — no live data loss today (audit found zero out-of-schema keys
  across all 331 entries on 2026-07-10), but the bug is a silent-data-loss trap that
  fires the moment anyone hand-adds a field the dataclass does not know about. Common
  pattern given entries are sometimes authored by hand.
- **Effort**: Small-Medium — Option A adds a single `extra: dict` field to four entry
  dataclasses plus uniform `from_dict`/`to_dict` updates; Option B modifies one function
  (`save_decisions`) and reuses the existing `deep_merge` utility.
- **Risk**: Low — round-trip change is additive (preserves previously-discarded data);
  the lossy `test_promote_drops_decision_only_fields` test (`scripts/tests/test_cli_decisions.py:1078`)
  must stay green (promote flow is intentionally lossy on its target field set).
- **Breaking Change**: No — `save_decisions` continues to emit modeled fields; new
  behavior is the additional preservation of unmodeled keys.

## Root Cause

- **File**: `scripts/little_loops/decisions.py`
- **Anchors**: `RuleEntry.from_dict`/`to_dict`, `DecisionEntry.from_dict`/`to_dict`,
  `ExceptionEntry.from_dict`/`to_dict`, `CouplingEntry.from_dict`/`to_dict`;
  `save_decisions()`.
- **Cause**: `from_dict` pulls a fixed set of `data.get(...)` keys and discards the
  rest; `to_dict` emits only the enumerated keys. The round-trip is therefore lossy
  for any unmodeled key. `save_decisions` rewrites the whole file, so the loss is
  applied globally, not just to the entry being added.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/decisions.py` — extend each entry's `from_dict`/`to_dict` to preserve unmodeled keys **or** rewrite `save_decisions` to merge raw dicts with modeled fields (see `## Codebase Research Findings` below for the two competing approaches)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/decisions.py:408` — `_cmd_add` calls `add_entry`, the lossy rewrite entry point
- `scripts/little_loops/cli/issues/decisions.py:694` — `_cmd_extract_from_completed` calls `add_entry` in a loop (LLM extraction flow)
- `scripts/little_loops/decisions.py:382` (`generate_from_completed`, calls `add_entry` per completed issue at line 430)
- `scripts/little_loops/decisions.py:334` — `set_outcome` calls `save_decisions` after in-place mutation
- `scripts/little_loops/decisions_sync.py` — reads via `list_entries` only; no change needed
- `scripts/little_loops/cli/verify_decisions.py` — consumes `load_decisions()`; no change needed (will not catch unknown keys until ENH-2587 lands)

### Similar Patterns (precedents in this codebase)
- `scripts/little_loops/events.py:31-62` — `LLEvent` already implements lossless round-trip via a `payload: dict[str, Any]` catch-all field (Option A precedent)
- `scripts/little_loops/init/writers.py:123-145` — `merge_with_existing` (BUG-2310 precedent) implements "preserve by default, drop opt-in via --force" via `deep_merge` (`scripts/little_loops/config/core.py:48-75`) (Option B precedent)
- `scripts/little_loops/fsm/fragments.py:137-148` — `dict.copy()` + `pop()` pattern separates known vs. unmodeled keys before deep merge (Option A variant)
- `scripts/little_loops/frontmatter.py:191-214` — `update_frontmatter` is the established raw-YAML-edit primitive; 20+ sites use it for "change one thing, keep everything else" (Option B variant)

### Tests
- `scripts/tests/test_decisions.py:181-188` — `test_round_trip_preserves_fields` is the closest existing analogue for round-trip assertion shape (but asserts only modeled-field equality)
- `scripts/tests/test_decisions.py:337-348` — `test_scope_and_optional_fields_round_trip` (DecisionEntry analog)
- `scripts/tests/test_decisions.py:778-806` — CouplingEntry round-trip tests (`test_round_trip`, `test_to_dict_omits_none_*`)
- `scripts/tests/test_init_core.py:1475-1535` — `test_apply_preserves_unmodeled_keys` + `test_apply_force_drops_unmodeled_keys` (BUG-2310) — model new tests after this
- _Suggested new tests in `scripts/tests/test_decisions.py`_: `test_save_decisions_preserves_unmodeled_keys` plus a per-entry-type variant asserting the bug's repro (entry with `owner: alice` survives `load → save → load` byte-equivalent) AND a cross-entry variant proving adding one entry does not strip fields from unrelated entries

### Documentation
- `docs/guides/DECISIONS_LOG_GUIDE.md:322` — already invites hand-editing ("Run it manually after editing `.ll/decisions.yaml` directly"); needs an explicit statement that round-trip preserves unknown keys
- `docs/ARCHITECTURE.md` (decisions subsystem entry) — may need a brief note on preservation semantics

### Configuration
- `.ll/decisions.yaml` — live log; 331 entries audited on 2026-07-10 with **zero** out-of-schema keys, so no production data is currently lossy
- `scripts/little_loops/config-schema.json:563` — `decisions` config block (`enabled`, `log_path`, `auto_generate`); unchanged by this fix

## Steps to Reproduce

1. Add a top-level key to any entry in `.ll/decisions.yaml` that is not on the
   corresponding dataclass (e.g. add `owner: alice` to a `rule` entry).
2. Trigger any write path, e.g. `add_entry(...)` (or `load_decisions()` followed by
   `save_decisions()`).
3. Re-open `.ll/decisions.yaml`: the `owner` key is gone, with no error emitted.

## Expected Behavior

Round-tripping an entry through `load_decisions()`/`save_decisions()` preserves all
of its data, or fails loudly if a key cannot be represented — it should never
silently discard fields.

## Current Behavior

Unmodeled keys are dropped on the first rewrite, silently and globally.

## Proposed Solution

Preserve unknown keys through the round-trip. Options:

- Capture leftover keys in `from_dict` (e.g. an `extra: dict` catch-all) and re-emit
  them in `to_dict`.
- Or store the raw source dict on the entry and merge modeled fields over it when
  serializing.

Optionally pair with a schema check (see ENH-2587) so genuinely invalid keys are
surfaced rather than tolerated.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Behavior summary.** `save_decisions` (`scripts/little_loops/decisions.py:285`) writes via `yaml.dump([e.to_dict() for e in entries], ...)`, after `load_decisions` (`scripts/little_loops/decisions.py:272`) has already discarded unknown keys via `_entry_from_dict` → `<EntryCls>.from_dict`. The four entry dataclasses (`RuleEntry` line 51, `DecisionEntry` line 99, `ExceptionEntry` line 152, `CouplingEntry` line 196) hard-code their field lists in `from_dict`/`to_dict`, so any unmodeled key is read into nothing and re-emitted as nothing. No test today asserts preservation of unmodeled keys; `test_promote_drops_decision_only_fields` (`scripts/tests/test_cli_decisions.py:1078-1116`) actually codifies loss as desired behavior for the promote flow.

**Codebase precedents.**
- `LLEvent` (`scripts/little_loops/events.py:31-62`) — lossless round-trip via `payload: dict` catch-all → direct precedent for Option A.
- `merge_with_existing` / `deep_merge` (`scripts/little_loops/init/writers.py:123-145` ← `scripts/little_loops/config/core.py:48-75`) — BUG-2310 "preserve by default, drop opt-in via --force" → direct precedent for Option B.
- `update_frontmatter` (`scripts/little_loops/frontmatter.py:191-214`) — established raw-YAML-edit primitive, 20+ call sites.

### Option A — `extra: dict` catch-all field on the entry dataclasses

> **Selected:** Option A — `extra: dict` catch-all field on the entry dataclasses — direct precedent in `LLEvent.payload` (`events.py:43,51,62`); symmetric load/save with no read-before-write coupling, no list-alignment logic, no concurrent-write exposure.

Add `extra: dict[str, Any] = field(default_factory=dict)` to each entry dataclass. `from_dict(cls, data)` does `copy = dict(data); known = {k: copy.pop(k, None) for k in _KNOWN_FIELDS}; known["extra"] = copy; return cls(**known)`. `to_dict` returns `{**self.extra, ...modeled_fields}` so unmodeled keys re-emit at the top level (not nested). Mirrors `LLEvent.payload`.

**Pros.** Symmetric on load and save; `entry.extra["owner"]` exposes residue to consumers; `save_decisions` itself is unchanged; each entry's `from_dict`/`to_dict` becomes uniform.
**Cons.** New dataclass field on every entry type (visible in `repr`, present in `dataclasses.asdict()`, becomes part of constructor identity — `extra=` shows up in kwargs). Touches every `from_dict`/`to_dict` + every constructor site. Couples preservation to the entry shape rather than the save layer.

### Option B — Raw source-dict overlay on `save_decisions`

Rewrite `save_decisions` to `yaml.safe_load()` the existing file, align raw entries to dataclass entries by `id`, `deep_merge(raw_entry, e.to_dict())` per entry, then `yaml.dump` the merged list. Dataclasses stay untouched; `load_decisions` stays untouched (its lossy load is fine because `save_decisions` is now raw-dict-aware on write). Mirrors `merge_with_existing` + `deep_merge` (BUG-2310).

**Pros.** Zero dataclass changes — `RuleEntry`, `DecisionEntry`, etc. stay byte-identical. Leverages the existing `deep_merge` utility (no new helper). "Preserve by default" matches the BUG-2310 contract. Only one function changes (`save_decisions`). Round-trip identity (key order, formatting) preserved up to `yaml.dump` semantics.
**Cons.** `save_decisions` now reads the file before writing — couples save to YAML I/O on the read path (worse unit-testability in isolation). Positional ordering of entries becomes keyed-by-`id` rather than list-order — alignment strategy changes. Fits `set_outcome`/`add_entry` ergonomics less cleanly: in-memory dataclass state and on-disk raw dict can drift if anyone hand-edits between load and save.

### Sibling / Follow-On

- ENH-2587 (`validate-decisions-yaml-schema-on-commit`) is the schema-validation sister. Pairing: once the round-trip preserves unknown keys, ENH-2587 governs *which* keys are valid; this fix is the substrate ENH-2587 was missing.
- ENH-2589 (`ll-verify-decisions`), ENH-2590 (pre-commit), ENH-2591 (pytest CI gate), ENH-2592 (PreToolUse) all rely on `ll-verify-decisions`, which does not currently catch unknown keys — they will continue to pass with no out-of-schema detection until ENH-2587 lands.

## Acceptance Criteria

- A round-trip test adds an out-of-schema key to each entry type, runs
  `load_decisions()` -> `save_decisions()`, and asserts the key survives unchanged.
- `add_entry()` on a file containing entries with extra keys leaves those extra keys
  intact.
- No existing decisions.yaml data is reformatted away by the change.

## Notes

- Surfaced while investigating the `OTHE-203` decisions.yaml corruption on
  2026-07-10 and discussing prevention (routing writes through the serializer vs. a
  validation hook). Sibling: ENH-2587.

## Status

**Open** | Created: 2026-07-10 | Priority: P3

Latent bug — no live data loss detected (audit on 2026-07-10 found zero out-of-schema
keys across all 331 entries). Tracked as a silent-data-loss trap awaiting the first
hand-authored out-of-schema field.

## Session Log
- `/ll:ready-issue` - 2026-07-11T01:37:59 - `284186ed-08f8-480b-bda6-e04b21c2a17d.jsonl`
- `/ll:ready-issue` - 2026-07-11T01:27:46 - `240f9a39-2745-445e-96f4-a82a79433877.jsonl`
- `/ll:refine-issue` - 2026-07-11T00:59:47 - `a936518a-a1c2-4329-9921-cc37c9c2e2c2.jsonl`
- manual session - 2026-07-10T21:08:10Z - captured from decisions.yaml corruption investigation
