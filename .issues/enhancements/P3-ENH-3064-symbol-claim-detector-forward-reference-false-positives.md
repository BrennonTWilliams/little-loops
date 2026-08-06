---
id: ENH-3064
title: 'stale_symbol_ref: exclude forward-reference sections from claim extraction'
type: ENH
priority: P3
status: cancelled
discovered_by: manage-issue
discovered_date: 2026-08-05
captured_at: '2026-08-05T00:00:00Z'
relates_to:
- ENH-3047
- FEAT-3048
labels:
- issues
- gates
decision_needed: false
testable: true
verify_verdict: NON_VALID
size: Very Large
---

# ENH-3064: Scope `stale_symbol_ref` extraction away from forward-looking sections

## Summary

`extract_symbol_claims()` (`scripts/little_loops/issues/symbol_claims.py:123`) scans an
issue's **entire body** with no section scoping. A measured sweep of all 72 active issues
(via `ll-issues format-check --all --format json`, recorded in ENH-3047) found
`stale_symbol_ref` fires on 46% of them (33/72), and spot-checks showed the dominant cause is
not a real false claim but a **forward reference**: symbols/functions an issue proposes to
*create* under `## Program Design § Signatures`, `### Files to Modify`, or
`## Implementation Steps`, which do not resolve yet by design.

Two concrete examples from ENH-3047's own research:

- FEAT-2942 reports `add_epic_consistency_parser` and `cmd_epic_consistency` as stale —
  both are functions FEAT-2942 proposes to add, not ones it claims already exist.
- ENH-3047 itself reported `missing_behavior_parity` as a stale symbol — it is a
  `FormatGaps` dataclass field name the issue's own test plan says to assert on, not a def-site
  claim.

## Current Behavior

`extract_symbol_claims()` has no concept of "planning" vs. "as-is" sections. Any symbol-shaped
token attributed to a file within `_MAX_ATTRIBUTION_DISTANCE` (80 chars) of a file reference is
extracted as a claim and checked against the current codebase, regardless of which section it
appears in.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- **BUG-3063 (`status: done`, completed 2026-08-05) already implements the exact fix this issue
  requests.** Its "A1" solution is allowlist-based section scoping:
  `_STALE_SYMBOL_SCOPE_H2_SECTIONS = ("Summary", "Current Behavior", "Root Cause", "Context")`
  and `_symbol_claim_scope_text()` (`scripts/little_loops/issue_parser.py:912`, `:915-922`).
  `extract_symbol_claims()` itself (`scripts/little_loops/issues/symbol_claims.py:131`) remains
  section-agnostic by design — scoping is applied by the caller, `check_format_gaps()`
  (`issue_parser.py:744-754`), which pre-slices the body to the H2 allowlist *before* the
  extractor ever sees it. `## Program Design`, `### Files to Modify`, and `## Implementation
  Steps` are all outside the allowlist, so claims inside them are never extracted.
- BUG-3063's "C" solution additionally downgrades resolves-elsewhere claims (mis-attribution,
  not staleness) to a distinct `FormatGaps.mislocated_symbol_ref` field
  (`issue_parser.py:265`, populated via `symbol_resolves_elsewhere()`,
  `symbol_claims.py:325`) rather than reporting them as `stale_symbol_ref`.
- **Current repo-wide sweep (2026-08-05, this refine pass)**: `ll-issues format-check --all
  --format json` over 70 active issues shows `stale_symbol_ref` on 2 issues (2 hits) and
  `mislocated_symbol_ref` on 4 issues (5 hits) — down from the 46% (33/72) baseline this issue
  cites.
- **This issue's own AC2 regression case is confirmed resolved**: `ll-issues format-check
  FEAT-2942 --format json` now returns empty `stale_symbol_ref` and `mislocated_symbol_ref`
  lists. `add_epic_consistency_parser`/`cmd_epic_consistency` no longer appear anywhere in its
  gap output.
- Regression coverage for this exact scoping behavior already exists:
  `TestStaleSymbolRefScoping` and `TestMislocatedSymbolRef` in
  `scripts/tests/test_feat3048_symbol_cli_claim_gaps.py:229-316`, including paired
  positive/negative controls and an arbitrary-unlisted-heading case (`## Rollout Notes`) proving
  allowlist-not-denylist semantics — the exact scenario this issue's Acceptance Criteria would
  need to test.
- **Conclusion**: every Acceptance Criterion in this issue (materially lower stale rate,
  FEAT-2942's two named gaps cleared, positive control preserved, tests green) already holds on
  `main`. This issue appears to be a duplicate of already-completed work; recommend reviewing it
  for closure as superseded by BUG-3063 rather than further implementation.

## Expected Behavior

Reduce the false-positive rate on forward-looking sections, via one (or a combination) of:

- **Section scoping**: exclude `## Program Design § Signatures`, `### Files to Modify`, and
  `## Implementation Steps` (or a documented equivalent heading set) from extraction entirely.
- **Forward-reference discriminator**: detect verbs/phrasing that mark a symbol as
  prospective ("will add", "proposes to add", "to create", "new function") near the
  attribution and skip those matches.

Either approach should materially reduce the 46% `stale_symbol_ref` rate measured in
ENH-3047 § Why Claims Are a Cap, Not an Override, without suppressing genuine false claims
about existing code (e.g. FEAT-2942's real error citing a nonexistent function as already
present in a file it does not propose to change).

## Motivation

ENH-3047 wired `stale_symbol_ref`/`stale_cli_flag` into `/ll:confidence-check` as a
Criterion 4 **cap**, deliberately *not* a hard `STOP` override, specifically because this
detector's precision on forward-looking issues was too low to gate on. That issue named this
as the explicit follow-up: fix the false-positive class first, then revisit whether
`stale_cli_flag` (currently 10% of active issues, a sharper signal — "no such subcommand" is
less ambiguous than an unresolved symbol) is ready to become a hard override.

## Scope Boundaries

**In scope:** `extract_symbol_claims()` and its section/phrasing discrimination logic.

**Explicitly out of scope:**
- Any change to `/ll:confidence-check`'s cap/override wiring (ENH-3047's territory) — this
  issue only improves the detector's precision; whether that earns a stricter consumer gate
  is a separate future decision.
- `stale_cli_flag` detection logic, unless the same section-scoping fix naturally covers it.

## Acceptance Criteria

1. Re-running `ll-issues format-check --all --format json` after the fix shows a materially
   lower `stale_symbol_ref` rate than the 46% (33/72) baseline recorded in ENH-3047's Blast
   Radius table — record the new count/percentage in this issue on completion.
2. FEAT-2942's `add_epic_consistency_parser`/`cmd_epic_consistency` forward-reference gaps no
   longer appear in its `stale_symbol_ref` list.
3. A genuine false claim (an issue asserting an existing function that does not exist, outside
   any forward-looking section) still triggers `stale_symbol_ref` — add a regression test
   fixture for this so the fix does not overcorrect to silence.
4. `python -m pytest scripts/tests/` exits 0.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Files Already Implementing the Requested Scoping (BUG-3063)
- `scripts/little_loops/issues/symbol_claims.py` — `extract_symbol_claims()` (line 131), `symbol_exists_in_file()` (line 303), `symbol_resolves_elsewhere()` (line 325), `build_symbol_index()` (line 292)
- `scripts/little_loops/issue_parser.py` — `_STALE_SYMBOL_SCOPE_H2_SECTIONS` (line 917), `_symbol_claim_scope_text()` (line 912), `check_format_gaps()` symbol-claim block (lines 744-754)

### Conventions in Force
- This codebase applies allowlist-based H2-section scoping to gap detectors in three independently-tuned places in `issue_parser.py`: `_symbol_claim_scope_text()` (stale/mislocated symbol refs), `_behavior_parity_scope_text()` (lines 889-903, different section set — includes `## Files to Modify` via `_heading_bodies()`), and `superseded_marker_count()`'s `_SUPERSEDED_DIRECTIVE_SECTIONS` (lines 925-950) — evidence the section-scoping pattern this issue asks for is an established, repeated convention, not a one-off.
- Counter-example — not every gap detector is section-scoped: `prose_dep_drift` scans the entire post-frontmatter body via `strip_frontmatter(content)` with no H2 allowlist (`issue_parser.py:644-669`), and `program_design_nonspecific` triggers on a single named section rather than a concatenated allowlist (`issue_parser.py:612-617`). Three distinct scoping shapes coexist in the same file.
- The code comment at `issue_parser.py:907-911` records the measured tradeoff that motivated allowlist-over-denylist: 73% false-positive clearance for the allowlist vs. 10% for a denylist of "future state" section names, measured on the active backlog.

### Tests
- `scripts/tests/test_feat3048_symbol_cli_claim_gaps.py` — `TestStaleSymbolRefScoping` (lines 229-284: positive controls in Summary/Current Behavior, negative controls in Program Design/Files to Modify/Implementation Steps, and an arbitrary-unlisted-heading case proving allowlist-not-denylist semantics) and `TestMislocatedSymbolRef` (lines 287-316)
- `scripts/tests/test_symbol_claims.py`, `scripts/tests/test_symbol_cli_claim_sweep.py` — related extractor/sweep coverage

### Documentation
- `docs/reference/API.md:890-891` — documents the exact allowlist and cross-references `mislocated_symbol_ref` as subject to the same scoping; the fix this issue requests is already documented, not just implemented.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Types

- `SymbolClaim.symbol: str` — the backticked symbol name (frozen dataclass, `scripts/little_loops/issues/symbol_claims.py`)
- `SymbolClaim.file: str` — resolved repo-relative path
- `SymbolClaim.raw: str` — original backticked text
- `FormatGaps.stale_symbol_ref: list[str]` — issue_parser.py:265 region, serialized by `to_dict()` and counted in `has_gaps`
- `FormatGaps.mislocated_symbol_ref: list[str]` — separate field from `stale_symbol_ref`, same serialization

### Signatures

- `extract_symbol_claims(body: str, ref_index: RefIndex) -> set[SymbolClaim]` — section-agnostic by design; scans whatever `body` substring it is given, with no heading awareness (`symbol_claims.py:131`)
- `_symbol_claim_scope_text(content: str) -> str` — concatenates `_section_body(content, name)` for each name in the `_STALE_SYMBOL_SCOPE_H2_SECTIONS` allowlist (`Summary`, `Current Behavior`, `Root Cause`, `Context`), the allowlist that already implements this issue's requested scoping (`issue_parser.py:912`)
- `symbol_exists_in_file(index: SymbolIndex, file: str, symbol: str) -> bool | None` — returns `False` when the symbol is absent from the claimed file (`symbol_claims.py:303`)
- `symbol_resolves_elsewhere(index: SymbolIndex, file: str, symbol: str) -> bool` — only consulted when `symbol_exists_in_file` returns exactly `False`, to route the claim to `mislocated_symbol_ref` instead of `stale_symbol_ref` (`symbol_claims.py:325`)

### Call Path

`check_format_gaps` -> `_symbol_claim_scope_text` -> `extract_symbol_claims` -> `symbol_exists_in_file` -> `symbol_resolves_elsewhere` -> `stale_symbol_ref` / `mislocated_symbol_ref` (`issue_parser.py:744-754`, pre-slice to the 4-heading allowlist before extraction)

### Decision Rules

N/A — no new decision logic. This section documents the *existing* mechanism (implemented by BUG-3063) that already satisfies this issue's Expected Behavior; this issue proposes no additional gate, threshold, or keyword list of its own.

## Impact

- **Priority**: P3 — improves detector precision behind an already-shipped soft cap; not
  blocking any other issue.
- **Effort**: Low-Moderate — scoped to `symbol_claims.py`'s extraction logic and its test file.

## Status

**Cancelled** | Created: 2026-08-05 | Priority: P3

Superseded by BUG-3063 (done, 2026-08-05), which already implements the exact section-scoping
fix this issue requests. See `## Codebase Research Findings` under Current Behavior for the
verification: 46%→~3% stale rate, FEAT-2942's named gaps cleared, regression tests already in
place. Cancelled via `/ll:wire-issue` rather than wired, per user decision.


## Session Log
- `/ll:wire-issue` - 2026-08-06T03:58:15 - `6ed170f1-8ba6-4222-9c9c-1583b6864b0d.jsonl`
- `/ll:verify-issues` - 2026-08-06T03:48:00 - `103e13a5-c71a-4b49-9cce-ecc33886b458.jsonl`
- `/ll:refine-issue` - 2026-08-06T03:42:53 - `33e08f3a-8c6c-400b-9153-7a47f52e7588.jsonl`
- `/ll:verify-issues` - 2026-08-06T03:38:41 - `acac57ce-aa01-4fed-a944-775278763d17.jsonl`
- `/ll:refine-issue` - 2026-08-06T03:35:13 - `37892105-511d-4105-985c-bc88c950f73f.jsonl`
