---
id: ENH-2184
title: GeminiRunner stub in host_runner.py
type: enhancement
status: done
priority: P4
parent: EPIC-2178
depends_on: [FEAT-2179]
captured_at: "2026-06-15T00:00:00Z"
discovered_date: 2026-06-15
discovered_by: capture-issue
labels: [gemini, host-compat, host-runner]
---

# ENH-2184: GeminiRunner stub in host_runner.py

## Summary

Add a `GeminiRunner` class to `scripts/little_loops/host_runner.py` that raises
`HostNotConfigured` on all `build_*` calls. Wire it into `_HOST_RUNNER_REGISTRY`
and `_PROBE_ORDER` so `resolve_host()` can select Gemini when `LL_HOST_CLI=gemini`
or `gemini` is on PATH. Analogous to `PiRunner`.

This is the stub step. Full implementation lands in ENH-2185.

## Current Behavior

`resolve_host()` does not recognize `gemini` as a host. Setting `LL_HOST_CLI=gemini`
(or having `gemini` on PATH) raises an unknown-host error, because there is no
`GeminiRunner` in `_HOST_RUNNER_REGISTRY` or `_PROBE_ORDER`. `ll-doctor` does not
list `gemini` among recognized hosts.

## Expected Behavior

`resolve_host()` selects a `GeminiRunner` when `LL_HOST_CLI=gemini` or `gemini` is on
PATH. All `build_*` calls on the stub raise `HostNotConfigured` with a remediation
hint pointing to ENH-2185 / EPIC-2178 — analogous to `PiRunner` before Pi support was
complete. `ll-doctor` lists `gemini` as a recognized host with stub status.

## Use Case

A developer sets `LL_HOST_CLI=gemini`. Without this stub, `resolve_host()` raises
an unknown-host error. With the stub, the host resolves correctly and
`HostNotConfigured` is raised with a helpful remediation hint, analogous to Pi's
behavior before Pi support was complete.

## Implementation Steps

1. Add `GeminiRunner` class to `host_runner.py`:
   - Inherits `HostRunner` protocol
   - `binary = "gemini"`
   - All `build_streaming`, `build_blocking_json`, `build_detached`,
     `build_version_check` raise `HostNotConfigured("gemini", "ENH-2185")`
   - `probe()` → `shutil.which("gemini") is not None`
2. Add `("gemini", GeminiRunner)` to `_HOST_RUNNER_REGISTRY`.
3. Add `("gemini", "gemini")` to `_PROBE_ORDER` after Pi.
4. Add a Gemini case to `_remediation_hint()` pointing to EPIC-2178.
5. Add test coverage to `scripts/tests/test_host_runner.py`:
   - `test_gemini_runner_stub_raises_host_not_configured`
   - `test_resolve_host_selects_gemini_when_ll_host_cli_set`

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified recipe against `PiRunner`. The following supersedes the specific API details in steps 1–4 above, which predate this research:_

1. **`GeminiRunner` class** — copy `PiRunner` (lines 698–767) verbatim and substitute. Note these corrections to step 1:
   - Class attrs are `name = "gemini"` and `capabilities = HostCapabilities()`. There is **no `binary` class attribute** — `PiRunner` hardcodes `"pi"` inside `detect()` and `describe_capabilities()`; do the same with `"gemini"`.
   - The protocol method is **`detect()`** (returns `shutil.which("gemini") is not None`), **not** `probe()`.
   - Runners do **not** inherit `HostRunner` — it is a `@runtime_checkable` Protocol satisfied structurally (the test asserts `isinstance(GeminiRunner(), HostRunner)`).
   - `HostNotConfigured` (line 54) is a bare `RuntimeError` subclass with **no custom `__init__`** — it takes a **single message string**, not `HostNotConfigured("gemini", "ENH-2185")`. Use the `PiRunner` wording, e.g.:
     `raise HostNotConfigured("Gemini orchestration not yet wired — see ENH-2185 / EPIC-2178. Set LL_HOST_CLI=claude-code to use Claude Code instead.")`
   - Implement **`describe_capabilities()`** (omitted from step 1) — this is the method that makes `ll-doctor` report stub status. Return a `CapabilityReport(host="gemini", binary="gemini", version="", capabilities=[CapabilityEntry("host", "unsupported", "binary not configured (HostNotConfigured) — see ENH-2185 / EPIC-2178")])`.
   - Add `"GeminiRunner"` to `__all__` (lines 36–51).
2. Add `"gemini": GeminiRunner` to `_HOST_RUNNER_REGISTRY` (lines 773–778).
3. Add `("gemini", "gemini")` to `_PROBE_ORDER` (lines 782–786) after `("pi", "pi")`.
4. **Correction to step 4**: `_remediation_hint()` (lines 789–794) is a single static string, **not** a per-host case switch — there is no "Gemini case" to add. Add `gemini` to both inline host lists in that string: the `"(one of: claude-code, codex, opencode, pi)"` enumeration and the `"install a supported host CLI on PATH (claude, codex, or pi)"` clause.
5. Tests — see the Integration Map § Codebase Research Findings for the full mirror plan (`TestGeminiRunner` from `TestPiRunner`, the `TestDescribeCapabilities` entry, and the conformance `_HOST_BINARY` addition). Verify with `python -m pytest scripts/tests/test_host_runner.py -k gemini` and `python -m pytest scripts/tests/conformance/test_host_conformance.py -k gemini`.

## Acceptance Criteria

- `resolve_host()` returns a `GeminiRunner` when `LL_HOST_CLI=gemini`.
- All `build_*` calls on the stub raise `HostNotConfigured`.
- `ll-doctor` lists `gemini` as a recognized host with stub status.
- Tests pass: `python -m pytest scripts/tests/test_host_runner.py -k gemini`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — clarifies the `ll-doctor` criterion:_

- `ll-doctor` does not enumerate all hosts; it reports the **currently resolved** host. The operational meaning of "lists gemini with stub status": with `LL_HOST_CLI=gemini` (or `gemini` on PATH), `ll-doctor` resolves `GeminiRunner`, calls `describe_capabilities()`, prints the `host` capability as `✗ unsupported`, and **exits 1** (`doctor.py` returns 1 when any capability is `unsupported`). Confirm with `LL_HOST_CLI=gemini ll-doctor`. No code change in `doctor.py` is required — the `describe_capabilities()` stub drives this.

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py` — `GeminiRunner` class, registry, probe order, remediation hint
- `scripts/tests/test_host_runner.py` — stub coverage

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/host_runner.py` — five concrete touch points, all verified against `PiRunner` (lines 698–767):
  - `__all__` (lines 36–51) — add `"GeminiRunner"` (currently exports `ClaudeCodeRunner`, `CodexRunner`, `OpenCodeRunner`, `PiRunner`).
  - New `GeminiRunner` class — mirror `PiRunner` exactly.
  - `_HOST_RUNNER_REGISTRY` (lines 773–778, a `dict[str, type[HostRunner]]`) — add `"gemini": GeminiRunner`.
  - `_PROBE_ORDER` (lines 782–786, a `list[tuple[str, str]]`) — add `("gemini", "gemini")` after the `("pi", "pi")` entry.
  - `_remediation_hint()` (lines 789–794) — see correction note below; this is **not** a per-host case switch.
- `scripts/tests/test_host_runner.py` — add `GeminiRunner` to the `from little_loops.host_runner import (...)` block (lines 23–37); add a `TestGeminiRunner` class mirroring `TestPiRunner` (lines 607–663, 8 tests); add `test_gemini_runner_returns_capability_report` to `TestDescribeCapabilities` (mirrors `test_pi_runner_returns_capability_report`, lines 782–788). Reuse the existing `isolated_env` fixture and the `monkeypatch.setattr("little_loops.host_runner.shutil.which", ...)` probe pattern.
- `scripts/tests/conformance/test_host_conformance.py` — `_HOST_BINARY` dict (lines 52–57): add `"gemini": "gemini"`. The golden-path test (`test_golden_path_invocation`, line 67) is **already parametrized over `_HOST_RUNNER_REGISTRY.keys()`**, so adding gemini to the registry auto-generates conformance cases. Tests stay green without the `_HOST_BINARY` entry (the stub raises `HostNotConfigured` → `pytest.skip`), but adding it gives the accurate PATH-based skip reason and matches the established convention.

### Auto-Covered (no change needed)

- `scripts/little_loops/cli/doctor.py` — `ll-doctor` does **not** enumerate hosts. `main_doctor()` calls `resolve_host()` for the *currently active* host, then renders `runner.describe_capabilities()`. Stub status surfaces automatically once `GeminiRunner.describe_capabilities()` returns a `CapabilityEntry("host", "unsupported", ...)`. See the Acceptance Criteria clarification.

## Research Notes

From FEAT-2179 findings:
- Binary: `gemini` (npm `@google/gemini-cli`), v0.46.0
- `probe()`: `shutil.which("gemini")`
- `build_version_check`: `gemini --version`

Pattern: follow `PiRunner` in `host_runner.py` — it's the simplest existing stub.

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified `PiRunner` stub conventions (`host_runner.py`):_

- `OpenCodeRunner` (lines 626–695) is the other stub but is **registered-only** — deliberately absent from `_PROBE_ORDER` (its `test_opencode_runner_gated_from_auto_probe` asserts this). Gemini follows the **`PiRunner` model** (present in both registry and probe order), per this issue's spec — so `gemini` on PATH auto-resolves to the stub.
- `HostRunner` protocol surface (line 152, `@runtime_checkable`): `name: str`, `detect()`, `build_streaming`, `build_blocking_json`, `build_version_check`, `build_detached`, `describe_capabilities` — all `build_*` params are keyword-only. The stub implements all six; `capabilities = HostCapabilities()` defaults every flag to `False`.
- `resolve_host()` (lines 797–841): `LL_HOST_CLI=gemini` today hits the unknown-host branch (line 829) and raises `HostNotConfigured` because `"gemini"` is not in `_HOST_RUNNER_REGISTRY`. After this stub, that branch resolves `GeminiRunner()`; the first `build_*` call is what raises.

## Scope Boundaries

In scope: the `GeminiRunner` stub class, `_HOST_RUNNER_REGISTRY` / `_PROBE_ORDER`
wiring, the `_remediation_hint()` case, and stub test coverage. Out of scope: the
real `build_*` implementations and any actual Gemini CLI invocation — those land in
ENH-2185.

## Impact

- **Priority**: P4 - Additive stub gated behind opt-in `LL_HOST_CLI=gemini`; enables ENH-2185 but unblocks no current user workflow.
- **Effort**: XS (< 1 hour)
- **Risk**: Very low — additive only, no existing behavior changes
- **Breaking Change**: No

---

## Verification Notes

2026-06-18 (UNSTARTED): `GeminiRunner` class does not exist in `host_runner.py`. Not in `_HOST_RUNNER_REGISTRY` or `_PROBE_ORDER`. FEAT-2179 is complete — `thoughts/research/gemini-cli-surface.md` confirms binary is `gemini`, version check is `gemini --version`, probe is `shutil.which("gemini")`. All research inputs for the stub are available.

2026-07-03 (DONE): Implemented together with ENH-2185 in one pass — `GeminiRunner`
landed **fully wired** (all four `build_*` methods functional) rather than as a
`HostNotConfigured` stub, since the flag-translation table from FEAT-2179 was
already verified. Registered in `_HOST_RUNNER_REGISTRY`, added `("gemini",
"gemini")` to `_PROBE_ORDER` after `("pi", "pi")`, added `gemini` to both host
lists in `_remediation_hint()`, exported via `__all__`. `describe_capabilities()`
reports full streaming/permission_skip and unsupported agent_select/
tool_allowlist/json_schema, so `ll-doctor` renders an accurate report.
Tests: `TestGeminiRunner` (17 tests) + `TestDescribeCapabilities` entry in
`scripts/tests/test_host_runner.py`; conformance `_HOST_BINARY` entry added.

**Done** | Created: 2026-06-15 | Completed: 2026-07-03 | Priority: P4


## Session Log
- `/ll:refine-issue` - 2026-06-26T23:08:57 - `abd8a5ef-13d7-492f-b92f-c138327f6bce.jsonl`
- `/ll:format-issue` - 2026-06-26T23:01:31 - `64adeb74-858e-4aba-8e05-0d67aa559f7c.jsonl`
