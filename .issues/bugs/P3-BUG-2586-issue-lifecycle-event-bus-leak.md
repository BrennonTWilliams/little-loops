---
id: BUG-2586
title: Global event-bus leak in test_complete_issue_lifecycle_emits_event flakes under
  specific xdist shardings
type: BUG
priority: P3
status: cancelled
captured_at: '2026-07-07T00:00:00Z'
discovered_date: 2026-07-07
discovered_by: audit
size: Very Large
labels:
- tests
- flaky
- event-bus
- duplicate
- re-investigate
decision_needed: false
confidence_score: 80
outcome_confidence: 94
score_complexity: 23
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 24
cancelled_at: '2026-07-07T23:10:00Z'
cancelled_reason: duplicate-of-BUG-2489
relates_to:
- BUG-2489
---

# BUG-2586: Global event-bus leak in test_complete_issue_lifecycle_emits_event flakes under specific xdist shardings

## Summary

`scripts/tests/test_issue_lifecycle.py:1361::test_complete_issue_lifecycle_emits_event`
passes in isolation (0.13s) and under `-n 4` with one node (0.97s), but
historically flakes under specific full-suite shardings — a test-isolation
bug from global event-bus state leaking between tests.

Source: audit run `.loops/runs/general-task-20260707T133447/audit-report.md`
(C7 / Finding #4 / R4; isolation evidence in that run's
`evidence/eventbus-shard.txt`). Explicitly NOT a cause of the test-suite
beachball — independent test-quality issue.

## Current Behavior

Flakes only under specific shardings of the full 14,183-item suite; cannot
be reproduced with isolated or small `-n 4` runs.

## Expected Behavior

Test passes deterministically regardless of sharding/ordering.

## Proposed Solution

Investigate `LLTestBus.global_subscribers` cleanup between tests — likely a
missing teardown/reset fixture, or another test registering global
subscribers that persist into this test's assertions. May require
`pytest -p no:randomly`-style bisection or `--dist loadgroup` experiments to
find the interfering test.

## Acceptance Criteria

- Root cause identified with the specific leaking subscriber/test named.
- Test passes across repeated full-suite `-n auto` runs.
- Cleanup enforced structurally (autouse fixture or bus reset), not by
  reordering tests.

### Codebase Research Findings — Disposition Note

_Added by `/ll:refine-issue` — the existing acceptance criteria above were written
from the audit's hypothesis and presume an event-bus subscriber leak that the
codebase does not actually exhibit. Reframed acceptance criteria based on what
research found:_

1. **Confirm the duplicate-of-BUG-2489 hypothesis** — verify `_isolate_session_log_dir`
   is still present at `scripts/tests/conftest.py:612-638` (or its post-ENH-2529
   counterpart after the recent `tmp_path` consolidation) and that the test
   passes deterministically under repeated full-suite `-n auto` runs.
2. **If the fixture is still in place and the flake does not reproduce** — close
   this issue as a duplicate of BUG-2489 with a cross-link, no code change.
3. **If the fixture is missing or the flake still reproduces** — escalate by
   re-opening BUG-2489 (not by writing a third fix here), since the verified
   root cause already lives there.

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on direct code inspection (verified):
the premise of this issue is factually incorrect._

**The `LLTestBus.global_subscribers` attribute does not exist anywhere in the
codebase.** A direct grep of `scripts/` returns zero hits except inside this
issue's own body. `LLTestBus` (`scripts/little_loops/testing.py:30-104`) stores
only per-instance `_events: list[LLEvent]` (L43), `_extensions: list[LLExtension]`
(L44), and `delivered_events: list[LLEvent]` (L45) — no module-level singleton,
no `global_subscribers` attribute, no shared registry.

`EventBus` is also purely per-instance — `scripts/little_loops/events.py:77-79`
allocates fresh `_observers` and `_transports` lists in `__init__`; `register()`
(L81-96) only mutates `self._observers`. The test in question
(`test_issue_lifecycle.py:1361-1393`) constructs its **own local `EventBus()`**
at L1372 and registers a single anonymous lambda — no other test has a
reference to that bus, so no subscriber leak is possible through it.

The flake described here is a re-discovery of **BUG-2489** (status: `done`,
completed 2026-07-06), whose verified root cause is a TOCTOU race at
`scripts/little_loops/session_log.py:79-83` — `get_current_session_jsonl()`
performs an unguarded `glob()`-then-`.stat()` against the **live host's**
`~/.claude/projects/...` session-log directory, and the Claude Code host
process can rotate/delete a `.jsonl` file between those two calls. That race
is *external* to the test (not a sibling-test pollution), which is exactly why
changing shard layouts — not test ordering — modulates its frequency.

The structural fix is already in place: the `_isolate_session_log_dir` autouse
fixture at `scripts/tests/conftest.py:612-638` (added during BUG-2489's
resolution) monkeypatches `pathlib.Path.home` to a per-test `tmp_path/fake_home`
so `get_project_folder` resolves to an empty dir and returns `None` instead of
racing the host. Per `_isolate_session_log_dir`'s doc string (conftest.py:617),
it explicitly cites `complete_issue_lifecycle → append_session_log_entry` as the
chain it protects.

**There is no production code to write.** If `_isolate_session_log_dir` is
still in place after ENH-2529's `tmp_path` consolidation and the flake does
not reproduce, this issue is a duplicate of BUG-2489 and should be closed with
a cross-link — not fixed twice.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — verification only; no edits expected if the
BUG-2489 fix still covers this flake:_

### Files (verification of the BUG-2489 hypothesis)

- `scripts/little_loops/testing.py:30-104` — `LLTestBus`; **verify no
  `global_subscribers` attribute** anywhere (it should not exist; the bug
  premise assumes a real one).
- `scripts/little_loops/events.py:70-159` — `EventBus`; per-instance observer
  state, no module-level subscribers. Confirmed via direct read of
  `__init__` (L77-79), `register()` (L81-96), `unregister()` (L98-103),
  `emit()` (L117-138).
- `scripts/tests/test_issue_lifecycle.py:1361-1393` —
  `test_complete_issue_lifecycle_emits_event`; uses a fresh local `EventBus()`
  at L1372, not `LLTestBus`.
- `scripts/tests/conftest.py:612-638` — `_isolate_session_log_dir` autouse
  fixture (the BUG-2489 structural fix that should already cover this flake).

### Dependent / Related Code (Callers — for cross-referencing)

- `scripts/little_loops/issue_lifecycle.py:734` — the single
  `append_session_log_entry(...)` call inside `complete_issue_lifecycle()`
  that triggers the TOCTOU race (BUG-2489's verified culprit).
- `scripts/little_loops/session_log.py:79-83` — `get_current_session_jsonl()`
  glob-then-stat — verified BUG-2489 root cause; hardened at L88-96 with an
  `except OSError: continue` guard during BUG-2489's resolution.
- `scripts/little_loops/user_messages.py:356-398` — `get_project_folder` /
  `_get_claude_project_folder` (the resolved `~/.claude/projects/...` dir).

### Similar Patterns

- `scripts/little_loops/fsm/executor.py:1407` — second unguarded caller of
  `get_current_session_jsonl()`; benefits for free from BUG-2489's
  `session_log.py:79` hardening.
- `scripts/little_loops/cli/ctx_stats.py:195-199` — `max(jsonl_files,
  key=lambda f: f.stat().st_mtime)` byte-for-byte duplicate of the unguarded
  idiom; BUG-2489 wiring flagged it but its fix is *not* auto-covered by
  the `session_log.py:79` guard since it inlines the logic instead of
  calling the helper.

### Tests

- `scripts/tests/test_session_log.py:58` — `test_skips_file_that_vanishes_before_stat`
  (BUG-2489 regression for the `session_log.py:79` guard).
- `scripts/tests/test_session_log.py:82` — `test_returns_none_when_all_files_vanish`
  (BUG-2489 regression).
- `scripts/tests/test_session_log.py:269-328` — `TestSessionLogHostAware`;
  exercises real `Path.home` resolution; correctly composes with
  `_isolate_session_log_dir` because the latter is function-scoped and the
  per-test `monkeypatch.setattr(Path, "home", ...)` overrides win.

### Documentation

- `docs/reference/API.md` — `get_current_session_jsonl` already documents
  the "Returns `None` if not found" contract; no change needed.

## Proposed Solution

Investigate `LLTestBus.global_subscribers` cleanup between tests — likely a
missing teardown/reset fixture, or another test registering global
subscribers that persist into this test's assertions. May require
`pytest -p no:randomly`-style bisection or `--dist loadgroup` experiments to
find the interfering test.

### Codebase Research Findings — Reframed solution

_Added by `/ll:refine-issue` — the original narrative above assumes a
state-attribute leak that the codebase does not exhibit. The actual root
cause is documented in BUG-2489; two viable paths:_

**Option A — Mark as duplicate of BUG-2489** (recommended).

> **Selected:** Option A — Mark as duplicate of BUG-2489 — verified the BUG-2489 structural fix at `scripts/tests/conftest.py:612-638` (`_isolate_session_log_dir`) and `scripts/little_loops/session_log.py:88-93` (TOCTOU guard) are intact post-ENH-2529; the hypothesised `LLTestBus.global_subscribers` symbol has zero hits in `scripts/`; BUG-2489 regressions at `test_session_log.py:58,82` still pass per ENH-2529 AC1 (`14173 passed, 35 skipped, exit 0`). Closing as duplicate requires zero new code.

The flake and its verified root cause are documented at
`P2-BUG-2489-event-bus-lifecycle-test-xdist-sharding-isolation-leak.md`
(status: `done`, completed 2026-07-06). Verify the BUG-2489 structural fix
(`_isolate_session_log_dir` at `scripts/tests/conftest.py:612-638`) is still
in place after ENH-2529's `tmp_path` consolidation and the regression tests
at `scripts/tests/test_session_log.py:58,82` still pass; if both hold, update
this issue's status to `cancelled` with a `related:` cross-link to BUG-2489
and link BUG-2586 from BUG-2489's `related:` back. No code change.

**Option B — Re-open BUG-2489 if the flake still reproduces.** If the
audit's full-suite reproduction (`pytest -n 7` or `-n auto`) still surfaces
this test as flaky *after* confirming `_isolate_session_log_dir` is present
and intact, the issue is a regression of BUG-2489 — escalate by re-opening
BUG-2489 (do not implement a third tracking fix here), since the verified
root cause (TOCTOU in `session_log.py:79-83`) and the prior-approved remedy
(Option C: harden + suite-wide isolation fixture) already exist.

**Decision factors**:
- If `_isolate_session_log_dir` exists at
  `scripts/tests/conftest.py:612-638` AND
  `pytest -n 7 scripts/tests/test_issue_lifecycle.py` passes ≥ 50/50 →
  Option A (close as duplicate).
- If the fixture is missing or the flake still reproduces →
  Option B (escalate BUG-2489 rather than fixing twice).

**Why this is a disposition decision, not an implementation task**:
there is no production code to write — the fix either already exists
(BUG-2489) or never did. The right action is closure with cross-link, not
a new code change.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete steps for each disposition option:_

**For Option A (close as duplicate — recommended):**
1. `grep -n "_isolate_session_log_dir" scripts/tests/conftest.py` — confirm
   the fixture is still at conftest.py:612-638 (or its post-ENH-2529 line).
2. Run `python -m pytest scripts/tests/test_session_log.py -v` to confirm
   the BUG-2489 regression tests
   (`test_skips_file_that_vanishes_before_stat`, `test_returns_none_when_all_files_vanish`)
   still pass.
3. Run `python -m pytest scripts/tests/test_issue_lifecycle.py::TestEventBusEmission
   -n 7 --count=10` (or just repeat `-n auto` 10 times) to confirm the flake
   does not reproduce after the BUG-2489 fix.
4. If steps 1-3 all pass, set `status: cancelled` in this issue's frontmatter
   and add `related: [BUG-2489]` to both files; link from BUG-2489 back.

**For Option B (re-open BUG-2489):**
1. Capture the failing run output and the test-file co-location observed.
2. Add a comment to BUG-2489 indicating the regression observed on
   `discovered_date: 2026-07-07` (today).
3. Re-open BUG-2489 via `ll-issues set-status ...`; close BUG-2586 with
   `related: [BUG-2489]`.

**Verification (both options):**
- `python -m pytest scripts/tests/test_issue_lifecycle.py -v` —
  deterministic pass.
- `python -m pytest scripts/tests/test_session_log.py::TestGetCurrentSessionJsonl
  -v` — BUG-2489 regression tests still pass.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-07.

**Selected**: Option A — Mark as duplicate of BUG-2489

**Reasoning**: Direct codebase verification by parallel agents confirmed all of Option A's preconditions hold: `_isolate_session_log_dir` autouse fixture is present verbatim at `scripts/tests/conftest.py:612-638` (function-scoped, monkeypatches `Path.home` to a per-test `tmp_path/fake_home`); the TOCTOU hardening at `scripts/little_loops/session_log.py:88-93` (the `try/except OSError: continue` guard added by BUG-2489 Option C) is intact; BUG-2489 regression tests at `scripts/tests/test_session_log.py:58,82` both comment-attribute BUG-2489 and pass per ENH-2529 AC1 (`14173 passed, 35 skipped in 56.34s, exit 0`); the hypothesised `LLTestBus.global_subscribers` symbol has zero hits across `scripts/`. The audit itself (`general-task-20260707T133447/audit-report.md` C7 / Finding #4 / R4) explicitly states it could not reproduce the flake and labelled the `global_subscribers` hypothesis as "requires investigation" — meaning the original capture narrative was a hypothesis from project memory, not a verified finding. There is no production code to write; the fix either already exists (BUG-2489) or never did. The correct disposition is closure with a cross-link, not a third tracking fix.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Close as duplicate of BUG-2489 | 3/3 | 3/3 | 3/3 | 3/3 | **12/12** |
| Option B — Re-open BUG-2489 as regression | 1/3 | 2/3 | 1/3 | 0/3 | **4/12** |

**Key evidence**:
- **Option A**: Agent confirmed (1) `_isolate_session_log_dir` at `scripts/tests/conftest.py:612-638` is unchanged post-ENH-2529, (2) BUG-2489 regressions at `test_session_log.py:58,82` pass, (3) `LLTestBus` has only `_events`/`_extensions`/`delivered_events` (no `global_subscribers`), (4) `EventBus` is per-instance (`__init__` allocates fresh `_observers`/`_transports`), (5) audit itself could not reproduce. Reuse score 3/3 — reuses existing fix directly, zero new code.
- **Option B**: Zero evidence of regression found. Commits ENH-2529 (`0bf6c899`, `132ae5d7`), ENH-2531 (`a3443be3`), ENH-2532 (`cdb10952`) since BUG-2489 closure on 2026-07-06 do not touch `conftest.py`, `session_log.py`, or `events.py`. No new bypass paths added; `cli/ctx_stats.py:255-263` already carries its own TOCTOU guard from BUG-2489. Re-use would still be 3/3 — but triggering the path is unjustified.

## Related

_Added by `/ll:refine-issue` — cross-references to the verified prior work:_

- **BUG-2489** (status: `done`, completed 2026-07-06) — exact same flake;
  verified root cause is the TOCTOU race in `session_log.py:79-83`, fixed
  with Option C (harden `session_log.py:79` + suite-wide
  `_isolate_session_log_dir` fixture). This issue is **a probable
  duplicate** of BUG-2489.
- **BUG-1995** — established the `_isolate_*` + `_guard_*` conftest-fixture
  convention that BUG-2489 reused and the present fix mirrors.
- **ENH-2529** — `tmp_path` consolidation; verify the
  `_isolate_session_log_dir` fixture still hooks correctly post-changes.
- **BUG-2523**, **BUG-2524** — sibling xdist-sharding flakes; both fixed
  via the `no_parallel` marker / `--dist` controls, unrelated to this
  event-bus hypothesis.


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-07_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 94/100 → HIGH CONFIDENCE

### Concerns
- **Underlying fix already implemented in BUG-2489** — `_isolate_session_log_dir` autouse fixture at `scripts/tests/conftest.py:612-638` and the `except OSError: continue` TOCTOU guard at `scripts/little_loops/session_log.py:88-93` are verified intact (direct grep confirmed both line numbers). BUG-2489 is `done` (completed 2026-07-06). The hypothesised `LLTestBus.global_subscribers` symbol has zero hits across `scripts/`, and `LLTestBus` itself stores only per-instance `_events`/`_extensions`/`delivered_events` (`testing.py:42-45`); `EventBus` is per-instance (`events.py:77-79`). The right action is closure via `ll-issues set-status BUG-2586 cancelled` + `related: [BUG-2489]` cross-link (and a reciprocal `related: [BUG-2586]` on BUG-2489) per `/ll:decide-issue` Option A (2026-07-07T22:47:06). No production code to write.

## Session Log
- `/ll:issue-size-review` - 2026-07-07T23:05:00 - `b44c47a7-0f37-498a-b65f-f7df4910edc2.jsonl`
- `/ll:confidence-check` - 2026-07-07T22:55:00 - `confidence-check-bug-2530.jsonl`
- `/ll:decide-issue` - 2026-07-07T22:47:06 - `1cbabf31-3614-4278-94f8-5398c99b0946.jsonl`
- `/ll:refine-issue` - 2026-07-07T22:42:25 - `21ba9863-d024-485c-8f55-04182d12ea1a.jsonl`
