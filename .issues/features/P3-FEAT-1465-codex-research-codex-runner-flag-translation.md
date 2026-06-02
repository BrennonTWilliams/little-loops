---
id: FEAT-1465
type: FEAT
priority: P3
status: done
parent: FEAT-1462
depends_on: FEAT-1464
discovered_date: 2026-05-15
completed_at: 2026-05-15T15:03:26Z
discovered_by: issue-size-review
confidence_score: 98
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# FEAT-1465: Codex Research + CodexRunner Flag Translation

## Summary

Research Codex CLI's headless-mode invocation contract, then implement `CodexRunner` with a verified flag translation table. Gated behind `LL_HOST_CLI=codex` until manually tested. Depends on FEAT-1464 (the `host_runner.py` scaffold must exist first).

## Parent Issue

Decomposed from FEAT-1462: Abstract Host CLI Invocation in Orchestration Layer

## Scope

Covers Implementation Steps 1 and 3 from the parent issue.

**Explicitly out of scope**: OpenCodeRunner, PiRunner, HOST_COMPATIBILITY.md docs row, doc-wiring tests (those land in FEAT-1466).

## Acceptance Criteria

- [ ] Codex headless-mode invocation contract documented in the issue (or in a `thoughts/` doc): `exec`/`-p` equivalent, output format, flag for permission skip, agent selection, tool allowlist
- [ ] `CodexRunner` added to `host_runner.py` with flag translation table per the research findings
- [ ] `CodexRunner.detect()` returns `True` when `codex` is on PATH
- [ ] `--dangerously-skip-permissions` translates to the correct Codex approval flag (e.g. `--ask-for-approval=never` — verify against Codex docs)
- [ ] Requesting `--agent` (agent selection) under Codex emits `CapabilityNotSupported` if Codex lacks this flag
- [ ] `test_host_runner.py::test_codex_runner_flag_translation` covers the translation table with snapshot assertions
- [ ] `test_host_runner.py::test_capability_warning` verifies `CapabilityNotSupported` emission for unsupported flags
- [ ] `CodexRunner` gated behind `LL_HOST_CLI=codex` in detection order until validated in production usage

## Research Task (Step 1)

Before writing code, confirm:

1. Codex's headless/non-interactive invocation command (`codex exec <prompt>`? `codex -p <prompt>`?)
2. Output format options (does Codex support `--output-format json`? Or line-delimited?)
3. Permission/approval flag (equivalent to `--dangerously-skip-permissions`)
4. Whether Codex supports agent selection (`--agent`) and tool allowlist (`--tools`)
5. Session persistence flags (`--no-session-persistence` equivalent, if any)
6. `--json-schema` flag for structured output (used by LLM-graded evaluator) — if absent, document as `CapabilityNotSupported`

Use the FEAT-957 cross-compat scope boundary notes and any existing Codex adapter code in `hooks/adapters/codex/` as a starting point.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**What's already known about Codex in this repo:**
- Binary name is `codex`; detection should use `shutil.which("codex")`.
- Host-identification env var pattern: `LL_HOOK_HOST=codex` (set in `hooks/adapters/codex/session-start.sh` and `pre-compact.sh`).
- The README at `hooks/adapters/codex/README.md` documents only hook-channel behavior (event names, stdin payload shape, exit-code semantics, trust model). It does NOT document headless invocation flags — those are the FEAT-1465 research items.
- `permission_mode` enum (from FEAT-957 / hook layer): `"default"`, `"acceptEdits"`, `"plan"`, `"dontAsk"`, `"bypassPermissions"`. Note that this is the hook-side permission model; the headless-CLI approval flag (`--ask-for-approval=…`) is a separate concept that still needs verification.

**Authoritative external sources for the research task:**
- `codex --help` and `codex exec --help` on the installed binary (primary source).
- OpenAI Codex CLI GitHub repo / docs for `exec` subcommand, `--ask-for-approval`, output formats, and model flag names.
- Existing GA Codex CLI version is Rust-based; previous Node-based Codex (deprecated) had different flags — verify against the current `codex` binary, not stale docs.

**Research deliverable:** capture findings in `thoughts/research/codex-headless-invocation.md` (preferred) or inline in this issue's Proposed Solution table. Each row of the translation table must cite the source (e.g. `codex exec --help` output, doc URL with commit/version).

## Proposed Solution

### Flag translation table (draft — verify via research)

| Claude Code flag | Codex equivalent | Notes |
|-----------------|-----------------|-------|
| `claude -p <prompt>` | `codex exec <prompt>` | Headless mode; confirm syntax |
| `--output-format stream-json` | TBD | May need capability gate |
| `--output-format json` | TBD | Blocking JSON mode |
| `--dangerously-skip-permissions` | TBD (e.g. `--ask-for-approval=never`) | Confirm from Codex docs |
| `--agent <name>` | N/A → `CapabilityNotSupported` | Codex uses different agent model |
| `--tools <list>` | TBD | May map to Codex tool config |
| `--verbose` | TBD | May be omitted or have equivalent |
| `--model <id>` | TBD | Confirm Codex model flag name |
| `--json-schema <schema>` | N/A → `CapabilityNotSupported` | If absent from Codex, evaluator must degrade |
| `--no-session-persistence` | TBD | Confirm |
| `--version` | `codex --version` (likely) | Preflight check |

### CodexRunner shape

```python
class CodexRunner:
    name = "codex"

    def detect(self) -> bool:
        return shutil.which("codex") is not None

    def build_streaming(self, *, prompt, working_dir, resume, agent, tools) -> HostInvocation:
        # translate flags per table above
        ...

    def build_blocking_json(self, *, prompt, model, json_schema) -> HostInvocation:
        # json_schema → CapabilityNotSupported if Codex lacks --json-schema
        ...

    def build_version_check(self) -> HostInvocation:
        return HostInvocation(binary="codex", args=["--version"], env={}, ...)

    def build_detached(self, *, prompt) -> HostInvocation:
        ...
```

### Codebase Research Findings — Implementation Pattern

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Authoritative pattern**: `scripts/little_loops/host_runner.py::ClaudeCodeRunner` (full class). `CodexRunner` mirrors its structure exactly; only flag-translation bodies differ. Key facts to honor:

1. **`name`** is a class attribute (str), not an instance attribute. `ClaudeCodeRunner.name = "claude-code"` → `CodexRunner.name = "codex"`.
2. **`capabilities`** is a class attribute holding a `HostCapabilities` instance. Set per Codex research findings — likely:
   - `streaming=<True if Codex has stream-json equivalent, else False>`
   - `permission_skip=True` (assuming `--ask-for-approval=never` exists)
   - `agent_select=False` (per issue assumption — verify)
   - `tool_allowlist=<TBD per research>`
3. **`HostInvocation` is `frozen=True`**. Return a new instance per build call — never mutate. Fields: `binary: str`, `args: list[str]`, `env: dict[str, str] = {}`, `capabilities: HostCapabilities`.
4. **`build_streaming` signature** is fixed by the Protocol:
   `(*, prompt: str, working_dir: Path | None = None, resume: bool = False, agent: str | None = None, tools: list[str] | None = None)`. Keyword-only, exactly these names.
5. **`build_blocking_json` signature**: `(*, prompt: str, model: str | None = None, json_schema: dict | None = None)`. Even unsupported params (e.g. `json_schema`) must be accepted to satisfy the Protocol — drop or warn, never raise `TypeError`.
6. **Worktree GIT_DIR resolution**: `ClaudeCodeRunner.build_streaming` reads `<working_dir>/.git` and, if it's a file starting with `"gitdir: "`, resolves it and sets `GIT_DIR` + `GIT_WORK_TREE` in `env`. If Codex also runs inside ll-parallel worktrees, replicate this block (`host_runner.py` lines in the existing `ClaudeCodeRunner.build_streaming` method are the template).
7. **`CapabilityNotSupported` emission convention**: It is a `UserWarning` subclass, NOT raised as an exception. The existing precedent is `warnings.warn("…message…", CapabilityNotSupported, stacklevel=2)`. Note that `ClaudeCodeRunner.build_blocking_json` silently drops `json_schema` with `_ = json_schema` — but the FEAT-1465 acceptance criterion explicitly requires CodexRunner to emit the warning, so emit it from inside the `CodexRunner.build_*` method when an unsupported kwarg is non-None. This is a deliberate divergence from `ClaudeCodeRunner` (which assumes its caller handles the warning) and should be commented as such.

### Codebase Research Findings — Registry & Probe Wiring

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `_PROBE_ORDER` in `host_runner.py` **already contains** `("codex", "codex")` (slot pre-reserved). No edit needed there.
- `_HOST_RUNNER_REGISTRY` currently has only `{"claude-code": ClaudeCodeRunner}`. CodexRunner must be added under key `"codex"`.
- **Gating**: the AC requires gating behind `LL_HOST_CLI=codex` "until validated in production". Implementation options:
  - Add `CodexRunner` to `_HOST_RUNNER_REGISTRY` and rely on the `LL_HOST_CLI` explicit-override path (`resolve_host` already prefers `LL_HOST_CLI` over probe order). Auto-probe via `_PROBE_ORDER` would then also pick Codex if `codex` is on PATH and `claude` is not — which may be undesirable. Mitigation: temporarily comment out the `("codex", "codex")` entry in `_PROBE_ORDER` until validated, OR add a guard in `resolve_host` that skips Codex auto-probe unless an opt-in env var is set.
  - Document the chosen gating mechanism in the issue before implementation. (Recommendation: keep registry entry, comment out probe row, leaving explicit `LL_HOST_CLI=codex` as the only activation path.)

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py` — add `CodexRunner` class (after `ClaudeCodeRunner`), register in `_HOST_RUNNER_REGISTRY`, decide on `_PROBE_ORDER` gating (see Registry & Probe Wiring above), update module `__all__` to export `CodexRunner`.
- `scripts/tests/test_host_runner.py` — add `TestCodexRunner` class with snapshot + capability-warning tests (see Test Patterns below).

### Files NOT to Modify (out of scope per issue)

- `scripts/little_loops/__init__.py` — top-level package re-exports (`CapabilityNotSupported`, `HostInvocation`, `HostNotConfigured`, `HostRunner` already exported; `ClaudeCodeRunner` is NOT re-exported, so `CodexRunner` shouldn't be either — keep symmetry).
- Existing call sites: `scripts/little_loops/cli/action.py`, `scripts/little_loops/parallel/worker_pool.py`, `scripts/little_loops/fsm/handoff_handler.py`, `scripts/little_loops/fsm/evaluators.py` — all already route through `resolve_host()` and will pick up CodexRunner automatically via the registry. No call-site changes in this issue.
- `scripts/little_loops/fsm/runners.py` — still builds `claude` argv inline; migrating it is FEAT-1469's scope, not FEAT-1465.
- `docs/reference/HOST_COMPATIBILITY.md` — orchestration row updates land in FEAT-1466 per scope boundary.

### Dependent Files (Callers — for context, not modification)

- `scripts/little_loops/cli/action.py::cmd_capabilities` — calls `resolve_host()` then `runner.detect()` and `runner.build_version_check()`. Codex will flow through this automatically.
- `scripts/little_loops/fsm/evaluators.py::evaluate_llm_structured` — calls `resolve_host().build_blocking_json(...)` then appends `--json-schema` and `--no-session-persistence` manually. If `CodexRunner.build_blocking_json` emits `CapabilityNotSupported` for `json_schema`, this call site will surface the warning under Codex — verify the warning is informational (not error-escalated) in this path.
- `scripts/little_loops/parallel/worker_pool.py` — uses `build_blocking_json(...)` for model detection then strips `--dangerously-skip-permissions`. Codex equivalent of that flag (per research) will end up stripped here too — confirm this is acceptable (it should be; the strip removes flags meant for real runs, not detection).
- `scripts/little_loops/fsm/handoff_handler.py::HandoffHandler._spawn_continuation` — uses `build_detached(...)` and strips `--dangerously-skip-permissions`. Same note as above.

### Test Patterns to Mirror

From `scripts/tests/test_host_runner.py::TestClaudeCodeRunner`:

- **Snapshot test** — `test_claude_runner_matches_legacy_args` uses inline-list equality:
  `assert [invocation.binary, *invocation.args] == ["claude", "--dangerously-skip-permissions", ...]`
  Replicate for `test_codex_runner_flag_translation` with the verified Codex argv.
- **Optional-flag tests** — `test_build_streaming_includes_resume_flag`, `test_build_streaming_includes_agent_and_tools` — replicate per Codex capabilities (skip the agent test if `agent_select=False`).
- **Version check** — `test_build_version_check` pattern: `assert invocation.args == ["--version"]`.
- **Protocol conformance** — `test_satisfies_host_runner_protocol`: `assert isinstance(CodexRunner(), HostRunner)`.
- **Capability warning** — `TestCapabilityWarning.test_capability_warning` shows the `pytest.warns(CapabilityNotSupported, match="...")` pattern. For CodexRunner: wrap a `runner.build_streaming(prompt="x", agent="some-agent")` call in `pytest.warns` and assert the warning fires.
- **`isolated_env` fixture** — `monkeypatch.delenv("LL_HOST_CLI", ...)` and `LL_HOOK_HOST`. Reuse for any test that touches `resolve_host` from `TestCodexRunner`.
- **Registry-injection precedent** — `TestResolveHost.test_explicit_override_beats_hook_host` shows the pattern of mutating `_HOST_RUNNER_REGISTRY` and restoring in `finally`. Once `CodexRunner` is in the registry permanently, this manual injection is no longer needed for production tests — but the pattern is the template for any temporary stub.

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**New tests to add to `TestCodexRunner`:**
- `test_codex_runner_registered` — `assert "codex" in hr._HOST_RUNNER_REGISTRY` (no analog exists for `ClaudeCodeRunner`; verifies the registry wiring step was completed) [Agent 1 + 3 finding]
- `test_resolve_host_picks_codex_via_env` — `resolve_host(env={"LL_HOST_CLI": "codex"})` returns a `CodexRunner` instance (complements `test_explicit_override_beats_hook_host` below; uses `isolated_env` fixture) [Agent 3 finding]
- `test_build_blocking_json_emits_warning_for_json_schema` — `pytest.warns(CapabilityNotSupported)` wrapping `runner.build_blocking_json(prompt="x", json_schema={...})`; verifies both the warning and that no `TypeError` is raised [Agent 3 finding]

**Existing test to update:**
- `TestResolveHost.test_explicit_override_beats_hook_host` — currently injects a `FakeCodex` stub via manual `_HOST_RUNNER_REGISTRY` mutation + `try/finally` restore (because `"codex"` wasn't in the registry when the test was written). Once `CodexRunner` is permanently registered, this scaffolding is obsolete; rewrite to call `resolve_host(env={"LL_HOST_CLI": "codex"})` directly and assert `isinstance(runner, CodexRunner)` [Agent 2 + 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

(Note: `docs/reference/HOST_COMPATIBILITY.md` is explicitly out of scope per FEAT-1466. The items below are **inline code comments** in arch/contributing docs — separate from the HOST_COMPATIBILITY orchestration rows.)

- `docs/ARCHITECTURE.md` — file-tree inline comment reads `# Host CLI abstraction (HostRunner Protocol + ClaudeCodeRunner)`; update to add `CodexRunner` [Agent 2 finding]
- `CONTRIBUTING.md` — same inline comment as `docs/ARCHITECTURE.md` file-tree entry; update in parallel [Agent 2 finding]
- `docs/reference/API.md` — module table row for `little_loops.host_runner` reads `HostRunner Protocol + ClaudeCodeRunner`; update to include `CodexRunner` [Agent 2 finding]

## Implementation Steps

1. **Research phase** — run `codex exec --help` (and `codex --help`) on the installed binary; verify each cell in the flag-translation table; record source citations. Capture in this issue's Proposed Solution table or `thoughts/research/codex-headless-invocation.md`.
2. **Add `CodexRunner` class** to `scripts/little_loops/host_runner.py` immediately after `ClaudeCodeRunner` (line ordering: helpers → dataclasses → `ClaudeCodeRunner` → `CodexRunner` → `_HOST_RUNNER_REGISTRY` → `resolve_host`). Mirror `ClaudeCodeRunner` structure; differ only in `name`, `capabilities`, and per-method flag construction.
3. **Wire registry** — add `"codex": CodexRunner` to `_HOST_RUNNER_REGISTRY`. Decide on `_PROBE_ORDER` gating per the Registry & Probe Wiring research finding above; the recommendation is to comment out the probe row until validated.
4. **Add tests** — extend `scripts/tests/test_host_runner.py` with a `TestCodexRunner` class mirroring `TestClaudeCodeRunner`. Required tests per AC: `test_codex_runner_flag_translation` (snapshot), `test_capability_warning` (verifies `CapabilityNotSupported` emission for `agent=` and `json_schema=`).
5. **Verify** — `python -m pytest scripts/tests/test_host_runner.py -v`. Also run `python -m mypy scripts/little_loops/host_runner.py` and `ruff check scripts/little_loops/host_runner.py`.
6. **Manual smoke** (gated) — with `codex` installed, set `LL_HOST_CLI=codex` and run `python -m little_loops.cli.action capabilities` to confirm `runner.build_version_check()` produces a working argv.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `TestResolveHost.test_explicit_override_beats_hook_host` in `scripts/tests/test_host_runner.py` — replace the `FakeCodex` stub + manual registry inject/restore with a direct `resolve_host(env={"LL_HOST_CLI": "codex"})` call and `isinstance(runner, CodexRunner)` assertion; the manual scaffolding was only needed because `"codex"` wasn't in `_HOST_RUNNER_REGISTRY` yet
8. Add `test_codex_runner_registered`, `test_resolve_host_picks_codex_via_env`, and `test_build_blocking_json_emits_warning_for_json_schema` to `TestCodexRunner` in `scripts/tests/test_host_runner.py` (see Tests subsection in Integration Map for exact patterns)
9. Update inline file-tree comments in `docs/ARCHITECTURE.md` and `CONTRIBUTING.md`: `# Host CLI abstraction (HostRunner Protocol + ClaudeCodeRunner)` → include `CodexRunner`; update module table row in `docs/reference/API.md` accordingly

## Dependencies

- **FEAT-1464** must land first (provides `host_runner.py` scaffold, `HostRunner` Protocol, `CapabilityNotSupported`)
- Can run in parallel with **FEAT-1466**

## Resolution

Implemented `CodexRunner` in `scripts/little_loops/host_runner.py` with verified flag translation per `thoughts/research/codex-headless-invocation.md`. Key decisions:

- **Headless invocation**: `codex exec <prompt>` (positional prompt; Codex's `-p` is `--profile`, not a prompt flag).
- **Permission bypass**: `--dangerously-bypass-approvals-and-sandbox` (semantically identical to Claude's `--dangerously-skip-permissions` — skips both approval and sandbox).
- **JSON output**: `--json` (NDJSON events; Codex has no single-blob JSON mode, so `build_blocking_json` also uses `--json` and callers consume the last event).
- **Resume**: restructures the subcommand to `codex exec resume --last <prompt>` per the Codex CLI reference.
- **Capabilities**: `streaming=True`, `permission_skip=True`, `agent_select=False`, `tool_allowlist=False`.
- **Unsupported flags** emit `CapabilityNotSupported` (deliberate divergence from `ClaudeCodeRunner` which silently drops unsupported params): `agent=`, `tools=`, and `json_schema=` (Codex `--output-schema` requires a file path, not an inline dict — possible future enhancement).
- **Gating**: registered in `_HOST_RUNNER_REGISTRY` but commented out of `_PROBE_ORDER` so only explicit `LL_HOST_CLI=codex` activates the runner until validated in production.

Updated `TestResolveHost.test_explicit_override_beats_hook_host` to use the real registry entry instead of the previous `FakeCodex` stub. Updated inline file-tree comments in `docs/ARCHITECTURE.md`, `CONTRIBUTING.md`, and the module table row in `docs/reference/API.md`.

29 host_runner tests pass; ruff and mypy on `host_runner.py` are clean. Codex binary not installed on dev host — the manual smoke step (`LL_HOST_CLI=codex python -m little_loops.cli.action capabilities`) is deferred until the binary is available for validation.

## Session Log
- `/ll:manage-issue` - 2026-05-15T15:03:26Z - `31f67c36-6bf8-4761-8505-85b5d934eabe.jsonl`
- `/ll:wire-issue` - 2026-05-15T14:52:04 - `f0da2172-e051-457f-b0f8-7021ec71c498.jsonl`
- `/ll:refine-issue` - 2026-05-15T14:47:24 - `aa72745d-9e6c-4cfa-b332-1e312570af5e.jsonl`
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `d0a84cca-2574-4c32-8edd-684205b8feb0.jsonl`
- `/ll:confidence-check` - 2026-05-15T15:30:00 - `8c130538-448f-4a14-b582-00eacc6f40d9.jsonl`
