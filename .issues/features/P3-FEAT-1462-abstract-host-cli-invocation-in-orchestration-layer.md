---
id: FEAT-1462
type: FEAT
priority: P3
status: done
discovered_date: 2026-05-15
discovered_by: manual-review
blocked_by: []
confidence_score: 90
outcome_confidence: 55
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 10
size: Very Large
completed_at: 2026-05-15T00:00:00Z
---

# FEAT-1462: Abstract Host CLI Invocation in Orchestration Layer

## Summary

ll's automation tools (`ll-auto`, `ll-parallel`, `ll-action`, `ll-loop`, FSM evaluators, FSM handoff) hard-code the `claude` binary and Claude-Code-specific flags (`--dangerously-skip-permissions`, `--output-format stream-json`, `--agent`, `--tools`). This issue introduces a `host_runner` abstraction that selects the right binary and flag set per host (Claude Code, Codex CLI, Pi, future), so the orchestration layer is reusable under the host adapters delivered by FEAT-769 (OpenCode), FEAT-957 (Codex CLI), and FEAT-992 (Pi).

## Current Behavior

The hook layer is host-agnostic (FEAT-1116) but the orchestration layer is not. Concrete call sites that bake in `claude`:

- `scripts/little_loops/subprocess_utils.py:261` — `run_claude_command()` (defined at line 219; not `run_claude_streaming` as previously stated) builds `["claude", "--dangerously-skip-permissions", "--verbose", "--output-format", "stream-json", ...]`
- `scripts/little_loops/parallel/worker_pool.py:584` — `_detect_worktree_model_via_api()` spawns `["claude", "-p", "reply with just 'ok'", "--output-format", "json"]` (note: `json` not `stream-json`, no permissions skip)
- `scripts/little_loops/cli/action.py:142,149` — `cmd_capabilities()` runs `shutil.which("claude")` + `["claude", "--version"]` preflight
- `scripts/little_loops/fsm/handoff_handler.py:114` — `_spawn_new_claude_session()` runs `["claude", "-p", prompt]` (fire-and-forget Popen with `start_new_session=True`)
- `scripts/little_loops/fsm/evaluators.py:609` — LLM-graded evaluator runs `["claude", "-p", prompt, "--output-format", "json", "--json-schema", schema, "--model", model, "--dangerously-skip-permissions", "--no-session-persistence"]`

Total: **6 hard-coded `"claude"` string literals across 5 files** — `grep -n '"claude"' scripts/little_loops/` confirms no others.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Reusable existing patterns**:
- **Protocol pattern**: `scripts/little_loops/extension.py` already defines `@runtime_checkable` Protocols (`LLExtension`, `LLHookIntentExtension`, `ActionProviderExtension`). Model `HostRunner` on these — same decorator, same `provided_*` discovery convention.
- **Lazy dispatch registry**: `scripts/little_loops/hooks/__init__.py:44-70` has the `_HOOK_INTENT_REGISTRY` + `_dispatch_table()` pattern (module-level dict, lazy built-in merge). Apply the same shape for `_HOST_RUNNER_REGISTRY`.
- **Host-branching extension point**: `scripts/little_loops/config/core.py:_config_candidates()` already documents "future hosts add a new branch here rather than a new code path elsewhere" — `host_runner` should follow the same closure-of-the-extension-point convention.
- **Warning vs. exception**: `config/core.py` uses `warnings.warn(..., DeprecationWarning, stacklevel=2)` for opt-in capture. `CapabilityNotSupported` should subclass `UserWarning` so callers can use `warnings.filterwarnings("error", category=CapabilityNotSupported)` to upgrade to abort — avoids needing a separate "abort vs. degrade" flag in the API.

**Design tension to resolve before scaffolding**: the proposed single-method `build_invocation(prompt, working_dir, resume, agent, tools)` signature does not accommodate the per-call-site flag profiles documented in the Integration Map (notably `--json-schema`, `--model`, `--no-session-persistence` for the evaluator and `--version` for the action preflight). Step 2 of Implementation Steps should resolve this — either expand the signature with optional kwargs (`json_schema`, `model`, `version_check`) or split into purpose-specific factory methods. This is a refinement of the existing approach, not an alternative design — no `decision_needed` flag required.

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

- `scripts/little_loops/subprocess_utils.py:261` — `run_claude_command()` (def line 219) becomes `run_host_command` (keep `run_claude_command` as alias); replace hard-coded list with `HostInvocation`. Already passes `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` env + worktree `GIT_DIR`/`GIT_WORK_TREE` — preserve these
- `scripts/little_loops/parallel/worker_pool.py:584` — `_detect_worktree_model_via_api()`; uses **blocking** `subprocess.run` with `--output-format json` (not stream-json). Routes through `HostInvocation` profile = "version-probe-style JSON"
- `scripts/little_loops/cli/action.py:142,149` — `cmd_capabilities()`; `shutil.which("claude")` preflight becomes `resolve_host().detect()` + `--version` via the resolved binary
- `scripts/little_loops/fsm/handoff_handler.py:114` — `_spawn_new_claude_session()`; fire-and-forget `Popen(start_new_session=True, stdin/stdout/stderr=DEVNULL)`. No env passed today; Codex equivalent needs the same detached-spawn semantics
- `scripts/little_loops/fsm/evaluators.py:609` — LLM-graded evaluator. Uses Claude-specific `--json-schema`, `--model`, `--no-session-persistence` flags — these will require explicit capability gating (Codex may lack `--json-schema`)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/runners.py:20` — imports `run_claude_command` from `subprocess_utils`; the FSM executor's `DefaultActionRunner.run()` delegates to it. Will continue to work via the alias after refactor but must be verified against the new host-runner path. [Agent 1 finding]
- `scripts/little_loops/issue_manager.py:38,45` — imports `run_claude_command` (and other utils) from `subprocess_utils`; `AutoManager` calls it for sequential issue processing. Same alias continuity applies. [Agent 1 finding]
- `scripts/little_loops/cli/generate_skill_descriptions.py:91` — imports `run_claude_command` dynamically; generates skill descriptions by invoking Claude directly. Same alias path as above. [Agent 1 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Per-call-site argv profile differs significantly** — `build_invocation()` cannot be a one-size-fits-all signature. Distinct profiles observed:

| Call site | Mode | Output format | Permissions | Other flags |
|-----------|------|---------------|-------------|-------------|
| `run_claude_command` | streaming | `stream-json` | `--dangerously-skip-permissions` | `-p`, `--verbose`, optional `--continue`, `--agent`, `--tools` |
| `_detect_worktree_model_via_api` | blocking probe | `json` | none | `-p` only |
| `cmd_capabilities` | version probe | none | none | `--version` |
| `_spawn_new_claude_session` | fire-and-forget Popen | none | none | `-p` only |
| LLM-graded evaluator | blocking | `json` | `--dangerously-skip-permissions` | `-p`, `--json-schema`, `--model`, `--no-session-persistence` |

Recommend `HostInvocation` carry an explicit `profile: Literal["streaming", "blocking_json", "version_probe", "detached"]` alongside `binary`/`args`/`env`, or split `build_invocation()` into purpose-specific methods (`build_streaming`, `build_blocking`, `build_version_check`, `build_detached`). The current single-method Proposed Solution undercounts the per-site variance.

**No call site currently reads `LL_HOOK_HOST`** — confirmed via grep. `LL_HOOK_HOST` is read only in `scripts/little_loops/config/core.py:108` (`resolve_config_path`) and `scripts/little_loops/hooks/__init__.py:104` (`main_hooks`). The orchestration layer is fully disconnected from the hook-layer host signal — closing this gap is the central work of this issue.

**Worker-pool layering nuance** — `parallel/worker_pool.py` imports `run_claude_command` as `_run_claude_base` for the actual work loop, but `_detect_worktree_model_via_api` (the line-584 call site) bypasses `subprocess_utils` entirely. After refactor, the model-detect path must also route through `host_runner` — otherwise the grep AC fails.

### New Files

- `scripts/little_loops/host_runner.py` — Protocol + registry + per-host implementations
- `scripts/tests/test_host_runner.py` — detection precedence, capability gating, flag translation snapshots
- `docs/reference/HOST_COMPATIBILITY.md` — extend the matrix added by FEAT-957 with an "Orchestration CLI" row showing per-host status

### Configuration

- `config-schema.json` — add `orchestration.host_cli` enum (`"auto" | "claude-code" | "codex" | "opencode" | "pi"`); default `"auto"`. Read by `host_runner.resolve_host()` after env vars.
- **Reuse precedent**: `config-schema.json:1103` already defines `hooks.host` as `enum: ["claude-code", "opencode", "codex"]`. The new `orchestration.host_cli` enum should be a superset (adds `"auto"` and `"pi"`) and use identical host-name spellings to avoid divergence.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py` — `BRConfig._parse_config()` (line 185) and `BRConfig.to_dict()` (line 464) need a new `OrchestrationConfig` dataclass and parse call so that `orchestration.host_cli` in `ll-config.json` is actually consumed by `resolve_host()`. Without this, the config-file path is blocked even if the schema allows the key. The `_config_candidates()` docstring (line 82) flags this as the extension point. [Agent 2 finding]
- `scripts/little_loops/config/__init__.py` — re-export `OrchestrationConfig` following the same `__all__` pattern as all other config dataclasses in that module. [Agent 2 finding]
- `scripts/little_loops/__init__.py` — decide whether `HostRunner`, `HostInvocation`, `HostNotConfigured`, `CapabilityNotSupported` are lifted into the package-level `__all__` (lines 50–103). All other Protocol types (`LLExtension`, `LLHookIntentExtension`, etc.) are in `__all__`; `HostRunner` would be the first Protocol omitted if the issue's `from little_loops.host_runner import …` form is taken as canonical. Choose one form and be explicit. [Agent 2 finding]

### Tests

- `test_host_runner.py::test_detect_explicit_override` — `LL_HOST_CLI=codex` wins over installed binaries
- `test_host_runner.py::test_detect_falls_back_to_hook_host` — uses `LL_HOOK_HOST` when `LL_HOST_CLI` unset
- `test_host_runner.py::test_detect_binary_probe_order` — claude → codex → pi
- `test_host_runner.py::test_raises_when_no_host` — clear error with remediation hint
- `test_host_runner.py::test_claude_runner_matches_legacy_args` — snapshot of pre-refactor argv; regression guard against unintended flag drift
- `test_host_runner.py::test_codex_runner_flag_translation` — `--dangerously-skip-permissions` → Codex `--ask-for-approval=never` (verify against Codex docs)
- `test_host_runner.py::test_capability_warning` — requesting `--agent` under Codex emits `CapabilityNotSupported`
- Integration: update `test_subprocess_utils.py`, `test_action.py`, `test_handoff_handler.py`, `test_evaluators.py` to mock `host_runner.resolve_host` instead of patching `subprocess`/`shutil.which`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_subprocess_mocks.py` — `TestRunClaudeCommand.test_command_includes_correct_arguments()` asserts the full argv list literally as `["claude", "--dangerously-skip-permissions", ...]`. Will break post-refactor; update to assert against `ClaudeCodeRunner` output via `host_runner` mock. [Agent 3 finding]
- `scripts/tests/test_worker_pool.py` — model-detect path (`_detect_worktree_model_via_api`) patches `subprocess.run` directly; patch target must shift to the `host_runner` dispatch point after refactor. Multiple `CompletedProcess(args=["claude", "-p", ...])` constructions establish implicit argv expectations to audit. [Agent 3 finding]
- `scripts/tests/test_config_schema.py` — add `test_orchestration_in_schema()` following the existing `test_hooks_in_schema()` pattern (line 136): assert `"orchestration"` key exists, `host_cli` enum contains `["auto", "claude-code", "codex", "opencode", "pi"]`, default is `"auto"`. [Agent 3 finding]
- `scripts/tests/test_feat1462_doc_wiring.py` (new) — repo uses `test_feat*_doc_wiring.py` files to enforce doc-update acceptance criteria. Assert: `API.md` contains `host_runner` entry; `ARCHITECTURE.md` mentions `host_runner`; `HOST_COMPATIBILITY.md` has orchestration row; `TROUBLESHOOTING.md` has `HostNotConfigured` entry; `.claude/CLAUDE.md` references `LL_HOST_CLI` or `host_runner`. [Agent 2 finding]

**Snapshot-test pattern to follow**: the repo has no golden-file infrastructure. Model `test_claude_runner_matches_legacy_args` on the inline-list-comparison pattern already used by `scripts/tests/test_subprocess_mocks.py::TestRunClaudeCommand::test_command_includes_correct_arguments` (captures argv via a `capture_popen` side-effect and asserts equality against a literal list). For sparse field checks, follow `scripts/tests/test_fsm_evaluators.py:674` (index-based `--flag` + value lookups).

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Add `OrchestrationConfig` dataclass to `scripts/little_loops/config/core.py` — add a parse call in `BRConfig._parse_config()` (line 185) and a serialization entry in `BRConfig.to_dict()` (line 464), mirroring how every other config section is wired. This is required for `resolve_host()` to read `orchestration.host_cli` from `ll-config.json`.
10. Re-export `OrchestrationConfig` from `scripts/little_loops/config/__init__.py` following the pattern used for all other config dataclasses in that module.
11. Decide and document in `scripts/little_loops/__init__.py` whether `HostRunner`, `HostInvocation`, `HostNotConfigured`, `CapabilityNotSupported` are added to the package-level `__all__` — all other Protocols in the package are exported there; pick a consistent approach.
12. Update `scripts/tests/test_subprocess_mocks.py` (`TestRunClaudeCommand.test_command_includes_correct_arguments`) — argv assertion currently hardcodes `["claude", ...]`; must be updated to patch `host_runner.resolve_host` and assert against `ClaudeCodeRunner`-produced output.
13. Update `scripts/tests/test_worker_pool.py` — shift the `_detect_worktree_model_via_api` mock target from `subprocess.run` to the `host_runner` dispatch point; audit `CompletedProcess(args=["claude", ...])` fixture objects for implicit expectations.
14. Add `test_orchestration_in_schema()` to `scripts/tests/test_config_schema.py` — following the `test_hooks_in_schema()` pattern to assert the new `orchestration.host_cli` schema structure.
15. Create `scripts/tests/test_feat1462_doc_wiring.py` — per repo convention, assert all four doc files and `.claude/CLAUDE.md` contain the required references after implementation.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-15_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 55/100 → LOW

### Outcome Risk Factors
- **Wide file surface despite local depth** — 20 distinct change sites (call sites, config wiring, test updates, docs). Per-site changes are Local in depth but the sweep is broad; any missed file creates a gap in the "no hard-coded claude literals" AC. Mitigation: ship Step 2 (ClaudeCodeRunner only) as a standalone PR with the verification grep as a CI gate before adding host-specific runners.
- **build_invocation() API shape deferred** — The signature design (optional kwargs vs purpose-specific factory methods) is left to Step 2. This decision sets the contract for all 5 call sites and test mocks. Resolve it before writing callers to avoid a second pass; split factory methods are recommended given the per-site profile table.
- **Test mock target migration required** — test_subprocess_mocks.py, test_worker_pool.py, and test_action.py currently patch subprocess.run/shutil.which directly. After refactor the patch targets shift to host_runner.resolve_host; easy to leave a phantom passing test by patching the wrong level.
- **CodexRunner gated on external research** — Step 3 cannot start until Codex headless-mode research (Step 1) confirms the flag translation table. The Step 2 PR is unblocked, but the full feature acceptance criteria require Codex flag verification.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-15
- **Reason**: Issue too large for single session

### Decomposed Into
- FEAT-1464: Scaffold host_runner.py + ClaudeCodeRunner + call site migrations + config wiring
- FEAT-1465: Codex research + CodexRunner flag translation
- FEAT-1466: OpenCodeRunner, PiRunner stub, docs sweep, HOST_COMPATIBILITY.md, doc wiring tests

## Session Log
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d0a84cca-2574-4c32-8edd-684205b8feb0.jsonl`
- `/ll:confidence-check` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfeb6eaa-4ec1-44a2-8e9b-cc6bfe2f5b09.jsonl`
- `/ll:wire-issue` - 2026-05-15T12:33:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1ac47014-a10c-4639-9aeb-49f711f8b333.jsonl`
- `/ll:refine-issue` - 2026-05-15T12:28:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7f8b027f-820b-4c3e-a9e3-de1673eb0241.jsonl`
- `/ll:format-issue` - 2026-05-15T12:23:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4689ac73-1c8c-466a-9a6f-710fdc35baef.jsonl`

- manual-review - 2026-05-15T00:00:00 - Filed during cross-compat readiness review of FEAT-957 / FEAT-992; identified six hard-coded `claude` call sites in scripts/little_loops/ that block real cross-host operation.

---

## Scope Boundary

**Note**: This issue addresses the **orchestration layer** only (`ll-auto`, `ll-parallel`, `ll-action`, `ll-loop`, FSM evaluators, FSM handoff). The **hook layer** is already abstracted by FEAT-1116 and per-host adapters under `hooks/adapters/`. Do not conflate the two — `host_runner` is for outbound subprocess calls *from* ll to the host CLI; the hook adapters are for inbound events *from* the host CLI to ll.

**Note**: Slash-command and skill content discovery is NOT in scope. Codex reads `.codex/prompts/`, OpenCode has its own conventions; mirroring `.claude/commands/` and `.claude/skills/` to host-native locations is a separate concern (no issue filed yet — capture if user demand surfaces).

**Note**: This is a **Host Adapter** complement, NOT an Extension in the FEAT-917 sense. No PyPI manifest, no `ll extensions` discovery.
