---
id: EPIC-2910
title: Kimi Code CLI host adapter — tracking
type: EPIC
status: open
priority: P3
captured_at: "2026-07-29T15:55:00Z"
discovered_date: 2026-07-29
discovered_by: capture-issue
relates_to:
- FEAT-2911
- ENH-2912
- ENH-2913
- FEAT-2914
- FEAT-2915
- FEAT-2916
- FEAT-2917
- ENH-2918
- ENH-2919
- BUG-2921
labels:
- epic
- captured
- kimi
- host-compat
- tracking
---

# EPIC-2910: Kimi Code CLI host adapter — tracking

## Summary

Moonshot AI's `kimi-code` CLI (binary `kimi`) is a major AI coding-agent host
whose surface is unusually Claude-compatible: native subagents, blockable
hooks, SKILL.md skills, Claude-loadable agent files, and a plugin manifest.
This epic is the umbrella tracking kimi-code as a first-class little-loops
host — analogous to EPIC-2178 (Gemini CLI host adapter tracking). The
research spike (FEAT-2911) is already complete, so implementation children
can start immediately.

## Motivation

`kimi-code` is a major AI coding-agent CLI with significant and growing
adoption, and its Claude-compatible surface makes adaptation cheap relative
to other hosts. Adding it as a supported host brings little-loops automation
(`ll-auto`, `ll-loop`, FSM loops) to kimi users. The architecture already
supports N hosts via `resolve_host()` / `HostRunner`; kimi follows the
established 4-layer pattern:

1. Runner → `host_runner.py`
2. Hook adapter → `hooks/adapters/kimi/`
3. Config probe → `config/core.py`
4. Parity matrix → `docs/reference/HOST_COMPATIBILITY.md`

plus the generic EPIC-2257 tooling (`ll-adapt --host kimi-code`, conformance
harness).

## Naming Decisions

Ratified during the 2026-07-29 planning session:

- **Runner host key**: `kimi-code` (binary `kimi`).
- **Emitter/capabilities key**: ALSO `kimi-code` — deliberately breaking the
  un-suffixed emitter convention (codex/gemini/omp) because
  `ll-verify-host-map` check 2 only cross-validates the
  `HOST_CAPABILITIES ∩ _HOST_RUNNER_REGISTRY` intersection.
- **Config dir**: `.kimi-code`.
- **Plugin id**: `ll` (preserves the `/ll:<command>` namespace).

## Goal

kimi-code users can run `ll-auto`, `ll-loop`, and FSM-based automation loops
with `LL_HOST_CLI=kimi-code`, with hook lifecycle events (`session_start`,
`pre_compact` at minimum) firing correctly.

End-state acceptance: a kimi-code column exists in
`docs/reference/HOST_COMPATIBILITY.md` with no unknown or untracked cells —
every cell is ✓, ✗ (with a tracking issue), or N/A.

## Scope

**In scope:**

- **Research spike** (FEAT-2911, **done**) — kimi-cli binary surface, hook
  events, plugin discovery; artifact `thoughts/research/kimi-cli-surface.md`.
- **`KimiRunner` stub** (ENH-2912) then **full implementation** (FEAT-2914)
  in `scripts/little_loops/host_runner.py`.
- **Hook adapter** `hooks/adapters/kimi/` + `ll-init` wiring + shared
  `write_agents_md()` (FEAT-2915).
- **Config probe** — `.kimi-code/ll-config.json` in `_config_candidates()`
  (ENH-2913).
- **ll-adapt emitter** (FEAT-2916) — atomic with its HOST_COMPATIBILITY
  adapter row.
- **kimi.plugin.json packaging** (FEAT-2917) — kimi-native install path.
- **Conformance + host-list plumbing** (ENH-2918) — config-schema enum
  (incl. gemini/omp drift fix); `ll-session` `get_project_folder()` branch.
- **HOST_COMPATIBILITY.md column + `docs/kimi/` onboarding** (ENH-2919).

**Out of scope:**

- Changes to existing claude/codex/gemini/omp adapters.
- Porting legacy `hooks/scripts/*.sh` to intents — hook parity is capped at
  the intent layer.
- Anthropic SDK / batch request path.
- Adding gemini/omp to `_KNOWN_HOSTS` or `ll-session --host` choices —
  deliberate non-goal: accurate absences, not drift.

## Children

- **FEAT-2911** — Research spike: kimi-cli binary surface, hook events, plugin discovery — ✅ **done**
- **ENH-2912** — KimiRunner stub in host_runner.py — ✅ **done** (landed as full runner with FEAT-2914, no stub stage)
- **ENH-2913** — Config probe — .kimi-code/ll-config.json in _config_candidates() — ✅ **done**
- **FEAT-2914** — KimiRunner full implementation (build_streaming, build_blocking_json, build_detached, build_version_check) — ✅ **done**
- **FEAT-2915** — Hook adapter — hooks/adapters/kimi + ll-init wiring + shared write_agents_md() — ✅ **done**
- **FEAT-2916** — ll-adapt emitter for kimi-code — ✅ **done** (adapter row landed atomically)
- **FEAT-2917** — kimi.plugin.json packaging — ✅ **done** (plugin-hooks caveat spun out to BUG-2921)
- **ENH-2918** — Conformance + host-list plumbing for kimi-code — ✅ **done**
- **ENH-2919** — HOST_COMPATIBILITY.md kimi-code column + docs/kimi/ onboarding — ✅ **done**
- **BUG-2921** — kimi plugin-manifest hooks inert on 0.30.0; config.toml managed block is the working route — open (captured from live plugin-install validation)

## Implementation Steps

1. ✅ Land research spike (FEAT-2911) — all downstream work depends on its findings. **done**
2. ✅ Add `KimiRunner` stub to `host_runner.py` + `_PROBE_ORDER` entry (ENH-2912). **done** (landed as full runner, no stub stage)
3. ✅ Implement full `KimiRunner` (FEAT-2914) and the hook adapter + `ll-init`
   wiring (FEAT-2915) — the critical path. **done**
4. ✅ Independent tracks (any order, parallel with 3): config probe (ENH-2913),
   ll-adapt emitter (FEAT-2916), plugin packaging (FEAT-2917),
   conformance/plumbing (ENH-2918). **done**
5. ✅ Docs last: complete the HOST_COMPATIBILITY.md kimi-code column and land
   `docs/kimi/` onboarding (ENH-2919). **done**
6. Remaining: live end-to-end smoke (`LL_HOST_CLI=kimi-code ll-auto`,
   `/plugins install` in the kimi TUI) and BUG-2921.

## Success Metrics

- `LL_HOST_CLI=kimi-code` resolves without error on a machine with `kimi` on PATH.
- `session_start` and `pre_compact` hook intents fire on kimi-code.
- `ll-auto` can process at least one issue end-to-end using the kimi runner.
- All kimi-code column cells in `HOST_COMPATIBILITY.md` are ✓, ✗ (linked), or N/A.
- `ll-doctor --full` and `ll-verify-host-map` stay green throughout.

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py` — `KimiRunner`, `_HOST_RUNNER_REGISTRY`, `_PROBE_ORDER`, `_remediation_hint()`
- `scripts/little_loops/config/core.py` — `KIMI_CONFIG_DIR`, `_config_candidates()` probe
- `scripts/little_loops/init/cli.py` — `_KNOWN_HOSTS`, `_detect_hosts()`, `_dispatch_host_adapters()`, `--hosts` help
- `scripts/little_loops/init/tui.py` — host checkbox
- `scripts/little_loops/init/writers.py` — `install_kimi_adapter()`, shared `write_agents_md()`
- `scripts/little_loops/adapters/core.py` — `_EMITTER_MAP` entry
- `scripts/little_loops/adapters/capabilities.py` — `HOST_CAPABILITIES` entry
- `scripts/little_loops/user_messages.py` — `get_project_folder()` kimi branch
- `scripts/little_loops/cli/session.py` — `--host` choices entry
- `scripts/little_loops/config-schema.json` — `orchestration.host_cli` enum (incl. gemini/omp drift fix)
- `scripts/tests/conformance/test_host_conformance.py` — `_HOST_BINARY` entry
- `docs/reference/HOST_COMPATIBILITY.md` — kimi-code column
- `docs/ARCHITECTURE.md` — `KimiRunner` in component table
- `README.md` — kimi install section
- `.claude/CLAUDE.md` — fix stale config-schema pointer

### New Files

- `scripts/little_loops/hooks/adapters/kimi/` — shims, TOML template, README
- `scripts/little_loops/adapters/kimi.py` — ll-adapt emitter
- `kimi.plugin.json` — plugin manifest (repo root)
- `scripts/tests/test_kimi_adapter.py`
- `docs/kimi/` — onboarding trio
- `thoughts/research/kimi-cli-surface.md` — spike artifact (**done**)

### Dependent Files

- `scripts/little_loops/hooks/__main__.py` — intent dispatch table
- `scripts/little_loops/hooks/intents/user_prompt_submit.py`, `post_tool_use.py`, `subagent_start.py`, `subagent_stop.py` — payload drift accessors
- `scripts/tests/test_host_runner.py` — `KimiRunner` coverage

## Impact

- **Priority**: P3 — tracking epic for a major host with an unusually
  Claude-compatible surface; cheaper to adapt than Gemini was, but still no
  confirmed user demand in hand.
- **Effort**: Large (aggregate) — each child is XS–Medium; the critical path
  is the runner + hook adapter.
- **Risk**: Low-Medium — additive, host-specific; no existing host behavior
  change. The completed research spike already de-risked the payload drift
  surface.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `thoughts/research/kimi-cli-surface.md` | FEAT-2911 spike artifact; source of truth for the kimi surface |
| `docs/reference/HOST_COMPATIBILITY.md` | Parity matrix this epic targets; kimi-code column added here |
| `docs/ARCHITECTURE.md` | `HostRunner` protocol and adapter tree |
| `scripts/little_loops/host_runner.py` | Implementation home for `KimiRunner` |
| `scripts/little_loops/hooks/adapters/codex/README.md` | Adapter contract template to follow |

## Verification Notes

2026-07-29 (PLANNED): EPIC and 9 children captured from the kimi-code host
adapter planning session. FEAT-2911 (research spike) is done —
`thoughts/research/kimi-cli-surface.md` written 2026-07-29 against kimi
0.30.0. No implementation code exists yet: no `KimiRunner` in
`host_runner.py`, no `hooks/adapters/kimi/`, no `.kimi-code` config probe, no
emitter. Critical path: ENH-2912 (stub) → FEAT-2914 (full runner) +
FEAT-2915 (hook adapter); ENH-2913, FEAT-2916, FEAT-2917, ENH-2918 are
independent; ENH-2919 closes last.

2026-07-29 (IN PROGRESS): Implementation landed same-day, ahead of the
planned critical path — the spike de-risked the runner enough that ENH-2912
and FEAT-2914 landed as one full `KimiRunner` (no stub stage). Done:
`KimiRunner` (157 host_runner tests pass), `.kimi-code` config probe
(ENH-2913, 3 tests), hook adapter package `scripts/little_loops/hooks/adapters/kimi/`
(8 shims + `hooks.toml` + README) with `install_kimi_adapter()` managed-block
install into `~/.kimi-code/config.toml`, ll-init wiring, host-shared
`write_agents_md()`, handler payload-tolerance fixes (FEAT-2915),
`KimiEmitter` + `HOST_CAPABILITIES`/`_EMITTER_MAP` keyed `kimi-code` with the
adapter doc row landed atomically (FEAT-2916 — `ll-verify-host-map` green,
`ll-adapt --host kimi-code --apply` → 55 adapted / 0 errors), repo-root
`kimi.plugin.json` (plugin id `ll`, `/ll:*` namespace preserved; FEAT-2917),
conformance `_HOST_BINARY` entry (4 golden paths pass on the real binary),
config-schema `host_cli` enum incl. gemini/omp drift fix, `get_project_folder()`
kimi branch via `session_index.jsonl` + `ll-session --host kimi-code`
(ENH-2918), pyproject metadata. Remaining: ENH-2919 (matrix column +
docs/kimi/) and the live end-to-end smoke (`LL_HOST_CLI=kimi-code ll-auto`,
`/plugins install` in the kimi TUI). Known limitation recorded: kimi
`wire.jsonl` uses a typed-event schema — `ll-session backfill` can locate but
not yet parse kimi session logs (follow-up needed under ENH-2918).

2026-07-29 (VERIFIED — /ll:verify-issues): All integration-map claims verified
against the codebase. Implementation has progressed beyond what this file
describes: every child listed as "open" above (ENH-2912, ENH-2913, FEAT-2914,
FEAT-2915, FEAT-2916, FEAT-2917, ENH-2918) has its code landed, and ENH-2919's
deliverables also exist — the kimi-code column is complete across the
HOST_COMPATIBILITY.md tables (hook intents, discovery, runner capabilities),
the `docs/kimi/` onboarding trio (`getting-started.md`, `hook-events.md`,
`automation.md`) is in place, and `KimiRunner` appears in
`docs/ARCHITECTURE.md` and the README. The Children table statuses and the
"Remaining: ENH-2919" note were stale at verification time; all eight open
children were subsequently closed (`status: done`) in this same session and
the Children table / Implementation Steps updated to match. Genuinely
remaining: the live end-to-end smoke (`LL_HOST_CLI=kimi-code ll-auto`,
`/plugins install` in the kimi TUI) and BUG-2921 (plugin-manifest hooks
inert). Minor drift: Integration Map promises a README under
`hooks/adapters/kimi/`; only the 8 shims + `hooks.toml` are present.

## Session Log
- `/ll:verify-issues` - 2026-07-29T20:51:41 - `7dce485a-c75c-400c-ac56-53fcf2521623.jsonl`
- `/ll:capture-issue` - 2026-07-29T15:55:00Z - kimi-code host adapter planning session

---

**Open** | Created: 2026-07-29 | Priority: P3
