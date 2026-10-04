---
id: ENH-3725
type: ENH
title: Model-specific cacheable prefix minimum for Sonnet 5.5
priority: P3
status: done
discovered_by: capture-issue
discovered_date: '2026-10-03'
captured_at: '2026-10-04T01:44:09Z'
completed_at: '2026-10-04T19:54:21Z'
testable: true
relates_to:
- EPIC-2456
- FEAT-2673
- BUG-3701
- EPIC-3562
confidence_score: 95
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3725: Model-specific cacheable prefix minimum for Sonnet 5.5

## Summary

Make the cache-marking oracle select a model-specific cacheable-prefix minimum for `claude-sonnet-5-5`. The verified Sonnet 5.5 minimum is 512 tokens, while the current generic Sonnet rule requires 1024. This is a standalone follow-up related to the completed EPIC-2456, and does not reopen that epic or gate EPIC-3562.

## Current Behavior

`CACHEABLE_PREFIX_MINIMUMS` contains family defaults (Sonnet 1024, Opus 4096). `_prefix_minimum_for` performs family substring matching, so concrete Sonnet 5.5 requests with stable 512–1023-token prefixes fail the oracle's size gate. `build_anthropic_request` passes its resolved concrete model into `decide_cache_marking`; SDK/batch callers already share that request path. Today the `sonnet` alias resolves to `claude-sonnet-5`; BUG-3701 owns changing that alias to Sonnet 5.5. This issue can ship independently for explicit Sonnet 5.5 requests and does not change default SDK/batch model selection.

## Expected Behavior

Use a verified exact model override for Sonnet 5.5 before the existing family fallback. Preserve older/pinned Sonnet defaults and the conservative unknown-model fallback. After case normalization, only the exact verified ID receives 512. Unverified dated/provider-prefixed Sonnet IDs keep the 1024 family floor; IDs matching no known family keep 4096. The size gate and reuse-stability gate remain independent; a sufficiently large first-sighting fragment still requires a repeat unless `require_repeat=False`.

## Motivation

Explicit Sonnet 5.5 requests with stable prefixes in the 512–1023 range are unnecessarily ineligible for marking. Default alias requests benefit once BUG-3701 lands. A model override addresses the verified gap without lowering the whole Sonnet family floor.

## Proposed Solution

Add an exact concrete-model minimum map (or equivalent small lookup) before the existing family defaults in `_prefix_minimum_for`, using the existing case-insensitive normalization for both lookups. Do not infer suffix/provider aliases without evidence: `build_anthropic_request` already resolves normal supported aliases before calling the oracle. Reconfirm the vendor minimum at implementation time and cite its date; preserve existing conservative behavior for unverified spellings.

Sources reverified 2026-10-04: [Anthropic Sonnet 5.5 overview](https://platform.claude.com/docs/en/models/sonnet-5-5/overview) states a 512-token minimum; [prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) documents prefix/breakpoint semantics. Replace the oracle docstring's claim that the floors were verified by `.ll/learning-tests/anthropic.md`: that proof covers SDK Usage fields and client-side acceptance of a cache-control dict, not vendor minimums. These are documented vendor constants with no runtime verification, distinct from the approximate `len(text) // 4` estimator.

Require differential integration fixtures at the actual marked prefix: empty `skill_body`, no tools, and `system_prompt="x" * 2048` (512 estimated tokens). For each of the SDK and batch builders, the first concrete Sonnet 5.5 call stays unmarked and the repeat carries `cache_control`; the same repeated older-Sonnet request stays unmarked. Isolate ambient auth variables as existing tests do. Existing 5000-character fixtures cannot discriminate the new threshold. Do not let a long skill body outside the marked system/tool prefix make the fixture eligible; broader builder accounting is a separate existing concern.

## Integration Map

### Files to Modify

- `scripts/little_loops/cache_marking_oracle.py` — lookup order and source comments/docstring.
- `scripts/tests/test_cache_control.py` — floor boundaries and request-shape integration.
- `scripts/tests/test_batch_request_path.py` — required differential batch request test with the same system-only fixture.
- `docs/reference/API.md` — model-specific floor, lookup precedence and estimator/source limits.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/host_runner.py::build_anthropic_request`; SDK and batch dispatch using that request.

### Similar Patterns

- FEAT-2673's conservative unknown-model floor and repeat gate; keep both.

### Tests

- Sonnet 5.5 boundaries 511/512/1023 under `len(text) // 4`, first/repeat sightings, and `require_repeat=False`. The 511 case must remain rejected even when the repeat gate is disabled.
- Preserve pinned older Sonnet boundaries 1023/1024, unknown-model boundaries 4095/4096, and existing case-insensitive lookup. Unverified dated/provider-prefixed Sonnet spellings retain 1024; no guessed 512 matching.
- Both SDK and batch builders use the system-only 2048-character fixture: literal Sonnet 5.5 first/repeat behavior plus an older-Sonnet negative twin. Assert the literal request model and marker on the system block, not just a spy or table-derived assertion. Alias target regressions stay in BUG-3701.

### Documentation

- Oracle source comments/docstring and `docs/reference/API.md`: dated vendor links, exact-ID/family/unknown lookup order, approximate estimator, no runtime verification, and the BUG-3701 alias limitation. Do not relabel the existing SDK learning proof as evidence for vendor floors.

### Configuration

- No new option, tokenizer, SDK dependency, or network test.

### Behavior Parity

| Artifact | Behavior | Disposition |
| --- | --- | --- |
| `scripts/little_loops/cache_marking_oracle.py` | Verified exact Sonnet 5.5 size floor | Changed to 512; family defaults, unknown fallback and repeat gate preserved |
| `scripts/little_loops/cache_marking_oracle.py` | Source attribution for vendor floors | Changed to dated vendor documentation |
| `.ll/learning-tests/anthropic.md` | SDK Usage-shape and cache-control acceptance proof | Preserved unchanged; does not prove vendor token floors |

## Program Design

### Types

- Proposed exact-model minimum map: `dict[str, int]` with `claude-sonnet-5-5: 512`; retain `CACHEABLE_PREFIX_MINIMUMS` as family defaults.

### Signatures

- `_prefix_minimum_for(model: str) -> int` — normalize case, check the verified exact-ID map, then use unchanged family matching and the 4096 unknown fallback.
- `decide_cache_marking(..., model: str, require_repeat: bool) -> CacheMarkingDecision` — existing retains its two independent gates.
- Existing `build_anthropic_request` supplies the resolved concrete model.

### Call Path

SDK/batch request builder → `build_anthropic_request` → `decide_cache_marking` → exact-model floor then family fallback → repeat gate → `cache_control` request field.

## Implementation Steps

1. Reverify and date the Sonnet 5.5 vendor minimum; add the exact override before family fallback.
2. Add size/reuse boundary tests, including below-minimum `require_repeat=False`, older/unknown boundaries and unverified-ID fallback preservation.
3. Add the differential system-only first/repeat and older-model twin tests for both SDK and batch request shapes; update source/API notes without changing model aliases.

## Impact

- **Priority:** P3 — useful cache-marking correction, independent of the multi-host epic's implementation.
- **Effort:** Small — one override plus existing oracle/request tests.
- **Risk:** Low — exact override and preserved conservative fallbacks limit the change.
- **Breaking Change:** No; some verified Sonnet 5.5 prefixes become eligible for marking under the existing reuse rules.

## Acceptance Criteria

- [ ] Concrete `claude-sonnet-5-5` uses 512, with 511 rejected and 512/1023 accepted by the size gate under the current estimator convention.
- [ ] Size eligibility alone does not bypass the repeat requirement; first/repeat behavior is tested independently, and 511 estimated tokens remain rejected with `require_repeat=False`.
- [ ] Pinned older Sonnet IDs retain the 1024 minimum (1023 rejected, 1024 accepted); unmatched models retain 4096 (4095 rejected, 4096 accepted). Unverified dated/provider-prefixed Sonnet IDs keep 1024, and case-insensitive normalization is preserved; no family-wide lowering or guessed suffix matching.
- [ ] Both `build_anthropic_request` and `build_batch_request` send literal `claude-sonnet-5-5` for the isolated 2048-character system-only fixture: first sight has no marker, the repeat marks the system block, and the identical older-Sonnet twin remains unmarked. No positive fixture relies on skill text outside the marked prefix.
- [ ] Source/API notes cite the vendor minimum reverified 2026-10-04, distinguish it from the approximate estimator and SDK learning proof, and state that default `sonnet` model selection remains BUG-3701's responsibility; tests require no provider call or new dependency.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In scope:** verified Sonnet 5.5 minimum override, lookup precedence, size/reuse tests, request integration and source notes.
- **Out of scope:** reopening EPIC-2456, generic tokenizer accuracy, broader builder prefix/skill accounting, other model-family updates without evidence, new reuse-frequency policy, and EPIC-3562's host cutovers/pricing. `MODEL_ALIASES` and default-model changes belong to BUG-3701; this issue has no functional dependency on that alias change.

## Related Key Documentation

- `docs/reference/API.md` — cache-marking and request-builder contracts.

## Status

**Open** | Created: 2026-10-03 | Priority: P3

## Review Notes

Revised 2026-10-04 after code review and `/ll:advise` with Opus. The exact override remains independently shippable; differential tests now prove the new interval at an actual system breakpoint, and the source and alias limitations are explicit.

## Session Log
- `/ll:manage-issue` - 2026-10-04T19:54:20 - `0faec551-cc94-46ef-ba4c-d1070de99343.jsonl`
- `/ll:ready-issue` - 2026-10-04T19:43:10 - `66b8d17a-8c59-466e-b40a-8e4940d650d1.jsonl`
- `/ll:confidence-check` - 2026-10-04T19:40:37 - `f268a55b-7429-41df-a3c5-3bf77154c17c.jsonl`
- `/ll:capture-issue` - 2026-10-04T01:51:02 - `7ac1ad38-c74f-402b-a14d-5845cde7ff55.jsonl`

## Resolution

**Completed** 2026-10-04

- Added exact-ID override `_MODEL_PREFIX_MINIMUMS = {"claude-sonnet-5-5": 512}` checked before the family defaults in `_prefix_minimum_for` (`scripts/little_loops/cache_marking_oracle.py`); family floors, unknown-model 4096 fallback and the repeat gate are unchanged.
- Oracle docstring now cites the vendor docs (reverified 2026-10-04) and no longer attributes the floors to the SDK learning proof; `docs/reference/API.md` documents lookup order and the BUG-3701 alias limitation.
- Tests: boundaries 511/512/1023, case-insensitivity, repeat-gate independence, older-Sonnet/unknown/unverified-spelling floors (`test_cache_control.py`); SDK and batch differential system-only fixtures (`test_cache_control.py`, `test_batch_request_path.py`).
- Full suite: 27876 passed, 293 skipped, 8 errors — all in `test_libsql_integration.py::TestLive` (live remote endpoint, "remote schema changed unexpectedly"), unrelated to this change.
