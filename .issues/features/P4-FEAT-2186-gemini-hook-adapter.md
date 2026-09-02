---
id: FEAT-2186
title: "Hook adapter \u2014 hooks/adapters/gemini/ translating gemini-cli events to\
  \ LLHookEvent"
type: feature
status: open
priority: P4
parent: EPIC-2178
decision_needed: false
decision_ref: ARCHITECTURE-046
verify_verdict: VALID
captured_at: '2026-06-15T00:00:00Z'
discovered_date: 2026-06-15
discovered_by: capture-issue
labels:
- gemini
- host-compat
- hooks
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-2186: Hook adapter — hooks/adapters/gemini/

## Summary

Create `hooks/adapters/gemini/` with adapter scripts that translate gemini-cli
lifecycle events into `LLHookEvent` format and invoke the ll hook handler.
Analogous to `hooks/adapters/codex/` and `hooks/adapters/claude-code/`.

## Current Behavior

Gemini CLI users have no hook adapter. None of the ll hook intents
(`session_start`, `pre_compact`, `pre_tool_use`, `post_tool_use`, etc.) fire
during Gemini lifecycle events, so history capture, context injection, and tool
auditing are unavailable when little-loops runs under Gemini. Only
`hooks/adapters/codex/`, `hooks/adapters/claude-code/`, and
`hooks/adapters/opencode/` exist; `hooks/adapters/gemini/` does not.

## Expected Behavior

`hooks/adapters/gemini/` exists with adapter scripts that mirror the Codex and
Claude Code adapters. Gemini lifecycle events (`SessionStart`, `PreCompress`,
`BeforeTool`, `AfterTool`, etc.) are translated into `LLHookEvent` format and
dispatched to the host-agnostic ll hook handler, so history capture, context
injection, and tool auditing behave the same as under Claude Code. Users
activate the adapter via `ll:configure --gemini`, which injects the hook entries
into `.gemini/settings.json`.

## Motivation

Gemini is one of the four hosts targeted by the host-compatibility epic
(EPIC-2178). Without the hook adapter, a Gemini user gets none of little-loops'
lifecycle automation — the analytics, history, and context-injection features
silently no-op. The adapter is the bridge that makes ll's host-agnostic hook
handler reachable from Gemini, bringing Gemini to parity with Codex and Claude
Code. The work is low-risk and additive: Gemini's stdin/stdout JSON hook
protocol is identical to Claude Code's, so the existing handler is reused as-is.

## Decision — RATIFIED 2026-06-24 (Option A; see ARCHITECTURE-046)

**Resolved: Option A** — inject hook entries into `.gemini/settings.json` via
`ll:configure --gemini`. Lower complexity, mirrors the existing
`hooks/adapters/claude-code/` pattern, and the ll hook handler is already
host-agnostic. Extension packaging (Option B) is deferred to a separate
enhancement if extension-based distribution is later wanted. The original
decision framing is preserved below for context.

Gemini hooks can be registered in two ways (FEAT-2179):
- **Option A**: Inject entries into `.gemini/settings.json` under `hooks:` — user
  activates by running `ll:configure --gemini` which patches their local
  `settings.json`.
- **Option B**: Package hooks as a Gemini Extension (`~/.gemini/extensions/ll/`)
  with a `gemini-extension.json` manifest — user installs the extension once.

`hooks migrate --from-claude` exists but migrates Claude Code hooks, not ll hooks.

**Option A is recommended**: lower complexity, same pattern as the Claude Code
adapter (`hooks/adapters/claude-code/`), and the ll hook handler is already
host-agnostic. Extension packaging (Option B) is a separate enhancement.

## Use Case

A Gemini user installs little-loops. `session_start`, `pre_compact`, `pre_tool_use`,
and `post_tool_use` ll hook intents fire when Gemini lifecycle events occur —
enabling history capture, context injection, and tool auditing.

## Event Mapping (from FEAT-2179)

| Gemini event | ll intent |
|-------------|-----------|
| `SessionStart` | `session_start` |
| `PreCompress` | `pre_compact` |
| `BeforeAgent` | `user_prompt_submit` |
| `BeforeTool` | `pre_tool_use` |
| `AfterTool` | `post_tool_use` |
| `SessionEnd` | `session_end` |

New events with no current ll intent (not wired in this issue):
`AfterAgent`, `BeforeModel`, `AfterModel`, `BeforeToolSelection`, `Notification`.

Protocol: stdin/stdout JSON — identical to Claude Code hooks. `CLAUDE_PROJECT_DIR`
alias is provided by Gemini for compatibility.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/cli.py` — add `"gemini"` to the `_KNOWN_HOSTS`
  frozenset (currently `{"claude-code", "codex", "opencode", "pi", "kimi-code",
  "qwen", "omp"}`, line 48-50) and a `gemini` branch in
  `_dispatch_host_adapters()` (lines 94-216) that calls `install_gemini_adapter()`;
  remove/update the comment at lines 41-47 stating Gemini has no install wiring.
- `scripts/little_loops/init/writers.py` — add `install_gemini_adapter()`,
  following `install_qwen_adapter`'s JSON-merge pattern (line 896) for
  `.gemini/settings.json` (see Implementation Step 8).

### New Files
- See [API/Interface § New Files](#apiinterface) for the full list of adapter
  scripts, `hooks.json`, `README.md`, and the test module.

### Dependent Files (Callers/Importers)
- The host-agnostic ll hook handler invoked by the adapter scripts — reused
  unchanged (`scripts/little_loops/hooks/`, entrypoint
  `python -m little_loops.hooks <intent>` → `main_hooks()`).
- `main_hooks()`'s `_dispatch_table()` (`scripts/little_loops/hooks/__init__.py`)
  only accepts existing ll intent names (`session_start`, `pre_compact`,
  `user_prompt_submit`, `pre_tool_use`, `post_tool_use`, `session_end`) — the
  Gemini→ll event-name translation happens entirely inside the adapter shell
  scripts, not in the handler.
- `_dispatch_host_adapters()` (`scripts/little_loops/init/cli.py`) — new caller
  of `install_gemini_adapter()` at install time.

### Similar Patterns
- `scripts/little_loops/hooks/adapters/codex/` — closest pattern for the
  adapter shell scripts + `hooks.json` shape (event→intent mapping); the
  runnable code lives under `scripts/little_loops/hooks/adapters/<host>/`, not
  the top-level `hooks/adapters/<host>/` (which holds only the docs-only
  README for codex/kimi/qwen/omp).
- `install_qwen_adapter` (`scripts/little_loops/init/writers.py:896`) — closest
  precedent for this issue's ratified Option A JSON-injection mechanism into
  `.gemini/settings.json`: managed entries identified by an `"ll:"`-prefixed
  `name` and an `"ll-gen:{{LL_GEN_VERSION}}"` stamp in `description`, since
  JSON has no comment syntax for markers (unlike Kimi's TOML comment-marker
  approach).
- `hooks/adapters/claude-code/` — alternate reference; same stdin/stdout JSON
  protocol Gemini uses.

### Tests
- `scripts/tests/test_gemini_adapter.py` — new; assert event→intent mapping and
  that each adapter script dispatches the correct `LLHookEvent`. Follow the
  existing per-host pattern: declare its own `ADAPTER_DIR` (pointing at
  `scripts/little_loops/hooks/adapters/gemini/`) and `EXPECTED_SHIMS`
  constants plus a `TestGeminiAdapterSentinels` + `TestGeminiAdapterIntegration`
  class split — each of `test_codex_adapter.py`, `test_kimi_adapter.py`,
  `test_qwen_adapter.py`, `test_omp_adapter.py`, `test_claude_code_adapter.py`,
  and `test_opencode_adapter.py` declares its own independently; there is no
  shared fixture/helper module to import from.

### Documentation
- `hooks/adapters/gemini/README.md` — installation instructions + event mapping.
- `docs/reference/HOST_COMPATIBILITY.md` — note Gemini hook support once landed.

### Configuration
- `.gemini/settings.json` — user-local file patched by `install_gemini_adapter()`
  via `ll-init --hosts gemini` (not `ll:configure`, which has no host/adapter
  wiring).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-02 — based on codebase analysis:_

- Runnable adapter files for existing hosts live under `scripts/little_loops/hooks/adapters/<host>/` (codex, kimi, qwen, omp), NOT the top-level `hooks/adapters/<host>/` — that top-level dir holds only a docs-only `README.md` for those four hosts (confirmed via `test_codex_adapter.py:34`, `test_kimi_adapter.py`'s `ADAPTER_DIR`, `test_qwen_adapter.py:36`, `test_omp_adapter.py:33-35,100` — the latter asserts `not (REPO_ROOT / "hooks" / "adapters" / "omp" / "index.ts").exists()`). `claude-code` and `opencode` are the two exceptions that keep both code and docs at the top-level `hooks/adapters/<host>/` (`test_claude_code_adapter.py:27,29`, `test_opencode_adapter.py:32-33`). No `hooks/adapters/gemini/` or `scripts/little_loops/hooks/adapters/gemini/` exists at either location today (confirmed via repo-wide glob, both paths).
- `ll:configure` (`skills/configure/SKILL.md`) has no host or adapter awareness at all — 0 hits for `host`, `adapter`, or `gemini` in that file. The actual mechanism every other host uses to install its adapter is `ll-init --hosts <host>` → `_dispatch_host_adapters()` (`scripts/little_loops/init/cli.py:94-216`), an if/elif chain gated by the `_KNOWN_HOSTS` frozenset (`cli.py:48-50`, currently `{"claude-code", "codex", "opencode", "pi", "kimi-code", "qwen", "omp"}` — no `"gemini"`), which calls `install_codex_adapter`/`install_kimi_adapter`/`install_qwen_adapter` (all in `scripts/little_loops/init/writers.py`). The comment at `cli.py:41-47` states gemini is "deliberately absent because it has no install wiring and would warn 'Unknown host'."
- The `.gemini/ll-config.json` config-dir probe is already implemented (prior/separate issue, ENH-2187) — `GEMINI_CONFIG_DIR = ".gemini"` and the `host == "gemini"` branch in `_config_candidates()` (`scripts/little_loops/config/core.py:56,144-145`) already exist and require no change for this issue.
- The closest existing precedent for this issue's ratified Option A (inject managed hook entries into a JSON settings file the host itself owns, with no comment syntax available for markers) is `install_qwen_adapter` (`scripts/little_loops/init/writers.py:896`), which performs a structured JSON merge into `.qwen/settings.json`: managed hook entries are identified by an `"ll:"`-prefixed `name` field (`_QWEN_MANAGED_NAME_PREFIX`) and a `"ll-gen:{{LL_GEN_VERSION}}"` stamp inside each entry's `description`, rather than Kimi's comment-marker-span approach (which only works because TOML supports comments). `install_qwen_adapter`'s own docstring names this "ARCHITECTURE-046 'Option A' (settings injection) — first implementation, landed for Qwen" — the same decision ID this issue's Decision section cites.
- `LLHookEvent.host` is populated once, at dispatch time, from `os.environ.get("LL_HOOK_HOST", "claude-code")` inside `main_hooks()` (`scripts/little_loops/hooks/__init__.py`). Every existing shell-based adapter shim sets this via `export LL_HOOK_HOST=<host>` before invoking `python -m little_loops.hooks <intent>` (e.g. `scripts/little_loops/hooks/adapters/codex/session-start.sh`).
- `main_hooks()`'s `_dispatch_table()` only accepts ll-side intent names (`session_start`, `pre_compact`, `user_prompt_submit`, `pre_tool_use`, `post_tool_use`, `session_end`, etc.) — there is no `pre_compress`/`before_agent`/`before_tool`/`after_tool` intent. This issue's own Event Mapping table's translation (Gemini event name → ll intent) must happen inside the adapter's own shell scripts, exactly mirroring how Codex's `hooks.json` maps its `"PreToolUse"` key to a script that invokes the `pre_tool_use` intent.
- Fail-open/blockable-event exit-code contract already implemented host-agnostically: `pre_tool_use.py` → `learning_tests_gate.gate()` returns `LLHookResult(exit_code=2, feedback=...)` on a hard block, `exit_code=0` otherwise; `edit_batch_nudge.py:197-218` explicitly branches `if event.host == "claude-code": <emit hookSpecificOutput JSON> else: return LLHookResult(exit_code=2, feedback=_NUDGE)` with the comment "Other hosts translate exit codes; exit 2 stays their model-visible channel." A Gemini adapter lands in the non-`claude-code` branch and gets the same exit-2/stderr contract Codex and Kimi already get — no JSON `hookSpecificOutput` needed.
- Each existing per-host adapter test module (`test_codex_adapter.py`, `test_kimi_adapter.py`, `test_qwen_adapter.py`, `test_omp_adapter.py`, `test_claude_code_adapter.py`, `test_opencode_adapter.py`) independently declares its own `ADAPTER_DIR`/`EXPECTED_SHIMS` constants and a `TestXAdapterSentinels` + `TestXAdapterIntegration` two-class split — there is no shared fixture/helper module a new `test_gemini_adapter.py` would import from.

## Implementation Steps

1. Create `scripts/little_loops/hooks/adapters/gemini/` directory — this is
   where the runnable adapter code lives (per the codex/kimi/qwen/omp
   precedent), not the top-level `hooks/adapters/gemini/`.
2. Create `scripts/little_loops/hooks/adapters/gemini/hooks.json` —
   event→handler mapping for the 6 events above.
3. Create `scripts/little_loops/hooks/adapters/gemini/session-start.sh` —
   exports `LL_HOOK_HOST=gemini` and invokes
   `python -m little_loops.hooks session_start`.
4. Create `scripts/little_loops/hooks/adapters/gemini/pre-compact.sh` — wraps
   `pre_compact`.
5. Create `scripts/little_loops/hooks/adapters/gemini/pre-tool-use.sh` — wraps
   `pre_tool_use` (Gemini's `BeforeTool` event).
6. Create `scripts/little_loops/hooks/adapters/gemini/post-tool-use.sh` —
   wraps `post_tool_use` (Gemini's `AfterTool` event).
7. Create `hooks/adapters/gemini/README.md` — top-level, docs-only (mirrors
   the codex/kimi/qwen/omp split) — installation instructions and event
   mapping table.
8. Add `"gemini"` to `_KNOWN_HOSTS` and add a `gemini` branch to
   `_dispatch_host_adapters()` (`scripts/little_loops/init/cli.py`) that calls
   new `install_gemini_adapter()` (`scripts/little_loops/init/writers.py`),
   which performs a structured JSON merge into `.gemini/settings.json`
   mirroring `install_qwen_adapter`'s managed-entry pattern (`"ll:"`-prefixed
   `name` + `"ll-gen:{{LL_GEN_VERSION}}"` stamp). Users activate via
   `ll-init --hosts gemini`, not `ll:configure --gemini`.
9. Add tests in `scripts/tests/test_gemini_adapter.py`.

## Acceptance Criteria

- `scripts/little_loops/hooks/adapters/gemini/hooks.json` exists with all 6
  event mappings.
- A `SessionStart` event from Gemini triggers the `session_start` ll intent handler.
- A `BeforeTool` event triggers `pre_tool_use`.
- `hooks/adapters/gemini/README.md` documents how to activate the adapter via
  `ll-init --hosts gemini`.
- `"gemini"` is added to `_KNOWN_HOSTS` and `_dispatch_host_adapters()` wires
  `install_gemini_adapter()`.
- Tests pass.

## API/Interface

### New Files

- `hooks/adapters/gemini/hooks.json`
- `hooks/adapters/gemini/session-start.sh`
- `hooks/adapters/gemini/pre-compact.sh`
- `hooks/adapters/gemini/pre-tool-use.sh`
- `hooks/adapters/gemini/post-tool-use.sh`
- `hooks/adapters/gemini/README.md`
- `scripts/tests/test_gemini_adapter.py`

### Reference

- `hooks/adapters/codex/` — pattern to follow
- `hooks/adapters/claude-code/` — alternate reference

## Program Design

### Types

N/A — no new data shape; reuses the existing `LLHookEvent`/`LLHookResult`
dataclasses (`scripts/little_loops/hooks/types.py`) unchanged.

### Signatures

- `install_gemini_adapter(project_root: Path, plugin_root: Path, force: bool = False, dry_run: bool = False) -> bool | None`
  — same signature shape as `install_codex_adapter`/`install_kimi_adapter`/`install_qwen_adapter`
  (`scripts/little_loops/init/writers.py`); return `None` = template missing,
  `False` = already installed at current gen-version, `True` = written.
- Adapter shell scripts invoke the existing, unchanged entrypoint:
  `python -m little_loops.hooks <intent>` (`scripts/little_loops/hooks/__main__.py`
  → `main_hooks()` in `scripts/little_loops/hooks/__init__.py`).

### Call Path

Gemini native event (e.g. `BeforeTool`) → adapter shell script sets
`LL_HOOK_HOST=gemini` and pipes stdin JSON to
`python -m little_loops.hooks pre_tool_use` → `main_hooks()`
(`scripts/little_loops/hooks/__init__.py`) builds
`LLHookEvent(host="gemini", intent="pre_tool_use", ...)` →
`_dispatch_table()["pre_tool_use"]` → `pre_tool_use.handle(event)` →
`LLHookResult(exit_code=..., feedback=...)` → exit code/stderr propagated back
to Gemini via the shim's `exit $?`.

Install-time path: `ll-init --hosts gemini` → `_dispatch_host_adapters()`
(`scripts/little_loops/init/cli.py`) → (new) `install_gemini_adapter()`
(`scripts/little_loops/init/writers.py`) → renders the adapter's manifest
template, substituting `{{LL_PLUGIN_ROOT}}`/`{{LL_GEN_VERSION}}`, and merges
it into `.gemini/settings.json`.

### Decision Rules

N/A — no new decision logic. This issue is a translation/install layer; the
event→intent mapping is a fixed table (already specified above), not a
runtime classification rule, and the exit-code/fail-open contract is inherited
unchanged from the existing host-agnostic handlers.

## Impact

- **Priority**: P4 — Gemini is a later-phase host in EPIC-2178; blocked behind FEAT-2179 and ENH-2184 and not on the critical path for the primary (Claude Code / Codex) hosts.
- **Effort**: S–M (4–8 hours)
- **Risk**: Low — additive; Gemini's hook protocol is stdin/stdout JSON, same as Claude Code
- **Breaking Change**: No

## Related Key Documentation

- `thoughts/research/gemini-cli-surface.md` — FEAT-2179 research spike confirming
  the stdin/stdout JSON hook protocol.
- `docs/reference/HOST_COMPATIBILITY.md` — host capability matrix.

_Run `/ll:normalize-issues` to discover and link additional relevant docs._

---

## Verification Notes

2026-06-18 (UNSTARTED): `hooks/adapters/gemini/` directory does not exist. FEAT-2179 (research spike) is complete — `thoughts/research/gemini-cli-surface.md` exists and confirms stdin/stdout JSON hook protocol identical to Claude Code. ENH-2184 (GeminiRunner stub) not yet implemented; this issue's `depends_on` correctly captures that ordering.

- **2026-06-26** (/ll:verify-issues): Corrected Current Behavior — added `hooks/adapters/opencode/` to the list of existing adapter subdirs (previously omitted, only codex and claude-code were listed); the central claim that `hooks/adapters/gemini/` is absent remains accurate.

- **2026-08-10** (`/ll:verify-issues`): OUTDATED as of 2026-08-10: `hooks/adapters/gemini/` is still absent — the core implementation gap is real. But both blocking dependencies (FEAT-2179, ENH-2184) are now `status: done` — this issue is actually UNBLOCKED and ready to implement, not blocked as its `blocked_by`/`depends_on` fields may currently suggest. Update the blocking-dependency fields/status accordingly.

- **2026-08-12** (`/ll:verify-issues`): VALID. `depends_on: [FEAT-2179, ENH-2184]` removed — both now `status: done`, so the issue is unblocked; `hooks/adapters/gemini/` remains absent.

**Open** | Created: 2026-06-15 | Priority: P4


## Session Log
- `/ll:confidence-check` - 2026-09-02T23:03:39 - `60db1b50-fe23-47d4-8b5d-f8c0cf6ef977.jsonl`
- `/ll:reconcile-issue` - 2026-09-02T22:34:55 - `89e1b823-9c08-49e4-9fdf-cadf3dbc0d62.jsonl`
- `/ll:refine-issue` - 2026-09-02T22:23:46 - `25d94b5b-402d-469f-a07b-24795969ce49.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:57 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:25:25 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:format-issue` - 2026-06-26T23:20:04 - `9c24a548-31d7-49d9-b376-2665d69b3ab4.jsonl`
