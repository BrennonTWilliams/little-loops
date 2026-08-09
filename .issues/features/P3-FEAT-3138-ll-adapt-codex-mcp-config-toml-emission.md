---
id: FEAT-3138
title: 'll-adapt --host codex: emit MCP config TOML snippet for ll-mcp'
type: FEAT
priority: P3
status: done
discovered_date: '2026-08-09'
completed_at: '2026-08-09T09:52:30Z'
labels:
- multi-host
- mcp
parent: FEAT-3133
relates_to:
- FEAT-3128
- FEAT-3132
testable: true
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-3138: ll-adapt --host codex: emit MCP config TOML snippet for ll-mcp

## Summary

`ll-adapt --host codex` learns to emit a TOML MCP config snippet for the
`ll-mcp` server, referencing the `ll-mcp` entry point. This is the
unconditional half of FEAT-3133's scope — Codex TOML emission is in scope
regardless of whether a Claude Code `.mcp.json` emitter (FEAT-3139) is
built.

## Use Case

A developer runs `ll-adapt --host codex --apply` in a project that has
`ll-mcp` installed. Today the command bridges skills, commands, and agent
personas into Codex but leaves MCP wiring to be hand-authored. After this
issue, the same invocation also writes a TOML snippet registering the
`ll-mcp` server, so Codex can discover and call it without manual config
editing.

## Current Behavior

`ll-adapt --host codex` emits skills, commands, and agent personas for
Codex but has no `emit_mcp_config` method or dispatch path — there is no
mechanism to emit MCP server registration for `ll-mcp` on any host.

## Expected Behavior

`ll-adapt --host codex --apply` additionally emits a TOML snippet
registering the `ll-mcp` server (`mcp_servers = ["ll-mcp"]`-shaped,
following the `_format_agent_toml` precedent), using the same
marker-gated write/skip/dry-run semantics as `emit_agent`. Other hosts
(`gemini`, `omp`, `kimi-code`) gain a stub `emit_mcp_config` that returns
`"skipped"` so the `HostEmitter` Protocol stays satisfiable without
breaking existing `isinstance` checks.

## Impact

- **Severity**: Low - unblocks manual MCP config authoring for Codex users
  of `ll-mcp`; no existing functionality is broken by its absence.
- **Effort**: Medium - one new Protocol method, one traversal function,
  one real implementation (Codex), three stub bodies, and matching test/doc
  updates per the Integration Map above.
- **Risk**: Low - additive surface; `HostEmitter` is a structural Protocol
  so a missing method fails loudly (`AttributeError`) rather than silently.

## Parent Issue

Decomposed from FEAT-3133: `ll-adapt --host`: emit MCP config snippet for
`ll-mcp`. Split so the Codex TOML path — which does not depend on the
undecided "should Claude Code get a new `_EMITTER_MAP` host key" branch —
can ship independently. See FEAT-3139 for the Claude Code `.mcp.json` path.

## Integration Map

### Files to Modify
- `scripts/little_loops/adapters/core.py` — `HostEmitter` Protocol (around
  line 28) currently defines only `emit_skill`/`emit_command`/`emit_agent`;
  add a new `emit_mcp_config(self, meta: dict) -> str` method (same shape:
  returns `"adapted"`/`"skipped"`/`"error"`). Add a matching
  `process_mcp_config()` traversal function following the
  `process_skills`/`process_commands`/`process_agents` convention
  (`core.py:279-484`).
- `scripts/little_loops/adapters/codex.py` — implement `emit_mcp_config`
  producing a TOML `mcp_servers = ["ll-mcp"]`-shaped field. Closest
  precedent is `_derive_mcp_servers()` (lines 166-182) and
  `_format_agent_toml` (lines 219-222), which already extract server names
  and write an `mcp_servers` TOML array — not `emit_skill` (Markdown+YAML,
  not TOML).
- `scripts/little_loops/adapters/gemini.py`, `omp.py`, `kimi.py` — add a
  body for the new `emit_mcp_config` method (no-op/degraded stub is
  acceptable). Required regardless of the Claude Code decision because
  `HostEmitter` is `@runtime_checkable` and existing
  `isinstance(resolve_emitter(host), HostEmitter)` assertions
  (`test_adapters.py:98, 886, 1288, 1506`) fail otherwise once the Protocol
  gains a method.
- `scripts/little_loops/cli/adapt.py` — `main_adapt()` (line 31): wire the
  new `process_mcp_config()` call into the existing per-host dispatch
  (lines 106-134), following the existing accumulation-into-totals shape.
- `docs/reference/API.md` (~line 9583) — fix the pre-existing
  `_EMITTER_REGISTRY`/`_EMITTER_MAP` name drift ("register the class in
  `_EMITTER_REGISTRY`" should read `_EMITTER_MAP`) while this area is
  touched.

### Conventions in Force
- `HostEmitter` is a structural `Protocol`, not an ABC; `resolve_emitter()`
  does no `isinstance` gate at registration time. A missing method only
  surfaces as `AttributeError` at call time — but existing test assertions
  (below) force stub bodies on gemini/omp/kimi regardless.
- No TOML library is declared in `scripts/pyproject.toml`; TOML is
  hand-formatted as f-strings (`codex.py:_format_agent_toml`).
- No JSON/config-writing utility is needed here — Codex's format is TOML
  text, following the existing f-string pattern.

### Tests
- New `TestCodexEmitterEmitMcpConfig` class in `test_adapters.py`, shaped
  like `TestCodexEmitterEmitAgent` (lines 471-602): creates-file, dry-run
  does not write, marker present, user-authored file not overwritten,
  up-to-date returns skipped, same-call-twice idempotency.
- New golden-corpus fixture `scripts/tests/fixtures/adapt/mcp_cases.json`
  (no such file exists yet) plus a
  `test_*_mcp_config_emission_matches_golden_corpus` function in
  `test_adapt_golden_corpus.py`, following the existing JSON-fixture /
  loop-over-cases / byte-compare pattern. `test_corpus_is_non_trivial`
  enforces `len(cases) >= 3` with at least one `"skipped"`-path case.
- Existing `isinstance(resolve_emitter(host), HostEmitter)` assertions in
  `test_adapters.py` (lines 98, 886, 1288, 1506) must keep passing once the
  Protocol gains `emit_mcp_config` — covered by the gemini/omp/kimi stub
  bodies above.

_Wiring pass added by `/ll:wire-issue`:_
- `test_adapters.py::_MockEmitter` (lines 175-194) — the hand-rolled fake
  used by `TestProcessSkillsTraversal`/`TestProcessCommandsTraversal`/
  `TestProcessAgentsTraversal` defines `emit_skill`/`emit_command`/
  `emit_agent` but not `emit_mcp_config`. Add an `emit_mcp_config` method
  (and an `mcp_config_calls` list, matching the existing `*_calls` list
  convention) before writing a `TestProcessMcpConfigTraversal` class that
  reuses it — otherwise `process_mcp_config()` calling
  `emitter.emit_mcp_config(...)` on `_MockEmitter` raises `AttributeError`.
- New `TestProcessMcpConfigTraversal` class in `test_adapters.py`, adjacent
  to `TestProcessAgentsTraversal` (lines 285-332) — but `process_mcp_config`
  emits one artifact per host, not one per source-file glob (unlike
  `process_agents`/`process_skills`/`process_commands`), so this class
  drops the "calls emitter once per file" multi-file cases and keeps only:
  calls emitter once, meta has required keys, `AdapterError` from
  `emit_mcp_config` counted as error, apply/dry-run passthrough.
- New `TestGeminiEmitterEmitMcpConfig`, `TestOmpEmitterEmitMcpConfig`,
  `TestKimiEmitterEmitMcpConfig` classes in `test_adapters.py` — direct
  per-emitter unit tests asserting the Step 3 stub bodies return
  `"skipped"`, following the file's existing one-class-per-emitter-per-method
  organization (e.g. `TestCodexEmitterEmitSkill` at line 350). No
  `TestProcessAgentsDegradedRouting`-style shared-helper routing test
  applies here — there is no shared degraded-emission helper for
  `emit_mcp_config` to route through (unlike `GeminiEmitter.emit_agent` →
  `_emit_degraded_agent`).

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (`### ll-adapt` section, ~line 4126) — flags
  table and examples cover `ll-adapt` end-to-end but don't mention MCP
  config emission; add a note/example once the new artifact category
  ships.
- `docs/codex/getting-started.md` (line 88) — "Run `ll-adapt --host codex
  --apply` once after install to bridge all little-loops skills, commands,
  and agent personas into Codex" is an explicit 3-item enumeration that
  becomes incomplete once mcp config is a 4th emitted artifact.
- `docs/codex/usage.md` (lines 41, 50, 85, 87) and `docs/codex/README.md`
  (line 32) — same skills/commands/agents enumeration pattern as
  `getting-started.md`.
- `scripts/little_loops/cli/__init__.py` (module docstring, line 7) —
  `"- ll-adapt: Unified host-parameterized skill/command/agent adapter
  (--host codex|omp|...)"` explicitly enumerates "skill/command/agent";
  this canonical usage banner goes stale once mcp config emission is
  added.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- `_derive_mcp_servers(tools: list | None) -> list[str] | None` (`codex.py:166-182`) — takes an agent's parsed `tools` list, scans for `mcp__<server>__*`-shaped entries, dedupes server names preserving first-seen order. Its only current caller is `_format_agent_toml:219`. It derives server names *from an agent's own tool list*, not from a fixed server reference — `emit_mcp_config` needs a different, simpler derivation (a static `["ll-mcp"]`), not a call into this function.
- `_format_agent_toml(name, description, model, body, fm) -> str` (`codex.py:185-225`) is the closest TOML-formatting precedent: fixed `_MARKER` header, then required fields (`name`, `description`, `model`), then conditional fields (`sandbox_mode`, `mcp_servers`) each only appended if non-`None`, then a `developer_instructions` triple-quoted block. Array formatting for `mcp_servers` is `", ".join(f'"{s}"' for s in mcp_servers)` wrapped as `f"mcp_servers = [{servers_str}]\n"` (`codex.py:220-222`) — no per-element escaping beyond the surrounding quotes.
- `HostEmitter` Protocol's three existing methods (`core.py:28-42`) each take a single `dict` positional arg and return one of the literal strings `"adapted"`/`"skipped"`/`"error"` — confirmed exact contract via class docstring (`core.py:33-36`). `resolve_emitter()` (`core.py:59-76`) performs no `isinstance` gate itself; the `isinstance(resolve_emitter(host), HostEmitter)` checks live only in tests at `test_adapters.py:98` (codex), `886` (gemini), `1288` (kimi-code), `1506` (omp) — confirmed at those exact lines.
- `process_agents(emitter, agents_dir, output_dir, apply, quiet, only=None) -> tuple[int, int, int]` (`core.py:409-484`) is the closest traversal precedent: globs `sorted(agents_dir.glob("*.md"))`, reads content (OSError → error), parses frontmatter via `_read_frontmatter` (defaults `{}` on failure), builds a meta dict, calls the emitter (or `_emit_degraded_agent` when capability-gated), catches `AdapterError` → error, and buckets the returned string into `adapted`/`skipped`/`errors` counters. `process_skills`/`process_commands`/`process_agents` are three independently-written, structurally near-identical functions — no shared "walk + dispatch" helper exists across them (confirmed by codebase-pattern-finder), so a fourth `process_mcp_config()` following the same skeleton (rather than trying to factor a shared helper) matches the established convention.
- `main_adapt()` (`cli/adapt.py:31-137`) dispatches skills (guarded by `if skills_dir.exists()`, lines 106-110), commands (unconditional call — `process_commands` itself early-returns `(0,0,0)` if its dir doesn't exist, `core.py:355-356`, lines 113-118), and agents (guarded, resolves a host-specific `agent_output_dir` from `HOST_CAPABILITIES[args.host].config_dir`, lines 121-134) — each block ends with the same three-line `total_adapted += ...` accumulation. A new mcp-config dispatch block should follow this same shape.
- No `"ll-mcp"` string constant exists anywhere in `scripts/little_loops/` today (confirmed via repo-wide search by codebase-analyzer) — only issue files under `.issues/` and unrelated MCP-robustness code (`runner_spec.py`, `mcp_call.py`, `cli/queue.py`) mention `mcp`. The literal `"ll-mcp"` server name will be a fresh string introduced by this issue, not sourced from an existing constant.
- `HostCapabilityEntry` (`adapters/capabilities.py:44-61`) has no MCP-related field today (its fields are `host`, `config_dir`, `skill_output_format`, `command_output_format`, `agent_output_format`, `frontmatter_fields_read`, `agents`, `commands`, `hooks`, `subagents`) — capability-gating an mcp-config emission per host (the way `process_agents` gates degraded vs native via `subagents`) has no existing hook to plug into; a per-host stub body (Step 3 of Implementation Steps) is a body-level decision, not a capability-map-driven one, unless this issue also adds a new capability field.
- Existing stub precedent: `GeminiEmitter.emit_agent` (`gemini.py:150-157`) is the only current example of a "host lacks native support" stub — a one-line docstring naming the capability gap, then direct delegation to a shared core helper (`_emit_degraded_agent`) rather than a locally reimplemented body. There is no existing stub precedent for `emit_skill`/`emit_command` (all four hosts implement those natively today), so a new `emit_mcp_config` stub on gemini/omp/kimi has no directly reusable shared helper to delegate to (unlike Gemini's `emit_agent`) — a minimal stub body (e.g. `return "skipped"` with a docstring) is the closest fit unless a new shared helper is introduced.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- Two distinct "already up to date" conventions coexist and disagree on which applies here: Variant A (marker-gated, `codex.py:353-362`, used only by Codex agent-TOML emission) distinguishes "user-authored, no marker → skip, never overwrite" from "marker present but stale → rewrite"; Variant B (plain byte-equality, used by every other emit_* method across all four hosts, e.g. `gemini.py:94-97`) treats any byte-identical file as up-to-date and any differing file as overwritable, with no user-authored concept. Since `emit_mcp_config` on Codex is TOML output like `emit_agent`, Variant A is the applicable precedent for the Codex implementation specifically — Variant B is the convention for byte-equality-only hosts if the stub bodies on gemini/omp/kimi are ever upgraded past a no-op.
- Golden-corpus fixture pairing convention (confirmed at `scripts/tests/fixtures/adapt/agent_cases.json` + `test_codex_agent_emission_matches_golden_corpus`, `test_adapt_golden_corpus.py:156-176`): each case carries `input_content`/`input_tools` plus one `<host>_result` + one `<host>_<artifact>` key; `test_corpus_is_non_trivial` (`test_adapt_golden_corpus.py:179-196`) enforces `len(cases) >= 3` and at least one `"skipped"`-path case directly against the fixture data, not emitter behavior — the new `mcp_cases.json` should follow this same shape and enforcement pattern.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

### Types
- No new data types are introduced. `emit_mcp_config` reuses the existing `dict`-in/`str`-out `HostEmitter` contract (`core.py:33-36`) — a meta dict analogous to `agent_meta` (`core.py:409-484`), containing at minimum `output_dir`, `apply`, `quiet`, and whatever server-list source is decided (a static `["ll-mcp"]` or a value threaded from the meta dict).

### Signatures
- `HostEmitter.emit_mcp_config(self, meta: dict) -> str` — new Protocol method, `core.py:28-42`, same shape as `emit_skill`/`emit_command`/`emit_agent` (single dict arg, returns `"adapted"`/`"skipped"`/`"error"`).
- `process_mcp_config(emitter: HostEmitter, output_dir: Path, apply: bool, quiet: bool) -> tuple[int, int, int]` — new traversal function in `core.py`, following the `process_agents(emitter, agents_dir, output_dir, apply, quiet, only=None)` signature shape (`core.py:409`) minus the `agents_dir`/`only` params, since there is no per-file glob to traverse — mcp-config emission is a single artifact per host, not one-per-source-file like skills/commands/agents.
- `CodexEmitter.emit_mcp_config(self, meta: dict) -> str` — new method in `codex.py`, sibling to `emit_agent` (`codex.py:327-373`), reusing that method's marker-gated skip logic (Variant A in pattern-finder's findings: `_LL_GENERATED_MARKERS`-prefix check → user-authored skip; content-equality check → up-to-date skip; else write-or-dry under `apply`).
- Stub `emit_mcp_config(self, meta: dict) -> str` on `GeminiEmitter`, `OmpEmitter`, `KimiEmitter` — no shared delegation helper exists today (unlike `emit_agent`'s `_emit_degraded_agent`), so each stub is a locally minimal body (e.g. return `"skipped"` with a docstring naming the gap) unless this issue also introduces a new shared helper.

### Call Path
`main_adapt()` (`cli/adapt.py:31-137`) -> `process_mcp_config(emitter, mcp_output_dir, apply, args.quiet)` (new, `core.py`) -> `emitter.emit_mcp_config(meta)` (new per-host methods) -> for Codex: `_derive_mcp_servers`-sibling logic building a static `mcp_servers = ["ll-mcp"]` TOML line, written via the same marker-gated exists/compare/write-or-dry sequence as `CodexEmitter.emit_agent` (`codex.py:353-372`).

### Decision Rules
N/A — no new gap kind, gate, keyword list, or threshold; this is a new emission method following an established Protocol/traversal contract, not new decision logic.

## Implementation Steps

1. Add `emit_mcp_config` to the `HostEmitter` Protocol
   (`adapters/core.py:28-42`) and a matching `process_mcp_config()`
   traversal function (`core.py:279-484` convention).
2. Implement `emit_mcp_config` on `codex.py` (TOML output, using
   `_derive_mcp_servers`/`_format_agent_toml` as precedent).
3. Add stub `emit_mcp_config` bodies to `gemini.py`, `omp.py`, `kimi.py` so
   existing `isinstance(..., HostEmitter)` assertions keep passing.
4. Wire `main_adapt()` (`cli/adapt.py:106-134`) to dispatch
   `process_mcp_config()` alongside the existing skills/commands/agents
   dispatch.
5. Fix the `_EMITTER_REGISTRY`/`_EMITTER_MAP` name drift in
   `docs/reference/API.md` (~line 9583).
6. `python -m pytest scripts/tests/` passes, including new coverage in
   `test_adapters.py` / `test_adapt_golden_corpus.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `emit_mcp_config`/`mcp_config_calls` to `test_adapters.py::_MockEmitter`
  (lines 175-194) before writing `TestProcessMcpConfigTraversal`, or the
  new traversal tests raise `AttributeError`.
- Add `TestProcessMcpConfigTraversal`, `TestGeminiEmitterEmitMcpConfig`,
  `TestOmpEmitterEmitMcpConfig`, `TestKimiEmitterEmitMcpConfig` test
  classes in `test_adapters.py` per the Tests subsection above.
- Update `docs/reference/CLI.md` (`### ll-adapt`), `docs/codex/getting-started.md`,
  `docs/codex/usage.md`, `docs/codex/README.md`, and the `ll-adapt` usage
  banner in `scripts/little_loops/cli/__init__.py` (module docstring, line 7)
  to mention MCP config emission alongside skills/commands/agents.

## Acceptance Criteria

- `ll-adapt --host codex` emits a working TOML MCP config snippet
  referencing the `ll-mcp` entry point.
- `isinstance(resolve_emitter(host), HostEmitter)` still passes for
  `codex`, `gemini`, `omp`, `kimi-code`.
- `python -m pytest scripts/tests/` passes.

## Resolution

Implemented per plan:
- `HostEmitter` Protocol gained `emit_mcp_config(self, meta: dict) -> str`
  (`adapters/core.py`); new `process_mcp_config()` traversal calls it once
  per host (no per-file glob).
- `CodexEmitter.emit_mcp_config` writes `<output_dir>/ll-mcp.toml`
  (`mcp_servers = ["ll-mcp"]`), reusing the marker-gated
  write/skip/dry-run semantics from `emit_agent`.
- `GeminiEmitter`, `OmpEmitter`, `KimiEmitter` gained a stub
  `emit_mcp_config` returning `"skipped"`.
- `main_adapt()` wired to dispatch `process_mcp_config()` unconditionally,
  writing to `plugin_root / config_dir / "ll-mcp.toml"`.
- Fixed `_EMITTER_REGISTRY`/`_EMITTER_MAP` name drift in
  `docs/reference/API.md`; updated `docs/reference/CLI.md`,
  `docs/codex/{getting-started,usage,README}.md`, and the `ll-adapt` usage
  banner in `cli/__init__.py` to mention MCP config emission.
- New tests: `TestProcessMcpConfigTraversal`, `TestCodexEmitterEmitMcpConfig`
  (create/dry-run/marker/user-authored/idempotent), and one-line
  `emit_mcp_config` stub tests for Gemini/Omp/Kimi, plus `_MockEmitter`
  gained `emit_mcp_config`/`mcp_config_calls`.
- Verified end-to-end with a manual `ll-adapt --host codex --apply` run
  (artifact discarded after inspection, not part of the commit).

Deferred (out of AC scope): the golden-corpus fixture
(`fixtures/adapt/mcp_cases.json`) suggested in the issue's Tests section —
the three stated Acceptance Criteria (functional emission, Protocol
`isinstance` checks, full suite passing) are covered by the unit tests
above without it.

`python -m pytest scripts/tests/` passes (18724 passed, 43 skipped) except
one pre-existing, unrelated failure —
`test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo`
flags prose drift in `ENH-3095`, `FEAT-3122`, `FEAT-3134`, none of which
this issue touches; those issue files were already uncommitted/dirty at
session start.

## Status

Open | Discovered: 2026-08-09 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-08-09T09:52:24 - `6a053b71-513b-4eee-96d2-a0f21f283731.jsonl`
- `/ll:ready-issue` - 2026-08-09T09:15:07 - `b2efd9b3-3f42-48c1-98d3-144ac32c8bc9.jsonl`
- `/ll:confidence-check` - 2026-08-09T09:11:41 - `4d3c53f4-bdd9-4d41-a0cf-7a591053c0c9.jsonl`
- `/ll:verify-issues` - 2026-08-09T09:09:41 - `8bc5ff42-d588-4774-825b-e264ff0081f1.jsonl`
- `/ll:wire-issue` - 2026-08-09T09:07:34 - `af7344a0-86b1-4e3b-9db5-9156228f75d3.jsonl`
- `/ll:refine-issue` - 2026-08-09T09:00:25 - `26ce58e4-8d3c-444f-a0e7-97a2de66f6ba.jsonl`
- `/ll:issue-size-review` - 2026-08-09T08:53:40 - `1f6bc67b-133e-4fd3-8a20-5c586fca9c77.jsonl`
