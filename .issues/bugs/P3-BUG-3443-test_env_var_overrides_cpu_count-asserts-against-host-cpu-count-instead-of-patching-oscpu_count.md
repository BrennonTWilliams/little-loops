---
id: BUG-3443
type: BUG
title: test_env_var_overrides_cpu_count asserts against host CPU count instead of
  patching os.cpu_count
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
parent: EPIC-3436
learning_tests_required:
- pytest-xdist
- pytest
confidence_score: 95
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3443: test_env_var_overrides_cpu_count asserts against host CPU count instead of patching os.cpu_count

## Summary

conftest.pytest_xdist_auto_num_workers clamps the PYTEST_XDIST_AUTO_NUM_WORKERS override to cpus-2, but test_env_var_overrides_cpu_count (test_conftest_cap.py ~50) is the only sibling that does not patch os.cpu_count, so it passes on 14 cores and fails 2==3 on the 4-core runner. Patch os.cpu_count like the siblings, correct the two stale docstrings describing pre-clamp behaviour, and add a case pinning the clamp itself (env=99, cpus=4 -> 2) (A2).

## Current Behavior

`TestXdistAutoNumWorkers.test_env_var_overrides_cpu_count` (scripts/tests/test_conftest_cap.py) sets `PYTEST_XDIST_AUTO_NUM_WORKERS=3` and asserts the hook returns 3 — without patching `os.cpu_count`, unlike every sibling in the class. Since `pytest_xdist_auto_num_workers` clamps the override to `max(1, min(int(env), cpus - 2))`, the result depends on the host core count: on the 14-core dev machine `min(3, 12) == 3` passes; on the 4-core CI runner `min(3, 2) == 2` fails with `assert 2 == 3`. Two docstrings in the file (the class docstring's "env var wins, parsed as int" bullet and this test's "returns N verbatim") still describe the pre-clamp behavior, and no test pins the clamp itself.

## Expected Behavior

- `test_env_var_overrides_cpu_count` patches `os.cpu_count` (e.g. `return_value=14`) like its siblings, so `env=3, cpus=14 -> 3` holds on any host.
- Both stale docstrings describe the clamped contract (override honored but bounded by `cpus - 2`).
- A new test pins the clamp: `env=99, cpus=4 -> 2`.
- The file passes on hosts of any core count, including the 4-core CI runner.

## Steps to Reproduce

1. On a machine with fewer than 5 logical cores (or simulate: the clamp makes host CPU count observable), run `python -m pytest "scripts/tests/test_conftest_cap.py::TestXdistAutoNumWorkers::test_env_var_overrides_cpu_count"`.
2. Observe: `AssertionError: assert 2 == 3` — the hook returned `min(3, 4 - 2) == 2` from the real 4-core host.
3. On a 14-core host the same command passes (`min(3, 12) == 3`), hiding the defect locally.

## Root Cause

- **File**: `scripts/tests/test_conftest_cap.py`
- **Anchor**: `in TestXdistAutoNumWorkers.test_env_var_overrides_cpu_count()`
- **Cause**: The test is the only one in the class that does not patch `os.cpu_count`, so its assertion `== 3` is evaluated against the host's real core count through the clamp `max(1, min(int(env), cpus - 2))` in `conftest.pytest_xdist_auto_num_workers`. The clamp was added to the hook after this test was written; the test and two docstrings were never updated.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- Confirmed: the hook reads `cpus = os.cpu_count() or 4` at `scripts/tests/conftest.py:63` and clamps at :71 (`return max(1, min(int(env), cpus - 2))`); the test at `scripts/tests/test_conftest_cap.py:47-50` calls the hook with env=3 and no cpu_count patch, so on hosts with fewer than 5 logical cores the clamp yields fewer than 3 (exactly 2 on a 4-core host) and `assert 2 == 3` fails
- The five siblings (`test_conftest_cap.py:52-81`) all wrap the assertion in `with patch("os.cpu_count", return_value=N)`; the unpatched test predates the clamp introduced under BUG-2788

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- Files to Modify: `scripts/tests/test_conftest_cap.py` — the only file this fix touches (test body at :47-50, two stale docstrings at :42 and :48, one new sibling test joining `TestXdistAutoNumWorkers` :37-81)
- Untouched dependency — the hook under test: `pytest_xdist_auto_num_workers` (`scripts/tests/conftest.py:51-78`; `cpus = os.cpu_count() or 4` :63, env read :64, clamp `return max(1, min(int(env), cpus - 2))` :71, no-env fallback `return max(2, cpus // 2)` :78)
- Loader shim: the test file loads the hook as an independent module via `importlib.util.spec_from_file_location("conftest_under_test", _CONFTEST_PATH)` (`test_conftest_cap.py:30-34`); the double-load is documented by a comment at `scripts/tests/conftest.py:278`
- Importers of the test file: none — pytest collection is its only entry point (repo-wide grep found no CI config, docs, or other test importing `test_conftest_cap`)
- Production writer of the env var (context, not modified): `verify_epic_branch_before_merge` setdefaults `PYTEST_XDIST_AUTO_NUM_WORKERS` to `str(max(2, (os.cpu_count() or 4) // 4))` for child verify-gate runs (`scripts/little_loops/worktree_utils.py:738`); that computed value has no test coverage
- Tests: the five siblings at `test_conftest_cap.py:52-81` already pin cpu_count; no shared env/cpu fixture exists in `scripts/tests/helpers.py` or `scripts/tests/conftest.py` to reuse — the new test needs no new machinery
- Configuration: `scripts/pyproject.toml:245-251` (addopts comment) documents the cap and the override; `.github/workflows/ci.yml` never sets `PYTEST_XDIST_AUTO_NUM_WORKERS` (repo-wide `.github/` grep: no hits), so the failure surfaces on any runner with fewer than 5 logical cores
- Documentation: `docs/development/TROUBLESHOOTING.md:849` already describes the knob as clamped to `cpus-2` — post-clamp text, no update needed
- Prior art: the clamp was introduced by BUG-2788 (`max(1, min(N, cpus-2))`); the test file was created under BUG-2501
- Conventions in force: cpu_count patching uses ONLY the string-target `unittest.mock.patch` context manager — `with patch("os.cpu_count", return_value=N)` (`test_conftest_cap.py:55,61,67,73,79`); `monkeypatch.setattr(os, "cpu_count", ...)` and decorator-form `@patch("os.cpu_count")` have zero occurrences tree-wide
- Conventions in force: env vars go through the `monkeypatch` fixture while OS functions go through `patch` context managers (suite-wide: 263 `monkeypatch.setenv` uses across 49 files vs 5 `patch.dict(os.environ)` in 2)
- Conventions in force: tests that ignore the env var still scrub it defensively via `monkeypatch.delenv("PYTEST_XDIST_AUTO_NUM_WORKERS", raising=False)` (`test_conftest_cap.py:60,66,72,78`), and every test in the class passes `MagicMock()` as the hook's config arg
- Conventions in force: clamp tests name `<input>_<verb>_<expected>` using verbs floors/yields/clamps/caps (`test_conftest_cap.py:58,64,70,76`; `test_git_lock.py:228`; `test_loop_suggester.py:190,200`), with boundary values injected as explicit inputs rather than ambient (`test_git_lock.py:230-235`); single-value clamp tests assert bare `==` with no message
- Conventions in force: every test method in `TestXdistAutoNumWorkers` carries a single-sentence RST docstring with double-backtick literals stating input → contract (`test_conftest_cap.py:48,53,59,65,71,77`)
- Scope boundary (research note, not a directive): the module docstring at `test_conftest_cap.py:6` and the hook comment at `scripts/tests/conftest.py:60-61` also predate the clamp; this issue's named scope covers only :42 and :48 — extending it is the implementer's call, not required

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue` — 2026-09-10:_

- None missed — confirmed by 3-agent trace: no file imports `test_conftest_cap` (sole non-prose mention is the double-load comment at `scripts/tests/conftest.py:278`), the hook's only in-repo invocation is this test file, and tree-wide greps for `PYTEST_XDIST_AUTO_NUM_WORKERS` / `pytest_xdist_auto_num_workers` / `test_conftest_cap` return zero hits across `plugin.json`, `hooks/` (incl. adapters), `commands/`, `skills/`, `agents/`, `.github/` [Agent 1 finding]
- Gate consumer (context, no edit): `.github/workflows/ci.yml` unit-tests job never sets the env var, so the 4-core self-hosted runner is where `assert 2 == 3` surfaces — this fix flips that job red→green with no exit-code or artifact-format change [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue` — 2026-09-10:_

- `scripts/tests/test_conftest_cap.py:40` — in-file gap: the class docstring's line-range ref `see ``scripts/tests/conftest.py:30-53``` points at the pre-cap range; the hook lives at `conftest.py:51-78`. Sits in the same docstring block as the `:42` bullet already in scope [Agent 2 finding]
- No external docs need updating — verified: `docs/development/TROUBLESHOOTING.md:849` already reads "(clamped to ``cpus-2``)"; `docs/reference/API.md:13129` documents the untouched writer in `worktree_utils.py`; `scripts/pyproject.toml:245-252` addopts comment stays accurate post-fix [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue` — 2026-09-10:_

- Nothing breaks: no test or doc asserts on the docstring strings at `:42`/`:48` being rewritten (repo-wide grep hits only the file itself, this issue, and unrelated same-phrase docstrings in `test_sync.py:110` / `test_host_runner.py:512`); no meta-test enumerates the file's test names, so a seventh method breaks nothing; `test_env_override_clamps_to_cpus_minus_two` collides with no existing name repo-wide [Agent 2/3 findings]
- Implementation note: the fixed `test_env_var_overrides_cpu_count` needs no defensive `monkeypatch.delenv` — it sets the env var itself, matching `test_invalid_env_var_falls_back_to_cpu_half` (`:52-56`), the only sibling combining `setenv` + cpu_count patch [Agent 3 finding]

## Program Design

### Signatures

- `test_env_var_overrides_cpu_count(self, monkeypatch: pytest.MonkeyPatch) -> None` — unchanged signature; body gains `with patch("os.cpu_count", return_value=14)` and docstring corrected.
- `test_env_override_clamps_to_cpus_minus_two(self, monkeypatch: pytest.MonkeyPatch) -> None` — new; `monkeypatch.setenv("PYTEST_XDIST_AUTO_NUM_WORKERS", "99")`, `patch("os.cpu_count", return_value=4)`, assert `== 2`.

### Call Path

pytest runner -> `TestXdistAutoNumWorkers` -> `conftest.pytest_xdist_auto_num_workers` (module loaded via `importlib.util.spec_from_file_location`) -> `os.cpu_count` (patched) / `os.environ.get("PYTEST_XDIST_AUTO_NUM_WORKERS")`

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

1. `TestXdistAutoNumWorkers.test_env_var_overrides_cpu_count` (`scripts/tests/test_conftest_cap.py:47-50`) passes on hosts of any core count — its hook assertion is made host-independent the same way the five siblings are, and its docstring (`:48`) states the clamped contract rather than "returns N verbatim"
2. The class docstring bullet at `test_conftest_cap.py:42` states that the override is honored but bounded by `cpus - 2`
3. A clamp-pinning test exists in the class asserting `env=99, cpus=4 -> 2`, with both operands injected explicitly and naming from the floors/yields/clamps family already in the file
4. `python -m pytest scripts/tests/test_conftest_cap.py -v` passes, and the full gate `python -m pytest scripts/tests/` exits 0

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Correct the stale line-range ref at `test_conftest_cap.py:40` (`conftest.py:30-53` → `conftest.py:51-78`) while editing the adjacent `:42` class-docstring bullet

## Impact

- **Priority**: P3 - Test-only defect; no product code affected, but it turns CI red on the 4-core self-hosted runner while passing locally on 14 cores, eroding trust in the gate.
- **Effort**: Small - Single test file: wrap one test in a `patch("os.cpu_count", ...)` context, correct two docstrings, add one clamp-pinning test.
- **Risk**: Low - Test-only change; the hook itself (`pytest_xdist_auto_num_workers`) is untouched.
- **Breaking Change**: No

## Verification Notes

`/ll:verify-issues --auto` — 2026-09-11: Verdict at time of check: **NEEDS_UPDATE** (corrections
below applied in the same pass, so the issue as it now reads is up to date — this section is a
record of what was wrong and fixed, not an outstanding action item).

- **Off-by-one failure threshold, corrected in this pass**: the issue claimed the test fails on
  hosts with "≤ 5 logical cores" (Steps to Reproduce, Codebase Research Findings, Integration Map).
  The clamp `max(1, min(int(env), cpus - 2))` with env=3 yields 3 on a 5-core host
  (`min(3, 5-2) == 3` passes); failure requires `cpus < 5` (yields 2 on 4 cores, 1 at ≤ 2 cores).
  All three occurrences now read "fewer than 5 logical cores".
- **Every other claim verified against HEAD**: all cited line numbers hold
  (`test_conftest_cap.py:30-34,37-81,40,42,47-50,48,52-81` with patches at :55,61,67,73,79 and
  delenv at :60,66,72,78; `conftest.py:51-78` hook with `cpus` read at :63, env read at :64, clamp
  at :71, fallback at :78; `worktree_utils.py:738` setdefault; `pyproject.toml:245-251` addopts
  comment; `TROUBLESHOOTING.md:849` clamp text; `API.md:13129` writer doc; double-load comment at
  `conftest.py:278`). `test_env_var_overrides_cpu_count` run directly: **passes on this 14-core
  host** (1 passed), matching the predicted host-dependence. Causal claims corroborated by direct
  git probe: test file born 2026-07-06 (949ef80aa, BUG-2501), clamp introduced 2026-07-24
  (920aade3f, the BUG-2788 four-phase landing) — after the test, as claimed.
- **Evidence check (`ll-verify-evidence`) — 2 detector findings, both false positives on manual
  trace**: (1) `AssertionError: assert 2 == 3` at :37 is a *predicted* failure output in Steps to
  Reproduce, never claimed as a quote from the named artifact; (2) the clamp span
  `max(1, min(int(env), cpus - 2))` at :44 exists **verbatim at `scripts/tests/conftest.py:71`** —
  the issue's own prose attributes it to `pytest_xdist_auto_num_workers` in conftest.py, which is
  correct; the detector's artifact inference (test_conftest_cap.py) was wrong. No fabricated
  evidence found; EVIDENCE_UNVERIFIED not assigned (documented detector precision on this
  paraphrase class: ~0.13–0.20, below the 0.30 bar — see BUG-3282 fallback F3).
- **Graph-assisted checks**: provider=`codegraph`, freshness=`fresh` — `references
  test_conftest_cap` returned empty; grep corroborated (sole mention is the double-load comment at
  `scripts/tests/conftest.py:278`), matching the issue's "no importers" claim.
- **Decisions gate**: ran clean — zero active required rules, nothing to violate.
- **Dependencies**: parent EPIC-3436 exists (open); referenced issues BUG-2788 and BUG-2501 exist
  (BUG-2788 is done). No `## Blocked By` section, so no backlink/cycle checks apply.

## Status

**Open** | Created: 2026-09-10 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-11T04:06:10 - `82aa9c16-7356-4996-ae53-14603c2e9a9b.jsonl`
- `/ll:verify-issues` - 2026-09-11T04:03:47 - `e932b503-6715-465c-b1b0-8faaee5f9773.jsonl`
- `/ll:wire-issue` - 2026-09-11T03:54:33 - `3c54b1f6-0a02-45d5-aeb1-ed084c2c42f8.jsonl`
- `/ll:refine-issue` - 2026-09-10T23:51:06 - `4d1eb983-c328-4793-b35a-8ba87f2992d7.jsonl`
- `/ll:format-issue` - 2026-09-10T22:12:19 - `895d3ceb-7c4a-44b3-826e-65829f565276.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:18 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
