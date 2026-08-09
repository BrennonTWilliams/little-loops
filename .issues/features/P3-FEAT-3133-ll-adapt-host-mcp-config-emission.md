---
id: 3133
title: 'll-adapt --host: emit MCP config snippet for ll-mcp'
type: FEAT
priority: P3
status: done
verify_verdict: VALID
discovered_date: '2026-08-09'
labels:
- multi-host
- mcp
parent: EPIC-3127
relates_to:
- FEAT-3128
- FEAT-3132
confidence_score: 80
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 18
size: Very Large
---

# FEAT-3133: ll-adapt --host: emit MCP config snippet for ll-mcp

## Summary

`ll-adapt --host <x>` learns to emit the host's MCP config snippet for the
`ll-mcp` server: `.mcp.json` for Claude Code, TOML for Codex. This lets a
consuming project wire up `ll-mcp` for a given host without hand-authoring
config.

FEAT-3132 (done) provides the `ll-mcp` console entry point; this issue only
ever needed the entry-point *name* from it, not its internals — it emits a
config snippet pointing at `ll-mcp`, it does not call into the server.

## Parent Issue

Decomposed from FEAT-3128: ll-mcp: read-only server (queries, resources,
prompts-from-skills from skills). Split out from the core server (FEAT-3132)
because host-config emission is a separately testable subsystem (the
`HostEmitter` Protocol and its per-host implementations) that only needs to
know the server's entry-point name, not its behavior.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/adapt.py` — `main_adapt()` (line 31) needs new
  host-config emission wired in for the MCP snippet work, joining its
  existing per-host dispatch for skills/commands/agents (lines 106-134)
- `scripts/little_loops/adapters/core.py` — `HostEmitter` Protocol (around
  line 28) currently defines only `emit_skill`/`emit_command`/`emit_agent`;
  needs a new MCP-config-emission method. `_EMITTER_MAP` (around line 51-56)
  needs extension if a new host key is registered; no Claude Code emitter
  exists in `_EMITTER_MAP` today (only `codex`, `gemini`, `omp`,
  `kimi-code`), so `.mcp.json` emission may need a new `"claude-code"` host
  key registered, not just a new method
- `scripts/little_loops/adapters/codex.py` — needs a TOML-emission method
  for the new `HostEmitter` method; `emit_skill` (`codex.py:242`) is the
  closest TOML-output template
  > ⚠ Superseded — `emit_skill` emits Markdown+YAML, not TOML; see § Codebase Research Findings
- `scripts/little_loops/adapters/capabilities.py` — `HOST_CAPABILITIES`/
  `config_dir` may need an MCP-config-path field per host

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/adapters/gemini.py` — `GeminiEmitter` (class body
  ~67-160) has no fourth `emit_*` method today; needed to keep satisfying
  `HostEmitter` isinstance checks once the Protocol grows a new method (see
  `### Tests` below — `test_adapters.py:886` breaks otherwise)
- `scripts/little_loops/adapters/omp.py` — `OmpEmitter` (class body
  ~47-130), same reason (`test_adapters.py:1506`)
- `scripts/little_loops/adapters/kimi.py` — `KimiEmitter` (class body
  ~46-140), same reason (`test_adapters.py:1288`). `HostEmitter` is
  `@runtime_checkable`; existing `isinstance(resolve_emitter(...),
  HostEmitter)` assertions in `test_adapters.py` (lines 98, 886, 1288, 1506)
  require the attribute to exist on gemini/omp/kimi once the Protocol gains
  a method — this is forced by these existing tests, not an optional
  "only if acceptance-tested" call as `### Conventions in Force` above
  states.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/adapters/__init__.py:2` — re-exports
  `resolve_emitter`, `HostEmitter`, `AdapterError`

### Conventions in Force
- `ll-adapt` host registration uses a lazy-import dict (`_EMITTER_MAP`,
  `adapters/core.py:51-56`) resolved via `resolve_emitter()`
  (`adapters/core.py:59-76`) against a `@runtime_checkable` `HostEmitter`
  Protocol (`adapters/core.py:28-42`) — no decorator-based registration
  pattern exists anywhere in this codebase.
- `HostEmitter` is a structural `Protocol`, not an ABC, and
  `resolve_emitter()` does no `isinstance` gate at registration time, so
  adding a new emit method to the Protocol does NOT force `gemini.py`/
  `omp.py`/`kimi.py` to implement it — a missing method only surfaces as
  `AttributeError` at call time for whichever host is actually exercised.
  Decide whether any implementation beyond `codex.py` needs a body for the
  new emit method; only add stubs there if those hosts are part of the
  acceptance-tested path.

### Tests
- `scripts/tests/test_adapt_golden_corpus.py`, `scripts/tests/test_adapters.py`
  — precedent location for `--host` MCP-config-emission tests
- `scripts/tests/test_verify_host_map.py::TestHostCapabilities::test_keys_match_emitter_map`
  — asserts `set(HOST_CAPABILITIES) == set(_EMITTER_MAP)`; only at risk if
  this issue registers a new `"claude-code"` host key for `.mcp.json`
  emission — both maps must gain the key together
- New `test_capabilities.py`, or an extension of `test_adapters.py` /
  `test_verify_host_map.py`, if `HostCapabilityEntry` gains a new field for
  an MCP-config path

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_verify_host_map.py::TestAdapterSectionHosts::test_finds_documented_hosts`
  (line ~48-51) — hard-codes `hosts == {"codex", "gemini", "omp",
  "kimi-code"}`; must be updated to include `"claude-code"` if that key is
  registered, in the same change as the `HOST_COMPATIBILITY.md` table row
  below, or `test_current_tree_has_no_mismatch` (line ~55-56) fails
- `scripts/tests/test_text_utils.py::TestMirrorPrefixes` (line ~361-370) —
  `test_mirror_prefixes_derive_from_host_registry` self-adjusts from
  `HOST_CAPABILITIES` and needs no edit, but it also asserts `.claude/` is
  never in `_mirror_prefixes()`; if a new `"claude-code"`
  `HostCapabilityEntry.config_dir` is ever set to `.claude`, this invariant
  breaks and needs deliberate handling
- New test class in `test_adapters.py`, shaped like
  `TestCodexEmitterEmitAgent` (lines 471-602 — the TOML-content-assertion
  precedent, not `TestCodexEmitterEmitSkill`) — creates-file / dry-run /
  idempotent-marker / content-substring assertions for the new TOML MCP
  emission
- If a `"claude-code"` emitter is registered: a matching
  `TestResolveEmitterClaudeCode` class (mirror `TestResolveEmitterGemini`,
  `test_adapters.py:881-886`)
- New golden-corpus fixture (e.g. `scripts/tests/fixtures/adapt/mcp_config_cases.json`)
  plus a `test_*_mcp_config_emission_matches_golden_corpus` function in
  `test_adapt_golden_corpus.py`, following its existing JSON-fixture /
  loop-over-cases / byte-compare pattern (no `mcp_cases.json` exists yet)
- `scripts/tests/test_mcp_call.py`'s `_VALID_MCP_CONFIG` fixture
  (lines ~22-29: `{"mcpServers": {"<name>": {"command": ..., "args":
  [...]}}}`) is the only existing definition of well-formed `.mcp.json`
  shape in this codebase — the new emission-side test should assert against
  this same shape (`json.loads()` + dict-key checks), not a JSON-Schema
  library (none is a dependency; see `test_config_schema.py:77-78`)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/HOST_COMPATIBILITY.md` (lines ~217-230) — the
  `## Adapter Host Capabilities` section intro states, verbatim, that
  `claude-code`/`opencode`/`pi` "have no adapter-side entry at all" — this
  directly contradicts registering a `"claude-code"` key and must be
  rewritten, plus a new table row (pattern at lines ~232-237) added
- `docs/ARCHITECTURE.md` (~lines 1308-1314, "Host Adapter Capability Map")
  — enumerates `codex`/`gemini`/`omp`/`kimi-code`; needs the new host
  listed if `"claude-code"` is registered
- `docs/reference/CLI.md` (~line 4134, `--host HOST` row: "e.g. codex,
  omp") — host examples become incomplete once a new host is emittable
- `scripts/little_loops/cli/adapt.py` — `--host` argparse help string
  (line ~52-53: `"Target host (e.g. codex, omp, kimi-code)"`) and epilog
  examples (lines ~41-47, all `--host codex`) don't mention the new host;
  no `choices=` restriction exists so nothing breaks mechanically, but the
  help text becomes incomplete
- `README.md` (lines ~74-79) — has onboarding blurbs for `--host codex
  --apply` and `--host kimi-code --apply` but no equivalent Claude Code
  blurb; a gap to fill if MCP config emission becomes a real Claude Code
  onboarding step, not something that breaks
- `docs/reference/API.md` (~line 9583) — "To add a host" instructions say
  "register the class in `_EMITTER_REGISTRY` in `core.py`", but the actual
  code symbol is `_EMITTER_MAP` (`adapters/core.py:51`) — pre-existing
  doc/code name drift, worth fixing while this area is touched

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- `HostEmitter.emit_skill`/`emit_command`/`emit_agent` all share the exact shape `(self, meta: dict) -> str`, returning one of the literal strings `"adapted"`/`"skipped"`/`"error"` — `adapters/core.py:28-42` (Protocol), `adapters/codex.py:233-374` (`CodexEmitter`), `adapters/gemini.py:67-78`, `adapters/omp.py:47-50`, `adapters/kimi.py:46-55`.
- Each `emit_*` Protocol method is paired with a `process_*` traversal function in `core.py` that walks a source directory, builds the metadata dict, and calls the emitter method: `process_skills` (`core.py:279-333`), `process_commands` (`core.py:336-406`), `process_agents` (`core.py:409-484`). A new MCP-config emission method needs a matching `process_*`-shaped traversal function to follow this pairing convention.
- No JSON-writing utility exists in the adapters subsystem today — no `emit_*` method writes JSON; the repo's own `.mcp.json` is a static hand-authored file (`{"mcpServers": {}}`). The only existing code touching `.mcp.json` is a *reader*, not a writer: `scripts/little_loops/mcp_call.py` (~lines 39-53) parses it to look up a server's `command` by name for `ll-mcp-call`-style invocation.
- No TOML library is declared in `scripts/pyproject.toml`; TOML is hand-formatted as f-strings elsewhere in this codebase. The TOML-formatting precedent is `codex.py:_format_agent_toml` (lines 185-204), used by `emit_agent` — see superseded-line annotation on `### Files to Modify` below.
- `HostCapabilityEntry` (`adapters/capabilities.py:44-61`) is a frozen dataclass; declaring a capability flag with no matching `emit_*` method is already established practice in this file (e.g. `hooks: bool` has no corresponding `emit_hook` method) — an MCP-path field with a not-yet-wired-up emitter method would be consistent with existing practice.
- Existing precedent for dynamic entry-point-name resolution (rather than hardcoding `"ll-mcp"`): `scripts/little_loops/cli/verify_cli_allowlist.py:_all_ll_entry_points()` (lines 46-59) reads installed distribution metadata via `importlib.metadata.distribution("little-loops").entry_points`. Elsewhere (`host_runner.py`), CLI binary names are hardcoded string literals — both patterns exist in this codebase; hardcoding vs. dynamic resolution of `"ll-mcp"` is a route choice, not a codebase-wide requirement.
- `main_adapt()`'s existing dispatch blocks (`cli/adapt.py:106-134`) all follow one shape: a guard, a `process_*` call, accumulation into `total_adapted`/`total_skipped`/`total_errors`, with the whole function's return code gated only by `total_errors == 0` at the end (lines 136-137) — no per-block distinct error handling exists today.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **Dependency reality check**: `depends_on: [FEAT-3132]` is satisfied at the tracker layer (FEAT-3132 is `status: done`), but FEAT-3132's own `## Resolution` records it as `Decomposed` into FEAT-3135/FEAT-3136/FEAT-3137, not implemented. Of those: FEAT-3135 (`ll-mcp` server skeleton and entry point) is `status: deferred`, FEAT-3136 is `open`, FEAT-3137 is `open`. Confirmed via `grep "ll-mcp" scripts/pyproject.toml` — no `ll-mcp = "..."` line exists in `[project.scripts]` today. This issue can implement and test the *emission* mechanics (config-writing, host dispatch) against a literal `"ll-mcp"` string, but cannot end-to-end verify the emitted config actually launches a server until FEAT-3135 lands.
- Repo's own `.mcp.json` (root) is `{"mcpServers": {}}` — an empty-but-present skeleton, not truly absent. A Claude Code emitter therefore needs read-modify-write (merge into the existing `mcpServers` key), not blind overwrite, since a consuming project's `.mcp.json` may already carry unrelated server entries.
- `scripts/little_loops/file_utils.py:35-57` — `atomic_write_json(path: Path, data: Any) -> None` (writes with mkdir, JSON round-trip validation, atomic write) is an existing JSON-writing utility used 10x elsewhere in the codebase (e.g. `init/writers.py:merge_settings()` for `.claude/settings.local.json`), even though no `adapters/` emitter uses it yet. `merge_settings()` (`init/writers.py:349-404`) is the closest existing precedent for a *merging* (not overwriting) JSON config writer, including its idempotency approach (strip-then-readd canonical entries while preserving user-added ones) — see `TestMergeSettings` (`test_init_core.py:944-1013`) for the corresponding test shape.
- `mcp_call.py:_load_mcp_config`/`_find_server_config` (lines 38-70) require each `mcpServers` entry to have a string `"command"` (not an argv list) plus optional `"args"`/`"env"`; no `"type"` field is read or required. A minimal valid entry for `ll-mcp` (no args) is `{"mcpServers": {"ll-mcp": {"command": "ll-mcp"}}}`. This reader is one consumer among possibly several — a lower bound on the emitted shape, not necessarily everything Claude Code itself expects from `.mcp.json`.
- Two dry-run/apply conventions coexist in this codebase with different polarity and threading: the adapters subsystem threads `apply: bool` inside each emitter's `meta` dict (`cli/adapt.py:82`: `apply = args.apply and not args.dry_run`; each `emit_*` branches `if apply: <write> else: <print DRY>` inline, e.g. `codex.py:265-277`), while `init/writers.py` instead threads a plain `dry_run: bool = False` keyword parameter with an early-return guard (e.g. `merge_settings(..., dry_run=False)`, `writers.py:396-404`). Both are live, established patterns in different subsystems — not a single codebase-wide convention.
- `main_adapt()`'s three existing dispatch blocks (`cli/adapt.py:106-134`) are not uniform: skills is gated on `skills_dir.exists()` (line 106) and agents on `agents_dir.exists()` (line 121), but commands (`process_commands`) is called unconditionally, with its own existence check internal to `core.py:355-356`. A new MCP-config block has no single established gating shape to copy from all three.
- `--only` (`cli/adapt.py:69-73`) is wired only into `process_agents`; `process_skills`/`process_commands` accept no `only` parameter. An MCP-config traversal (emitting once per project rather than once per source file) likely has no natural `--only` semantics to inherit.
- `HostCapabilityEntry` (`capabilities.py:44-61`) is a non-kw-only frozen dataclass with five required positional fields followed by fields carrying defaults; a new MCP-config-path/format field must itself carry a default (or be added after the last defaulted field) to avoid forcing an edit to all four existing `HOST_CAPABILITIES` entries — though all four already construct via keyword arguments, so this is a minor, not a breaking, constraint.

## Program Design

### Signatures
- `little_loops.adapters.core.resolve_emitter(host: str) -> HostEmitter` —
  `adapters/core.py:59-76`; the `HostEmitter` Protocol
  (`adapters/core.py:28-42`) currently defines only
  `emit_skill`/`emit_command`/`emit_agent`, no MCP-config method exists —
  this is the extension point for `ll-adapt --host` MCP config emission
- `main_adapt() -> int` — `cli/adapt.py:31`; dispatches per-host processing
  today for skills/commands/agents (lines 106-134), a new
  `process_mcp_config()`-shaped call would join that dispatch

### Call Path
- `ll-adapt --host <x>` → `main_adapt()` (`cli/adapt.py:31`) →
  `resolve_emitter(host)` (`adapters/core.py:59-76`) → an `HostEmitter`
  method not yet present on the Protocol → `.mcp.json` (Claude Code) / TOML
  (Codex, via `codex.py`'s `emit_skill` at line 242 as the TOML-output
  template)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- Confirmed signature shape for the new Protocol method should match the existing three: `emit_<name>(self, meta: dict) -> str` returning `"adapted"` / `"skipped"` / `"error"` literal strings (`adapters/core.py:28-42`, `codex.py:233-374`).
- Call path clarification: `main_adapt()` (`cli/adapt.py:31`) → a new `process_*` traversal function in `core.py` (paired per the `process_skills`/`process_commands`/`process_agents` convention at `core.py:279-484`) → `emitter.emit_<new>(meta)` → per-host output (`.mcp.json` string for Claude Code / TOML string via an f-string builder following `codex.py:_format_agent_toml` lines 185-204 — not `emit_skill`, which emits Markdown + a YAML sidecar, not TOML).

_Wiring pass added by `/ll:wire-issue`:_
- There is a second, more directly relevant TOML-MCP precedent than
  `_format_agent_toml` alone: `codex.py:_derive_mcp_servers()` (lines
  166-182) already extracts server names from `mcp__<server>__*` tool
  references and `_format_agent_toml` (lines 219-222) already writes an
  `mcp_servers = ["name", ...]` TOML array field from it — this is
  existing, working code that writes an MCP-related TOML field, closer to
  this issue's TOML-output need than the generic f-string-formatting
  pattern alone.
- `HostEmitter` is `@runtime_checkable`, and four existing test assertions
  (`test_adapters.py:98, 886, 1288, 1506`) call
  `isinstance(resolve_emitter(<host>), HostEmitter)` for codex/gemini/
  kimi-code/omp — adding a method to the Protocol without adding a body
  (even a stub) to `gemini.py`/`omp.py`/`kimi.py` breaks these three
  `isinstance` checks at test time, contradicting the "not forced" framing
  in `### Conventions in Force` above. See `### Files to Modify`.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- `TestCodexEmitterEmitAgent` (`test_adapters.py:471-602`) is the fixed shape for a new emitter method's unit tests: creates-file, per-field content-substring assertions (not full-file equality), dry-run-does-not-write, marker-present, user-authored-file-not-overwritten, up-to-date-returns-skipped, and a same-call-twice idempotency check. `TestResolveEmitterGemini` (`test_adapters.py:881-886`) is the fixed two-test shape repeated for every registered host (`isinstance(resolve_emitter(host), <HostEmitterSubclass>)` + `isinstance(resolve_emitter(host), HostEmitter)`) — a `TestResolveEmitterClaudeCode` class would mirror this exactly if a `"claude-code"` key is registered.
- Golden-corpus fixtures (`fixtures/adapt/agent_cases.json`, read via `test_adapt_golden_corpus.py`) carry raw input plus one `<host>_result`/`<host>_<artifact>` pair per host in the same JSON file, and the consuming test asserts full-string equality against the expected output (stricter than `test_adapters.py`'s substring checks) via `for case in data["cases"]`. `test_corpus_is_non_trivial` additionally enforces `len(cases) >= 3` with at least one `"skipped"`-path case — a repeated pattern across skill/command/agent corpora, so a new `mcp_cases.json` should follow the same `>= 3` + skipped-case shape.
- `codex.py:_derive_mcp_servers()` (lines 166-182) and `_format_agent_toml` (lines 219-222) are existing, working code that already extracts server names from `mcp__<server>__*` tool references and writes an `mcp_servers = [...]` TOML array field — closer precedent for this issue's TOML output than the generic f-string-formatting pattern in `_format_agent_toml` alone.

## Implementation Steps

1. Decide the `HostEmitter` Protocol extension shape for MCP config
   emission and whether a new `"claude-code"` host key is registered in
   `_EMITTER_MAP` for `.mcp.json` emission.
2. Implement the new emit method on `codex.py` (TOML output) and, if a
   `"claude-code"` key is registered, on a new or existing Claude Code
   emitter for `.mcp.json` output. If a `"claude-code"` key is added to
   `_EMITTER_MAP`, add the matching key to `HOST_CAPABILITIES` in the same
   change.
3. Wire `main_adapt()` to dispatch the new emission alongside the existing
   skills/commands/agents dispatch.
4. `ll-adapt --host <x>` emits a working MCP config snippet, verified
   against both `.mcp.json` (Claude Code) and TOML (Codex) output.
5. `python -m pytest scripts/tests/` passes, including new coverage in
   `test_adapters.py` / `test_adapt_golden_corpus.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a body for the new `emit_*` method to `gemini.py`, `omp.py`, and
  `kimi.py` (even if it's a no-op/degraded stub) — required regardless of
  whether a `"claude-code"` host key is registered, because existing
  `isinstance(resolve_emitter(...), HostEmitter)` assertions in
  `test_adapters.py` (lines 98, 886, 1288, 1506) fail otherwise
- Update `docs/reference/HOST_COMPATIBILITY.md`'s `## Adapter Host
  Capabilities` intro and table, `docs/ARCHITECTURE.md`'s host list, and
  `docs/reference/CLI.md`'s `--host` examples if a new host key is added
- Update `scripts/tests/test_verify_host_map.py::test_finds_documented_hosts`'s
  hard-coded host set alongside the `HOST_COMPATIBILITY.md` table row
- Add new test coverage: a `TestCodexEmitterEmitMcpConfig`-shaped class in
  `test_adapters.py`, a golden-corpus fixture in
  `test_adapt_golden_corpus.py`, and (if a `"claude-code"` emitter is
  added) a `TestResolveEmitterClaudeCode` class
- Fix the `_EMITTER_REGISTRY`/`_EMITTER_MAP` name drift in
  `docs/reference/API.md` (~line 9583) while this area is touched

## Acceptance criteria

- `ll-adapt --host <x>` emits a working MCP config snippet for that host.
- Emitted config correctly references the `ll-mcp` entry point.
- If a `"claude-code"` host key is added, `HOST_CAPABILITIES` and
  `_EMITTER_MAP` stay in parity (`test_verify_host_map.py`).


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-09_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 67/100 → MODERATE

### Concerns
- Implementation Step 1 defers a core design decision to coding time: whether a new `"claude-code"` host key is registered in `_EMITTER_MAP`/`HOST_CAPABILITIES` for `.mcp.json` emission, or whether only the Codex TOML path is implemented this pass. Half the acceptance criteria are conditional on this branch. Resolve the decision before or very early in implementation, since it determines whether `capabilities.py`, `HOST_COMPATIBILITY.md`, `test_verify_host_map.py`'s hard-coded host set, and a new `TestResolveEmitterClaudeCode` test class are in scope at all.
- Soft dependency risk (non-blocking): `FEAT-3132` is marked `done` at the tracker layer but was decomposed rather than implemented — the `ll-mcp` entry point does not yet exist in `pyproject.toml` (`FEAT-3135` is `deferred`). The issue correctly scopes around this by testing emission mechanics against a literal `"ll-mcp"` string, but end-to-end verification that the emitted config actually launches a working server is not possible until `FEAT-3135` lands.
- `format-check` flags missing standard FEAT template sections (Acceptance Criteria heading casing, Current/Expected Behavior, Use Case, Impact) — a template-compliance gap, not a content gap, but worth a pass through `/ll:format-issue` if strict template conformance matters here.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-08-09
- **Reason**: Issue too large for single session (size score 9/11, Very
  Large); the parent also deferred a core design decision (whether to
  register a new `"claude-code"` host key) to implementation time, and
  splitting by host resolves that ambiguity by making the Claude Code path
  its own explicitly optional/deferrable child.

### Decomposed Into
- FEAT-3138: `ll-adapt --host codex`: emit MCP config TOML snippet for
  `ll-mcp`
- FEAT-3139: `ll-adapt --host claude-code`: register host and emit
  `.mcp.json` for `ll-mcp`

## Session Log
- `/ll:issue-size-review` - 2026-08-09T08:53:40 - `1f6bc67b-133e-4fd3-8a20-5c586fca9c77.jsonl`
- `/ll:confidence-check` - 2026-08-09T08:50:42 - `8a0425ea-3119-4b42-9f68-977b5a05a593.jsonl`
- `/ll:verify-issues` - 2026-08-09T08:47:50 - `42d3b075-beb3-4887-b042-062965c7836c.jsonl`
- `/ll:refine-issue` - 2026-08-09T08:44:32 - `216f962f-ad96-4ead-bc0d-f4bb715f43fa.jsonl`
- `/ll:refine-issue` - 2026-08-09T08:44:26 - `216f962f-ad96-4ead-bc0d-f4bb715f43fa.jsonl`
- `/ll:verify-issues` - 2026-08-09T08:38:53 - `d572feda-609f-43d0-ae78-a9cd63fd239a.jsonl`
- `/ll:wire-issue` - 2026-08-09T08:33:56 - `056f9f80-cf4f-4302-81fa-7245192e4d09.jsonl`
- `/ll:refine-issue` - 2026-08-09T08:23:50 - `aa4a443a-3d08-4ead-9eb5-4255062b3067.jsonl`
- `/ll:issue-size-review` - 2026-08-09T06:59:29 - `1a2b4d88-27a6-4756-bc3a-7bce0e10a356.jsonl`
