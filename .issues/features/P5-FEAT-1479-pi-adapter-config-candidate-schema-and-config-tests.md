---
id: FEAT-1479
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
depends_on: [FEAT-1476]
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

### Step 3: Update Config Schema

In `config-schema.json`, add `"pi"` to `hooks.properties.host.enum` (around line 1102–1104). The `orchestration.host_cli` already includes `"pi"` — no change needed there.

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

**Verdict**: VALID — Verified 2026-05-22 (re-verified, prior note was incorrect)

- `config-schema.json:1103` `hooks.properties.host.enum` is still `["claude-code", "opencode", "codex"]` — `"pi"` is NOT present. The earlier 2026-05-22 note claiming partial schema landing was wrong (likely confused `hooks.host.enum` with `orchestration.host_cli`, which does include `"pi"` and is a different enum).
- `scripts/little_loops/config/core.py` missing `PI_CONFIG_DIR` constant and `host == "pi"` branch — not implemented.
- Nothing from this issue has actually landed yet; full scope remains outstanding.
- Parent `FEAT-1477` is now `status: done` — re-parenting this child to a new Pi-adapter umbrella epic.

**Verdict**: NEEDS_UPDATE — Verified 2026-05-22 (superseded — claim about schema was inaccurate)

- ~~`config-schema.json` already has `"pi"` in `hooks.properties.host.enum` (`["claude-code", "codex", "opencode", "pi"]`) ✓~~ INCORRECT — see entry above.
- `scripts/little_loops/config/core.py` missing `PI_CONFIG_DIR` constant and `host == "pi"` branch — not yet implemented
- Partial implementation: schema change landed, code changes (core.py + tests) remain outstanding

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-24T06:05:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8cdfeedd-6a9f-4683-a41d-9ff3860ac7e0.jsonl`
- `/ll:verify-issues` - 2026-05-23T00:35:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2955f8fa-d24c-40f9-9d2d-3d46811662f9.jsonl`
- `/ll:verify-issues` - 2026-05-22T16:11:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d87b546d-fad7-425c-a8f4-8246f0ea8de8.jsonl`
- `/ll:verify-issues` - 2026-05-22T11:10:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d87b546d-fad7-425c-a8f4-8246f0ea8de8.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-18T05:05:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/16717e5e-bfe4-4e7f-8d36-177b4b791f2d.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-17T18:46:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ebf7abce-1ef1-46c8-8cbc-56d9f857d730.jsonl`
- `/ll:manage-issue` - 2026-05-15T20:23:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a222200-0970-406f-ab67-4aaf8d296ca4.jsonl`
- `/ll:ready-issue` - 2026-05-15T20:19:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3f9a440f-13e7-4f06-9cb4-450f590e4bfe.jsonl`
- `/ll:wire-issue` - 2026-05-15T20:14:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/283ba605-37bc-48cb-a598-ae75817694a9.jsonl`
- `/ll:refine-issue` - 2026-05-15T20:08:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bf5992b2-5c8e-47de-b8e1-f647db5de5b1.jsonl`
- `/ll:issue-size-review` - 2026-05-15T20:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e9b11ad-de12-4f82-9761-25c38e59c783.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): All documentation file edits for the Pi adapter (HOST_COMPATIBILITY.md, ARCHITECTURE.md, TROUBLESHOOTING.md, API.md, CONFIGURATION.md) are exclusively owned by FEAT-1476. Do NOT include doc-file edits in this issue's PR. The `depends_on: [FEAT-1476]` frontmatter encodes this handoff as a formal dependency.
