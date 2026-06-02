---
id: FEAT-1481
type: FEAT
priority: P4
status: done
captured_at: '2026-05-15T20:37:29Z'
completed_at: '2026-05-15T22:11:18Z'
discovered_date: 2026-05-15
discovered_by: capture-issue
depends_on: FEAT-1465
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-1481: Validate CodexRunner and Lift `_PROBE_ORDER` Gate

## Summary

`CodexRunner` is registered in `_HOST_RUNNER_REGISTRY` but commented out of `_PROBE_ORDER` (gated behind `LL_HOST_CLI=codex`). Once manually smoke-tested against a real `codex` binary, the gate should be lifted so Codex auto-detects when on PATH and `claude` is absent.

## Current Behavior

`CodexRunner` only activates via explicit `LL_HOST_CLI=codex`. Even if `codex` is installed and `claude` is not, `resolve_host()` will raise `HostNotConfigured` instead of picking up Codex automatically. The commented-out probe entry in `host_runner.py` reads:

```python
# ("codex", "codex"),  # FEAT-1465: gated behind LL_HOST_CLI until validated
```

## Expected Behavior

After validation:
1. `resolve_host()` auto-detects `codex` binary when on PATH and no override env var is set (probe order: `claude → codex → pi`).
2. `("codex", "codex")` is uncommented in `_PROBE_ORDER`.
3. `test_host_runner.py::test_detect_binary_probe_order` passes with codex in the sequence.

## Use Case

A developer on a Codex-only machine — `codex` is on PATH, `claude` is absent — invokes any `ll-` command without setting `LL_HOST_CLI`. After this change, `resolve_host()` auto-detects `codex` and the tool chain runs normally, with no env var configuration required.

## Acceptance Criteria

- [ ] `resolve_host(env={})` returns a `CodexRunner` instance when `codex` is on PATH and `claude` is absent (verified via `shutil.which` monkeypatching)
- [ ] `("codex", "codex")` is uncommented in `_PROBE_ORDER` in `host_runner.py`
- [ ] `test_codex_runner_gated_from_auto_probe` is deleted and replaced by `test_codex_runner_probed_when_on_path` which asserts the runner is `CodexRunner`
- [ ] `test_detect_binary_probe_order` passes without modification (its `seen[0] == "claude"` assertion is unaffected)
- [ ] All four docs updated: `HOST_COMPATIBILITY.md`, `API.md`, `TROUBLESHOOTING.md`, `ARCHITECTURE.md`

## Motivation

The gate was a deliberate safety measure in FEAT-1465 — "gated until validated in production usage." That validation is the remaining work. Without it, Codex-only environments require manual env var configuration that the probe order is designed to avoid.

## Proposed Solution

1. **Smoke test** — with `codex` installed, set `LL_HOST_CLI=codex` and run:
   ```bash
   python -m little_loops.cli.action capabilities
   ll-auto --dry-run   # or ll-sprint --dry-run on a real sprint
   ```
   Verify `build_streaming`, `build_blocking_json`, `build_version_check`, and `build_detached` produce working argv.
2. **Ungate** — uncomment `("codex", "codex")` in `_PROBE_ORDER` in `scripts/little_loops/host_runner.py`.
3. **Remove gating comment** — delete or update the inline comment on the probe entry.
4. **Verify test** — confirm `test_detect_binary_probe_order` in `scripts/tests/test_host_runner.py` passes with codex in the sequence (the test already uses `shutil.which` mocking, so no codex binary needed for CI).

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py` — uncomment `("codex", "codex")` in `_PROBE_ORDER` (~line 553)
- `scripts/tests/test_host_runner.py` — ensure `test_detect_binary_probe_order` covers the updated probe order

### Files to Reference (not modify)

- `thoughts/research/codex-headless-invocation.md` — flag translation research (FEAT-1465)
- `hooks/adapters/codex/README.md` — adapter smoke-test reference

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/__init__.py` — re-exports `HostInvocation`, `HostNotConfigured`, `HostRunner`, `CapabilityNotSupported` as public API; no code change needed, listed for blast-radius awareness [Agent 1]
- `scripts/little_loops/subprocess_utils.py` — calls `resolve_host()` in `run_claude_command()`; will automatically benefit from codex auto-detection; no code change needed [Agent 1]
- `scripts/little_loops/cli/action.py` — calls `resolve_host()` and `build_version_check()` in `cmd_capabilities()`; no code change needed [Agent 1]
- `scripts/little_loops/parallel/worker_pool.py` — calls `resolve_host().build_blocking_json()` in `_detect_worktree_model_via_api()`; no code change needed [Agent 1]
- `scripts/little_loops/fsm/handoff_handler.py` — calls `resolve_host().build_detached()` in `_spawn_continuation()`; no code change needed [Agent 1]
- `scripts/little_loops/fsm/evaluators.py` — calls `resolve_host().build_blocking_json()` for LLM-graded evaluation; no code change needed [Agent 1]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/HOST_COMPATIBILITY.md` — Section "Orchestration CLI": Codex column shows `gated[^orch]` for all tool rows (`ll-auto`, `ll-parallel`, `ll-action`, `ll-loop`, FSM evaluators); `[^orch]` footnote defines "gated"; prose line calls `CodexRunner` "gated behind `LL_HOST_CLI=codex` until validated". All become stale post-lift — update column cells to `✓` and remove/update `[^orch]` footnote. [Agent 2]
- `docs/reference/API.md` — Section `little_loops.host_runner`: (1) concrete runners table `CodexRunner` row shows status `✓ wired (gated)` and notes "Gated behind explicit `LL_HOST_CLI=codex`"; (2) `resolve_host` step 3 says `"claude → pi"` and explicitly states codex is omitted. Both need updating to reflect `claude → codex → pi` auto-detection. [Agent 2]
- `docs/development/TROUBLESHOOTING.md` — Section "HostNotConfigured": inline comment after `which codex` states `"# Codex (also requires LL_HOST_CLI=codex — gated)"`. After the change, `which codex` on PATH is sufficient; remove the gating comment. [Agent 2]
- `docs/ARCHITECTURE.md` — Section "Host Runner Layer": `CodexRunner` table row describes it as `"Stub for the codex CLI (FEAT-1465 tracks completion)"`. CodexRunner is not a stub and FEAT-1465 is now complete; update description. [Agent 2]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Precise test changes required (the issue's current description is inaccurate):**

- `scripts/tests/test_host_runner.py` — `TestCodexRunner.test_codex_runner_gated_from_auto_probe` (~line 178): currently asserts `"codex" not in probe_hosts`; this test **will fail** after uncommenting the probe entry and **must** be inverted or replaced before `pytest` passes.
- `scripts/tests/test_host_runner.py` — `TestResolveHost.test_detect_binary_probe_order` (~line 72): **no change needed** — its only assertion (`seen[0] == "claude"`) remains true after the uncomment.
- New test to add in `TestCodexRunner` — `test_codex_runner_probed_when_on_path` — modeled on `TestPiRunner.test_pirunner_probe_returns_stub_not_raise` (~line 357):

  ```python
  def test_codex_runner_probed_when_on_path(
      self, isolated_env: None, monkeypatch: pytest.MonkeyPatch
  ) -> None:
      monkeypatch.setattr(
          "little_loops.host_runner.shutil.which",
          lambda binary: "/usr/local/bin/codex" if binary == "codex" else None,
      )
      runner = resolve_host(env={})
      assert isinstance(runner, CodexRunner)
      invocation = runner.build_streaming(prompt="hi")
      assert invocation.binary == "codex"
  ```

**`_PROBE_ORDER` structure after uncomment** (from `host_runner.py` ~line 551):
```python
_PROBE_ORDER: list[tuple[str, str]] = [
    ("claude-code", "claude"),
    ("codex", "codex"),   # <-- uncomment this line; remove the FEAT-1465 comment
    ("pi", "pi"),
]
```

## Implementation Steps

1. Install `codex` binary locally (or use a CI environment that has it)
2. Run smoke tests with `LL_HOST_CLI=codex` as documented above
3. If all commands produce correct argv and no runtime errors, uncomment the probe entry
4. Run `python -m pytest scripts/tests/test_host_runner.py -v` to verify
5. Run `python -m mypy scripts/little_loops/host_runner.py` and `ruff check scripts/little_loops/host_runner.py`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 3.5 — Update test suite before running `pytest` (required between steps 3 and 4):**

Without this, step 4 will fail: `test_codex_runner_gated_from_auto_probe` explicitly asserts `"codex" not in probe_hosts`, which becomes false as soon as the probe entry is uncommented.

- In `scripts/tests/test_host_runner.py` `TestCodexRunner`: delete `test_codex_runner_gated_from_auto_probe` and replace with `test_codex_runner_probed_when_on_path` (see Integration Map for the exact code)
- `test_detect_binary_probe_order` in `TestResolveHost` does **not** need updating — its `seen[0] == "claude"` assertion is unaffected by adding codex to the probe list

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Remove stale block comment in `scripts/little_loops/host_runner.py` — the block comment at lines ~547–553 above `_PROBE_ORDER` that explains why the codex entry is commented out should be deleted or replaced with a brief note after the uncomment [Agent 2]
7. Update `docs/reference/HOST_COMPATIBILITY.md` — change Codex tool rows from `gated[^orch]` to `✓`; update or remove the `[^orch]` footnote defining "gated"; update prose description of `CodexRunner` [Agent 2]
8. Update `docs/reference/API.md` — in the `little_loops.host_runner` concrete runners table, update `CodexRunner` status and notes columns; update `resolve_host` step 3 probe order description from `claude → pi` to `claude → codex → pi` [Agent 2]
9. Update `docs/development/TROUBLESHOOTING.md` — remove `"# Codex (also requires LL_HOST_CLI=codex — gated)"` comment from the `which codex` block [Agent 2]
10. Update `docs/ARCHITECTURE.md` — update `CodexRunner` row description from "Stub for the codex CLI (FEAT-1465 tracks completion)" to reflect its production status [Agent 2]

## Impact

- **Scope**: Single-line code change after validation
- **Risk**: Low — CodexRunner is already fully implemented and tested; this only affects auto-detection fallback
- **Unblocks**: Codex-only environments that can't or don't want to set `LL_HOST_CLI`

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/host_runner.py` | `_PROBE_ORDER` and `CodexRunner` implementation |
| `thoughts/research/codex-headless-invocation.md` | Flag translation research from FEAT-1465 |
| `hooks/adapters/codex/README.md` | Codex adapter contract and smoke-test steps |

## Labels

host-runner, codex, validation

## Status

**Open** | Created: 2026-05-15 | Priority: P4

---

## Session Log
- `/ll:manage-issue` - 2026-05-15T22:11:18Z - `fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:ready-issue` - 2026-05-15T22:09:17 - `5c45a74f-bbc0-4345-9149-bcaccc39976d.jsonl`
- `/ll:confidence-check` - 2026-05-15T22:30:00Z - `9e951eea-b429-4afc-a87a-f9b0a4c74d8c.jsonl`
- `/ll:wire-issue` - 2026-05-15T22:05:07 - `5b456ff6-f764-4bf8-814b-d72f02697c46.jsonl`
- `/ll:refine-issue` - 2026-05-15T22:00:52 - `90114ade-06a1-4cda-9397-15a4b59c4a90.jsonl`
- `/ll:capture-issue` - 2026-05-15T20:37:29Z - `5ac48eaf-913e-40cd-8b15-98d99f2901cc.jsonl`
