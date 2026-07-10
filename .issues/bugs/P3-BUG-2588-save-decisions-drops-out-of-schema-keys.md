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

## Severity / Status

Latent, not currently firing. An audit on 2026-07-10 found **zero** out-of-schema
keys across all 331 entries (125 `decision`, 206 `rule`), so no data is being lost
today. The risk activates the moment anyone hand-adds a field the dataclass does not
know about (a common pattern, given entries are sometimes authored by hand) — the
field will vanish on the next `add_entry`/`save_decisions` with no error or warning.
Priority P3 reflects "no live loss yet, but a silent-data-loss trap."

## Root Cause

- **File**: `scripts/little_loops/decisions.py`
- **Anchors**: `RuleEntry.from_dict`/`to_dict`, `DecisionEntry.from_dict`/`to_dict`,
  `ExceptionEntry.from_dict`/`to_dict`, `CouplingEntry.from_dict`/`to_dict`;
  `save_decisions()`.
- **Cause**: `from_dict` pulls a fixed set of `data.get(...)` keys and discards the
  rest; `to_dict` emits only the enumerated keys. The round-trip is therefore lossy
  for any unmodeled key. `save_decisions` rewrites the whole file, so the loss is
  applied globally, not just to the entry being added.

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

## Actual Behavior

Unmodeled keys are dropped on the first rewrite, silently and globally.

## Proposed Fix

Preserve unknown keys through the round-trip. Options:

- Capture leftover keys in `from_dict` (e.g. an `extra: dict` catch-all) and re-emit
  them in `to_dict`.
- Or store the raw source dict on the entry and merge modeled fields over it when
  serializing.

Optionally pair with a schema check (see ENH-2587) so genuinely invalid keys are
surfaced rather than tolerated.

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

## Session Log
- manual session - 2026-07-10T21:08:10Z - captured from decisions.yaml corruption investigation
