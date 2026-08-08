---
id: FEAT-3108
title: Advisor capability floor - MODEL_RANKS, rank_model, check_floor
type: FEAT
parent: FEAT-3044
priority: P3
status: done
testable: true
discovered_date: 2026-08-08
completed_at: '2026-08-08T18:38:31Z'
labels:
- planning-hub
verify_verdict: VALID
size: Large
reconcile_attempted: true
confidence_score: 95
outcome_confidence: 82
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 25
---

# FEAT-3108: Advisor capability floor - MODEL_RANKS, rank_model, check_floor

## Summary

Ship the capability-rank comparison used to gate a consult on model
strength: a static `MODEL_RANKS` table, `rank_model()`, and `check_floor()`.
This is the one genuinely new algorithmic piece of the advisor core
(FEAT-3044) and is a pure-logic module with no transport dependency — it
does not require FEAT-3042 (shared blocking transport) to ship.

## Parent Issue

Decomposed from FEAT-3044: Advisor core - `ll-advise` CLI, capability
floor, and `ll-doctor` check. FEAT-3044 scored Very Large (11/11) on
`ll-issues size` and covers three architecturally separable concerns
called out as distinct subsections in its own "Proposed Solution": Surface
A (invocation CLI, → FEAT-3109), Capability floor (this issue), and the
`ll-doctor` check (→ FEAT-3110). This child ships the capability-floor
concern first because, unlike the other two, it has no dependency on
FEAT-3042 and can be built and tested standalone.

## Current Behavior

No capability-rank/ordering table exists anywhere in the codebase.
Adjacent model tables are not ranks: `MODEL_ALIASES`
(`host_runner.py:79-96`, alias→concrete-ID map, case-insensitive,
whitespace-stripped, unknown values pass through unchanged),
`MODEL_PRICING` (`pricing.py:15-79`, insertion order implies a hierarchy
but is not a rank), `MODEL_CONTEXT_WINDOW` (`context_window.py:19-33`).
No `enum.IntEnum` usage exists anywhere in `scripts/little_loops/`.

## Use Case

A user has `orchestration.advisor` configured with a weaker model than
their main session (e.g. advisor pinned to `haiku`, main session running
`opus`) — a cost-saving choice that silently degrades advice quality. Once
FEAT-3109 wires `check_floor` into `consult()`, this module is what lets
that call classify the pairing instead of trusting it blindly:
`check_floor("claude-code", "haiku", "claude-code", "opus")` returns
`violation`, giving the caller a concrete signal to warn or refuse rather
than return advice from a strictly weaker model. Cross-host pairings (e.g.
advisor on `codex`, main on `claude-code`) return `advisory` instead of
`violation`, since capability ranks aren't comparable across hosts. This
issue ships only the classification primitive; the refusal/warning
behavior itself is FEAT-3109's concern.

## Expected Behavior

- `rank_model(host, model) -> int | None` normalizes `model` through
  `resolve_model_alias()` before table lookup, then returns an ordinal
  rank within `host`; an unrankable model returns `None`.
- `check_floor(advisor_host, advisor_model, main_host, main_model) ->
  FloorResult` classifies the pairing as `ok`, `violation` (same host,
  advisor ranks below main), `advisory` (cross-host mismatch), or
  `unknown` (either model unrankable) — never a silent pass on `unknown`.
- Pinned case: `check_floor("claude-code", "haiku", "claude-code",
  "opus")` returns `violation`.
- `MODEL_RANKS` keys on the canonical host-name set
  `_HOST_RUNNER_REGISTRY`'s keys (`host_runner.py:1522-1530`):
  `claude-code`, `codex`, `opencode`, `pi`, `gemini`, `omp`, `kimi-code`.
  `MODEL_RANKS`/`rank_model()` cover `fable` alongside `opus`/`sonnet`/
  `haiku`.

## API/Interface

```python
# scripts/little_loops/advisor.py (new)
@dataclass(frozen=True)
class FloorResult:
    status: Literal["ok", "violation", "advisory", "unknown"]
    detail: str

MODEL_RANKS: dict[str, dict[str, int]]  # e.g. {"claude-code": {"haiku": 1, "sonnet": 2, "opus": 3, "fable": ...}, ...}

def rank_model(host: str, model: str) -> int | None:
    """Capability rank within *host*; None when unrankable."""

def check_floor(
    advisor_host: str, advisor_model: str, main_host: str, main_model: str
) -> FloorResult:
    """`ok` | `violation` (same host) | `advisory` (cross host) | `unknown`."""
```

## Program Design

### Types

- `FloorResult: {status: Literal["ok", "violation", "advisory", "unknown"], detail: str}`
- `MODEL_RANKS: dict[str, dict[str, int]]`

### Signatures

- `rank_model(host: str, model: str) -> int | None`
- `check_floor(advisor_host: str, advisor_model: str, main_host: str, main_model: str) -> FloorResult`

### Decision Rules

- Rank lookup must normalize through `resolve_model_alias()`
  (`host_runner.py:87-96`) before table lookup — a table keyed only on
  alias names silently no-ops on every non-alias (concrete-ID) value.
- `opencode`/`pi` are unwired stubs (`HostNotConfigured`) — their rank
  rows exist in `MODEL_RANKS` for completeness but are unreachable in
  practice, since an unwired host fails soft in `consult()` (FEAT-3109)
  before `check_floor` ever sees it.
- Equality semantics (advisor rank == main rank) are **open** and not
  pinned by this issue — only the haiku < opus same-host case is given.
  Whoever wires `check_floor` into the consult-refusal path (FEAT-3109)
  must fix this before the gate goes live; document the chosen semantics
  in this issue's own tests as the pin.
- **Capability-rank table shape** (open, pick one knowingly — no existing
  precedent to imitate structurally): (a) a flat ordered tuple +
  `.index()` lookup, single-axis only (`PRIORITY_TIERS`/`_priority_rank()`,
  `queue_store.py:96,225-230`); (b) `dict[str, dict[str, int]]` for
  per-key multi-field tables, the closest structural analog being
  `MODEL_PRICING` (`pricing.py:14-15`), but rank would just be an
  ordinary `int` field with no ordinal semantics in the type itself.
- **`FloorResult.status` typing**: model as a `Literal[...]` field
  directly on the dataclass, matching `cli/doctor.py`'s own
  `CheckResult`/`FindingDetail` pattern (`doctor.py:32-36,39-51,54-73`) —
  not a separate `enum.Enum` (the disagreeing precedent elsewhere in the
  codebase, e.g. `ValidationSeverity`, `fsm/validation/_base.py:15-20`).

### Deviations

_Added by `/ll:manage-issue` — 2026-08-08:_

- Design said non-`claude-code` hosts' rank rows "exist in `MODEL_RANKS` for
  completeness" (implying populated per-model rows for `codex`/`opencode`/
  `pi`/`gemini`/`omp`/`kimi-code`). Implemented as an empty `{}` per host
  instead — there's no in-repo capability data for those hosts' model
  catalogs to populate rows with, and a fabricated ordinal would be worse
  than none. `rank_model` still returns `None` for any model on those
  hosts (same practical effect: unranked → `check_floor` reports
  `unknown`/`advisory`, never a silent pass), and the host keys themselves
  are present per the "keys on the canonical host-name set" requirement.
  A follow-up issue can populate real per-model rows when that data exists.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- `resolve_model_alias()` (`host_runner.py:87-96`) only lowercases/strips the *lookup key* — on a miss it returns the original `model` argument verbatim, uppercase/whitespace intact (`MODEL_ALIASES.get(model.strip().lower(), model)`). Consequence for `rank_model`: a concrete model ID passed with non-canonical casing (e.g. `"Claude-Sonnet-5"`) is normalized only if it happens to match an alias key — otherwise it reaches the `MODEL_RANKS[host]` lookup with its original casing preserved, so `MODEL_RANKS` keys must match the exact casing callers pass for non-alias values, or `rank_model` must apply its own additional normalization beyond calling `resolve_model_alias()` [Agent 2 finding].

### Call Path
`check_floor(advisor_host, advisor_model, main_host, main_model)` -> `rank_model(host, model)` (called twice, once per pairing) -> `resolve_model_alias(model)` (`host_runner.py:87-96`) -> `MODEL_RANKS[host]` dict lookup. No caller of `check_floor` exists yet within this issue's own scope — `consult()` (FEAT-3109, not yet built) and `cli/doctor.py`'s `_advisor_check()` (FEAT-3110, not yet built) are the two planned callers, per those issues' own Decision Rules sections; neither exists in the tree today.

## Integration Map

### New Files

- `scripts/little_loops/advisor.py` — `MODEL_RANKS`, `rank_model`,
  `check_floor`, `FloorResult`. (FEAT-3109 adds `consult`/`AdvisorVerdict`
  to this same module in a later commit.)

### Documentation

- `docs/reference/API.md` — `FloorResult`, `check_floor`, `rank_model`
  rows (module-overview row for `little_loops.advisor` is added once the
  module exists; FEAT-3109 completes the `## little_loops.advisor` body
  section for `consult`/`AdvisorVerdict`).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — insertion point: `API.md` is ordered
  chronologically by landing order, not alphabetically. Add the new
  `little_loops.advisor` Module Overview row as the **last** row in that
  table (currently ends at `little_loops.mcp_call`), and the new
  `## little_loops.advisor` body section as the **last** module section,
  immediately before the `## Agents` heading (currently preceded by
  `## little_loops.init.install_check`) [Agent 2 finding].

### Tests

- `scripts/tests/test_advisor.py` (new) — `rank_model` normalizes through
  `resolve_model_alias`; unrankable → `None`; `check_floor` returns
  `violation` same-host, `advisory` cross-host, `unknown` on unrankable
  (never a silent pass); pinned case
  `check_floor("claude-code", "haiku", "claude-code", "opus")` →
  `violation`. Follow `test_context_window.py`'s `TestContextWindowFor`
  convention — one `class Test<FunctionName>` per public symbol
  (`TestModelRanks`, `TestRankModel`, `TestCheckFloor`), plain
  `def test_<behavior>(self)` methods with direct `assert`, no
  `pytest.mark.parametrize` [Agent 3 finding].

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_reference_docs.py` — add `DOC_STRINGS_PRESENT`
  tuples `("docs/reference/API.md", "little_loops.advisor", "FEAT-3108")`,
  `("docs/reference/API.md", "FloorResult", "FEAT-3108")`,
  `("docs/reference/API.md", "check_floor", "FEAT-3108")`,
  `("docs/reference/API.md", "rank_model", "FEAT-3108")` — this file is a
  doc-coverage lockstep gate; it has zero existing rows for these symbols
  and will not enforce the new `API.md` section without them [Agent 2
  finding].

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- Module-docstring convention for new pure-logic table-driven modules disagrees across the two closest structural analogs: `pricing.py:1-8` and `context_window.py:1-11` each open with a purpose statement, but `pricing.py` adds a "Source: ..." provenance line citing the issue IDs that shaped the table (`ENH-2745`, `ENH-2835`), while `context_window.py` instead states an explicit numbered precedence list. `queue_store.py:1-22` (a heavier, non-analogous module) states which sibling module it's modeled on instead. `advisor.py`'s docstring should pick one of these shapes rather than inventing a fourth [Agent 3 finding].

### Dependent Files (Callers/Importers)
- None yet — `advisor.py` is net-new and additive; confirmed absent anywhere in the tree today (no `advisor.py` or `cli/advise.py` exists). The only planned callers are sibling issues FEAT-3109 (`consult()`, not yet built) and FEAT-3110 (`cli/doctor.py`'s `_advisor_check()`, not yet built) — both name `check_floor`/`rank_model`/`MODEL_RANKS` as something they consume, not modify.

### Conventions in Force
- Frozen-dataclass-with-inline-`Literal[...]`-status is the closest structural analog for `FloorResult`, chained across `host_runner.CapabilityEntry` (`host_runner.py:168-177`, `status: Literal["full", "partial", "unsupported"]`) → `cli/doctor.py:CheckResult` (`doctor.py:54-73`) → `cli/doctor.py:FindingDetail` (`doctor.py:40-51`) — each docstring explicitly names which prior class's shape it mirrors. A separate `enum.Enum` (not `IntEnum`) exists elsewhere (`ValidationSeverity`, `fsm/validation/_base.py:15-20`, consumed by a non-frozen `ValidationError` dataclass) but is not the convention the closest structural analogs use.
- Rank/lookup-table shape has three disagreeing precedents in this codebase, none of which is per-host+ordinal like `MODEL_RANKS` needs to be: (a) flat ordered tuple + `.index()`, single axis (`PRIORITY_TIERS`/`_priority_rank()`, `queue_store.py:96,225-230`, raises `ValueError` on miss, case-normalized via `.upper()`); (b) `dict[str, dict[str, T]]` keyed on model id, inner dict of named fields with no ordinal meaning (`MODEL_PRICING`, `pricing.py:15-79`, `.get()` returns `None` on miss); (c) `dict[str, int]` flat with a named fallback constant (`MODEL_CONTEXT_WINDOW`, `context_window.py:19-33`, `_DEFAULT_CONTEXT_WINDOW`). None is multi-axis (host outer key + model inner key) — the issue's own Program Design section already flags this table shape as an open decision.
- No existing `ok`/`violation`/`advisory`/`unknown`-style classification status exists anywhere in `scripts/little_loops/` to imitate — `FloorResult`'s status set is genuinely new vocabulary. (The only near-miss, `decisions.py`'s `enforcement: str = "advisory"` field, is an unrelated free-string field on `.ll/decisions.yaml` decision-rule dataclasses, not a closed classification type.)
- `MODEL_ALIASES` (`host_runner.py:79-84`) currently contains exactly: `{"fable": "claude-fable-5", "opus": "claude-opus-5", "sonnet": "claude-sonnet-5", "haiku": "claude-haiku-4-5"}` — `resolve_model_alias()` (`host_runner.py:87-96`) does `MODEL_ALIASES.get(model.strip().lower(), model)`. This is the exact alias→concrete-ID mapping `rank_model()` must normalize through before a `MODEL_RANKS["claude-code"]` lookup.
- Small pure-logic table-driven modules test with one `class Test<Function>:` per public function and one `assert fn(...) == expected` per method — no `pytest.mark.parametrize` (`test_pricing.py`, `test_context_window.py`, both closer scope-matches to a new `test_advisor.py` than the exception below). The one exception is alias-resolution testing itself: `test_host_runner_dispatch.py:360-385`'s `TestModelAliasResolution` already parametrizes over the same four aliases (`sonnet`/`opus`/`haiku`/`fable`) plus case/whitespace variants — a `test_advisor.py` covering `rank_model`'s alias-normalization behavior can follow either convention already in use in this codebase.

## Acceptance Criteria

1. `check_floor("claude-code", "haiku", "claude-code", "opus")` returns
   `violation`. The same mismatch across hosts (`advisor_host !=
   main_host`) returns `advisory`.
2. `rank_model` returns the same rank for `"opus"` and its concrete ID
   from `MODEL_ALIASES`; an unknown/dated model returns `None` and
   `check_floor` returns `unknown` for that pairing.
3. `MODEL_RANKS` covers `haiku`/`sonnet`/`opus`/`fable` for at least the
   `claude-code` host.
4. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` all pass.

## Out of Scope (covered by sibling children of FEAT-3044)

- **FEAT-3109** — `consult()`, `AdvisorVerdict`, the `ll-advise` CLI,
  `/ll:advise` skill, and wiring `check_floor`'s `violation` result into
  an actual consult refusal.
- **FEAT-3110** — the `ll-doctor` advisor-reachability check that reports
  `check_floor`'s `advisory`/`unknown` results as informational findings.

## Impact

- **Priority**: P3 — a capability gap, not a defect.
- **Effort**: Small — one new pure-logic module, no transport/CLI
  surface, unblocked by FEAT-3042.
- **Risk**: Low — additive, no existing call sites.
- **Breaking Change**: No.

## Related Key Documentation

- `docs/reference/API.md#little_loopshost_runner`

## Status

**Open** | Created: 2026-08-08 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-08-08T18:38:31 - `c20ba1e0-2f7e-443c-a379-8792ba818c13.jsonl`
- `/ll:manage-issue` - 2026-08-08T18:38:20 - `c20ba1e0-2f7e-443c-a379-8792ba818c13.jsonl`
- `/ll:ready-issue` - 2026-08-08T18:21:11 - `db24f11b-8e0c-4937-835f-570bc1dada63.jsonl`
- `/ll:ready-issue` - 2026-08-08T18:21:03 - `db24f11b-8e0c-4937-835f-570bc1dada63.jsonl`
- `/ll:confidence-check` - 2026-08-08T18:17:19 - `0e5913bc-2c3e-42d3-8bea-cb9d02922b50.jsonl`
- `/ll:reconcile-issue` - 2026-08-08T18:15:13 - `0502af68-be69-4bc7-9a20-ab205fa5ea1d.jsonl`
- `/ll:verify-issues` - 2026-08-08T18:13:13 - `f8cc6709-62f2-45b9-a30a-a1c3497aebb0.jsonl`
- `/ll:verify-issues` - 2026-08-08T18:13:06 - `f8cc6709-62f2-45b9-a30a-a1c3497aebb0.jsonl`
- `/ll:refine-issue` - 2026-08-08T18:11:17 - `fab4bfc0-c66b-4e6c-90d6-1f52b62c845d.jsonl`
- `/ll:verify-issues` - 2026-08-08T18:06:46 - `805bda5b-824b-4a51-9b93-ba36bae96e60.jsonl`
- `/ll:wire-issue` - 2026-08-08T18:03:13 - `47f42065-4220-4c09-974b-7fd99cd15eb2.jsonl`
- `/ll:refine-issue` - 2026-08-08T17:58:23 - `00eabf40-35ea-49dc-9b3c-8d36a713a164.jsonl`
- `/ll:issue-size-review` - 2026-08-08T17:51:40 - `45d84ae4-d7b1-4342-a5e2-fb2f78de65a2.jsonl`
