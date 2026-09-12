---
id: ENH-3460
title: Doc sync for the second test-only host runner (ARCHITECTURE, API, CONFORMANCE,
  TESTING)
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
confidence_score: 85
outcome_confidence: 77
score_complexity: 22
score_test_coverage: 10
score_ambiguity: 23
score_change_surface: 22
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
  the eight production rows untouched. **While in this table**, fix the stale
  `HostCapabilities` row (`:861`): it lists four flags (`streaming`,
  `permission_skip`, `agent_select`, `tool_allowlist`) but the dataclass has six
  (`host_runner.py:289-313` adds `structured_output`, ENH-2627, and
  `workspace_sandboxed`, FEAT-2878). The composition suite's "all six flags
  `False`" wording only makes sense if the doc lists six.
- `docs/reference/API.md` `## little_loops.host_runner` — "Concrete runners" table:
  `FakeMinimalHostRunner` row (`name`, `binary`, one-line divergence note); mention
  in the `TEST_ONLY_HOSTS` entry FEAT-3454 adds.
- `docs/development/CONFORMANCE.md:9, 57` — new short section "Composition suite":
  what `test_host_composition.py` proves (same `Observed` from two divergent fakes
  through the unpatched executor; AST-pinned interface surface;
  `_structured_output_args` as the one named carve-out), how to run it, and that
  the Popen-driving classes skip when `ll-fake-host` is not on PATH while the AST
  classes are unmarked and run in the plain unit suite (ENH-3459 Design § marker
  placement).
- `docs/development/CONFORMANCE.md:40-52` — "Baseline Pass/Fail Board" has no
  policy for test-only hosts. Add one sentence under the board: registry keys in
  `TEST_ONLY_HOSTS` are deliberately **not** columns (they always PASS by
  construction and carry no host-support signal); the next board refresh must not
  add them. Extend step 3 of "Adding a New Host" (`:59`) with "test-only hosts are
  excluded from the board", so a future refresh doesn't invent a column.
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
2. ARCHITECTURE table row + six-flag fix on the `HostCapabilities` row.
3. API concrete-runners row + `TEST_ONLY_HOSTS` mention.
4. CONFORMANCE "Composition suite" section + baseline-board test-only-host policy
   sentence + "Adding a New Host" step 3 clause.
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

- `docs/ARCHITECTURE.md:857-875` (incl. the `HostCapabilities` row at `:861`)
- `docs/reference/API.md` (`## little_loops.host_runner`)
- `docs/development/CONFORMANCE.md:9, 40-52, 57-59`
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

## Verification Notes

Verdict: **VALID**. Checked against current codebase state
(2026-09-12, graph provider=`codegraph` freshness=`fresh`):

- `docs/ARCHITECTURE.md`, `docs/reference/API.md`, `docs/development/CONFORMANCE.md`,
  and `docs/development/TESTING.md` currently contain zero mentions of `fake` /
  `FakeMinimalHostRunner` — consistent with the "Current Behavior" claim that these
  docs describe a pre-FEAT-3454/ENH-3459 world.
- Cited signatures match exactly: `_documented_hosts(project_root: Path, column:
  int) -> set[str]` (`scripts/tests/test_wiring_guides_and_meta.py:374`) and
  `_check_doc_parity(doc_path: Path) -> list[str]`
  (`scripts/little_loops/cli/verify_host_map.py:87`), including the Call Path claim
  that `ll-verify-host-map` routes `_check_doc_parity` at
  `docs/reference/HOST_COMPATIBILITY.md`.
- `TEST_ONLY_HOSTS`, `FakeHostRunner`/`FakeMinimalHostRunner`, and
  `TEST_ONLY_BINARIES` do not yet exist in `host_runner.py` — confirms this issue is
  correctly gated behind FEAT-3454/ENH-3459 landing first.
- `HOST_COMPATIBILITY.md:462-472,491-507` currently has no per-fake enumeration, as
  expected.
- Dependency refs check out: `blocked_by: ENH-3459` (open, exists) is backlinked in
  ENH-3459's Related Issues prose ("ENH-3460 (open, P3) — un-gated doc prose after
  this lands") rather than a `## Blocks` heading — consistent with this pair's
  frontmatter-driven convention, not a broken link. `relates_to: ENH-3453` (open),
  `ENH-3456` (done, parent) both resolve. No cycle.
- `ll-verify-evidence --json`: clean (`count: 0`, no attributed quotes to check).
- No active required decision rules to check against (empty registry).
- No `## Proposed Solution` section present, so the B6 consequence check does not
  apply to this Scope-Boundaries/Implementation-Steps issue.

**Addendum (second `/ll:verify-issues --auto` pass, same day) — cross-issue scope
check against ENH-3453:** sibling ENH-3453 (open, P2, `relates_to` this issue)
proposes rewriting `_check_runtime_contradiction`
(`scripts/little_loops/cli/verify_host_map.py:100-128`) from today's
intersection-based check (`set(HOST_CAPABILITIES) & set(_HOST_RUNNER_REGISTRY)`,
verified present at line 116) to a **strict key-parity** check —
`set(RUNTIME_HOST_CAPABILITIES) == set(_HOST_RUNNER_REGISTRY)` — per ENH-3453's
own `## Files to Modify` and Implementation Step #4. ENH-3453 describes no
`TEST_ONLY_HOSTS` carve-out for that new equality check anywhere in its text. If
ENH-3453 lands *after* FEAT-3454/ENH-3459 register `fake`/`fake-minimal` in
`_HOST_RUNNER_REGISTRY`, the rewritten check would fail on those two test-only
hosts unless ENH-3453 (or FEAT-3454) adds an exclusion — which would flip the
"no edit" claim in this issue's `## Why this is small` (`verify_host_map`
bullet) from true to false, though `verify_host_map.py` is not itself in this
issue's `## Files to Modify`, so it doesn't change ENH-3460's own scope or
verdict. Not a defect in this issue — this issue already hedges the ENH-3453
landing-order risk in `## Related Issues` (API table shape) — but the same
hedge should extend to `verify_host_map.py`, and ENH-3453's or FEAT-3454's
implementer should account for a `TEST_ONLY_HOSTS` exclusion in the rewritten
check. Flagged per the verification pass's explicit ask to note (not invent a
link for) this class of conflict. No line-number or path corrections were
needed anywhere else; evidence (`ll-verify-evidence --json`) and decisions
(`ll-issues decisions list --type rule --enforcement required --active-only`)
both remain clean. Verdict unchanged: **VALID**.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-12_

**Readiness Score**: 85/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 77/100 → Good

### Gaps to Address
- Dependencies Hard Override (BUG-3051): `blocked_by` lists ENH-3459, currently
  `open` (not `done`/`cancelled`). This issue's own text says to "start only
  from a green `main`" after ENH-3459 merges — the block is real, not stale.
  Remedy: wait for ENH-3459 to land, then re-run this check.

## Session Log
- `/ll:confidence-check` - 2026-09-12T18:35:39 - `ee8721cf-6b02-4322-9968-721a9a834aac.jsonl`
- Manual review - 2026-09-12 (second pass) - added the stale six-flag `HostCapabilities` row fix in ARCHITECTURE, a test-only-host policy for the CONFORMANCE baseline board and "Adding a New Host" step 3, and the marker-placement detail for the Composition suite section; ENH-3453 landing-order hedge resolved upstream (ENH-3453 step 4 now subtracts `TEST_ONLY_HOSTS`)
- `/ll:verify-issues` - 2026-09-12T17:09:11 - `1e2ab216-51bc-448b-8f81-d875cf66efd8.jsonl`
- `/ll:verify-issues` - 2026-09-12T17:04:12 - `1e2ab216-51bc-448b-8f81-d875cf66efd8.jsonl`
- `/ll:issue-size-review` - 2026-09-12T06:09:09 - `a6c3ba7b-8baf-4ae7-b742-fb9d4cbad25c.jsonl`
- Manual review rewrite - 2026-09-12 - collapsed to un-gated doc prose; gated items (registry, `TEST_ONLY_HOSTS`, tier row, `_HOST_BINARY`) moved to ENH-3459; count-based rename, `_remediation_hint`, `verify_host_map`, `test_adapters`, `__all__` items removed as absorbed by FEAT-3454 or not applicable
