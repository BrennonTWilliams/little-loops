---
id: FEAT-1462
type: FEAT
priority: P3
status: open
discovered_date: 2026-05-15
discovered_by: manual-review
blocked_by: []
confidence_score: 50
outcome_confidence: 40
score_complexity: 18
score_test_coverage: 14
score_ambiguity: 16
score_change_surface: 12
---

# FEAT-1462: Abstract Host CLI Invocation in Orchestration Layer

## Summary

ll's automation tools (`ll-auto`, `ll-parallel`, `ll-action`, `ll-loop`, FSM evaluators, FSM handoff) hard-code the `claude` binary and Claude-Code-specific flags (`--dangerously-skip-permissions`, `--output-format stream-json`, `--agent`, `--tools`). This issue introduces a `host_runner` abstraction that selects the right binary and flag set per host (Claude Code, Codex CLI, Pi, future), so the orchestration layer is reusable under the host adapters delivered by FEAT-769 (OpenCode), FEAT-957 (Codex CLI), and FEAT-992 (Pi).

## Current Behavior

The hook layer is host-agnostic (FEAT-1116) but the orchestration layer is not. Concrete call sites that bake in `claude`:

- `scripts/little_loops/subprocess_utils.py:261` — `run_claude_streaming` builds `["claude", "--dangerously-skip-permissions", "--verbose", "--output-format", "stream-json", ...]`
- `scripts/little_loops/parallel/worker_pool.py:584` — worker spawns `claude` per issue
- `scripts/little_loops/cli/action.py:142,149` — `shutil.which("claude")` + `["claude", "--version"]` preflight
- `scripts/little_loops/fsm/handoff_handler.py:114` — `["claude", "-p", prompt]`
- `scripts/little_loops/fsm/evaluators.py:609` — `["claude", ...]` for LLM-graded evaluator

Result: under Codex CLI or Pi, the hook adapter fires but every `ll-*` automation entry point fails with "claude: command not found" or the wrong invocation contract. Cross-compat is half-done without this.

## Expected Behavior

A single `little_loops.host_runner` module owns:

1. Host detection (env var `LL_HOST_CLI`, else `LL_HOOK_HOST`, else probe `claude` → `codex` → `pi` on PATH, else error)
2. Binary resolution per host
3. Headless/print-mode flag translation (Claude `-p`, Codex `exec`, Pi tbd)
4. Capability flags (permission skip, output format, agent selection, tool allowlist) — with a documented fallback when a host doesn't support a given capability
5. Streaming-JSON output normalization to a common envelope, OR a documented capability gate that disables features requiring stream-json on hosts that lack it

All six call sites listed above route through this module. Hard-coded `"claude"` strings disappear from `scripts/little_loops/`.

## Motivation

- **Unlocks FEAT-957 / FEAT-992 acceptance**: those issues deliver hook adapters but explicitly carve out the orchestration layer (see FEAT-957 Cross-Compat Scope Boundaries). Until this ships, "cross-compat" is hook-only and `ll-auto` etc. remain Claude-Code-only.
- **Removes hidden coupling**: the `LL_HOOK_HOST` env var already advertises a host abstraction, but the orchestration code doesn't read it. Users will reasonably expect "if hooks work under codex, automation does too" — closing that expectation gap.
- **Foundation for future hosts**: any new host added after this becomes a config entry plus a flag-translation table, not a code rewrite.

## Use Case

A developer installs little-loops under Codex CLI. `ll:init --codex` (FEAT-957) sets up `.codex/hooks.json`, and hooks work. The developer then runs `ll-auto`, expecting Codex to process the backlog. Today it fails immediately. With this feature, `host_runner` detects Codex, invokes `codex exec ...` with translated flags, and the automation proceeds.

## Acceptance Criteria

- [ ] New module `scripts/little_loops/host_runner.py` exposes `resolve_host()`, `HostInvocation`, `HostRunner` protocol, `HostNotConfigured`, and `CapabilityNotSupported`
- [ ] Host detection resolves in documented order: `LL_HOST_CLI` env → `LL_HOOK_HOST` env → binary probe (`claude` → `codex` → `pi`) → `HostNotConfigured` with remediation hint
- [ ] `ClaudeCodeRunner` produces argv byte-identical to pre-refactor calls (verified by snapshot tests in `test_host_runner.py::test_claude_runner_matches_legacy_args`)
- [ ] All six call sites route through `host_runner`: `subprocess_utils.py` (`run_claude_streaming`), `parallel/worker_pool.py` (worker spawn), `cli/action.py` (preflight + version check), `fsm/handoff_handler.py` (handoff spawn), `fsm/evaluators.py` (LLM-graded evaluator)
- [ ] `grep -rn '"claude"' scripts/little_loops/` returns no hard-coded binary literals (only comments/docs/test fixtures)
- [ ] `CodexRunner` translates Claude-Code flags to Codex equivalents per the documented translation table (e.g. `--dangerously-skip-permissions` → Codex approval flag)
- [ ] Requesting an unsupported capability (e.g. `--agent` under Codex) emits `CapabilityNotSupported`; default behavior logs to stderr and continues, opt-in abort available
- [ ] `OpenCodeRunner` ships alongside Codex; `PiRunner` raises `HostNotConfigured` with a pointer to FEAT-992 until Pi research lands
- [ ] `config-schema.json` includes `orchestration.host_cli` enum with default `"auto"`, consumed by `resolve_host()` after env-var checks
- [ ] Existing test suite stays green for Claude-Code users; new `test_host_runner.py` covers detection precedence, capability gating, and per-host flag translation snapshots
- [ ] Docs updated: `ARCHITECTURE.md` layering diagram, `API.md` public API entries, `HOST_COMPATIBILITY.md` orchestration row, `TROUBLESHOOTING.md` entry for `HostNotConfigured`

## Proposed Solution

Introduce `scripts/little_loops/host_runner.py` with:

```python
@dataclass(frozen=True)
class HostInvocation:
    binary: str
    args: list[str]
    env: dict[str, str]
    capabilities: HostCapabilities  # streaming, permission_skip, agent_select, tool_allowlist


class HostRunner(Protocol):
    name: str
    def detect(self) -> bool: ...
    def build_invocation(self, *, prompt: str, working_dir: Path,
                          resume: bool, agent: str | None,
                          tools: list[str] | None) -> HostInvocation: ...


def resolve_host() -> HostRunner:
    """Returns the active host runner. Resolution order:
       1. LL_HOST_CLI env var (explicit override)
       2. LL_HOOK_HOST env var (reuse the hook-layer signal)
       3. Binary probe: claude → codex → pi
       4. Raise HostNotConfigured with actionable error
    """
```

Implementations (one per host, all in the same module to keep the registry honest):

- `ClaudeCodeRunner` — current behavior; `claude -p` + existing flags
- `CodexRunner` — `codex exec` (Codex's headless mode); flag translation table TBD via Codex docs research
- `OpenCodeRunner` — `opencode` headless mode (FEAT-769 has a hook adapter; runner is new ground)
- `PiRunner` — stub until FEAT-992 plugin-API research lands

Refactor the five call sites to construct invocations through `resolve_host().build_invocation(...)` and `subprocess.run` the result.

Capability gating: if a feature (e.g. `--agent`) isn't supported by the active host, the runner returns the invocation without that flag AND raises a typed `CapabilityNotSupported` warning that callers can choose to log-and-degrade or abort. Default: log to stderr and continue.

## API/Interface

```python
# New public API
from little_loops.host_runner import resolve_host, HostInvocation, HostNotConfigured

inv = resolve_host().build_invocation(
    prompt="...",
    working_dir=cwd,
    resume=False,
    agent="general-purpose",
    tools=["Read", "Edit"],
)
proc = subprocess.run([inv.binary, *inv.args], env=inv.env, cwd=working_dir, ...)
```

New env vars:
- `LL_HOST_CLI` — explicit override (e.g. `"codex"`); takes precedence over auto-detection
- (Reuses) `LL_HOOK_HOST` — already exists; runner falls back to it

New exceptions:
- `HostNotConfigured` — no host detected and no override set
- `CapabilityNotSupported` — caller requested a flag the host doesn't expose

## Integration Map

### Files to Modify

- `scripts/little_loops/subprocess_utils.py:261` — `run_claude_streaming` becomes `run_host_streaming` (or keep the name as an alias); replace hard-coded list with `HostInvocation`
- `scripts/little_loops/parallel/worker_pool.py:584` — worker subprocess construction
- `scripts/little_loops/cli/action.py:142,149` — `shutil.which("claude")` preflight becomes `resolve_host().detect()` + `--version` via the resolved binary
- `scripts/little_loops/fsm/handoff_handler.py:114` — handoff spawn
- `scripts/little_loops/fsm/evaluators.py:609` — LLM-graded evaluator spawn

### New Files

- `scripts/little_loops/host_runner.py` — Protocol + registry + per-host implementations
- `scripts/tests/test_host_runner.py` — detection precedence, capability gating, flag translation snapshots
- `docs/reference/HOST_COMPATIBILITY.md` — extend the matrix added by FEAT-957 with an "Orchestration CLI" row showing per-host status

### Configuration

- `config-schema.json` — add `orchestration.host_cli` enum (`"auto" | "claude-code" | "codex" | "opencode" | "pi"`); default `"auto"`. Read by `host_runner.resolve_host()` after env vars.

### Tests

- `test_host_runner.py::test_detect_explicit_override` — `LL_HOST_CLI=codex` wins over installed binaries
- `test_host_runner.py::test_detect_falls_back_to_hook_host` — uses `LL_HOOK_HOST` when `LL_HOST_CLI` unset
- `test_host_runner.py::test_detect_binary_probe_order` — claude → codex → pi
- `test_host_runner.py::test_raises_when_no_host` — clear error with remediation hint
- `test_host_runner.py::test_claude_runner_matches_legacy_args` — snapshot of pre-refactor argv; regression guard against unintended flag drift
- `test_host_runner.py::test_codex_runner_flag_translation` — `--dangerously-skip-permissions` → Codex `--ask-for-approval=never` (verify against Codex docs)
- `test_host_runner.py::test_capability_warning` — requesting `--agent` under Codex emits `CapabilityNotSupported`
- Integration: update `test_subprocess_utils.py`, `test_action.py`, `test_handoff_handler.py`, `test_evaluators.py` to mock `host_runner.resolve_host` instead of patching `subprocess`/`shutil.which`

### Documentation

- `docs/ARCHITECTURE.md` — add `host_runner` module to the layering diagram alongside the existing hook-intent layer
- `docs/reference/API.md` — document the new public API
- `docs/reference/HOST_COMPATIBILITY.md` — orchestration row per host
- `docs/development/TROUBLESHOOTING.md` — entry for `HostNotConfigured` with `LL_HOST_CLI` remediation
- `.claude/CLAUDE.md` — note the new abstraction near the existing "Automation: Scratch Pad" section so contributors know not to add new `"claude"` literals

## Implementation Steps

1. **Codex headless-mode research** — confirm Codex's `exec`/`-p` equivalent, flag mappings, output format. Block scaffolding on this. (Equivalent to FEAT-957's plugin-API research phase.)
2. **Scaffold `host_runner.py`** with `ClaudeCodeRunner` only — refactor all five call sites to route through it; full test suite stays green. This is the safe-refactor PR; no behavior change for Claude Code users.
3. **Add `CodexRunner`** with flag translation table; gate behind `LL_HOST_CLI=codex` until tested manually.
4. **Add capability-warning surface** — typed exceptions + opt-in abort-vs-degrade behavior.
5. **Add `OpenCodeRunner`** — OpenCode has had a hook adapter since FEAT-769 but no orchestration story; close that gap now.
6. **Stub `PiRunner`** — raises `HostNotConfigured("Pi orchestration not yet wired — see FEAT-992")` until Pi plugin API is researched.
7. **Update `HOST_COMPATIBILITY.md`** (file created by FEAT-957) with the orchestration row.
8. **Sweep for stragglers** — grep for any remaining `"claude"` literals in `scripts/little_loops/`; either route through `host_runner` or document why a literal is intentional.

## Impact

- **Priority**: P3 — Required to deliver on FEAT-957 and FEAT-992 cross-compat promise; blocking real Codex/Pi users from actually using ll automation.
- **Effort**: Medium — Refactor is mechanical at five call sites but flag-translation tables require per-host research and the test surface is wide (snapshot tests for argv parity are critical to avoid silent regressions in Claude Code users).
- **Risk**: Medium — Every ll automation entry point flows through this module. A bad refactor breaks `ll-auto` and `ll-parallel` for all users. Mitigation: Step 2 (Claude-Code-only scaffold) ships standalone with argv snapshot tests before any new host code lands.
- **Breaking Change**: No (`run_claude_streaming` retained as alias if needed; flag behavior identical for Claude Code users).

## Related Key Documentation

- `.claude/CLAUDE.md` — CLI tools list
- `docs/ARCHITECTURE.md` — hook intent abstraction layer (FEAT-1116) is the architectural sibling

## Blocked By

_None._ Step 1 (Codex headless-mode research) is an in-issue task, not a dependency. Could ship Step 2 (Claude-Code-only refactor) immediately as a safe-refactor PR even before research completes.

## Blocks

- FEAT-957 (Codex CLI compatibility — hook layer ships independently, but full Codex parity requires this)
- FEAT-992 (Pi compatibility — same)

## Labels

`feat`, `refactor`, `host-abstraction`, `compatibility`, `cross-host`

## Status

**Open** | Created: 2026-05-15 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-05-15T12:23:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4689ac73-1c8c-466a-9a6f-710fdc35baef.jsonl`

- manual-review - 2026-05-15T00:00:00 - Filed during cross-compat readiness review of FEAT-957 / FEAT-992; identified six hard-coded `claude` call sites in scripts/little_loops/ that block real cross-host operation.

---

## Scope Boundary

**Note**: This issue addresses the **orchestration layer** only (`ll-auto`, `ll-parallel`, `ll-action`, `ll-loop`, FSM evaluators, FSM handoff). The **hook layer** is already abstracted by FEAT-1116 and per-host adapters under `hooks/adapters/`. Do not conflate the two — `host_runner` is for outbound subprocess calls *from* ll to the host CLI; the hook adapters are for inbound events *from* the host CLI to ll.

**Note**: Slash-command and skill content discovery is NOT in scope. Codex reads `.codex/prompts/`, OpenCode has its own conventions; mirroring `.claude/commands/` and `.claude/skills/` to host-native locations is a separate concern (no issue filed yet — capture if user demand surfaces).

**Note**: This is a **Host Adapter** complement, NOT an Extension in the FEAT-917 sense. No PyPI manifest, no `ll extensions` discovery.
