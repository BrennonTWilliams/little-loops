---
id: FEAT-3681
type: FEAT
title: Extract reusable utility scorer from ll-loop next-loop
priority: P3
status: open
blocks:
- FEAT-3561
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T01:30:51Z'
---

# FEAT-3681: Extract reusable utility scorer from ll-loop next-loop

## Summary

Extract `ll-loop next-loop`'s scoring into a reusable, pure `utility/` module, retain a small geometric helper for FEAT-3561, and register only the keyed configuration that the existing command consumes: `next.loop_history.weights`. With default configuration, this is a behavior-preserving foundation for FEAT-3561's arena. It does not add `ll-next`, project gate evaluation, candidate generators, acceptance logging, or a history schema migration.

## Current Behavior

`ll-loop next-loop` calculates a weighted additive score from frequency, recency, and success rate with hardcoded weights `0.50`, `0.30`, and `0.20` in `cli/loop/next_loop.py`. The scorer and its response curves are not reusable by another action type.

The current frequency curve is `log1p(run_count) / log1p(50)` and is **not capped** at 1. Recency has a seven-day half-life and can exceed 1 for future timestamps. Missing, malformed, and timezone-naive timestamps produce zero recency; the latest timestamp is selected by string ordering. `_recency_score` and `_build_rationale` each read the clock. These behaviors must be characterized before extraction and preserved here; changing them belongs in a separate issue.

## Expected Behavior

With default configuration, `ll-loop next-loop` emits byte-identical text and JSON for the same fixed project state and clock. Its weighted sum remains unnormalized and unclipped. A separate geometric aggregate returns `None` when no positive-weight axis resolves; an ordinary zero score is floored rather than treated as a veto. FEAT-3561 owns project gate evaluation and coverage/fallback selection.

The consumed `next.loop_history.weights` object supports one-key local overrides without replacing siblings. Explicit nondefault weights may change rankings by user choice. Invalid supplied settings fail at the next-loop consumer boundary with exit 2, one concise stderr diagnostic, and no recommendation output or traceback; merely constructing `BRConfig` must not fail because of invalid `next` settings.

## Motivation

The arena needs auditable scoring, while existing loop recommendations must not shift merely because their implementation moved. Extracting and testing the scorer first gives the later multi-verb CLI a stable foundation.

## Proposed Solution

1. Capture golden output against the unmodified implementation, patching the module clock so both recency and rationale see the same instant. Then move the response curves and weighted sum to `little_loops.utility` as pure, typed functions. Capture one UTC `as_of` at the command boundary and pass it through scoring and rationale rendering.
2. Keep the additive and geometric policies distinct. Preserve next-loop's arithmetic and legacy curves; define the geometric helper's missing-data, score-domain, zero-weight, and floor contracts explicitly. Neither aggregator accepts or evaluates gates, and neither adds a make-up term.
3. Add the narrow `next.loop_history.weights` config/schema surface with defaults `0.50/0.30/0.20`. Pass the already-loaded config into `cmd_next_loop` and validate the consumed settings there, rather than raising during eager `BRConfig` construction. Keep unused per-verb, curve, and gate configuration deferred to their consuming issues.

## Scope Boundaries

- **In scope:** pure legacy response curves and additive scorer, the small geometric helper with explicit no-utility semantics, next-loop adaptation, consumed keyed weight config/schema, consumer-boundary validation, documentation, and fixed-clock compatibility tests.
- **Out of scope:** curve corrections or configurable curve families; project gate evaluation and gate configuration; per-verb arena settings, `ll-next`, and its four core generators (FEAT-3561); bucket pressure, `recommendation_events`, acceptance matching, and any `SCHEMA_VERSION` bump (FEAT-3711); backtesting (FEAT-3712); extra generators (FEAT-3713/3714). Decision-rule compliance remains deferred until rules have machine-evaluable scope.

## Integration Map

### Files to Modify

- New `scripts/little_loops/utility/` module and focused pure scorer/curve tests.
- `scripts/little_loops/cli/loop/next_loop.py`: adapt scoring, inject `as_of` into scoring and rationale, consume resolved weights, and handle `NextConfigError`.
- `scripts/little_loops/cli/loop/__init__.py`: pass the existing `BRConfig` into `cmd_next_loop`; preserve dispatch and CLI flags.
- `scripts/little_loops/config/features.py`, `scripts/little_loops/config/core.py`, and `scripts/little_loops/config/__init__.py`: config types, deferred validation/resolution, root parsing/property/serialization wiring, public exports, and `__all__`.
- `scripts/little_loops/config-schema.json`: declare the consumed weight object, bounds, defaults, and unknown-key rejection.
- `scripts/tests/test_cli_loop_next.py` and `scripts/tests/test_cli_loop_dispatch.py`: golden output, error/exit behavior, clock propagation, config forwarding, and mocked execution.
- `scripts/tests/test_config.py`, `scripts/tests/test_config_schema.py`, and `scripts/tests/test_config_properties.py`: local overrides, runtime validation, `_DATACLASS_SECTION_MAP` completeness, schema-default parity, and serialization idempotence with nondefault weights.
- `docs/reference/CONFIGURATION.md`, `docs/reference/CLI.md`, and `docs/reference/API.md`: consumed config shape, defaults/reset behavior, exit codes, and pure utility contracts. Existing CLI registry tests must remain green; no new entry point is registered.

### Similar Patterns and Configuration

- Reuse the typed config and explicit-key patterns around `NextIssueConfig`, but do not copy its eager `ValueError` behavior or list-valued `sort_keys`. Arrays replace on local override merge; keyed objects deep-merge. `NextIssueConfig` remains under `issues.next_issue` and is unaffected by the new top-level `next` object.
- `load_raw_config` already merges local overrides; it does not validate JSON Schema at runtime. Declare schema bounds for editor/tooling validation and enforce matching constraints in the next-loop resolver using stdlib/existing dependencies. Do not introduce global schema validation or a new dependency for this issue.

## Program Design

### Signatures

- `weighted_sum(scores: Mapping[str, float], weights: Mapping[str, float]) -> float`.
- `weighted_geometric(scores: Mapping[str, float | None], weights: Mapping[str, float], *, floor: float = 1e-6) -> float | None`.
- `frequency_score(run_count: int) -> float` — preserves the reference count of 50 and the uncapped `log1p` formula.
- `recency_score(started_at: str | None, *, as_of: datetime) -> float` — preserves the seven-day half-life and existing timestamp fallback behavior; `as_of` is timezone-aware UTC.
- `cmd_next_loop(args, loops_dir, logger, config: BRConfig) -> int` — receives the config already loaded by `main_loop`.
- A next-loop config resolver returns validated effective weights or raises a specific `NextConfigError` at the consumer boundary. Constructing `BRConfig` must preserve invalid `next` input for later validation without raising a next-specific error.

### Aggregator contracts

- Both aggregators accept keyed mappings. Weights are finite, nonnegative real numbers; booleans, nonnumeric values, NaN, and infinities are invalid. Supplied score keys without corresponding weights are invalid rather than silently ignored. The module is pure: no filesystem, database, clock, or network access.
- **Additive:** every weighted axis must have a finite, nonnegative real score, excluding booleans. Missing/`None` scores are invalid; the legacy adapter represents missing recency as an explicit `0.0`. Scores above 1 are allowed. Iterate in the supplied weight mapping's order using ordinary left-to-right multiplication/addition; the legacy adapter constructs that mapping in the canonical order `frequency`, `recency`, `success`. Do not normalize, clip, use `math.fsum`, or change the arithmetic association. Two empty mappings return `0.0`; the command separately rejects configured weights that are all zero.
- **Geometric:** an absent score key or `None` means missing; a supplied zero is present. Present scores must be finite real numbers in `[0, 1]`, excluding booleans. Zero-weight axes contribute nothing. Aggregate only present positive-weight axes, renormalizing their weights. Return `None` if none resolve, including empty input or an all-zero weight mapping; never invent utility `0` or `1` for missing evidence.
- **Floor:** use one named parameter, `floor`, default `1e-6`, validated as finite with `0 < floor < 1` and excluding booleans. Each included geometric score is replaced by `max(score, floor)`, including a positive value below the floor. Compute the weighted geometric mean in log space. This is separate from the legacy additive path and adds no make-up term.
- **Ownership:** neither aggregator receives gates or implements vetoes, coverage, or fallback ordering. FEAT-3561 handles these before/after the geometric helper. Its adapters must resolve bounded geometric axes separately; they must not change legacy next-loop curves to satisfy the geometric score domain.

### Consumed configuration

```json
{
  "next": {
    "loop_history": {
      "weights": {
        "frequency": 0.50,
        "recency": 0.30,
        "success": 0.20
      }
    }
  }
}
```

- Omitted sections and omitted weight leaves use these defaults. Partial weight objects are valid; the effective three-axis set is validated after defaults are applied.
- Declare `additionalProperties: false` at the `next`, `loop_history`, and `weights` levels. Only the three named weight keys exist in this issue. Each supplied weight is a number with minimum 0; there is no normalization requirement or upper bound. All three effective weights being zero is a runtime config error.
- A one-key `.ll/ll.local.md` override preserves sibling weights. Local `null` removes a configured leaf, so subsequent default resolution restores its default; a zero weight intentionally disables that contribution. Explicit `null` in the base JSON config is invalid.
- FEAT-3561 may add a separate `next.verbs` object when its per-verb settings have consumers. It must not reinterpret `next.loop_history.weights` as arena weights.
- Invalid consumed shapes, unknown keys, invalid numeric values, or an all-zero effective set yield exit 2, one concise stderr diagnostic naming the setting, and empty stdout in both text and JSON modes. There must be no traceback, recommendation rendering, or `cmd_run` call on that path. Invalid `next` settings alone must not prevent unrelated commands from constructing `BRConfig` and running.
- Preserve current no-history/all-excluded behavior: exit 1 with existing text or JSON `[]`. Successful recommendation output remains exit 0; text `--execute` continues to return the dispatched run result.

### Call Path

`main_loop` → `cmd_next_loop(..., config)` → resolve/validate legacy weights → capture one `as_of` → existing history scan and `_score_loop` adapter → pure curves and `utility.weighted_sum` → existing rendering with the same `as_of` for rationale. Preserve timestamp selection, stable score-only sorting, status counting, parameter resolution, and output formats. FEAT-3561 later calls `utility.weighted_geometric` after its own gate evaluation; neither utility function reads project state itself.

## Implementation Steps

1. Before changing production code, capture literal text and JSON golden output against the current implementation with color settings and both clock reads fixed. Use a compact multi-loop fixture covering ties, more than 50 runs, missing/malformed/naive/future timestamps, and mixed run statuses. Pin the raw additive formula as well as rendered rounding.
2. Extract the pure response curves and additive scorer, passing `as_of` through scoring and rationale. Preserve canonical arithmetic order, timestamp string ordering, stable tie order, success counting, JSON `round(..., 4)`, and text `.3f` formatting.
3. Add the consumed config/schema, complete root/export/serialization wiring, pass config through dispatch, and resolve/validate it at the consumer boundary. Test defaults, deliberate nondefault ranking changes, partial objects, one-key local merge, local leaf removal/default restoration, malformed shapes, unknown keys, invalid numbers, and all-zero weights. Verify an invalid `next` value does not break an unrelated command.
4. Add the geometric helper with focused missing-axis, zero-weight, zero-score, floor, no-utility, and invalid-input tests. Test invariance to multiplying all included weights by the same positive factor; keep gate evaluation tests in FEAT-3561.
5. Add CLI cases for exclusions, no history, resolved parameters where practical, and `--execute` with `cmd_run` mocked. Preserve the existing behavior that `--json --execute` renders JSON without dispatching execution. Update docs and run the local suite, lint, and type checks.

## Impact

- **Priority:** P3 — prerequisite for FEAT-3561 without changing current recommendations.
- **Effort:** Medium — scorer extraction, config/schema and tests.
- **Risk:** Medium — a default or time-source change could silently reorder existing output.
- **Breaking Change:** No.

## Acceptance Criteria

- [ ] Golden output is captured before extraction. Default-config text and JSON remain byte-identical with a fixed clock shared by recency and rationale, including stable ties, rounding, uncapped frequency, future recency, timestamp fallbacks/string ordering, and mixed statuses.
- [ ] Default legacy weights are exactly `0.50/0.30/0.20`; the additive path retains the original multiplication/addition order without normalization, clipping, or `math.fsum`.
- [ ] Pure aggregator tests enforce the contracts above: valid/invalid weights and score domains, missing data, zero weights, ordinary zero scores, the floor and values below it, geometric weight-scale invariance, and `None` when no positive-weight axis resolves. No gates or make-up term are added.
- [ ] `next.loop_history.weights` is declared in `config-schema.json` with matching runtime validation, unknown-key rejection, and defaults. Partial objects and one-key local overrides preserve siblings; local leaf removal restores a default; explicit zero remains zero.
- [ ] Root config/property/export/serialization wiring is complete; schema-default parity, dataclass-map completeness, and nondefault serialization idempotence tests pass.
- [ ] The real `ll-loop next-loop` entry point handles invalid consumed config in text/JSON modes with exit 2, one concise stderr diagnostic, empty stdout, no traceback, and no execution. Invalid `next` values alone do not break unrelated commands.
- [ ] Existing no-history/all-excluded exit 1 behavior, exclusions, parameter resolution, mocked text execution, and JSON-with-execute behavior remain unchanged. Dispatch passes the already-loaded config through.
- [ ] No `ll-next` entry point or history schema change is introduced; `python -m pytest scripts/tests/`, lint and type checks pass.

## Related

- FEAT-3561 (stateless arena core; blocked by this issue) and EPIC-3710 (arena umbrella).
- FEAT-3711 owns recommendation events, acceptance, pressure, and the history schema bump; ENH-3678 protects that bump and is not a prerequisite for this extraction.
- FEAT-3712 owns backtesting; FEAT-3713/3714 own additional or deferred generators.

## Use Case

A user runs `ll-loop next-loop` with default configuration after the extraction and gets the same recommendation and explanation. They can override one legacy weight locally without replacing the others. A later `ll-next` implementation imports the pure geometric helper without copying loop-specific code or coupling its policy to legacy weights.

## Related Key Documentation

- `docs/reference/CLI.md` (`ll-loop next-loop`), `docs/reference/CONFIGURATION.md` (`next.loop_history.weights`), and `docs/reference/API.md` (pure utility contracts).

## Status

**Open** | Created: 2026-09-30 | Priority: P3
