---
id: BUG-1890
title: ll:init auto-enables Codex setup when running in Claude Code
status: done
priority: P3
type: BUG
captured_at: '2026-06-03T04:04:46Z'
completed_at: '2026-06-03T04:27:38Z'
discovered_date: '2026-06-03'
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 22
---

# BUG-1890: ll:init auto-enables Codex setup when running in Claude Code

## Summary

Running `/ll:init` inside Claude Code writes `.codex/hooks.json` even when the user never asked for Codex integration.

## Motivation

Users who have both Claude Code and Codex installed receive unexpected `.codex/hooks.json` artifacts during `/ll:init`, violating the least-surprise principle. The downstream effect is a Codex hook-trust dialog appearing in the next Codex session for a project the user never intended to configure for Codex — creating cross-host confusion that is hard to diagnose. Every host should own its own initialization artifacts. The Codex auto-detection logic (`command -v codex || [ -d ".codex" ]`) is host-blind: it fires whenever `codex` is on PATH or a `.codex/` directory already exists, regardless of the active host CLI. As a result, Claude Code users who also happen to have Codex installed get Codex artifacts silently injected, violating the principle that each host should configure itself through its own init flow.

## Steps to Reproduce

1. Install both Claude Code and the Codex CLI (or have an existing `.codex/` dir).
2. Open a new project in Claude Code.
3. Run `/ll:init`.
4. Observe: `.codex/hooks.json` is created and the completion message says `[Codex] .codex/hooks.json written.`

## Expected Behavior

When running in Claude Code, `/ll:init` should only set up Claude Code artifacts. Codex artifacts (`.codex/hooks.json`) should be created only when running `/ll:init` inside Codex (or when `--codex` is explicitly passed).

## Current Behavior

`.codex/hooks.json` is written unconditionally when `codex` is on PATH or `.codex/` already exists, even during a Claude Code session. Completion output includes:

```
Created: .codex/hooks.json (Codex CLI hook adapter)
[Codex] .codex/hooks.json written. Codex will show a hook-trust dialog on next session start...
```

## Root Cause

`skills/init/SKILL.md` lines 58–60 (auto-detect block in **Step 1 — Parse Flags**):

```bash
# Auto-detect Codex CLI (codex on PATH or existing .codex/) if not passed.
if [[ "$CODEX" == false ]]; then
    if command -v codex >/dev/null 2>&1 || [ -d ".codex" ]; then CODEX=true; fi
fi
```

This block fires whenever the `codex` binary is on PATH or a `.codex/` directory exists — regardless of which host is currently running the skill. It does not consult `$LL_HOST_CLI`, `$LL_HOOK_HOST`, or any equivalent session signal. When `CODEX=true`, **Step 8.5 (Install Codex CLI Hook Adapter)** writes `.codex/hooks.json` (source: `hooks/adapters/codex/hooks.json`) into the project root after substituting `{{LL_PLUGIN_ROOT}}`.

`host_runner.py:resolve_host()` does correctly prioritize `LL_HOST_CLI` → `LL_HOOK_HOST` → binary probe in that order, but it is **never called** by the SKILL.md init flow — the skill uses raw Bash `command -v` with no equivalent priority ordering.

Note: `$CLAUDE_CODE_SESSION` is mentioned in several design discussions as a candidate signal, but it does **not** exist anywhere in the codebase as a set or checked env var.

## Proposed Solution

**Recommended approach — read `$LL_HOST_CLI` / `$LL_HOOK_HOST` directly (no subprocess):**

Replace lines 58–60 of `skills/init/SKILL.md` with:

```bash
# Auto-detect Codex CLI only when the active host is not Claude Code.
if [[ "$CODEX" == false ]]; then
    _ACTIVE_HOST="${LL_HOST_CLI:-${LL_HOOK_HOST:-}}"
    if [[ "$_ACTIVE_HOST" != "claude-code" ]]; then
        if command -v codex >/dev/null 2>&1 || [ -d ".codex" ]; then CODEX=true; fi
    fi
fi
```

This mirrors the exact detection order in `host_runner.py:resolve_host()` (line 751): `LL_HOST_CLI` checked first, `LL_HOOK_HOST` as fallback. No subprocess is needed. When neither env var is set (unknown host), auto-detection is skipped — a safe default since `--codex` is always available for explicit opt-in.

**Why not `ll-doctor --print-host`?**

The `--print-host` flag does **not exist** in the current `ll-doctor` CLI (`scripts/little_loops/cli/doctor.py:main_doctor()`). The doctor only accepts `--json` / `-j`. The JSON output does carry `report.host`, so `ll-doctor --json | jq -r .host` is a workaround but adds subprocess cost and a `jq` dependency. The env var approach above is simpler and more robust. If `--print-host` is desirable for other uses, it should be tracked as a separate enhancement to `doctor.py`.

## Implementation Steps

1. Open `skills/init/SKILL.md`; locate the auto-detect block in **Step 1 (Parse Flags)** at lines 58–60.
2. Replace the block with the host-guarded version that reads `${LL_HOST_CLI:-${LL_HOOK_HOST:-}}` before calling `command -v codex` (see Proposed Solution above).
3. Verify no regression: simulate a Codex session (`LL_HOST_CLI=codex`) with `codex` on PATH — `.codex/hooks.json` must still be created.
4. Verify fix: simulate a Claude Code session (`LL_HOST_CLI=claude-code`) with `codex` on PATH — `.codex/hooks.json` must NOT be created.
5. Add a test in `scripts/tests/` using the `isolated_env` fixture pattern from `scripts/tests/test_host_runner.py` to assert that the auto-detect does not set `CODEX=true` when `LL_HOST_CLI=claude-code` is set.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Create `scripts/tests/test_bug1890_init_host_guard.py` — text-content assertions (following `test_feat1743_init_wiring.py` pattern) that verify `LL_HOST_CLI`, `LL_HOOK_HOST`, and `claude-code` appear in the auto-detect block of `skills/init/SKILL.md`
7. Update `docs/guides/GETTING_STARTED.md` — in the `--codex` flag row of the "Set Up Your Project" flag table, add a host-scope note: "Auto-enabled only on non-Claude-Code hosts when `codex` is on PATH or a `.codex/` directory already exists"

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — auto-detect block at lines 58–60 (Step 1, Parse Flags)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/GETTING_STARTED.md` — `--codex` flag table row ("Set Up Your Project") states "Auto-enabled when the `codex` binary is on PATH or a `.codex/` directory already exists" — this description is now host-scoped and needs a clarifying note [Agent 2 finding]

### Dependent Files (Callers/Importers)
- N/A — SKILL.md is invoked by the harness directly, no importers

### Similar Patterns
- `scripts/little_loops/host_runner.py` — `resolve_host()` (line 751): authoritative host detection; the fix aligns with its `LL_HOST_CLI` → `LL_HOOK_HOST` → binary-probe priority order
- `hooks/adapters/codex/session-start.sh` — sets `LL_HOOK_HOST=codex`; Claude Code adapters in `hooks/adapters/claude-code/` omit `LL_HOOK_HOST`; this is the fallback signal the fix can use

### Tests
- `scripts/tests/test_host_runner.py` — `isolated_env` fixture (clears `LL_HOST_CLI`/`LL_HOOK_HOST`) is the canonical test setup for host-conditional behavior; binary-probe mocking via `monkeypatch.setattr("little_loops.host_runner.shutil.which", ...)` demonstrates the pattern
- `scripts/tests/test_cli_doctor.py` — reference if `ll-doctor --print-host` is added as a future enhancement
- Add a new test asserting the auto-detect block skips Codex when `LL_HOST_CLI=claude-code` is set and `codex` is on PATH

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_bug1890_init_host_guard.py` — new test file to create; follow pattern from `test_feat1743_init_wiring.py` (text-content assertions against `INIT_SKILL.read_text()`); assert `LL_HOST_CLI`, `LL_HOOK_HOST`, and `claude-code` appear in the auto-detect block [Agent 3 finding]

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — add a note clarifying that Codex artifacts are only written when the active host is Codex

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/GETTING_STARTED.md` — `--codex` flag table row describes auto-detection without host scope; update with "only on non-Claude-Code hosts" caveat [Agent 2 finding]

### Configuration
- N/A

## Impact

- **Priority**: P3 — Affects dual-install users (Claude Code + Codex); unexpected file creation but no data loss or breakage
- **Effort**: Small — Single guard condition added to a shell script block in SKILL.md (~5–10 lines)
- **Risk**: Low — Guard only prevents incorrect auto-detection; correct-host behavior is unchanged
- **Breaking Change**: No

**User-facing effects:**

- Creates unexpected files in user repositories without explicit opt-in.
- Confusing UX: the Codex hook-trust dialog appears in the next Codex session for a project the user never intended to configure for Codex.
- Violates the least-surprise principle: each host should own its own initialization.

## Labels

`bug`, `host-compat`, `init`, `codex`, `ux`

## Status

**Open** | Created: 2026-06-03 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-03T04:22:12 - `a11d2e64-c58f-424b-8fe2-9b5c35b06965.jsonl`
- `/ll:confidence-check` - 2026-06-03T05:00:00 - `219b778b-07e9-46c7-9b69-bfce8188ae25.jsonl`
- `/ll:wire-issue` - 2026-06-03T04:18:48 - `52cae352-510e-45d1-8164-e4287f33e891.jsonl`
- `/ll:refine-issue` - 2026-06-03T04:14:22 - `809f95d7-c601-44e5-9e04-4be7f0323f00.jsonl`
- `/ll:refine-issue` - 2026-06-03T04:30:00 - ``
- `/ll:format-issue` - 2026-06-03T04:08:11 - `f8ff5be9-c1e4-4ab0-af18-3b828aa926c8.jsonl`
- `/ll:capture-issue` - 2026-06-03T04:04:46Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5a9ea643-815c-4ba4-a65c-06a79d2602a1.jsonl`
