---
id: FEAT-1482
type: FEAT
priority: P5
status: done
captured_at: '2026-05-15T20:37:29Z'
completed_at: '2026-05-15T22:43:21Z'
discovered_date: 2026-05-15
discovered_by: capture-issue
parent: FEAT-957
decision_needed: false
confidence_score: 95
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1482: Wire `UserPromptSubmit` Hook Intent for Codex Adapter

## Summary

The Codex hook adapter (`hooks/adapters/codex/`) implements `SessionStart` and `PreCompact` but leaves `UserPromptSubmit` deferred. Claude Code uses this intent for the auto-prompt-optimizer hook. This issue tracks wiring it for Codex so Codex users can benefit from the same auto-prompt optimization.

## Current Behavior

`hooks/adapters/codex/README.md` event mapping table shows:

| Codex event | ll intent | Status |
|---|---|---|
| `UserPromptSubmit` | — | Deferred — Claude Code uses this for auto-prompt-optimizer; track separately |

No `UserPromptSubmit` entry exists in `hooks/adapters/codex/hooks.json`. Codex users cannot trigger the `user_prompt_submit` intent (and by extension, the auto-prompt-optimizer) via hooks.

## Expected Behavior

- `hooks/adapters/codex/hooks.json` includes a `UserPromptSubmit` handler wired to the Python dispatcher (`python -m little_loops.hooks user_prompt_submit`)
- `hooks/adapters/codex/prompt-submit.sh` (or equivalent) adapter script sets `LL_HOOK_HOST=codex` and forwards the event payload to the dispatcher
- The `user_prompt_submit` intent fires for Codex users when a prompt is submitted
- Behavior matches the Claude Code adapter's `UserPromptSubmit` handling

## Use Case

A Codex CLI user who has installed little-loops types a new prompt. With this feature, the `UserPromptSubmit` hook fires and the auto-prompt-optimizer processes their prompt before execution — the same experience Claude Code users get today. Without it, Codex users see only `SessionStart` and `PreCompact` hooks, missing the most user-visible session-time feature.

## Acceptance Criteria

- [ ] `hooks/adapters/codex/hooks.json` includes a `UserPromptSubmit` entry pointing to `prompt-submit.sh` with `timeout: 5` and `statusMessage: "Checking prompt..."`
- [ ] `hooks/adapters/codex/prompt-submit.sh` exists, is executable, sets `LL_HOOK_HOST=codex`, and invokes `python -m little_loops.hooks user_prompt_submit`
- [ ] `scripts/little_loops/hooks/user_prompt_submit.py` created and registered as `"user_prompt_submit"` in `_dispatch_table()` in `scripts/little_loops/hooks/__init__.py`
- [ ] Python handler reads `prompt_optimization.*` config via `resolve_config_path()` (host-aware; probes `.codex/ll-config.json` when `LL_HOOK_HOST=codex`)
- [ ] `scripts/tests/test_codex_adapter.py`: `test_adapter_files_exist`, `test_adapter_scripts_are_executable`, `test_prompt_submit_sets_ll_hook_host_codex`, and `test_hooks_json_has_user_prompt_submit` all pass
- [ ] `scripts/tests/test_hook_intents.py`: `test_dispatch_user_prompt_submit_happy_path` passes
- [ ] `hooks/adapters/codex/README.md` event table updated: `UserPromptSubmit` row changed from "Deferred" to "Implemented"
- [ ] `docs/reference/HOST_COMPATIBILITY.md` `user_prompt_submit` Codex CLI cell updated from `(deferred)` to `✓`

## Motivation

The auto-prompt-optimizer is one of ll's most visible session-time features. Codex CLI users who install little-loops get `SessionStart` and `PreCompact` but miss prompt optimization — a visible parity gap. Wiring this closes the most user-facing hook gap for Codex.

## Proposed Solution

1. **Research Codex `UserPromptSubmit` payload** — confirm the event's stdin JSON shape (fields: `hook_event_name`, `session_id`, `prompt`, `cwd`, `model`). Verify against Codex CLI docs or `codex exec --help`.
2. **Add adapter script** — create `hooks/adapters/codex/prompt-submit.sh` mirroring `hooks/adapters/codex/session-start.sh`: set `LL_HOOK_HOST=codex`, pipe stdin to `python -m little_loops.hooks user_prompt_submit`, propagate exit code.
3. **Register in hooks.json** — add a `UserPromptSubmit` entry to `hooks/adapters/codex/hooks.json` pointing to `prompt-submit.sh`.
4. **Verify Python dispatcher** — confirm `little_loops/hooks/__init__.py` handles the `user_prompt_submit` intent (it should already, since Claude Code uses it; verify the handler doesn't assume Claude Code–specific payload fields).
5. **Test** — add a test case to `scripts/tests/test_codex_adapter.py` for the new script, mirroring the `test_adapter_sets_ll_hook_host_codex` pattern.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**CRITICAL CORRECTION**: Step 4 above is incorrect. Claude Code's `UserPromptSubmit` handler is **not** in the Python dispatcher. It is implemented entirely in Bash at `hooks/scripts/user-prompt-check.sh`. The Python dispatcher at `scripts/little_loops/hooks/__init__.py` registers only `pre_compact` and `session_start` in `_dispatch_table()`. There is no `user_prompt_submit` Python module or registered intent.

This creates a two-option decision for how to wire Codex `UserPromptSubmit`:

**Option A: Bash Delegation (low effort, config-resolution limitation)**

- `hooks/adapters/codex/prompt-submit.sh` sets `LL_HOOK_HOST=codex` then delegates stdin directly to `hooks/scripts/user-prompt-check.sh`
- No Python changes required
- **Limitation**: `user-prompt-check.sh` calls `ll_resolve_config` from `hooks/scripts/lib/common.sh`, which only probes `.ll/ll-config.json` and root `ll-config.json`. It has no awareness of `.codex/ll-config.json`. Codex users who store config at `.codex/ll-config.json` (the Codex-idiomatic path) will fail the config check and get the "run /ll:init" reminder every prompt.
- The payload field consumed is `.prompt` (via `jq -r '.prompt // ""'`); Codex `UserPromptSubmit` field name must still be verified.

**Option B: Python Handler (higher effort, full Codex integration)**

> **Selected:** Option B: Python Handler — all existing adapters call Python; `resolve_config_path()` already handles `.codex/` config correctly; test infrastructure is directly reusable; Option A introduces a structurally novel (and untestable) Bash-delegation pattern with no codebase precedent.

- Create `scripts/little_loops/hooks/user_prompt_submit.py` that ports the logic from `user-prompt-check.sh`
- Register `"user_prompt_submit": user_prompt_submit.handle` in `_dispatch_table()` at `scripts/little_loops/hooks/__init__.py:_dispatch_table()` (line ~60)
- `hooks/adapters/codex/prompt-submit.sh` follows the same `export LL_HOOK_HOST=codex` → `python -m little_loops.hooks user_prompt_submit` pattern as `session-start.sh`
- Python config resolution (`scripts/little_loops/config/core.py:resolve_config_path()`) correctly probes `.codex/ll-config.json` first when `LL_HOOK_HOST=codex`, solving the config-path limitation of Option A
- More work, but the correct path if Codex users store config at `.codex/ll-config.json`

**Payload field note**: `user-prompt-check.sh` reads `.prompt` from the host's JSON payload. Whether Codex's `UserPromptSubmit` event delivers the prompt text at `.prompt` is undocumented in the codebase (the Codex README's subprocess contract only documents `SessionStart` and `PreCompact` payloads). Must verify before implementing either option.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-15.

**Selected**: Option B: Python Handler

**Reasoning**: Every existing Codex adapter script (`session-start.sh`, `pre-compact.sh`) follows the `export LL_HOOK_HOST=codex` → `python -m little_loops.hooks <intent>` pattern — Option A would be the only adapter in the codebase to delegate to another Bash script, breaking both the structural convention and the sentinel-file test pattern (which requires a Python subprocess to intercept). Option B is further validated by `resolve_config_path()` already probing `.codex/ll-config.json` when `LL_HOOK_HOST=codex` (tested in `test_falls_back_to_codex_dir_config`), meaning the Codex config-path limitation of Option A is solved at zero additional cost in the Python path. The single new infrastructure gap — resolving `hooks/prompts/optimize-prompt-hook.md` from within the Python module — is a one-time convention, and both `_dispatch_table()` registration and the adapter script are copy-paste extensions of existing patterns.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A: Bash Delegation | 0/3 | 2/3 | 1/3 | 1/3 | 4/12 |
| Option B: Python Handler | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:
- Option A: `hooks/scripts/lib/common.sh:ll_resolve_config` has zero `.codex/` awareness (`host` env var ignored); no existing adapter delegates to Bash; sentinel-file test pattern requires a Python subprocess and cannot test an Option A script.
- Option B: `_dispatch_table()` has 2 prior examples (`pre_compact`, `session_start`); `resolve_config_path()` already probes `.codex/ll-config.json` when `LL_HOOK_HOST=codex`; reuse score 3/3 from pattern-finder agent.

## Integration Map

### Files to Modify

- `hooks/adapters/codex/hooks.json` — add `UserPromptSubmit` handler entry
- `hooks/adapters/codex/README.md` — update event mapping table: change `UserPromptSubmit` status from "Deferred" to "Implemented"

### Files to Create

- `hooks/adapters/codex/prompt-submit.sh` — new adapter script

### Files to Reference (not modify)

- `hooks/adapters/codex/session-start.sh` — canonical template for new adapter script
- `hooks/adapters/claude-code/` — Claude Code's `UserPromptSubmit` wiring for reference
- `scripts/tests/test_codex_adapter.py` — existing test patterns to mirror

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Actual Claude Code UserPromptSubmit implementation** (not an adapter script — this is the full handler):
- `hooks/scripts/user-prompt-check.sh` — reads `.prompt` from stdin JSON via `jq`, applies bypass guards (slash commands, `#`, `?`, `*`-prefix, <10 chars), reads `prompt_optimization.*` config via `ll_resolve_config` + `ll_config_value`, renders `hooks/prompts/optimize-prompt-hook.md` to stdout. Exit 0 always.
- `hooks/scripts/lib/common.sh` — provides `ll_resolve_config` (probes `.ll/ll-config.json` then root `ll-config.json` only — no `.codex/` awareness) and `ll_feature_enabled` / `ll_config_value`
- `hooks/hooks.json` lines 17–28 — Claude Code's `UserPromptSubmit` entry: no `matcher`, `timeout: 5`, `statusMessage: "Checking prompt..."`, command: `bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/user-prompt-check.sh`

**Codex hooks.json format** (for the new `UserPromptSubmit` block):
- Path placeholder: `{{LL_PLUGIN_ROOT}}` (double curly — not `${CLAUDE_PLUGIN_ROOT}`)
- No `matcher` key on the group (match all prompts)
- `timeout: 5` to match Claude Code, `statusMessage: "Checking prompt..."`

**Existing adapter script template** (`session-start.sh` / `pre-compact.sh` pattern):
```bash
#!/usr/bin/env bash
export LL_HOOK_HOST=codex
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks <intent>
exit $?
```

**Python dispatcher** (`scripts/little_loops/hooks/__init__.py:_dispatch_table()` ~line 60):
- Registers only `"pre_compact"` and `"session_start"` — no `"user_prompt_submit"`
- `_HOOK_INTENT_REGISTRY` (extension registry) would also be checked — no `user_prompt_submit` there
- Adding Option B requires: new `scripts/little_loops/hooks/user_prompt_submit.py` module + entry in `built_ins` dict

**Test file** (`scripts/tests/test_codex_adapter.py:TestCodexAdapterIntegration`):
- `test_adapter_sets_ll_hook_host_codex` (line 128) — sentinel-file pattern: fake `little_loops/hooks/__main__.py` shim, `PYTHONPATH` override, assert sentinel reads `"codex"`
- `test_adapter_files_exist` (line 40) — asserts each script path exists; add `prompt-submit.sh` here
- `test_adapter_scripts_are_executable` (line 47) — checks `os.access(path, os.X_OK)`; add `prompt-submit.sh` here
- `test_hooks_json_references_plugin_root_placeholder` (line 68) — checks `{{LL_PLUGIN_ROOT}}` in hooks.json text

**Config path** — Option B advantage: `scripts/little_loops/config/core.py:resolve_config_path()` probes `.codex/ll-config.json` first when `LL_HOOK_HOST=codex`. Option A (Bash delegation) misses this.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/__init__.py` — (Option B only) update `_USAGE` string to add `user_prompt_submit` to available intents list; add `"user_prompt_submit": user_prompt_submit.handle` to `built_ins` dict in `_dispatch_table()` [Agent 1 & 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/HOST_COMPATIBILITY.md` — update `user_prompt_submit` Codex CLI cell from `(deferred)` to `✓`; add FEAT-1482 to "Tracking issues" section [Agent 2 finding]
- `docs/ARCHITECTURE.md` — add `prompt-submit.sh` to `hooks/adapters/codex/` directory listing with inline comment [Agent 2 finding]
- `skills/init/SKILL.md` — update line 285 description from `SessionStart matcher=startup, PreCompact` to include `UserPromptSubmit` [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md` — (Option B only) add `user_prompt_submit` per-intent payload note alongside existing `pre_compact` and `session_start` notes [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_codex_adapter.py::TestCodexAdapterIntegration::test_adapter_files_exist` — update: add `PROMPT_SUBMIT = ADAPTER_DIR / "prompt-submit.sh"` constant and assertion [Agent 3 finding]
- `scripts/tests/test_codex_adapter.py::TestCodexAdapterIntegration::test_adapter_scripts_are_executable` — update: add `os.access(PROMPT_SUBMIT, os.X_OK)` assertion [Agent 3 finding]
- `scripts/tests/test_codex_adapter.py::TestCodexAdapterIntegration::test_prompt_submit_sets_ll_hook_host_codex` — new: sentinel-file pattern mirroring `test_adapter_sets_ll_hook_host_codex`; stdin `{"hook_event_name": "UserPromptSubmit", "prompt": "test prompt"}`; assert sentinel reads `"codex"` [Agent 3 finding]
- `scripts/tests/test_codex_adapter.py::TestCodexAdapterIntegration::test_hooks_json_has_user_prompt_submit` — new: JSON structure assertion verifying `UserPromptSubmit` key exists and `prompt-submit.sh` appears in the command path [Agent 3 finding]
- `scripts/tests/test_hook_intents.py::TestHooksMainModule::test_dispatch_user_prompt_submit_happy_path` — (Option B only) new: mirrors `test_dispatch_session_start_happy_path`; exercises `python -m little_loops.hooks user_prompt_submit` end-to-end [Agent 3 finding]

## Implementation Steps

1. Confirm `UserPromptSubmit` payload fields from Codex CLI docs
2. Create `prompt-submit.sh` from `session-start.sh` template, replacing intent name
3. Add hook entry to `hooks.json`; keep matcher unrestricted (fire on all user prompts)
4. Verify the `user_prompt_submit` Python handler is host-agnostic
5. Add test to `test_codex_adapter.py`
6. Update README event mapping table

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 (payload verification)** — cannot be resolved from codebase alone. The Codex README's subprocess contract table (`hooks/adapters/codex/README.md` lines 65–74) documents `SessionStart`/`PreCompact` payloads but not `UserPromptSubmit`. Verify the prompt field name (`.prompt`?) against Codex CLI source or `codex --help` before implementing.

**Step 2 (create prompt-submit.sh)** — depends on option chosen (see Proposed Solution):
- *Option A*: `export LL_HOOK_HOST=codex && bash "${LL_PLUGIN_ROOT}/hooks/scripts/user-prompt-check.sh"` — no Python call; stdin flows through naturally
- *Option B*: copy `hooks/adapters/codex/session-start.sh` verbatim, replace `session_start` → `user_prompt_submit` (after creating the Python module)

**Step 3 (hooks.json entry)** — exact format to add to `hooks/adapters/codex/hooks.json`:
```json
"UserPromptSubmit": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "bash {{LL_PLUGIN_ROOT}}/hooks/adapters/codex/prompt-submit.sh",
        "timeout": 5,
        "statusMessage": "Checking prompt..."
      }
    ]
  }
]
```

**Step 4 (Python dispatcher)** — CORRECTION: there is no existing `user_prompt_submit` Python handler. Option B requires creating `scripts/little_loops/hooks/user_prompt_submit.py` and registering it in `_dispatch_table()` at `scripts/little_loops/hooks/__init__.py` (~line 60). Port logic from `hooks/scripts/user-prompt-check.sh` using `resolve_config_path()` from `scripts/little_loops/config/core.py` (host-aware) instead of `ll_resolve_config` from `common.sh` (Bash-only, not `.codex/` aware).

**Step 5 (tests)** — add to `scripts/tests/test_codex_adapter.py:TestCodexAdapterIntegration`:
- `test_adapter_files_exist` (line 40): add `hooks/adapters/codex/prompt-submit.sh` to the paths list
- `test_adapter_scripts_are_executable` (line 47): add `prompt-submit.sh`
- New test mirroring `test_adapter_sets_ll_hook_host_codex` (line 128) for `prompt-submit.sh`

**Step 6 (README)** — `hooks/adapters/codex/README.md` line 36: change `UserPromptSubmit` row from `Deferred — Claude Code uses this for auto-prompt-optimizer; track separately` to `Implemented` with Python invocation filled in (or `bash …/prompt-submit.sh` for Option A).

**Trust-hash note** (`hooks/adapters/codex/README.md` lines 113–126): Codex hashes the command string in `hooks.json`, not the script body. Adding a new `UserPromptSubmit` entry to `.codex/hooks.json` will change the trust hash, prompting users to re-trust. Document in PR description.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/reference/HOST_COMPATIBILITY.md` — change `user_prompt_submit` Codex CLI cell from `(deferred)` to `✓`; add FEAT-1482 to "Tracking issues" section
8. Update `docs/ARCHITECTURE.md` — add `prompt-submit.sh` to the `hooks/adapters/codex/` directory listing with inline comment
9. Update `skills/init/SKILL.md` — extend line 285 description to include `UserPromptSubmit` alongside `SessionStart matcher=startup, PreCompact`
10. Update `scripts/tests/test_codex_adapter.py` — add `PROMPT_SUBMIT` module constant; update `test_adapter_files_exist` and `test_adapter_scripts_are_executable`; add `test_prompt_submit_sets_ll_hook_host_codex` and `test_hooks_json_has_user_prompt_submit`
11. (Option B only) Update `scripts/little_loops/hooks/__init__.py` — add `user_prompt_submit` to `_USAGE` string and to `built_ins` dict in `_dispatch_table()`
12. (Option B only) Update `docs/reference/EVENT-SCHEMA.md` — add `user_prompt_submit` per-intent payload note
13. (Option B only) Add `test_dispatch_user_prompt_submit_happy_path` to `scripts/tests/test_hook_intents.py::TestHooksMainModule`

## Impact

- **Scope**: New shell script + hooks.json entry + one test
- **Risk**: Low — reuses existing dispatcher; only adds a new hook entry
- **Note**: Trust-hash implications: adding a new `UserPromptSubmit` entry to `.codex/hooks.json` will change the trust hash, prompting users to re-trust on next startup (per FEAT-957 trust model). Document in the PR.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `hooks/adapters/codex/README.md` | Event mapping table and subprocess contract |
| `hooks/adapters/codex/session-start.sh` | Canonical adapter script template |
| `scripts/tests/test_codex_adapter.py` | Test patterns for codex adapter scripts |

## Labels

codex, hooks, auto-prompt-optimizer

## Status

**Open** | Created: 2026-05-15 | Priority: P5

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-15_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- Option A vs B is unresolved (`decision_needed: true`); implementer must choose before writing code
- Codex `UserPromptSubmit` payload field `.prompt` is undocumented in the codebase and needs external verification before either option can be safely implemented

### Outcome Risk Factors
- Unresolved decision between Option A (Bash delegation, simple) and Option B (Python handler, full Codex config-path integration) — resolve before implementing; choosing incorrectly means rework
- Payload field `.prompt` is unverified against Codex CLI; silent failure risk if the field name differs

## Session Log
- `/ll:manage-issue` - 2026-05-15T22:43:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:ready-issue` - 2026-05-15T22:37:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/46d366b8-67d8-408e-baa5-1f470fe2dccd.jsonl`
- `/ll:confidence-check` - 2026-05-15T23:15:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee7de6e9-997b-4bb6-a6ae-e81063eeaa11.jsonl`
- `/ll:decide-issue` - 2026-05-15T22:31:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c83fb486-18e2-416c-9520-e73ea7fb0cda.jsonl`
- `/ll:confidence-check` - 2026-05-15T22:45:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d397b69c-45f5-4133-a09f-ea94689a1f66.jsonl`
- `/ll:wire-issue` - 2026-05-15T22:25:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d981d92-9139-4c22-b492-04043e84a3a9.jsonl`
- `/ll:refine-issue` - 2026-05-15T22:20:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/66e53879-c16f-4ee7-82b3-c7d6b199900c.jsonl`
- `/ll:capture-issue` - 2026-05-15T20:37:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ac48eaf-913e-40cd-8b15-98d99f2901cc.jsonl`
