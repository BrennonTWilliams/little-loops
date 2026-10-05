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
confidence_score: 95
outcome_confidence: 58
score_complexity: 5
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# FEAT-3681: Extract reusable utility scorer from ll-loop next-loop

## Summary

Extract `ll-loop next-loop`'s scoring into a reusable, pure `utility/` module, retain a small geometric helper for FEAT-3561, and register only the keyed configuration that the existing command consumes: `next.loop_history.weights`. With default configuration, this is a behavior-preserving foundation for FEAT-3561's arena. It does not add `ll-next`, project gate evaluation, candidate generators, acceptance logging, or a history schema migration.

## Current Behavior

`ll-loop next-loop` calculates a weighted additive score from frequency, recency, and success rate with hardcoded weights `0.50`, `0.30`, and `0.20` in `cli/loop/next_loop.py`. The scorer and its response curves are not reusable by another action type.

The current frequency curve is `log1p(run_count) / log1p(50)` and is **not capped** at 1. Recency has a seven-day half-life and can exceed 1 for future timestamps. Missing, malformed, and timezone-naive timestamps produce zero recency; the latest timestamp is selected by string ordering. `_recency_score` and `_build_rationale` each read the clock. These behaviors must be characterized before extraction and preserved here; changing them belongs in a separate issue.

`_score_loop([])` has a separate fast path returning `(0.0, 1.0, None)`; running those values through the ordinary additive formula would incorrectly contribute the default success weight. An extreme future timestamp currently raises `OverflowError` in `math.exp`; retain that exceptional behavior separately from the new controlled validation of configured weights.

## Expected Behavior

With default weights and unchanged effective settings outside `next`, `ll-loop next-loop` emits byte-identical text and JSON for the same fixed project state and clock on inputs the legacy implementation successfully scores. The shared local-null merge correction intentionally restores defaults for affected settings outside `next`; those cases have separate before/after regressions rather than an impossible byte-parity promise. Its weighted sum remains unnormalized and unclipped; the legacy empty-run fast path and extreme-future exception are also preserved. A separate geometric aggregate returns `None` when no positive-weight axis resolves; an ordinary zero score is floored rather than treated as a veto. FEAT-3561 owns project gate evaluation and coverage/fallback selection.

The consumed `next.loop_history.weights` object supports one-key local overrides without replacing siblings. Explicit nondefault weights may change rankings by user choice. Invalid supplied settings fail at the next-loop consumer boundary with exit 2, one concise stderr diagnostic, and no recommendation output or traceback; merely constructing `BRConfig` must not fail because of invalid `next` settings.

## Motivation

The arena needs auditable scoring, while existing loop recommendations must not shift merely because their implementation moved. Extracting and testing the scorer first gives the later multi-verb CLI a stable foundation.

## Proposed Solution

1. Capture golden output against the unmodified implementation, patching the module clock so both recency and rationale see the same instant. Then move the response curves and weighted sum to `little_loops.utility` as pure, typed functions. Capture one UTC `as_of` at the command boundary and pass it through scoring and rationale rendering.
2. Keep the additive and geometric policies distinct. Preserve next-loop's arithmetic and legacy curves; define the geometric helper's missing-data, score-domain, zero-weight, and floor contracts explicitly. Neither aggregator accepts or evaluates gates, and neither adds a make-up term.
3. Add the narrow `next.loop_history.weights` config/schema surface with defaults `0.50/0.30/0.20`. Pass the already-loaded config into `cmd_next_loop` and validate the consumed settings there, rather than raising during eager `BRConfig` construction. Keep unused per-verb, curve, and gate configuration deferred to their consuming issues.

## Scope Boundaries

- **In scope:** pure legacy response curves and additive scorer, the small geometric helper with explicit no-utility semantics, next-loop adaptation, consumed keyed weight config/schema, consumer-boundary validation, documentation, and fixed-clock compatibility tests.
- **Out of scope:** curve corrections or configurable curve families; project gate evaluation and gate configuration; per-verb arena settings, `ll-next`, and its four core generators (FEAT-3561); `recommendation_events`, acceptance matching, and any `SCHEMA_VERSION` bump (FEAT-3711); bucket pressure and automatic attribution (FEAT-3722, deferred); backtesting (FEAT-3712, cancelled); extra generators (FEAT-3713/3714). Decision-rule compliance remains deferred until rules have machine-evaluable scope.

## Integration Map

### Files to Modify

- New `scripts/little_loops/utility/` module, public exports for the four pure functions below, and focused pure scorer/curve tests.
- `scripts/little_loops/cli/loop/next_loop.py`: adapt scoring, pass one captured time through scoring and rationale, consume resolved weights, and handle `NextConfigError`.
- `scripts/little_loops/cli/loop/__init__.py`: pass the existing `BRConfig` into `cmd_next_loop`; preserve dispatch and CLI flags.
- `scripts/little_loops/config/features.py`, `scripts/little_loops/config/core.py`, and `scripts/little_loops/config/__init__.py`: config types, deferred validation/resolution, root parsing/property/serialization wiring, public exports, and `__all__`.
- `scripts/little_loops/config-schema.json`: declare the consumed weight object, bounds, defaults, and unknown-key rejection.
- `hooks/scripts/session-start.sh`: align the retained inline config merge with the shared recursive-null fix; Python session-start/edit-batch handlers already use the shared helper.
- `scripts/tests/test_cli_loop_next.py`, `scripts/tests/test_cli_loop_dispatch.py`, and `scripts/tests/test_ll_loop_commands.py::TestCmdNextLoop`: golden output, error/exit behavior, clock propagation, config forwarding, and mocked execution. The latter contains five direct three-argument handler calls plus direct `_score_loop` calls; update these along with dispatch. Move private `_recency_score` tests to the public pure curve API rather than retaining a clock-reading compatibility wrapper.
- `scripts/tests/test_config.py`, `scripts/tests/test_config_schema.py`, and `scripts/tests/test_config_properties.py`: local overrides, runtime validation, schema-default parity, and serialization idempotence with nondefault weights. Check `_DATACLASS_SECTION_MAP` in `scripts/tests/test_config_schema.py` for completeness.
- Shared-merge consumers to audit: `scripts/little_loops/hooks/session_start.py`, `scripts/little_loops/hooks/edit_batch_nudge.py`, `scripts/little_loops/session_store/db.py::_read_backend_block`, and `scripts/little_loops/init/writers.py::merge_with_existing`. Extend their existing focused tests where reset behavior is observable (`test_hook_session_start.py`, `test_edit_batch_hook.py`, `test_libsql_backend.py::TestConfigResolution`, `test_init_core.py::TestMergeHelpers`); retain the inline-hook parity regression. `test_history_backend_config.py` covers typed/schema/serialization behavior, not the cached backend loader's local override path. Initialization strips `None` leaves before merging; preserve that policy and unmodeled config keys. Preserve the direct-null no-op tests for retention `compact`/`prune` in `test_session_store_lifecycle.py`; do not change those lifecycle functions or their CLI loader. Do not change `fsm.fragments._deep_merge`, whose null-retention semantics are intentional.
- `scripts/tests/test_init_audit_fixes.py`: add `next` to `_ALLOWED_UNTOUCHED_SECTIONS` with the reason that runtime resolver defaults suffice; `TestSchemaCoverageGuard` otherwise rejects the new schema root. Add no init template or TUI setting. Non-force re-init must preserve existing partial/nondefault `next` values; retain force/empty-existing fast paths.
- `docs/reference/CONFIGURATION.md`, `docs/reference/CLI.md`, and `docs/reference/API.md`: consumed config shape, defaults/reset behavior, exit codes, and pure utility contracts. Existing CLI registry tests must remain green; no new entry point is registered.

### Similar Patterns and Configuration

- Reuse the typed config and explicit-key patterns around `NextIssueConfig`, but do not copy its eager `ValueError` behavior or list-valued `sort_keys`. Arrays replace on local override merge; keyed objects deep-merge. `NextIssueConfig` remains under `issues.next_issue` and is unaffected by the new top-level `next` object.
- `load_raw_config` already merges local overrides; it does not validate JSON Schema at runtime. Declare schema bounds for editor/tooling validation and enforce matching constraints in the next-loop resolver using stdlib/existing dependencies. Do not introduce global schema validation or a new dependency for this issue.

### Shared-Merge Verification Boundaries

The source audit on `main` identifies the following required checks. These are bounded regression/unchanged-policy checks, not a request to refactor the consumers. In-memory probes confirmed the expected distinction between raw merged output and effective fallback settings; production regressions remain implementation work.

| Consumer | Required evidence after the isolated merge correction |
|---|---|
| `config.core.deep_merge` / `load_raw_config` | Missing ancestors and scalar-to-mapping replacement remove override null leaves. Preserve base-only nulls, false/zero/empty-string values, input immutability, and opaque list replacement, including nulls or mappings inside a list. Do not recursively sanitize the base or list contents. Pin one observable typed-setting change: base `{}` plus local `cli.color: null` currently leaves effective color `None`; the correction removes that leaf and restores `True`. With color forced and `NO_COLOR` unset, text gains ANSI color intentionally; this is outside the scorer parity guarantee. |
| `hooks.session_start.handle` and inline `session-start.sh` | Pin the intentionally changed merged stdout for a newly introduced mapping containing a null reset, and Python/inline parity. This correction applies to all overlay keys, not only `next`. |
| `hooks.edit_batch_nudge._load_settings` | One absent-ancestor null/default case preserves effective settings; existing leaf fallback semantics need no production refactor. |
| `session_store.db._read_backend_block` | A local null under an absent/scalar backend mapping disappears from the returned raw block. Exercise this helper directly; when testing `load_backend_config`, clear its per-process cache before/after the case so cached settings cannot hide the change. Use the local stub/config-resolution tests, not a live remote service. |
| `init.writers.merge_with_existing` | Non-force merge continues to strip incoming null leaves before merging, retains existing unmodeled/base-null values and partial/nondefault `next`, and leaves both inputs unchanged. Preserve the force/empty-existing branches. |
| `fsm.fragments._deep_merge` | Existing null-retention policy remains unchanged; no production edit. |

The nullable-default source audit on `main` found three config dataclass fields whose type permits `None` but whose default does not equal `None`: `ProjectConfig.type_cmd` (derived `mypy <src_dir>`), `ProjectConfig.format_cmd` (`ruff format .`), and `RetentionConfig.raw_event_max_age_days` (`90`). For local nulls under newly introduced mappings, default restoration is intentional; with existing mapping ancestors the old merger already restores these defaults. Pin both ancestor shapes and preserve explicit base-only nulls: those still disable the corresponding command or retention operation. `ll-session compact`/`prune` currently read base JSON directly, so do not claim this merge correction changes their local-override behavior or add overlay loading there. Document the distinction between a local null reset and a retained base null with meaningful disable semantics.

## Program Design

### Signatures

- `weighted_sum(scores: Mapping[str, float], weights: Mapping[str, float]) -> float`.
- `weighted_geometric(scores: Mapping[str, float | None], weights: Mapping[str, float], *, floor: float = 1e-6) -> float | None`.
- `frequency_score(run_count: int) -> float` — accepts a nonnegative integer excluding booleans; zero returns `0.0`. Invalid arguments or counts unrepresentable in `log1p`'s float arithmetic raise `ValueError`. Preserve the reference count of 50 and the uncapped `log1p` formula for valid inputs.
- `recency_score(started_at: str | None, *, as_of: datetime) -> float` — preserves the seven-day half-life, expression order, and existing timestamp fallback behavior. Require a timezone-aware datetime; the command supplies UTC, while an offset-aware `as_of` representing the same instant must give the same score. Reject invalid/naive `as_of` with `ValueError` before timestamp fallbacks, even when `started_at` is missing. A caller clock error must not become zero recency. The legacy extreme-future `OverflowError` is unchanged.
- `cmd_next_loop(args, loops_dir, logger, config: BRConfig) -> int` — receives the config already loaded by `main_loop`.
- `_score_loop(runs: list[dict[str, Any]], *, as_of: datetime, weights: Mapping[str, float]) -> tuple[float, float, str | None]` and `_build_rationale(run_count, success_rate, last_started_at, param_note, *, as_of: datetime) -> str` remain private adapters with required injected values. Update existing callers/tests; do not add default clocks, optional config, or config reloads to keep old private signatures working.
- `NextConfig.resolve_loop_history_weights(self) -> dict[str, float]` returns a fresh validated effective mapping in canonical `frequency`, `recency`, `success` order, or raises `NextConfigError` at the consumer boundary. Construction of `BRConfig` preserves invalid `next` input for later validation without raising a next-specific error. The method does no I/O, does not cache a caller-mutable result, and neither mutates nor returns an alias of the retained raw envelope; test that mutating its result or a serialized `next` subtree cannot change later resolution/serialization. No additional typed weight record or generic resolver framework is required. Root allowed-key checking is shared; each resolver validates its own consumed subtree, allowing FEAT-3561 to add independent `resolve_*` methods later.

### Aggregator contracts

- Both aggregators accept keyed mappings. Numeric arguments accept `int` or `float`, excluding booleans; weights must be finite and nonnegative. Nonnumeric values, NaN, and infinities are invalid. Supplied score keys without corresponding weights are invalid rather than silently ignored. The module is pure: no filesystem, database, clock, or network access.
- Numeric validation must itself fail in a controlled way: an integer such as `10**400` can raise `OverflowError` during `float(...)` or `math.isfinite(...)`. Reject values that cannot be represented finitely for float arithmetic with axis-naming `ValueError`, including on zero-weight axes; the config resolver translates invalid weight leaves to setting-naming `NextConfigError`. Do not coerce numeric strings or booleans. This representation check is distinct from clipping scores, normalizing weights, or changing the legacy recency curve's exception.
- Validate every supplied non-missing score even when its weight is zero; a disabled axis does not excuse NaN, infinity, a boolean, or an out-of-domain value. Invalid arguments raise `ValueError` with the axis name. For the geometric helper only, absent/`None` scores remain valid missing evidence, including on zero-weight axes.
- **Additive:** every key in the supplied weights mapping, including a zero-weight key, must have a finite, nonnegative real score, excluding booleans. Missing/`None` scores are invalid; the legacy adapter represents missing recency as an explicit `0.0`. Scores above 1 are allowed. Iterate in the supplied weight mapping's order using ordinary left-to-right multiplication/addition; the legacy adapter constructs that mapping in the canonical order `frequency`, `recency`, `success` regardless of config key order. Do not normalize, clip, use `math.fsum`, or change the arithmetic association. Two empty mappings return `0.0`; the command separately rejects configured weights that are all zero.
- **Finite aggregate:** if nondefault finite weights overflow an additive product/sum, raise `ValueError`; the command translates that into the same exit-2 diagnostic boundary as invalid weights, with empty stdout and no execution. Do not silently emit infinity/NaN into rankings or JSON. This does not change the default legacy arithmetic.
- **Geometric:** an absent score key or `None` means missing; a supplied zero is present. Present scores must be finite real numbers in `[0, 1]`, excluding booleans. Zero-weight axes contribute nothing. Aggregate only present positive-weight axes, renormalizing their weights. Return `None` if none resolve, including empty input or an all-zero weight mapping; never invent utility `0` or `1` for missing evidence.
- **Analytical oracle:** pin a hand-computed sparse case: scores `{"a": 0.25, "b": None, "c": 1.0, "d": 0.5}` and weights `{"a": 1, "b": 5, "c": 1, "d": 0}` yield `0.5` within ordinary floating-point tolerance. This proves missing and disabled axes do not enter the denominator. Include a single present zero-score case yielding `floor`; do not derive expected values using a second copy of the implementation.
- **Geometric numerics:** normalize included weights by their maximum before computing normalized shares, so finite weights such as `1e308/1e308` do not overflow their denominator. Test large equal weights and small positive weights; scale-invariance assertions apply only when the scaled weights remain finite and positive. Do not use this normalization on the additive path.
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
- Use a narrow raw-preserving `NextConfig` envelope: retain whether the root `next` key exists in the **merged** configuration, and deep-copy its merged value without assuming it is a mapping. A whole-section local null reset removes the key and therefore resolves/serializes as absent; do not infer presence from the pre-merge file or add provenance tracking. `BRConfig.next` exposes that envelope; an explicit resolver produces typed effective weights or raises `NextConfigError`. Construction and `to_dict()` perform no next-specific validation. Serialization emits a fresh copy of the supplied raw `next` value verbatim, including partial objects, nulls, malformed shapes and unknown keys; when absent, emit the default tree above. Neither resolution nor serialization modifies the retained raw value. Never turn invalid supplied input into defaults. Pin missing versus supplied-null and valid-partial/nondefault/invalid serialization idempotence with explicit parametrized cases; a general deferred-validation framework is unnecessary.
- Declare `additionalProperties: false` at the `next`, `loop_history`, and `weights` levels. Keep the allowed `next` root keys in one resolver constant (`loop_history` only), mirrored by the schema. Only the three named weight keys exist in this issue. Each supplied weight is a number with minimum 0; there is no normalization requirement or upper bound. All three effective weights being zero is a runtime config error.
- Unknown-key diagnostics must handle YAML integer/boolean keys as well as strings without leaking `TypeError`. Allowed keys are strings, so these are already unknown keys; no separate key-validation framework is needed. Format offending keys with `repr`, sort the resulting strings, and name the parent setting in `NextConfigError`. Add one real YAML-load/merge/resolver fixture with mixed string/integer/boolean weight keys; existing entry-point config-error cases cover the CLI boundary without repeating a malformed-input matrix.
- A one-key `.ll/ll.local.md` override preserves sibling weights. Local `null` removes a configured leaf, so subsequent default resolution restores its default; a zero weight intentionally disables that contribution. Any explicit null surviving in the final merged `next` value is invalid. A base-file null overwritten by a valid local value, or removed by a local null, is no longer supplied to the resolver and does not cause an error; do not validate the pre-merge file or add provenance tracking. Pin surviving, overwritten, and removed base-null cases.
- Pin local resets at each ancestor: `next: null` removes the root; `next.loop_history: null` removes only that child; `next.loop_history.weights: null` removes only the weight object. Resolution supplies defaults at the omitted level, while serialization follows the existing raw-envelope rule (absent root emits the default tree; present partial root remains partial). Keep unaffected siblings. These differ from supplying the same null in the merged base configuration.
- Reset semantics also apply when `next`, `loop_history`, or `weights` was absent from the base file, or the local override replaces a non-object base value. `config.core.deep_merge` currently recurses only when both sides already contain a mapping, so a null leaf inside a newly introduced mapping survives instead of being removed. Include the small merge correction as an isolated first production change after golden capture: recurse over override mappings against an empty mapping when the base is missing/non-mapping, preserving array replacement and input immutability. Audit the config, session-start, edit-batch, history-backend, init-writer and inline-hook consumers named above; record their reset regression or unchanged-policy coverage in the implementation notes. Keep the retained inline merge in `hooks/scripts/session-start.sh` consistent, with a Python/inline-hook parity regression; Python hook handlers already import the shared function. Test absent ancestors and scalar-to-object replacement, not only a populated base object. Do not reinterpret base-file null as a reset in the resolver.
- FEAT-3561 may add a separate `next.verbs` object when its per-verb settings have consumers. Its extension must update both the shared resolver's allowed root keys and schema, preserving strict `loop_history` validation and proving legacy next-loop still works alongside valid arena settings. It must not reinterpret `next.loop_history.weights` as arena weights. Do not add an extension registry or unused `verbs` setting here.
- Invalid consumed shapes, unknown keys, invalid numeric values, or an all-zero effective set yield exit 2, one concise stderr diagnostic naming the setting, and empty stdout in both text and JSON modes. There must be no traceback, recommendation rendering, or `cmd_run` call on that path. Invalid `next` settings alone must not prevent unrelated commands from constructing `BRConfig` and running.
- Validation precedes the loop archive scan (`_scan_history` under `.loops/.history`), so invalid consumed config takes exit-2 precedence even with no history or all candidates excluded. This does not remove `main_loop`'s existing `cli_event_context` telemetry or impose FEAT-3561's history-free CLI contract on this legacy command. Entry-point tests stub that existing telemetry; assert no archive scan or execution. Catch `NextConfigError` from the resolver. Around the `weighted_sum` call alone, translate its `ValueError` to a controlled aggregation diagnostic naming `next.loop_history.weights` and the affected loop; all candidates are scored before rendering. Do not wrap the whole handler or `_score_loop` in a broad `ValueError`/`OverflowError`/`Exception` catch that relabels history, parameter, rendering, or legacy curve failures as configuration errors.
- Preserve current no-history/all-excluded behavior: exit 1 with existing text or JSON `[]`. Successful recommendation output remains exit 0; text `--execute` continues to return the dispatched run result.

### Call Path

`main_loop` → `cmd_next_loop(..., config)` → resolve/validate legacy weights → capture one `as_of` → existing history scan and `_score_loop` adapter → pure curves and `utility.weighted_sum` → existing rendering with the same `as_of` for rationale. Capture `as_of` via the existing module-level `next_loop.datetime` name so the pre-extraction frozen-clock goldens keep exercising the real clock boundary after refactoring. Pass the already-loaded config without another handler-level `BRConfig(Path.cwd())` load; leave the existing autodev parameter resolver unchanged. Preserve timestamp selection, stable score-only sorting, status counting, parameter resolution, and output formats. FEAT-3561 later calls `utility.weighted_geometric` after its own gate evaluation; neither utility function reads project state itself.

## Implementation Steps

1. Before changing production code, capture literal text and JSON golden output against the current implementation with color settings and both clock reads fixed. Use a compact multi-loop filesystem fixture with the current flat archive layout (`.loops/.history/<run_id>-<loop_name>/state.json`), covering ties, more than 50 runs, missing/malformed/naive/future timestamps, and mixed run statuses. Include offset timestamps whose lexical and chronological order differ. Pin the raw additive formula as well as rendered rounding; characterize `_score_loop([])` and the extreme-future exception separately from successful output goldens.
2. Land the bounded shared-merge correction and retained inline-hook parity as an isolated change. Complete the fixed consumer checks in Shared-Merge Verification Boundaries and record regression/unchanged-policy evidence before adapting scoring/config, including the intentional effective CLI-color default restoration; preserve opaque array replacement, base-only nulls, input immutability, init's null stripping and fragment merge semantics. Split/reconsider the merge correction if these checks reveal unexpected consumer behavior beyond the documented reset change.
3. Extract the pure response curves and additive scorer, passing `as_of` through scoring and rationale. Preserve the empty-run fast path, canonical arithmetic/exponential expression order, timestamp string ordering, stable tie order, success counting, JSON `round(..., 4)`, and text `.3f` formatting. Add direct public-curve tests for zero/negative/fractional/boolean/unrepresentable run counts, invalid `as_of`, and equivalent aware clock instants; assert the command captures the UTC clock once and neither pure utility nor rationale reads it independently.
4. Add the consumed config/schema, complete root/export/serialization wiring, pass config through dispatch, and resolve/validate it at the consumer boundary. Map the new `NextConfig` dataclass to `next` in `_DATACLASS_SECTION_MAP` (and any nested config dataclasses added); register `next` as deliberately untouched by init in its schema coverage guard. Test defaults, deliberate nondefault ranking changes, partial objects, one-key local merge, local leaf/whole-section removal/default restoration (including absent ancestors), malformed shapes, unknown keys, invalid numbers, and all-zero weights. Preserve malformed raw `next` values until resolution; parsing or serializing unrelated config must not coerce them into defaults or raise a next-specific error. Verify an invalid `next` value does not break an unrelated command, and invalid consumed config fails before scanning even when history is absent or all loops are excluded.
5. Add the geometric helper with focused missing-axis, zero-weight, zero-score, floor, no-utility, and invalid-input tests, including oversized integers and invalid arguments on otherwise empty/missing evidence. Include the independent analytical sparse-axis/floor cases above. Test invariance to multiplying all included weights by the same positive factor; keep gate evaluation tests in FEAT-3561. Reuse numeric validation with representative boundary cases rather than multiplying the same large test grid across every function.
6. Add CLI cases for exclusions, no history, resolved parameters where practical, and `--execute` with `cmd_run` mocked. Preserve the existing behavior that `--json --execute` renders JSON without dispatching execution. Update docs and run the local suite, lint, and type checks.

## Impact

- **Priority**: P3 — prerequisite for FEAT-3561 without changing current recommendations.
- **Effort**: Medium — scorer extraction, config/schema and tests.
- **Risk**: Medium — a default or time-source change could silently reorder existing output.
- **Breaking Change**: No scoring or CLI format change with unchanged effective settings. The shared merge fix intentionally changes previously broken nested local-null resets, including settings outside `next`; document that correction.

## Acceptance Criteria

- [ ] Golden output is captured before extraction. With default weights and unchanged effective settings outside `next`, text and JSON remain byte-identical with a fixed clock shared by recency and rationale, including stable ties, rounding, uncapped frequency, future recency, timestamp fallbacks/string ordering, and mixed statuses. Intentional local-null/default restoration has separate before/after evidence.
- [ ] Default legacy weights are exactly `0.50/0.30/0.20`; the additive path retains the original multiplication/addition order without normalization, clipping, or `math.fsum`.
- [ ] The legacy empty-run tuple and extreme-future recency exception are characterized and preserved. Public curve argument validation distinguishes a bad caller clock/count from missing timestamp evidence; scoring/rationale share one captured UTC instant without additional clock reads.
- [ ] Pure aggregator tests enforce the contracts above: valid/invalid weights and score domains, missing data, zero weights, ordinary zero scores, the floor and values below it, geometric weight-scale invariance, and `None` when no positive-weight axis resolves. No gates or make-up term are added.
- [ ] Zero-weight scores are still validated; large finite geometric weights normalize safely; oversized integer validation never leaks conversion exceptions; additive overflow from nondefault weights produces a controlled exit-2 failure before rendering/execution without catching legacy curve exceptions.
- [ ] `next.loop_history.weights` is declared in `config-schema.json` with matching runtime validation, unknown-key rejection, and defaults. Partial objects and one-key local overrides preserve siblings; local leaf removal restores a default; explicit zero remains zero.
- [ ] Local leaf and ancestor null resets work with missing ancestors and scalar-to-mapping replacement; null surviving in the merged `next` config is invalid, while overridden/removed base nulls are valid after merge. Shared and retained hook merge behavior agrees, base-only nulls/list contents and merge inputs remain unmodified, and the isolated merge correction has the fixed per-consumer evidence above, including CLI-color restoration, the three audited nullable defaults, uncached history backend reads and init writers. Base-null command/retention disable semantics, existing retention lifecycle tests and fragment merge remain unchanged.
- [ ] Root config/property/export/serialization wiring is complete; schema-default parity and dataclass-map completeness pass. The lazy envelope preserves supplied partial/nondefault/invalid `next` values through serialization, emits defaults only for an absent root, and has explicit idempotence and returned-data mutation-isolation tests without global validation. Its concrete resolver returns fresh canonical-order weights.
- [ ] Init's schema coverage guard accounts for `next` as deliberately untouched; non-force re-init preserves user `next` settings without new template/TUI wiring. All existing direct handler/scoring/rationale callers are updated for required config/clock injection, with no hidden clock/config fallback.
- [ ] The real `ll-loop next-loop` entry point handles invalid consumed config in text/JSON modes with exit 2, one concise stderr diagnostic, empty stdout, no traceback, no loop archive scan, and no execution, including no-history/all-excluded projects. A mixed-key YAML override yields a controlled setting-naming resolver error. Existing CLI telemetry is stubbed in entry-point tests. Invalid `next` values alone do not break unrelated commands.
- [ ] Existing no-history/all-excluded exit 1 behavior, exclusions, parameter resolution, mocked text execution, and JSON-with-execute behavior remain unchanged. Dispatch passes the already-loaded config through.
- [ ] No `ll-next` entry point or history schema change is introduced; `python -m pytest scripts/tests/`, lint and type checks pass.

## Related

- FEAT-3561 (stateless arena core; blocked by this issue) and EPIC-3710 (arena umbrella).
- FEAT-3711 owns recommendation events, acceptance, and the history schema bump; FEAT-3722 (deferred) owns bucket pressure and automatic attribution; ENH-3678 protects that bump and is not a prerequisite for this extraction.
- FEAT-3712 (backtesting) is cancelled; FEAT-3713/3714 own additional or deferred generators.

## Use Case

A user runs `ll-loop next-loop` with default configuration after the extraction and gets the same recommendation and explanation. They can override one legacy weight locally without replacing the others. A later `ll-next` implementation imports the pure geometric helper without copying loop-specific code or coupling its policy to legacy weights.

## Related Key Documentation

- `docs/reference/CLI.md` (`ll-loop next-loop`), `docs/reference/CONFIGURATION.md` (`next.loop_history.weights`), and `docs/reference/API.md` (pure utility contracts).

## Status

**Open** | Created: 2026-09-30 | Priority: P3

## Review Notes

- 2026-10-04: Pre-implementation review with `/ll:advise --signal user_requested --host claude-code --model opus` (confidence 0.74 across the three issues). Added zero-weight validation, stable geometric weight normalization, controlled nondefault additive overflow, and the source-proven local-null merge gap. Retained byte-identical default behavior and the small scope. Opus suggested clamping future timestamps; rejected here because curve corrections belong outside this extraction and FEAT-3561 already owns bounded arena adapters. An extreme future timestamp currently raises `OverflowError` in the legacy recency curve; characterize that exception rather than silently clamping it.

- Second Opus pass (2026-10-04, confidence 0.74): added the shared-merge consumer audit/parity check. Retained unconditional stable normalization in the new geometric helper; it never runs on the legacy additive path, so the concern about changing old score bits is inapplicable.

- 2026-10-05: Focused source/probe review and `/ll:advise --signal user_requested --host claude-code --model opus` (confidence 0.74). Added a refactor-stable frozen-clock seam, the empty-run fast path, explicit raw-envelope/serialization semantics, controlled oversized-integer validation, config-error precedence and a `weighted_sum`-only exception boundary. Expanded the merge audit to history backend and init writers and put that correction first after golden capture. Kept strict base-JSON null rejection and the shared merge correction in this issue: Opus preferred relaxed null semantics plus a separate BUG, but also found isolation with per-consumer evidence defensible; local-overlay reset semantics and base schema validity remain distinct. Kept the geometric helper because FEAT-3561 explicitly declares this prerequisite. Accepted aware-clock equivalence for the pure recency API while the command captures UTC. Baseline verification: 121 existing next-loop, dispatch and deep-merge tests passed; no production code changed in this review.

- 2026-10-05 (follow-up review on `main`): `/ll:advise --signal user_requested --host claude-code --model opus` recommended proceeding after concrete wiring fixes (confidence 0.80). Added the omitted `TestCmdNextLoop` caller migration and init schema coverage registration, required private clock/config injection, analytical geometric oracles, merged-root presence/reset semantics, and the future root-key/schema extension handoff. Replaced the open-ended shared-merge audit with fixed consumer checks and the correct backend test seam/cache handling. Source inspection and in-memory probes confirmed the intentional change to raw merged output while preserving base-only nulls, opaque list contents, edit-batch effective defaults, and init's existing null-stripping/preservation policy. Opus's dissent still preferred a separate merge BUG; retain the isolated first change, reopening that choice only if its regressions expose unexpected behavior. Baseline: 209 focused existing tests passed (next-loop helpers/dispatch/direct callers, merge, schema parity/completeness, init, session-start, edit-batch, history config). Only the issue changed; these passes do not verify the future implementation or replace its full-suite gate.


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-05_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 58/100 → LOW

### Concerns
- Deviates from the eager-validation `NextIssueConfig` pattern (deferred `NextConfigError` at the consumer boundary); justified in the issue, but it is a new config idiom.

### Outcome Risk Factors
- Broad enumeration across 16+ change sites (new `utility/` module, `next_loop.py`, dispatch, three config modules, schema, inline hook, ~10 test files, 3 docs) with moderate per-site depth (raw-preserving config envelope, deferred validation, controlled exception boundaries).
- Wide blast radius for the shared `config.core.deep_merge` correction: 6 dependents (`config/core.py`, `hooks/session_start.py`, `hooks/edit_batch_nudge.py`, `session_store/db.py`, `init/writers.py`, inline `session-start.sh`) must each be shown unchanged or regression-covered; the audit outcome is still open.
- Minor residual ambiguity: consumer-audit results and `_DATACLASS_SECTION_MAP` completeness are determined during implementation.

Follow-up disposition (2026-10-05): the source audit now fixes the expected consumer boundaries above, and the dataclass-map action is explicit. Their production regression evidence remains an implementation gate. The scores above are the prior confidence-check result; this review does not rescore them or treat Opus's advisory confidence as an outcome-gate waiver.

## Session Log
- `/ll:confidence-check` - 2026-10-05T18:50:34 - `1ad6292f-f7e1-46c9-9095-237d6fd2352d.jsonl`
- `/ll:audit-issue-conflicts` - 2026-10-05T03:38:27 - `a86cd5e0-6077-4ee6-8374-60b76cefc32b.jsonl`
