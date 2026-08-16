---
id: ENH-3086
type: ENH
title: ll-auto --only reports bare not_found with no did-you-mean for a wrong type
  prefix
priority: P4
status: done
captured_at: '2026-08-06T16:17:02Z'
completed_at: '2026-08-16T20:33:49Z'
discovered_date: 2026-08-06
discovered_by: capture-issue
labels:
- ll-auto
- cli-ux
- issue-management
verify_verdict: VALID
confidence_score: 97
outcome_confidence: 86
score_complexity: 24
score_test_coverage: 22
score_ambiguity: 16
score_change_surface: 24
---

# ENH-3086: ll-auto --only reports bare not_found with no did-you-mean for a wrong type prefix

## Summary

`_id_matches()` (`cli_args.py:366-386`) matches a bare numeric pattern against
any type (`_id_matches("ENH-732", "732") is True`) but requires exact equality
for a fully-typed ID (`_id_matches("ENH-732", "BUG-732") is False`). That is
correct behavior — a typed ID is an assertion about the type. But when it fails,
`_unreachable_reason()` (`issue_manager.py:1714-1748`) returns the bare string
`"not_found"`, even though it has already loaded every issue in the project and
could see that the same number exists under a different type.

Observed 2026-08-06: `ll-auto --only "ENH-3066,..."` reported
`ENH-3066: not_found`. The issue exists as **BUG-3066**
(`P3-BUG-3066-otel-loop-span-never-marks-error-outcome-never-emitted.md`).
`--only 3066` would have resolved it.

## Current Behavior

```
[01:46:34]   ENH-3066: not_found
```

No indication that `BUG-3066` exists, and no hint that the numeric form matches
across types.

## Expected Behavior

```
ENH-3066: not_found (did you mean BUG-3066? bare `3066` matches any type)
```

## Motivation

`--only` is typed by hand or copied from notes, and the type prefix is the
easiest part to get wrong — the number is the identity, the type is a
classification that can change. The fix is nearly free: the data needed for the
suggestion is already in scope at the point the bare string is returned.

Low priority: no work is lost, and the run reports it clearly at the end. This
is a legibility win, not a correctness fix.

## Current Pain Point

The operator must go grep `.issues/` to find out whether the ID was mistyped,
already closed, or genuinely nonexistent — three quite different situations that
currently share one output string.

## Proposed Solution

In `_unreachable_reason()`, in the `if not terminal_matches:` branch
(issue_manager.py:1810), before returning `"not_found"`: if `requested_id`
parses as `<TYPE>-<NNN>`, re-match `all_issues` on the numeric suffix alone. If
exactly one issue shares the number under a different type, return a suggestion
string; otherwise fall back to `"not_found"` unchanged.

```python
if not terminal_matches:
    suffix = requested_id.rsplit("-", 1)[-1]
    if suffix.isdigit():
        cross = sorted(
            i.issue_id for i in all_issues if i.issue_id.rsplit("-", 1)[-1] == suffix
        )
        if cross:
            return f"not_found (did you mean {', '.join(cross)}?)"
    return "not_found"
```

Keep the leading `not_found` token intact — loops and tests may match on it.

## Scope Boundaries

- **In scope**: the suggestion string in `_unreachable_reason()`.
- **Out of scope**: changing `_id_matches()` semantics. A typed ID must keep
  meaning what it says; loosening it to match across types would silently
  process the wrong issue, which is far worse than a clear `not_found`.

## API/Interface

`_unreachable_reason()` returns a human-readable string already documented as
free-form (`"human-readable reason string"`). Verify no test asserts exact
equality with `"not_found"` before changing it — prefer `startswith` there.

## Integration Map

| File | Anchor | Change |
|------|--------|--------|
| `scripts/little_loops/issue_manager.py` | `_unreachable_reason`, ~1810 | Cross-type suggestion |
| `scripts/tests/` | `not_found` assertions | Loosen exact-equality assertions if present |

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

- Confirmed current location (as of 2026-08-16): `_unreachable_reason()` signature at `scripts/little_loops/issue_manager.py:1780`; the `if not terminal_matches: return "not_found"` branch is at lines 1809-1810 (previously drifted through :1743/:1730-1748/:1806, now stable at :1809-1810 per repeated verification passes).
- `all_issues` in scope at the `not_found` return is `list[IssueInfo]` from `find_issues(self.config, category=self.category, status_filter=set(_ALL_STATUSES))` (`issue_parser.py:2462`); each element exposes `.issue_id: str` (e.g. `"BUG-3066"`), matching the Proposed Solution's `i.issue_id for i in all_issues` iteration.
- `_id_matches(candidate: str, pattern: str) -> bool` confirmed at `scripts/little_loops/cli_args.py:380` (signature) / `:398-400` (body): `if _NUMERIC_RE.match(pattern): return candidate.split("-")[-1] == pattern; return candidate == pattern`.
- Only caller of `_unreachable_reason()` in production code: `AutoManager.run()` at `issue_manager.py:1937`, reached inside the `if self.only_ids:` / `if unreached:` block (`issue_manager.py:1932-1937`).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:1937` — `AutoManager.run()` calls `self._unreachable_reason(requested_id)` and logs the result; no other production call sites exist repo-wide.
- `scripts/tests/test_issue_manager.py` — six direct-call tests: `test_unreachable_reason_classifications` (:3769-3795), `test_unreachable_reason_attempted_and_failed` (:3797-3816), `test_unreachable_reason_attempted_no_recorded_outcome` (:3819-3836), `test_unreachable_reason_was_blocked_and_plan_created_wording` (:3838-3874), `test_unreachable_reason_earlier_run_suffix` (:3877-3897), `test_unreachable_reason_catch_all_reworded` (:3899-3918).
- `scripts/tests/test_issue_manager.py:3748-3767` — `test_run_returns_one_when_only_id_not_found` exercises `AutoManager.run()` end-to-end but only asserts `result == 1` and that `mock_process` was never called; it does not inspect the reason string, so it is unaffected by this change.

### Conventions in Force
- This codebase's existing "did you mean" wording appends the suggestion as a trailing sentence, not a parenthetical — e.g. `f" Did you mean \`{matches[0]}\`?"` in `_check_evaluate_unknown_keys` (`scripts/little_loops/fsm/validation/structural_rules.py:~1548-1566`) and `f"Did you mean target={suggested_target}?"` in `_check_zero_retry_budget` (same file, `~1164-1177`) — both capitalize "Did you mean" and backtick-quote the suggestion. A third, lowercase instance is documented (not yet implemented) in `.issues/bugs/P2-BUG-2069-*.md`. ENH-3086's own proposed wording nests the suggestion inside parentheses after the base token instead, which follows this function's *own* internal convention (see next bullet) rather than the repo-wide "did you mean" convention — both conventions coexist and the choice is a stylistic one, not settled by precedent.
- `_unreachable_reason()` already embeds optional parenthetical detail on other branches in the same function — e.g. `f"{issue_id}: attempted, {state.failed_issues[issue_id]}{_earlier_run_suffix(issue_id)}"` producing `"...verification failed (earlier run)"` (tested at `test_issue_manager.py:3897`). This is the established in-function shape: base token, then a parenthesized qualifier appended directly.
- A second, independently-written ID resolution helper, `_resolve_issue_id()` (`scripts/little_loops/cli/issues/show.py:41+`), treats a mismatched type prefix as advisory and silently resolves to the correctly-numbered file (BUG-2003 policy), tested at `scripts/tests/test_issues_path.py:308-350`. This is a materially different policy from `_id_matches`/ENH-3086, which only *suggests* the cross-type ID rather than resolving to it — both conventions exist side by side, tied to different call sites (`ll-issues path`/`show` vs. `ll-auto --only`). ENH-3086's Scope Boundaries section already rules out adopting `_resolve_issue_id`'s silent-resolve behavior here; this is confirmation that boundary is deliberate, not an oversight.
- No shared "resolve or disambiguate" (0/1/many) helper exists to reuse for the cross-type suffix lookup; `_id_matches`'s own numeric-suffix branch (`candidate.split("-")[-1] == pattern`) is the closest existing logic, but it cannot be reused directly for the *pattern* side (a full typed `requested_id`) — its cross-type-matching branch only triggers when the *pattern* argument is purely numeric.

### Tests
- `scripts/tests/test_issue_manager.py:3793` is the only exact-equality (`==`) assertion against `"not_found"` in the suite: `assert manager._unreachable_reason("BUG-999") == "not_found"`. This is the assertion the issue's own API/Interface section flags as needing verification before widening the return string — confirmed as the sole exact match.
- No `startswith("not_found")` assertion exists anywhere in the suite today (grep confirmed zero matches) — the API/Interface section's suggestion to "prefer `startswith`" would be a new test pattern, not an existing one.
- The suite's existing convention for multi-outcome joined strings (the `"; "`-joined `already_<status>` branch) uses substring (`in`) assertions instead of exact equality (e.g. `test_unreachable_reason_classifications:3794`: `assert "BUG-006 blocked by: BUG-005" in manager._unreachable_reason("BUG-006")`) — exact-equality is reserved for single-outcome branches, which is the category `not_found` currently falls into.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

### Types
- No new data shape introduced. `all_issues: list[IssueInfo]` (existing type, `issue_parser.py:1759`) is reused; each `IssueInfo.issue_id: str` is the only field the cross-type lookup needs.

### Signatures
- `AutoManager._unreachable_reason(self, requested_id: str) -> str` — `scripts/little_loops/issue_manager.py:1780`. Existing signature, unchanged; only the `not_found` branch body (lines 1809-1810) gains new logic.
- `_id_matches(candidate: str, pattern: str) -> bool` — `scripts/little_loops/cli_args.py:380`. Existing helper, not modified (Scope Boundaries already rules this out) but its numeric-suffix branch (`candidate.split("-")[-1] == pattern`, `cli_args.py:398-400`) is the logic the new cross-type lookup parallels rather than calls directly, since here the *pattern* side is a full typed ID whose suffix must be extracted first via `requested_id.rsplit("-", 1)[-1]`.

### Call Path
`AutoManager.run()` (`issue_manager.py:1937`) → `_unreachable_reason(requested_id)` (`issue_manager.py:1780`) → existing `all_issues = find_issues(self.config, category=self.category, status_filter=set(_ALL_STATUSES))` (`issue_parser.py:2462`, already computed in this branch today) → [new] cross-type suffix scan over `all_issues` keyed on `i.issue_id.rsplit("-", 1)[-1] == suffix` → returns either the widened `"not_found (did you mean ...)"` string or the unchanged `"not_found"`.

### Decision Rules
- **Trigger condition**: only fires inside the existing `if not terminal_matches:` branch (`issue_manager.py:1809`) — i.e., only when zero issues match `requested_id` under `_id_matches()` at all, including terminal statuses.
- **Match rule**: `requested_id.rsplit("-", 1)[-1]` must be all-digits (`.isdigit()`); if the requested ID has no `-` or a non-numeric suffix, the cross-type lookup is skipped and plain `"not_found"` is returned unchanged.
- **Cardinality**: the Proposed Solution's snippet does not special-case "more than one cross-type match" — if 2+ issues share the numeric suffix under different types, all are listed comma-separated in a single suggestion string (`", ".join(cross)`); there is no distinct "ambiguous" wording or behavior for that case, unlike the 0/1/many disambiguation pattern used elsewhere in this codebase (e.g. `text_utils.py:suffix_match_candidates()`, `cli/queue.py:_not_found_or_ambiguous()`) which was surveyed and found to have no shared helper applicable here.
- **Escape hatch**: any requested ID whose suffix matches zero other issues (a genuinely nonexistent ID) still returns the unchanged bare `"not_found"` — the leading token is preserved either way per the issue's own "Keep the leading `not_found` token intact" instruction, so callers matching on `.startswith("not_found")` or the literal string as a prefix are unaffected; only the sole exact-equality assertion at `test_issue_manager.py:3793` needs updating.

## Implementation Steps

1. Grep the test suite for exact `"not_found"` assertions.
2. Add the cross-type lookup and suggestion.
3. Test: wrong prefix suggests the right ID; genuinely absent ID still returns
   plain `not_found`.

## Impact

Purely diagnostic. No behavior change to which issues are processed.

## Status

open

## Verification Notes

**2026-08-10** (`/ll:verify-issues`): Verified 2026-08-10: `_id_matches()`
confirmed in cli_args.py:380 matching description. `_unreachable_reason()`'s
`not_found` branch confirmed in issue_manager.py, but now around line 1806,
not the previously cited :1743/:1730-1748. Logic and shape unchanged, only
line numbers drifted.

**2026-08-12** (`/ll:verify-issues`): Re-verified VALID; refreshed the
`_unreachable_reason()` citation to the exact current line (issue_manager.py:1810)
in the Proposed Solution and Integration Map sections.

## Session Log
- `/ll:manage-issue` - 2026-08-16T20:33:28 - `4461670e-6ad1-40b8-9a36-bfaee7770c79.jsonl`
- `/ll:confidence-check` - 2026-08-16T19:41:27 - `a441e649-6a94-4074-a117-b8df44bd2807.jsonl`
- `/ll:refine-issue` - 2026-08-16T19:37:24 - `0fd7d919-ef7e-411a-97ea-008f8e6eed78.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:12 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:26:28 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:capture-issue` - 2026-08-06T16:20:22 - `ee676905-966c-42aa-ac9d-d7d4aaeea91d.jsonl`
