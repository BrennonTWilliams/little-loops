---
id: ENH-3460
title: Doc sync for the second test-only host runner (ARCHITECTURE, API, CONFORMANCE, TESTING)
type: ENH
priority: P3
status: open
testable: false
discovered_date: '2026-09-12'
labels: []
parent: ENH-3456
unproven_mechanism: false
spike_attempted: false
spike_completed: false
blocked_by:
- ENH-3459
relates_to:
- ENH-3453
- ENH-3456
---

## Summary

Decomposed from ENH-3456. Brings the **un-gated** documentation up to date after
ENH-3459 registers `fake-minimal`: the Host Runner Layer table in ARCHITECTURE, the
concrete-runners table in API, a CONFORMANCE section describing the composition
suite, and the TESTING live-guard note. Nothing here is enforced by a test; every
gated change (registry, `TEST_ONLY_HOSTS`, tier-table row, `_HOST_BINARY`) ships in
ENH-3459 so `main` is never red between the two.

## Parent Issue

Decomposed from [ENH-3456](../P3-ENH-3456-prove-host-agnosticism-with-two-deliberately-divergent-fakes-not-one.md):
"Prove host-agnosticism with two deliberately divergent fakes, not one"

## Current Behavior

After ENH-3459 merges, `main` is green but four docs still describe a world with one
test-only runner: `docs/ARCHITECTURE.md`'s Host Runner Layer table and
`docs/reference/API.md`'s concrete-runners table list `fake` only;
`docs/development/CONFORMANCE.md` describes Tier 1/Tier 2 but not the composition
suite; `docs/development/TESTING.md`'s live-guard note explains one carve-out
basename without saying two runners share it.

## Expected Behavior

Each of those four docs mentions `fake-minimal` / `FakeMinimalHostRunner` in the
place a maintainer would look, CONFORMANCE has a "Composition suite" section that
says what `test_host_composition.py` proves and how to run it, and
`HOST_COMPATIBILITY.md` prose is confirmed fake-agnostic (no per-fake enumeration).
No test changes; the wiring gates stay green.

## Why this is small (review 2026-09-12)

The original draft of this child listed nine drift gates. FEAT-3454 now absorbs them
structurally, once, for every fake:

- `_remediation_hint()` is derived from `sorted(set(_HOST_RUNNER_REGISTRY) - TEST_ONLY_HOSTS)`
  — no edit per fake.
- The binary-count test is count-free (`HOST_BINARY_NAMES - TEST_ONLY_BINARIES == {eight}`)
  and `fake-minimal` shares `ll-fake-host` anyway — no edit.
- The live-spawn carve-out is derived from `TEST_ONLY_BINARIES` — no edit.
- `verify_host_map._check_runtime_contradiction` intersects with `HOST_CAPABILITIES`;
  a fake with no map entry is not checked — no edit (FEAT-3454 corrected finding).
- `HOST_COMPATIBILITY.md` prose refers to `TEST_ONLY_HOSTS` and never enumerates
  fakes — no edit. The tier-table **row** is gated and lands in ENH-3459.
- `test_adapters.py` registry-presence checks exist because kimi/qwen have hook
  emitters; fakes have none — not applicable.
- `__all__` / package re-export — unconditional now (class lives in `host_runner.py`)
  and lands with the class in ENH-3459.

What is left is prose no test reads.

## Scope Boundaries

- `docs/ARCHITECTURE.md:857-875` — Host Runner Layer table: add a `fake-minimal` row
  beside FEAT-3454's `fake` row, both under the existing test-fixture footnote. Keep
  the eight production rows untouched.
- `docs/reference/API.md` `## little_loops.host_runner` — "Concrete runners" table:
  `FakeMinimalHostRunner` row (`name`, `binary`, one-line divergence note); mention
  in the `TEST_ONLY_HOSTS` entry FEAT-3454 adds.
- `docs/development/CONFORMANCE.md:9, 57` — new short section "Composition suite":
  what `test_host_composition.py` proves (same `Observed` from two divergent fakes
  through the unpatched executor; AST-pinned interface surface;
  `_structured_output_args` as the one named carve-out), how to run it, and that it
  skips when `ll-fake-host` is not on PATH.
- `docs/development/TESTING.md:1075-1088` — one sentence: both test-only runners
  share `ll-fake-host`, so the guard carve-out is a single basename.
- Verify `docs/reference/HOST_COMPATIBILITY.md:462-472, :491-507` needs **no** change
  (FEAT-3454's wording must already cover any `TEST_ONLY_HOSTS` member). If it does
  need a change, that is a FEAT-3454 wording bug — fix the sentence to be
  fake-agnostic rather than adding a name.

Out (owned by ENH-3459): every gated change listed in the Summary.

## Implementation Steps

1. Confirm ENH-3459 is merged and `python -m pytest scripts/tests/` is green on
   `main` — this child must start from green, not fix red.
2. ARCHITECTURE table row.
3. API concrete-runners row + `TEST_ONLY_HOSTS` mention.
4. CONFORMANCE "Composition suite" section.
5. TESTING one-liner.
6. `grep -n "fake" docs/reference/HOST_COMPATIBILITY.md` — assert no per-fake
   enumeration crept in; if it did, generalise the sentence.
7. `python -m pytest scripts/tests/test_wiring_guides_and_meta.py` (doc-shape gates
   that might read these files), `ll-verify-host-map`, `ll-verify-private-refs`.

## Program Design

Doc-only. The one structural rule: prose points at `TEST_ONLY_HOSTS` rather than
naming fakes, so a third fake needs no doc edit beyond its own table rows.

### Types
- None.

### Signatures
- `_documented_hosts(project_root: Path, column: int) -> set[str]` — existing, `test_wiring_guides_and_meta.py`; reads the tier table this child leaves untouched.
- `_check_doc_parity(doc_path: Path) -> list[str]` — existing, `cli/verify_host_map.py`; same file, same reason.
- No new or changed signatures.

### Call Path
`python -m pytest scripts/tests/test_wiring_guides_and_meta.py` → `test_host_tier_table_matches_runner_registry` → `_documented_hosts(project_root, _COL_RUNNER)` → `docs/reference/HOST_COMPATIBILITY.md` (untouched here) — confirms the gated doc stays green. `ll-verify-host-map` → `_check_doc_parity` → same file. No test reads `ARCHITECTURE.md`, `API.md`, `CONFORMANCE.md`, or `TESTING.md` host tables.

## Impact

- **Priority (P3)**: keeps the four maintainer-facing docs truthful after the
  second registry entry; no runtime or test change.
- Removes the last per-fake enumeration risk in prose.

## Status

Open. Blocked on ENH-3459; start only from a green `main`.

## Conventions in Force

- Registry ↔ tier-table strict equality is the source-of-truth gate
  (`test_wiring_guides_and_meta.py:381-392`); the doc row lives with the registry
  change, never in a follow-up.
- `TEST_ONLY_HOSTS` / `TEST_ONLY_BINARIES` (FEAT-3454) are the only place that names
  test-only entries; prose points at the constant instead of listing fakes.
- Tier semantics in `HOST_COMPATIBILITY.md:491-507` exclude test-time shapes from the
  "Orchestration runner" tier.

## Tests

None new. Existing doc-shape gates in `test_wiring_guides_and_meta.py` must stay
green.

## Files to Modify

- `docs/ARCHITECTURE.md:857-875`
- `docs/reference/API.md` (`## little_loops.host_runner`)
- `docs/development/CONFORMANCE.md:9, 57`
- `docs/development/TESTING.md:1075-1088`

## Related Issues (Dependencies)

- ENH-3459 (open, P3) — registry entry, `TEST_ONLY_HOSTS` entry, tier-table row,
  composition suite. Hard block; start only from a green `main`.
- FEAT-3454 (open, P2) — owns the constants and the fake-agnostic doc wording this
  child relies on.
- ENH-3456 (done) — parent decomposition.
- ENH-3453 (open, P2) — if it lands first, the API table shape may have changed;
  re-anchor.

## Reference Documentation

- Parent `ENH-3456` — wiring-pass findings and the original nine-gate inventory
  (now mostly absorbed by FEAT-3454).
- `.claude/CLAUDE.md` § Host CLI Abstraction.

## Session Log
- `/ll:issue-size-review` - 2026-09-12T06:09:09 - `a6c3ba7b-8baf-4ae7-b742-fb9d4cbad25c.jsonl`
- Manual review rewrite - 2026-09-12 - collapsed to un-gated doc prose; gated items (registry, `TEST_ONLY_HOSTS`, tier row, `_HOST_BINARY`) moved to ENH-3459; count-based rename, `_remediation_hint`, `verify_host_map`, `test_adapters`, `__all__` items removed as absorbed by FEAT-3454 or not applicable
