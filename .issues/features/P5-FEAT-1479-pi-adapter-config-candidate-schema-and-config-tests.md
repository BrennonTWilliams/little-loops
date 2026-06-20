---
id: FEAT-1479
title: Pi Adapter — Config Candidate, Schema, and Config Tests
type: FEAT
priority: P5
status: open
parent: EPIC-1622
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
relates_to: FEAT-1476
milestone: refined-ready
---

# FEAT-1479: Pi Adapter — Config Candidate, Schema, and Config Tests

## Summary

Add `PI_CONFIG_DIR` constant and `_config_candidates()` branch in `config/core.py`, add `"pi"` to `config-schema.json`'s `hooks.properties.host.enum`, and write the associated config and session-start tests.

## Current Behavior

`_config_candidates()` in `config/core.py` has no `pi` branch, so `LL_HOOK_HOST=pi` falls through to the default probe order (`.ll/ll-config.json`, then root-level). `hooks.properties.host.enum` in `config-schema.json` does not include `"pi"`, and the `OrchestrationConfig` docstring still annotates `"pi"` as `(reserved for FEAT-992)`.

## Expected Behavior

Setting `LL_HOOK_HOST=pi` (or `LL_STATE_DIR=.pi`) causes `.pi/ll-config.json` to be probed first, mirroring the existing Codex branch. `hooks.properties.host.enum` includes `"pi"` alongside the other hosts. The stale `"pi" (reserved for FEAT-992)` annotation is removed from the `OrchestrationConfig` docstring and from `_config_candidates()`'s "Future hosts" note.

## Use Case

A developer using the Pi host adapter stores their `ll-config.json` in `.pi/` and has it auto-loaded via the session-start hook when `LL_HOOK_HOST=pi`, without any manual path configuration.

## Parent Issue

Decomposed from FEAT-1477: Pi Adapter — Python Backend: Config, Host Runner, Schema, and Tests

## Acceptance Criteria

- `scripts/little_loops/config/core.py` has `PI_CONFIG_DIR = ".pi"` constant (after `CODEX_CONFIG_DIR`) and an `elif host == "pi" or state_dir == PI_CONFIG_DIR:` branch in `_config_candidates()`
- `OrchestrationConfig` docstring no longer references `"pi" (reserved for FEAT-992)` annotation
- `config-schema.json` includes `"pi"` in `hooks.properties.host.enum` (resolves inconsistency with `orchestration.host_cli`)
- Config probe-order tests pass: `python -m pytest scripts/tests/test_config.py -k pi`
- Schema assertion passes: `python -m pytest scripts/tests/test_config_schema.py -k hooks`
- Session-start config load test passes: `python -m pytest scripts/tests/test_hook_session_start.py -k pi`
- No regressions in existing config or schema tests

## Proposed Solution

### Step 1: Confirm Codex Template

Verify `_config_candidates()` in `config/core.py` has the `codex` branch — use as template for the Pi branch.

### Step 2: Add Pi Config Candidate

In `scripts/little_loops/config/core.py` (~line 36), add after `CODEX_CONFIG_DIR = ".codex"`:
```python
PI_CONFIG_DIR = ".pi"
```

In `_config_candidates()` (~lines 84-88), add branch mirroring the codex branch:
```python
elif host == "pi" or state_dir == PI_CONFIG_DIR:
    candidates.append(project_root / PI_CONFIG_DIR / CONFIG_FILENAME)
```

Also update `OrchestrationConfig` docstring: remove `"pi" (reserved for FEAT-992)` annotation.

### ~~Step 3: Update Config Schema~~ **already done**

`"pi"` is already present in `hooks.properties.host.enum` in `config-schema.json` (confirmed at line 1356 as of 2026-06-17). Skip this step.

### Step 4: Write Config and Session-Start Tests

- `scripts/tests/test_config.py:TestResolveConfigPath` — add Pi probe-order tests after `test_codex_path_takes_precedence_when_host_codex` (~line 1040), mirroring the codex variant with `LL_HOOK_HOST=pi` and `.pi/ll-config.json`
- `scripts/tests/test_config_schema.py:test_hooks_in_schema` (~line 155) — update exact-equality assertion to include `"pi"` in `hooks.host.enum`: `["claude-code", "opencode", "codex", "pi"]`
- `scripts/tests/test_hook_session_start.py` (~line 64) — add Pi parallel of `test_falls_back_to_codex_dir_config`: set `LL_HOOK_HOST=pi`, create `.pi/ll-config.json`, assert it is loaded through the session-start handler

### Step 5: Update Companion Docstrings (Wiring Phase added by `/ll:wire-issue`)

_These in-file touchpoints were identified by wiring analysis and must be included in the implementation:_

5. In `scripts/little_loops/config/core.py` — update `_config_candidates()` docstring: remove the forward-reference `"Future hosts (e.g. FEAT-992 Pi) add a new branch here"` and replace with `"Hosts with a dedicated state dir (codex, pi) probe their dir first; all others use the default order"` (or equivalent accurate prose) [Agent 2]
6. In `scripts/tests/test_config.py:1087` — update `test_opencode_host_uses_default_order` docstring from `"only \`\`codex\`\` does (FEAT-957)"` to `"only \`\`codex\`\` and \`\`pi\`\` do"` — stale comment after Pi branch lands [Agent 3]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Verified line numbers** (exact):
- `CODEX_CONFIG_DIR = ".codex"` → `core.py:36`
- `_config_candidates()` codex branch → `core.py:85-86`; uses bare `if`, so Pi branch chains as `elif`
- `OrchestrationConfig` docstring → `core.py:124-127`; line 126 contains the annotation to remove: `plus "auto" (the sentinel for env/probe resolution) and "pi" (reserved for FEAT-992).`
- `hooks.properties.host.enum` → `config-schema.json:1103`; current value: `["claude-code", "opencode", "codex"]`
- `test_hooks_in_schema` exact assertion → `test_config_schema.py:155`
- `test_falls_back_to_codex_dir_config` → `test_hook_session_start.py:64-81`; uses `in_tmp` fixture (chdir into `tmp_path`) not `tmp_path` directly

**Concrete test code for `test_config.py`** (3 functions, add after line 1085 inside `TestResolveConfigPath`):
```python
def test_pi_path_takes_precedence_when_host_pi(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``LL_HOOK_HOST=pi`` puts ``.pi/ll-config.json`` ahead of ``.ll/`` and root-level (FEAT-1479)."""
    from little_loops.config.core import resolve_config_path

    monkeypatch.setenv("LL_HOOK_HOST", "pi")
    monkeypatch.delenv("LL_STATE_DIR", raising=False)
    (tmp_path / ".pi").mkdir()
    pi_cfg = tmp_path / ".pi" / "ll-config.json"
    pi_cfg.write_text('{"pi": true}')
    (tmp_path / ".ll").mkdir()
    (tmp_path / ".ll" / "ll-config.json").write_text('{"ll": true}')
    (tmp_path / "ll-config.json").write_text('{"root": true}')

    assert resolve_config_path(tmp_path) == pi_cfg

def test_pi_path_takes_precedence_when_state_dir_pi(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``LL_STATE_DIR=.pi`` is an alternate trigger for the pi probe order (FEAT-1479)."""
    from little_loops.config.core import resolve_config_path

    monkeypatch.delenv("LL_HOOK_HOST", raising=False)
    monkeypatch.setenv("LL_STATE_DIR", ".pi")
    (tmp_path / ".pi").mkdir()
    pi_cfg = tmp_path / ".pi" / "ll-config.json"
    pi_cfg.write_text('{"pi": true}')
    (tmp_path / ".ll").mkdir()
    (tmp_path / ".ll" / "ll-config.json").write_text('{"ll": true}')

    assert resolve_config_path(tmp_path) == pi_cfg

def test_pi_host_falls_through_to_ll_dir_when_pi_absent(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pi host with no ``.pi/ll-config.json`` falls back to ``.ll/`` then root-level."""
    from little_loops.config.core import resolve_config_path

    monkeypatch.setenv("LL_HOOK_HOST", "pi")
    (tmp_path / ".ll").mkdir()
    ll_cfg = tmp_path / ".ll" / "ll-config.json"
    ll_cfg.write_text('{"ll": true}')

    assert resolve_config_path(tmp_path) == ll_cfg
```

**Concrete test code for `test_hook_session_start.py`** (add after `test_falls_back_to_codex_dir_config` at line 81):
```python
def test_falls_back_to_pi_dir_config(
    self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When LL_HOOK_HOST=pi, ``.pi/ll-config.json`` is probed first (FEAT-1479)."""
    monkeypatch.setenv("LL_HOOK_HOST", "pi")
    (in_tmp / ".pi").mkdir()
    (in_tmp / ".pi" / "ll-config.json").write_text(json.dumps({"pi": True}))
    (in_tmp / ".ll").mkdir()
    (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({"ll": True}))

    result = handle(
        LLHookEvent(host="pi", intent="session_start", payload={})
    )

    assert result.exit_code == 0
    assert result.stdout is not None
    assert json.loads(result.stdout) == {"pi": True}
```

**Side note**: `test_opencode_host_uses_default_order` (line 1087) has docstring "only ``codex`` does" — consider updating to "only ``codex`` and ``pi`` do" for accuracy after this lands.

## Integration Map

### Files to Modify
- `scripts/little_loops/config/core.py` — `CODEX_CONFIG_DIR = ".codex"` at line 36; `_config_candidates()` codex branch at lines 85–86; `OrchestrationConfig` docstring (~line 118)
- `config-schema.json` — `hooks.properties.host.enum` (currently `["claude-code", "opencode", "codex"]`; add `"pi"`)

### Test Files
- `scripts/tests/test_config.py:1040` — `TestResolveConfigPath`; codex probe-order tests at lines 1040–1085 are the template
- `scripts/tests/test_config_schema.py:136` — `test_hooks_in_schema`; exact assertion at line 155: `assert host["enum"] == ["claude-code", "opencode", "codex"]`
- `scripts/tests/test_hook_session_start.py:64` — `TestSessionStartConfigLoad`; `test_falls_back_to_codex_dir_config` is the template

### Dependent Files (Transparent Beneficiaries)
- `scripts/little_loops/hooks/session_start.py` — calls `resolve_config_path()` which internally calls `_config_candidates()`; will automatically probe `.pi/ll-config.json` once the branch is added — no code change needed

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/HOST_COMPATIBILITY.md` — "Config probe path" and "State directory" tables enumerate hosts; Pi row absent; add `.pi/ll-config.json` probe-order entry (full doc update tracked in FEAT-1476) [Agent 2]
- `docs/reference/CONFIGURATION.md` — no `hooks.host` enum section exists; Pi probe-order prose absent; add documentation for `hooks.host` (tracked in FEAT-1476) [Agent 2]
- `docs/reference/EVENT-SCHEMA.md` — `LLHookEvent` host field example list is `"claude-code", "opencode", "codex"` — missing `"pi"` (tracked in FEAT-1476) [Agent 2]
- `docs/development/TESTING.md` — `run_hook_intent` fixture docstring host example list missing `"pi"` (minor; tracked in FEAT-1476) [Agent 2]
- `docs/reference/API.md` — `LLHookEvent` host field table row example list missing `"pi"` (tracked in FEAT-1476) [Agent 2]

## Labels

`pi-adapter`, `config`, `schema`, `tests`

## Impact

- **Priority**: P5
- **Effort**: Small
- **Risk**: Low — purely additive; no changes to existing host logic

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-18): This issue modifies `config-schema.json` (adds `"pi"` to `hooks.properties.host.enum`). Two other open issues touch the same file: BUG-1461 (removes or implements `continuation.auto_detect_on_session_start`) and FEAT-948 (adds a top-level `decisions` object schema). All three edits are to different keys and are additive, but concurrent PRs on the same JSON file risk merge conflicts. Resolve BUG-1461 first (FEAT-948 already notes this); sequence FEAT-1479 after BUG-1461 resolves so `config-schema.json` is stable before the Pi enum addition.

## Status

**Open** | Created: 2026-05-15 | Priority: P5

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-03_

**Verdict: NEEDS_UPDATE** — Stale line numbers: CODEX_CONFIG_DIR is at config/core.py:41 (not 36); codex branch is at lines 92-93 (not 85-86). The future `PI_CONFIG_DIR` constant and `host=='pi'` branch are still absent from core.py. config-schema.json hooks.host.enum at line 1173 is still `["claude-code","opencode","codex"]` — no 'pi' entry yet.

- `/ll:verify-issues` - 2026-06-05 - Partial progress: `config-schema.json` already has `"pi"` in the host enum (Step 1 of config candidate done). Remaining work: `config/core.py` needs `PI_CONFIG_DIR` constant, `elif host == "pi"` branch in `_config_candidates()`, and updated docstring. No tests written. Stale line numbers in body: CODEX_CONFIG_DIR is at line 40 (not 36). Update line references before starting.
- `/ll:verify-issues` - 2026-06-13 - `"pi"` confirmed in `config-schema.json:1335` (schema step done). `config/core.py` still has no `PI_CONFIG_DIR` constant (CODEX_CONFIG_DIR is now at line 41). Test targeting schema enum assertion would pass immediately — scope down to config/core.py work only.
- 2026-06-13: Schema enum step (adding 'pi' to hooks.host.enum in config-schema.json) is already done — step 1 is complete. Remaining work: add PI_CONFIG_DIR branch to scripts/little_loops/config/core.py. Stale line numbers: CODEX_CONFIG_DIR is now at :41 (issue may say :36), codex branch at :92-93. Tests not yet written.
- 2026-06-17: Step 1 (config-schema.json enum) confirmed done — `"pi"` at `hooks.host.enum` (line 1356). Remaining: `PI_CONFIG_DIR` constant and `elif host == "pi"` branch still absent from `config/core.py` (CODEX_CONFIG_DIR is at line 41, codex branch at lines 92-93). Tests not written.

2026-06-19 (NEEDS_UPDATE): Step 1 (config-schema.json enum) confirmed done — `"pi"` at `hooks.host.enum` line 1368. Remaining: `PI_CONFIG_DIR` constant and `elif host == "pi"` branch absent from `config/core.py`. Stale OrchestrationConfig docstring reference no longer in `core.py` (moved); implementation target is now solely `config/core.py._config_candidates()`. Tests not written.

## Session Log
- `/ll:verify-issues` - 2026-06-20T00:34:46 - `fe5ace5b-6f94-43ca-9f1d-09a0705f08c4.jsonl`
- `/ll:verify-issues` - 2026-06-17T00:00:00 - `7473c42a-1313-4587-925f-e177ac5fcc85.jsonl`
- `/ll:verify-issues` - 2026-06-14T00:14:07 - `7db6ce0f-4d7c-486d-927d-6804d39ee7b7.jsonl`
- `/ll:verify-issues` - 2026-06-13T21:13:58 - `cfa3cf65-c671-4bf6-a513-92cc448d76e6.jsonl`
- `/ll:verify-issues` - 2026-06-09T09:21:00 - `e40557ae-4da3-4ea7-b023-bf5e57e8b61a.jsonl`
- `/ll:verify-issues` - 2026-06-05T22:34:32 - `1a4d9590-60c8-47b0-9997-b0f543664183.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`
- `/ll:verify-issues` - 2026-06-04T04:22:06 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-03T21:54:23 - `882d6aa0-cbf0-47c3-9d9c-32d8d6c6ef92.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:54 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-06-01T03:08:52 - `ed2ec455-964e-4a94-92a4-e94218c08ad6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:58 - `5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T21:48:17 - `6805d559-982e-47e7-9513-9c8b17a1c054.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:15 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-24T06:05:45 - `8cdfeedd-6a9f-4683-a41d-9ff3860ac7e0.jsonl`
- `/ll:verify-issues` - 2026-05-23T00:35:43 - `2955f8fa-d24c-40f9-9d2d-3d46811662f9.jsonl`
- `/ll:verify-issues` - 2026-05-22T16:11:43 - `d87b546d-fad7-425c-a8f4-8246f0ea8de8.jsonl`
- `/ll:verify-issues` - 2026-05-22T11:10:00 - `d87b546d-fad7-425c-a8f4-8246f0ea8de8.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-18T05:05:17 - `16717e5e-bfe4-4e7f-8d36-177b4b791f2d.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-17T18:46:35 - `ebf7abce-1ef1-46c8-8cbc-56d9f857d730.jsonl`
- `/ll:manage-issue` - 2026-05-15T20:23:44 - `6a222200-0970-406f-ab67-4aaf8d296ca4.jsonl`
- `/ll:ready-issue` - 2026-05-15T20:19:22 - `3f9a440f-13e7-4f06-9cb4-450f590e4bfe.jsonl`
- `/ll:wire-issue` - 2026-05-15T20:14:54 - `283ba605-37bc-48cb-a598-ae75817694a9.jsonl`
- `/ll:refine-issue` - 2026-05-15T20:08:45 - `bf5992b2-5c8e-47de-b8e1-f647db5de5b1.jsonl`
- `/ll:issue-size-review` - 2026-05-15T20:30:00 - `3e9b11ad-de12-4f82-9761-25c38e59c783.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): All documentation file edits for the Pi adapter (HOST_COMPATIBILITY.md, ARCHITECTURE.md, TROUBLESHOOTING.md, API.md, CONFIGURATION.md) are exclusively owned by FEAT-1476. Do NOT include doc-file edits in this issue's PR. The `depends_on: [FEAT-1476]` frontmatter encodes this handoff as a formal dependency.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The `depends_on: [FEAT-1476]` entry in this issue's frontmatter reflects an incorrect ordering — this issue's code changes (`config/core.py`, `config-schema.json`, tests) can be delivered independently and do not require FEAT-1476's documentation to land first. The dependency arrow should flow FEAT-1476 → FEAT-1479 (docs wait for code, not the reverse). Remove `depends_on: [FEAT-1476]` from the frontmatter when implementing; the doc delegations in the Integration Map section (wiring pass) already correctly point to FEAT-1476 and no frontmatter dependency is needed to enforce that split.
