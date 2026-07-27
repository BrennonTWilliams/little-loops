---
id: ENH-2836
type: ENH
priority: P2
status: done
parent: EPIC-2765
captured_at: '2026-07-27T00:08:18Z'
completed_at: '2026-07-27T05:27:43Z'
discovered_date: 2026-07-27
discovered_by: capture-issue
labels:
- cli
- doctor
- docs
- dx
confidence_score: 100
outcome_confidence: 81
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 20
---

# ENH-2836: ll-check-links conflates network timeouts with broken links

## Summary

`ll-check-links` reports unreachable-due-to-network-timeout external URLs as
`Broken`, indistinguishable from genuine 404s, and exits 1 on the aggregate
count. Because `ll-doctor --full` aggregates the `ll-verify-*`/`ll-check-links`
family (FEAT-2795), a flaky or offline network turns the documented preflight
gate red for reasons that have nothing to do with the repo's correctness.

## Current Behavior

A run on 2026-07-26 produced:

```
Summary:
  Total links: 3515
  Valid: 1207
  Broken: 326
  Internal refs: 1591
  Ignored: 391
```

with individual entries reading `Error: Connection error: timed out`. Exit code
is `1` (verified directly, not inferred from a piped `$?`).

326 "broken" of 3515 is large enough that the report carries no actionable
signal: a genuinely broken link committed today would be indistinguishable from
the timeout noise. In practice the check is read as "always red, ignore it,"
which is the failure mode that makes a gate worthless.

Note the ratio: 1207 valid + 326 broken = 1533 external links attempted, so
roughly **21% of external checks fail on timeout alone**.

## Expected Behavior

Timeout / DNS / connection-refused outcomes are a distinct category from an
HTTP error response, and are reported and exit-coded separately:

- **Broken** — the host answered and said no (404, 410, 500). Fails the gate.
- **Unreachable** — no usable answer (timeout, DNS failure, connection reset).
  Reported for visibility but does **not** fail the gate by default.

Exit 1 only on the `Broken` count. Offer a flag (e.g. `--strict-network`) for
callers that genuinely want unreachable treated as failure, and consider
`--offline` / `--skip-external` to check internal refs only.

## Motivation

`ll-doctor` is documented as the preflight gate for little-loops, and
FEAT-2795 folds this command into `ll-doctor --full`. A gate that fails on
ambient network conditions trains users to ignore it — and an ignored gate
catches nothing. The repo has no hosted CI, so local gates are the *only*
enforcement layer; their signal-to-noise ratio is load-bearing.

This also interacts with the exit-code semantics FEAT-2793 settled: the
check-registry protocol splits error-tier from warn-tier severity. "Unreachable
external host" is the archetypal warn-tier result and should flow through that
split rather than hard-failing.

## Proposed Solution

1. Classify each external-link failure at the point of capture. The requests /
   urllib exception type already distinguishes these — a timeout raises a
   different exception than a 404 response, so no heuristic string-matching on
   error text is needed.
2. Add an `Unreachable: N` line to the summary, separate from `Broken: N`.
3. Gate the exit code on `Broken` only.
4. Register the check with the FEAT-2793 check-registry at **warn** severity for
   unreachable and **error** severity for broken, so `ll-doctor --full`
   inherits the split rather than reimplementing it.
5. Consider a short retry (1 retry, backoff) before classifying as unreachable,
   and a bounded per-host concurrency cap — a chunk of the 326 may be one slow
   host being hit serially until it times out.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Severity-split precedent to follow**: `_capability_check_results()` (`scripts/little_loops/cli/doctor.py`, near line 69) already maps a subsystem's own outcome vocabulary into `CheckResult.severity` via a lookup set (`_ADVISORY_CAPABILITIES`) — `severity="informational" if c.name in _ADVISORY_CAPABILITIES else "error"`. `_full_des_audit_check()` (line 704-714) does the same by threading `severity=data.get("severity", "error")` up from its own adapter data. Point 4 of this solution should follow the `_full_des_audit_check` shape exactly: have `_full_check_links_data()` return a `"severity"` key alongside `"status"`/`"note"`, then have `_full_check_links_check()` pass it through — this is the only sibling adapter that currently omits this passthrough.
- **Enum pattern precedent**: no existing `LinkOutcome`-style enum exists yet for link status (current `LinkResult.status` is a bare string per the line-55 docstring), but `scripts/little_loops/parallel/types.py` has two directly analogous `Enum` classes (`MergeStatus`, `WorkerStage`, lines 165-199) using string `.value` members serialized via `.value` in `to_dict()` — a template for the proposed `LinkOutcome(Enum)` (`VALID`/`BROKEN`/`UNREACHABLE`/`IGNORED`).
- **Test-stubbing pattern already established**: `scripts/tests/test_link_checker.py::TestCheckUrl` uses `@patch("urllib.request.urlopen")` with `side_effect=urllib.error.HTTPError(...)` / `TimeoutError()` (lines ~142-198) to stub the fetcher per-outcome without live network calls — Implementation Step 6's new test cases should extend this same class rather than introduce a new stubbing approach. `test_check_concurrent_mixed_results` (line 323) shows the pattern for `patch("little_loops.link_checker.check_url", side_effect=<callable>)` to vary outcomes across concurrent URLs in one test.
- **No existing `--strict-network`/`--offline` flag precedent** — searched the full CLI surface, none exists. The new flag should follow the existing `action="store_true"` idiom already used for `--json`/`--fix`/`--verbose` in `main_check_links()` (`cli/docs.py`, alongside its current `--timeout`/`-t` and `-w`/`--workers` args, lines 313-431).
- **No shared retry-with-backoff utility exists** to reuse. The one comparable hand-rolled implementation is `WebhookTransport._post_with_retry` (`scripts/little_loops/transport.py`, lines 557-576) — doubling backoff (`_WEBHOOK_RETRY_BASE_S=0.5` capped at `_WEBHOOK_RETRY_MAX_S=8.0`), bounded by a `max_retries` constructor param, with a final warning log on exhaustion. It's transport-specific and not extracted to a shared module, so Implementation Step 5's retry-before-unreachable logic would need its own small inline implementation modeled on this shape rather than an import.

## Integration Map

| File | Change |
|---|---|
| `scripts/little_loops/` link-checker module (entry point `ll-check-links`) | classify failure modes; split summary counters; gate exit code on broken-only |
| `ll-doctor --full` aggregation (FEAT-2795) | consume the severity split rather than the raw exit code |
| `scripts/tests/` | tests for each classification using a stubbed fetcher; no live network in tests |

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — re-exports `main_check_links` from `cli.docs` (line 59) and lists it in `__all__` (line 107); no logic change needed but confirms the entry-point chain has exactly one re-export hop [Agent 1 finding]
- `scripts/little_loops/loops/lib/cli.yaml` — `ll_check_links` fragment (lines 70-77) shells out `ll-check-links 2>&1` and evaluates via `type: exit_code`; inherits the new broken-only exit-code semantics automatically, but its `description` field (lines 71-73) doesn't mention the unreachable/broken split and should be updated for loop authors [Agent 1 + Agent 2 finding]
- `scripts/little_loops/loops/docs-sync.yaml` — built-in FSM loop that consumes the `ll_check_links` fragment; no change needed but confirms one live consumer of the exit-code contract [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` § `### ll-check-links` (~lines 3053-3079) — flags table needs a `--strict-network` row (and `--offline`/`--skip-external` if implemented); the literal `**Exit codes:** \`0\` = all links valid, \`1\` = broken links found, \`2\` = error` line (3069) needs rewording for broken-only gating [Agent 2 finding]
- `docs/reference/CLI.md` line ~236 (`--full` section under `ll-doctor`) — describes the `--full` JSON payload shape for `check_links` as `{status, note}`; needs `severity` added to the schema description [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` line ~3402 — "Common Fragments" table row for `ll_check_links` documents its current behavior; should note the broken-only exit-code semantics [Agent 2 finding]
- `docs/reference/API.md` § `### main_check_links` (~lines 4143-4151) — one-line docstring summary; low risk but worth a pass if `--strict-network` warrants a flag mention for parity with other documented flags [Agent 2 finding]
- `docs/codex/usage.md`, `docs/reference/HOST_COMPATIBILITY.md` — matched in a broad grep for `check-links`/`check_links`; not content-verified, flagged as leads to check before closing out doc work [Agent 2 finding]
- `.claude/CLAUDE.md` line 227 (`ll-check-links` CLI Tools one-liner) — optional, but other severity-split checks (line 239, `ll-doctor --full` description) already document the error/warn split pattern; consider a matching mention [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_link_checker.py::TestCheckUrl` — return-tuple assertions on `check_url()` (`(is_valid, error_message)`) will need updating if the return contract changes shape to carry a `LinkOutcome`; existing `broken_links`/`has_errors` fixtures that stub `TimeoutError`/`URLError` and assert `broken_links == 1` must be re-classified to `unreachable_links` once the split lands [Agent 2 + Agent 3 finding]
- `scripts/tests/test_link_checker.py::TestFormatters::test_format_result_json` / `test_format_result_markdown_with_errors` — construct `LinkCheckResult(...)` without an `unreachable_links`/`LinkOutcome` field; safe if defaulted, but don't exercise the new fields — extend to cover them [Agent 2 + Agent 3 finding]
- `scripts/tests/test_cli_docs.py::TestMainCheckLinks::test_errors_returns_1` — mocks `LinkCheckResult` wholesale via `MagicMock(has_errors=True)`; still passes post-change but doesn't exercise `--strict-network` or the broken-vs-unreachable exit-code split — parametrize for both cases [Agent 2 + Agent 3 finding]
- `scripts/tests/test_cli_doctor_full.py::TestFullAdapters::test_check_links_reports_unsupported_on_broken` — add a `severity` assertion, following the sibling pattern `test_des_audit_reports_informational_when_missing`/`test_triggers_reports_unsupported_on_failure` (asserts `data["severity"]` after mocking the underlying data function directly) [Agent 3 finding]; add a parallel new case for an unreachable-only result asserting a non-error severity, mirroring `_full_des_audit_data()`'s `"informational"` shape [Agent 2 + Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` (line ~9434) and `scripts/tests/test_fsm_fragments.py` (lines ~895-901, ~965-988) — reference/test the `ll_check_links` fragment and `docs-sync.yaml`'s use of it; re-run after the fragment description update, no assertion changes expected since they test structural resolution, not exit-code semantics [Agent 1 finding]
- Retry-with-backoff test pattern to model Implementation Step 5 on: `scripts/tests/test_transport.py::TestWebhookTransport::test_retry_on_5xx_then_success` / `test_retry_exhausted_logs_warning` — closure-based `side_effect` with `nonlocal call_count`, `mock.patch("time.sleep")` to neutralize delay, and separate tests for "retries then succeeds" vs. "retries exhausted" [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Entry point chain**: `scripts/pyproject.toml:72` (`ll-check-links = "little_loops.cli:main_check_links"`) → `scripts/little_loops/cli/__init__.py` re-exports `main_check_links` → actual implementation in `scripts/little_loops/cli/docs.py` `main_check_links()` (starts line 313).
- **Exception classification site**: `scripts/little_loops/link_checker.py` `check_url()` (line 155) is the single choke point. Four branches all collapse to `(False, <error string>)` with no type distinction:
  - `urllib.error.HTTPError` (line 177-178) → `(False, "HTTP {code}")` — genuine broken.
  - `urllib.error.URLError` (line 179-180) → `(False, "Connection error: {reason}")` — **this is where most real-world timeouts actually land**, since `urlopen()` wraps low-level socket timeouts in `URLError(reason=TimeoutError(...))` before they'd hit a bare `TimeoutError`.
  - `except TimeoutError` (line 181-182) → `(False, "Timeout")` — exists but is reached inconsistently depending on connect vs. read phase.
  - `except Exception` (line 183-184) → generic catch-all.
  - Important nuance for Implementation Step 3: correctly classifying "unreachable" requires inspecting `URLError.reason` (is it a `TimeoutError`/`socket.timeout`/`ConnectionRefusedError`?) in addition to the bare `TimeoutError` branch — a plain `isinstance(e, TimeoutError)` check on the outer exception will miss most real timeouts.
- **`LinkResult.status` already documents `"timeout"` as a legal value** (`link_checker.py:55`) but no code path ever assigns it — the enum values exist in the docstring/type comment but not in practice, meaning the `status` field's contract is already wider than its current implementation.
- **Summary/exit-code chain**: `LinkCheckResult.has_errors` (line 80-83, `return self.broken_links > 0`) is the single boolean read by both `main_check_links()`'s exit code (`cli/docs.py:429-431`) and `ll-doctor`'s adapter — confirms Proposed Solution point 3 has exactly one call site to change per consumer.
- **`ll-doctor --full` adapter gap**: `_full_check_links_data()` / `_full_check_links_check()` (`scripts/little_loops/cli/doctor.py:717-732`) construct `CheckResult` **without** passing `severity=`, so it silently defaults to `severity="error"` (`CheckResult.severity` default, line 47) — unlike sibling adapters `_full_triggers_check()` (561-570), `_full_design_tokens_check()` (665-674), and `_full_des_audit_check()` (704-712), which all explicitly thread `severity=data.get("severity", "error")` from their own data function. Proposed Solution point 4 (register at warn/error split) requires *adding* this missing `severity=` passthrough, mirroring the `_full_des_audit_check` shape exactly.
- **No retry logic exists today** anywhere in `check_url()`/`check_markdown_links()` — confirms Proposed Solution point 5 is greenfield, not a modification of existing retry code.
- **Test files already covering this surface**: `scripts/tests/test_link_checker.py` (`TestCheckUrl`, lines 142-198) and `scripts/tests/test_cli_docs.py`; doctor-side coverage in `scripts/tests/test_cli_doctor_full.py`. All three will need new cases per Implementation Step 6.
- **Check-registry protocol mechanics (FEAT-2793), precise** — `scripts/little_loops/cli/doctor.py`: `register_check`/`_CHECKS` (55-61) and `register_full_check`/`_FULL_CHECKS` (458-469) are decorator/list pairs that collect no-arg `Callable[[], list[CheckResult]]` functions; `_run_registered_checks()` (90-95) flattens results; `_exit_code_for()` (98-101) is the exact fold: `1 if any(r.severity == "error" and r.status == "unsupported" for r in results) else 0`. This confirms Proposed Solution point 4's target shape precisely: a timeout-only result should resolve to `severity="informational"` (not just `status` alone) to avoid tripping `_exit_code_for()`.
- **No per-host concurrency precedent exists** for Implementation Step 5's "bounded per-host concurrency cap" — the only concurrency-limiting code in the repo is a flat, non-host-keyed `asyncio.Semaphore` in `scripts/doc_scraper.py` (`PageProcessor.__init__`, line 539-543, default `concurrent=3`, acquired per-fetch at line 600-602). If a genuine per-host cap is implemented, there's no existing host-keyed-semaphore pattern to model it on — it would be new structure, not an adaptation of prior art.

## Implementation Steps

1. Locate the link-checker implementation behind the `ll-check-links` entry
   point and identify where external fetch exceptions are caught.
2. Introduce a `LinkOutcome` enum (`VALID`, `BROKEN`, `UNREACHABLE`, `IGNORED`).
3. Map exception types to outcomes; keep HTTP status codes on the `BROKEN` path.
4. Split the summary rendering and the exit-code computation.
5. Add `--strict-network` to restore the old behavior for callers that want it.
6. Add tests with an injected fake fetcher covering: 404 -> broken, timeout ->
   unreachable, 200 -> valid, and exit codes for each combination.
7. Re-run against the real repo and record the new broken/unreachable split.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `main_check_links()`'s argparse epilog exit-code text (`cli/docs.py:342-346`) in the same change as the new `--strict-network` argument — it hardcodes the old `0/1/2` exit-code meanings directly in `--help` output, not just in docs.
9. Update `docs/reference/CLI.md` `### ll-check-links` (flags table + exit-codes line) and the `--full` JSON payload description for `check_links`.
10. Update the `ll_check_links` fragment's `description` in `scripts/little_loops/loops/lib/cli.yaml` (lines 70-77) and its row in `docs/guides/LOOPS_REFERENCE.md`'s Common Fragments table to reflect broken-only exit-code semantics.
11. Extend `test_link_checker.py::TestCheckUrl`/`TestFormatters`, `test_cli_docs.py::TestMainCheckLinks`, and `test_cli_doctor_full.py::TestFullAdapters` per the Tests subsection of the Integration Map, including a severity-split case mirroring `test_des_audit_reports_informational_when_missing`.
12. Re-run `scripts/tests/test_builtin_loops.py` and `scripts/tests/test_fsm_fragments.py` after the fragment description change to confirm no structural regressions.

## Impact

- **Users**: `ll-doctor --full` becomes trustworthy offline and on flaky
  networks; a red result once again means something is actually wrong.
- **Risk**: Low. Strictly a reclassification of results the command already
  produces; no change to what is fetched.
- **Effort**: Small — the exception types are already distinct at the catch
  site.
- **Backwards compatibility**: Exit code becomes *less* strict by default,
  which could mask genuinely-broken links for anyone relying on the aggregate.
  Mitigated by keeping both counts visible and offering `--strict-network`.

## Success Metrics

- With the network unavailable, `ll-check-links` exits 0 and reports all
  external links as unreachable rather than broken.
- A deliberately broken internal link still exits 1.
- `ll-doctor --full` passes on a machine with no network access.

## Scope Boundaries

**In scope**: failure classification, summary output, exit-code semantics,
optional retry/concurrency tuning.

**Out of scope**: fixing any link the checker finds genuinely broken; rewriting
the crawler; adding link checking to new file types.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | Orchestration layers and CLI surface |
| `.claude/CLAUDE.md` § Testing & CI Policy | Local gates are the only enforcement layer; no hosted CI |

## Context

Identified while verifying documentation after a CLI color-palette change. The
new `docs/development/CLI_COLOR_PALETTE.md` contains no links, yet
`ll-check-links` still reported 326 broken — all external timeouts — making it
impossible to use the command to confirm the doc was clean.

## Session Log
- `/ll:manage-issue` (improve) - 2026-07-27T05:27:15 - `408c91f3-d756-4de2-84b7-308806c714f6.jsonl`
- `/ll:ready-issue` - 2026-07-27T05:07:54 - `429a86aa-f713-4ede-b9b3-3906a2c7c3c2.jsonl`
- `/ll:confidence-check` - 2026-07-27T00:35:00 - `c21a4ad9-40fa-4eac-ac93-516f6a21f2df.jsonl`
- `/ll:refine-issue` - 2026-07-27T05:03:46 - `442a68cf-215e-4533-9698-0a63d93d25b2.jsonl`
- `/ll:confidence-check` - 2026-07-27T00:30:43 - `686c8dcb-74d5-48e6-9a23-028ec64a8dbf.jsonl`
- `/ll:wire-issue` - 2026-07-27T00:29:44 - `8c131682-ec68-43f5-84a8-24fcb0c8b6c0.jsonl`
- `/ll:refine-issue` - 2026-07-27T00:25:29 - `9ce371ff-4ca1-4ba2-ad6e-8b38c84db732.jsonl`
- `/ll:capture-issue` - 2026-07-27T00:08:18Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2c83098-37d1-4d7b-86d1-fbf55d285134.jsonl`

---

## Status

open
