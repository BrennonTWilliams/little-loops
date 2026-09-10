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

1. On a machine with ≤ 5 logical cores (or simulate: the clamp makes host CPU count observable), run `python -m pytest "scripts/tests/test_conftest_cap.py::TestXdistAutoNumWorkers::test_env_var_overrides_cpu_count"`.
2. Observe: `AssertionError: assert 2 == 3` — the hook returned `min(3, 4 - 2) == 2` from the real 4-core host.
3. On a 14-core host the same command passes (`min(3, 12) == 3`), hiding the defect locally.

## Root Cause

- **File**: `scripts/tests/test_conftest_cap.py`
- **Anchor**: `in TestXdistAutoNumWorkers.test_env_var_overrides_cpu_count()`
- **Cause**: The test is the only one in the class that does not patch `os.cpu_count`, so its assertion `== 3` is evaluated against the host's real core count through the clamp `max(1, min(int(env), cpus - 2))` in `conftest.pytest_xdist_auto_num_workers`. The clamp was added to the hook after this test was written; the test and two docstrings were never updated.

## Program Design

### Signatures

- `test_env_var_overrides_cpu_count(self, monkeypatch: pytest.MonkeyPatch) -> None` — unchanged signature; body gains `with patch("os.cpu_count", return_value=14)` and docstring corrected.
- `test_env_override_clamps_to_cpus_minus_two(self, monkeypatch: pytest.MonkeyPatch) -> None` — new; `monkeypatch.setenv("PYTEST_XDIST_AUTO_NUM_WORKERS", "99")`, `patch("os.cpu_count", return_value=4)`, assert `== 2`.

### Call Path

pytest runner -> `TestXdistAutoNumWorkers` -> `conftest.pytest_xdist_auto_num_workers` (module loaded via `importlib.util.spec_from_file_location`) -> `os.cpu_count` (patched) / `os.environ.get("PYTEST_XDIST_AUTO_NUM_WORKERS")`

## Impact

- **Priority**: P3 - Test-only defect; no product code affected, but it turns CI red on the 4-core self-hosted runner while passing locally on 14 cores, eroding trust in the gate.
- **Effort**: Small - Single test file: wrap one test in a `patch("os.cpu_count", ...)` context, correct two docstrings, add one clamp-pinning test.
- **Risk**: Low - Test-only change; the hook itself (`pytest_xdist_auto_num_workers`) is untouched.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-10 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-10T22:12:19 - `895d3ceb-7c4a-44b3-826e-65829f565276.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:18 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
