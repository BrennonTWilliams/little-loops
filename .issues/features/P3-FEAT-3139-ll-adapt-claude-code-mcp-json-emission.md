---
id: FEAT-3139
title: 'll-adapt --host claude-code: register host and emit .mcp.json for ll-mcp'
type: FEAT
priority: P3
status: done
discovered_date: '2026-08-09'
completed_at: '2026-08-09T10:56:19Z'
labels:
- multi-host
- mcp
parent: FEAT-3133
relates_to:
- FEAT-3128
- FEAT-3132
- FEAT-3138
depends_on:
- FEAT-3138
decision_needed: false
verify_verdict: VALID
confidence_score: 98
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# FEAT-3139: ll-adapt --host claude-code: register host and emit .mcp.json for ll-mcp

## Summary

`ll-adapt --host claude-code` learns to emit a `.mcp.json` snippet for the
`ll-mcp` server, referencing the `ll-mcp` entry point. This registers a new
`"claude-code"` host key in `_EMITTER_MAP`/`HOST_CAPABILITIES` — no such key
exists today (only `codex`, `gemini`, `omp`, `kimi-code`) — resolving the
design decision FEAT-3133's confidence-check flagged as deferred.

FEAT-3138 (Codex TOML path) is done and already added the `emit_mcp_config`
method to the `HostEmitter` Protocol and the `process_mcp_config()`
traversal function this issue reuses; this issue only adds the
Claude-Code-specific emitter and host registration.

## Parent Issue

Decomposed from FEAT-3133: `ll-adapt --host`: emit MCP config snippet for
`ll-mcp`. Split so the Claude Code `.mcp.json` path — which requires
registering a brand-new host key and touches capability parity tests and
docs — is tracked and can be deferred independently of the Codex path
(FEAT-3138).

## Current Behavior

`ll-adapt --host claude-code` is not a recognized host — `"claude-code"` is
absent from `_EMITTER_MAP` in `adapters/core.py`. It is also absent from
`HOST_CAPABILITIES` in `adapters/capabilities.py`. As a result,
`resolve_emitter("claude-code")` raises and no `.mcp.json` snippet for
`ll-mcp` can be emitted for Claude Code projects.

## Expected Behavior

`ll-adapt --host claude-code` emits a `.mcp.json` snippet at the project
root registering the `ll-mcp` server, merging into (not overwriting) any
existing `mcpServers` entries, following the same dry-run/apply contract as
the other host emitters.

## Use Case

Consuming projects that install little-loops via the Claude Code plugin
path need `.mcp.json` populated with the `ll-mcp` server entry so Claude
Code can discover and launch `ll-mcp` without manual JSON editing.

## Impact

Without this, Claude Code users of little-loops have no automated path to
register `ll-mcp` — they'd have to hand-write `.mcp.json`, which is
error-prone (risk of clobbering existing `mcpServers` entries) and
undocumented.

## Status

Open — not yet implemented. Its dependency has been resolved (see
`depends_on` in frontmatter).

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

Research surfaced one concrete decision the implementer needs before writing
`ClaudeCodeEmitter.emit_mcp_config`: where does the `.mcp.json` file get
written, given `process_mcp_config()` only ever hands the emitter
`meta["output_dir"] = plugin_root / config_dir` (`cli/adapt.py:125-126,140-142`)
and `.mcp.json` must live at the project root, not inside a per-host config
subdirectory (and `config_dir=".claude"` would itself trip
`test_text_utils.py::TestMirrorPrefixes`).

**Option A**: Give the new `HostCapabilityEntry` a `config_dir` of `"."`
(project root). Since `claude-code` needs no skill/command/agent adaptation
(those flow through the plugin marketplace natively — this entry only
implements `emit_mcp_config`, stubbing the other three `emit_*` methods as
`"skipped"` the way `gemini`/`omp`/`kimi` already stub `emit_mcp_config`),
`config_dir` is otherwise unused for this host, so pointing it at the project
root only affects the one method that's actually implemented.

> **Selected:** Option A — reuses the existing `meta["output_dir"]` threading
> with no `HostCapabilityEntry` schema change; scored higher on both
> consistency and simplicity than Option B.

**Option B**: Add a distinct field to `HostCapabilityEntry` (e.g.
`mcp_config_path: str | None = None` — must carry a default per the
dataclass's field-ordering constraint) that `ClaudeCodeEmitter.emit_mcp_config`
reads directly, ignoring `meta["output_dir"]` entirely and resolving the
target path itself (e.g. relative to `plugin_root`, the project root).

**Recommended**: Option A — it reuses the existing `meta["output_dir"]`
threading `process_mcp_config()` already provides to every emitter, requires
no `HostCapabilityEntry` schema change, and the risk case (some future
`claude-code` skill/command/agent emission wanting a real `.claude` output
directory) doesn't exist today per the doc's own claim that Claude Code needs
"no adapter-side entry at all" for those artifact types.

### Decision Rationale

**Selected: Option A** (`config_dir="."`, reuse `meta["output_dir"]`).

Codebase evidence from parallel `codebase-pattern-finder` agents confirmed the
issue's own inline recommendation. Option A reuses the existing
`plugin_root / config_dir` → `meta["output_dir"]` threading that
`process_mcp_config()` already provides to every emitter (`adapters/core.py:
488-525`), requiring zero `HostCapabilityEntry` schema changes; pathlib
collapses `plugin_root / "."` to `plugin_root`, giving the correct
project-root path with no extra normalization code. Option B has no
precedent in this codebase — every existing emitter (`codex.py`, the
`gemini`/`omp`/`kimi` stubs) reads exclusively from `meta`, never from
`HostCapabilityEntry` fields directly, so a `mcp_config_path` field bypassing
`meta["output_dir"]` would introduce a novel access pattern for no benefit.

Option A does carry one documented risk: `config_dir="."` is a novel value
(all four existing hosts use dotted subdirectory names), which adds an inert
`"./"` entry to `_mirror_prefixes()` (`text_utils.py:146`) and would collapse
`agent_output_dir` onto the source `agents/` dir if `claude-code`'s
`emit_agent` is ever un-stubbed. Neither risk is live today since claude-code
implements only `emit_mcp_config`; flagged here for whoever un-stubs the
other `emit_*` methods later.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 2/3 | 1/3 |
| Simplicity | 3/3 | 1/3 |
| Testability | 3/3 | 2/3 |
| Risk | 2/3 | 2/3 |
| **Total** | **10/12** | **6/12** |

## Integration Map

### Files to Modify
- `scripts/little_loops/adapters/core.py` — `_EMITTER_MAP` (around lines
  51-56) needs a new `"claude-code"` key.
- A new Claude Code emitter (e.g. `scripts/little_loops/adapters/
  claude_code.py`) implementing the `HostEmitter` Protocol's
  `emit_mcp_config` (added by FEAT-3138) for `.mcp.json` output.
- `scripts/little_loops/adapters/capabilities.py` — `HOST_CAPABILITIES`
  (around lines 44-61) needs a new `"claude-code"` entry with an
  MCP-config-path field; `HostCapabilityEntry` is a non-kw-only frozen
  dataclass with defaulted trailing fields, so any new field must itself
  carry a default (or be added after the last defaulted field).

### Conventions in Force
- Repo's own root `.mcp.json` is `{"mcpServers": {}}` — an empty-but-present
  skeleton, not truly absent. The Claude Code emitter needs read-modify-write
  (merge into the existing `mcpServers` key), not blind overwrite, since a
  consuming project's `.mcp.json` may already carry unrelated server
  entries.
- `scripts/little_loops/file_utils.py:35-57` — `atomic_write_json(path:
  Path, data: Any) -> None` is an existing JSON-writing utility (used
  elsewhere, e.g. `init/writers.py:merge_settings()`), though no `adapters/`
  emitter uses it yet.
  `init/writers.py:merge_settings()` (lines 349-404) is the closest
  existing precedent for a *merging* (not overwriting) JSON config writer,
  including its idempotency approach (strip-then-readd canonical entries
  while preserving user-added ones) — see `TestMergeSettings`
  (`test_init_core.py:944-1013`) for the corresponding test shape.
- `mcp_call.py:_load_mcp_config`/`_find_server_config` (lines 38-70)
  require each `mcpServers` entry to have a string `"command"` (not an argv
  list) plus optional `"args"`/`"env"`. A minimal valid entry is
  `{"mcpServers": {"ll-mcp": {"command": "ll-mcp"}}}`.
- `test_text_utils.py::TestMirrorPrefixes` (~lines 361-370) asserts
  `.claude/` is never in `_mirror_prefixes()`. If the new
  `HostCapabilityEntry.config_dir` for `"claude-code"` is ever set to
  `.claude`, this invariant breaks and needs deliberate handling.

_Wiring pass added by `/ll:wire-issue`:_
- Confirmed safe with the selected `config_dir="."`: `_mirror_prefixes()`
  (`text_utils.py:131-146`) will emit an inert `"./"` entry, but its only
  real consumer, `suffix_match_candidates()` (`text_utils.py:291`), matches
  against repo-relative paths from `git ls-files -z` that never carry a
  leading `"./"` segment — no breakage. `TestMirrorPrefixes` (`test_text_utils.py:
  361-370`) re-derives its expected set from `HOST_CAPABILITIES` inline
  rather than hardcoding it, so it self-updates and needs no edit.
- `cli/adapt.py:130` — `agent_output_dir = plugin_root / config_dir /
  "agents"` resolves, under `config_dir="."`, to the *same path* as the
  source `agents_dir` the loop reads from (`cli/adapt.py:94`). Currently
  inert only because claude-code's `emit_agent` is stubbed `"skipped"`
  (never touches `output_dir`); whoever un-stubs `emit_agent` for
  claude-code later must route around this exact source/output collision,
  not just the general "`config_dir='.'` is novel" risk already noted above.
- `cli/verify_host_map.py::_check_runtime_contradiction()` (lines 100-128)
  computes `shared_hosts = set(HOST_CAPABILITIES) & set(_HOST_RUNNER_REGISTRY)`
  — currently empty, so its inner comparison loop never executes. Adding
  `"claude-code"` to `HOST_CAPABILITIES` makes `shared_hosts` non-empty for
  the first time (since `host_runner._HOST_RUNNER_REGISTRY` already has a
  `"claude-code"` entry, `host_runner.py:294`), activating a previously-
  dormant code path. Confirmed still passes today because
  `HostCapabilityEntry`'s fields share zero names with `host_runner.
  HostCapabilities`'s fields, so `shared_fields` stays empty — but
  `TestCheckRuntimeContradiction::test_current_tree_has_no_contradiction`
  (`test_verify_host_map.py:70-72`) now exercises a genuinely different
  branch than it did before this feature.

### Tests
- `scripts/tests/test_verify_host_map.py::TestHostCapabilities::
  test_keys_match_emitter_map` — asserts `set(HOST_CAPABILITIES) ==
  set(_EMITTER_MAP)`; both maps must gain the `"claude-code"` key together.
- `scripts/tests/test_verify_host_map.py::TestAdapterSectionHosts::
  test_finds_documented_hosts` (~line 48-51) — hard-codes `hosts ==
  {"codex", "gemini", "omp", "kimi-code"}`; update to include
  `"claude-code"` in the same change as the `HOST_COMPATIBILITY.md` table
  row, or `test_current_tree_has_no_mismatch` (~line 55-56) fails.
- New `TestResolveEmitterClaudeCode` class in `test_adapters.py`, mirroring
  `TestResolveEmitterGemini` (lines 881-886):
  `isinstance(resolve_emitter("claude-code"), <ClaudeCodeEmitter>)` +
  `isinstance(resolve_emitter("claude-code"), HostEmitter)`.
- Extend `scripts/tests/fixtures/adapt/mcp_cases.json` (created by
  FEAT-3138) with a `claude-code` case, following the existing per-host
  `<host>_result`/`<host>_<artifact>` pair shape.
- New emitter unit test class shaped like `TestCodexEmitterEmitAgent`
  (`test_adapters.py:471-602`): creates-file, dry-run does not write,
  merges into an existing non-empty `mcpServers` key without clobbering
  unrelated entries, idempotent on repeat calls.
- The new `.mcp.json` shape should assert against
  `test_mcp_call.py`'s `_VALID_MCP_CONFIG` fixture shape (lines ~22-29:
  `{"mcpServers": {"<name>": {"command": ..., "args": [...]}}}`) via
  `json.loads()` + dict-key checks — no JSON-Schema library is a
  dependency (`test_config_schema.py:77-78`).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_adapt_golden_corpus.py` has **no MCP-config golden
  test for any host today** (confirmed by full read — its docstring scopes
  to skill/command/agent only; MCP emission postdates this module). Add a
  new `mcp_config_cases.json` fixture plus
  `test_claude_code_mcp_config_emission_matches_golden_corpus`, following
  the established `<kind>_cases.json` / `test_<host>_<kind>_emission_
  matches_golden_corpus` naming convention (`test_codex_skill_emission_
  matches_golden_corpus`, line 49, is the pattern). Per this module's own
  stated scope (snapshot every emitter's real output byte-for-byte), also
  add the retroactive `test_codex_mcp_config_emission_matches_golden_corpus`
  for the already-merged `CodexEmitter.emit_mcp_config` — it was never
  added when FEAT-3138 landed.
- New emitter test class (item above, mirroring `TestCodexEmitterEmitMcpConfig`)
  should additionally mirror two `TestMergeSettings` sub-cases
  (`test_init_core.py:970-978`, `1008-1016`) not implied by the generic
  create/dry-run/merge/idempotent shape: (1) a *sibling* `mcpServers` entry
  (e.g. `{"mcpServers": {"other-server": {"command": "foo"}}}`) survives
  the merge untouched; (2) a same-key-different-value collision (an
  existing `"ll-mcp"` entry with a different `"command"` value already
  present) is handled deliberately, not silently overwritten or silently
  kept-stale.
- New `TestMirrorPrefixes` case for `config_dir="."` — no existing case
  covers this value (only the four hosts' dotted subdirs and the `.claude/`
  exclusion are tested); add one asserting `"./"` behaves as inert per the
  Conventions note above.

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` (~lines 217-230) — the `##
  Adapter Host Capabilities` section intro states, verbatim, that
  `claude-code`/`opencode`/`pi` "have no adapter-side entry at all" — this
  directly contradicts registering a `"claude-code"` key and must be
  rewritten, plus a new table row (pattern at lines ~232-237) added.
- `docs/ARCHITECTURE.md` (~lines 1308-1314, "Host Adapter Capability Map")
  — add `"claude-code"` to the enumerated host list.
- `docs/reference/CLI.md` (~line 4134, `--host HOST` row) — add
  `claude-code` to the host examples.
- `scripts/little_loops/cli/adapt.py` — `--host` argparse help string
  (~lines 52-53) and epilog examples (~lines 41-47) — add a
  `--host claude-code` mention.
- `README.md` (~lines 74-79) — has onboarding blurbs for `--host codex
  --apply` and `--host kimi-code --apply`; add an equivalent Claude Code
  blurb.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/adapters/capabilities.py` module docstring
  (lines 4-10) — lists `_EMITTER_MAP`'s hosts as `"codex"`, `"gemini"`,
  `"omp"` (already stale — omits `kimi-code` too); update to the full
  5-host list in the same change.
- `scripts/little_loops/adapters/core.py` — `resolve_emitter()` docstring's
  `Args: host:` line (~line 64) enumerates `"codex"`, `"gemini"`, `"omp"`,
  `"kimi-code"` in prose; add `"claude-code"`. (The runtime error string at
  line 74 is generated dynamically from `_EMITTER_MAP` and needs no edit.)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **FEAT-3138 landed on `main` (commit `0dda61ce`)** — this issue's dependency
  is resolved. `HostEmitter` Protocol (`adapters/core.py:28-43`) already
  declares `emit_mcp_config(self, meta: dict) -> str`; `process_mcp_config()`
  already exists at `adapters/core.py:488-525` and is already wired at
  `cli/adapt.py:138-145` inside `main_adapt()` for every registered host —
  a `"claude-code"` key added to `_EMITTER_MAP` needs no change there to be
  picked up. `gemini.py`/`omp.py`/`kimi.py` already carry 3-line
  `emit_mcp_config` stubs returning `"skipped"`; `CodexEmitter.emit_mcp_config`
  (`adapters/codex.py:375-404`) is the only real implementation today, and it
  writes TOML via blind-overwrite-with-marker (`_MARKER`/`_LL_GENERATED_MARKERS`,
  `codex.py:22-30`), not a JSON merge — no emitter in this codebase currently
  performs a JSON key-merge write. `_EMITTER_MAP`/`HOST_CAPABILITIES` today
  hold exactly `{codex, gemini, omp, kimi-code}` (confirmed by direct read).
- **`ll-mcp` entry point is not yet present in the tree.** `scripts/pyproject.toml`'s
  `[project.scripts]` (line 67) has no `ll-mcp = ...` entry, and no
  `scripts/little_loops/mcp*` package exists. This is scoped to FEAT-3135
  (status: Deferred, not FEAT-3139) — the `.mcp.json` snippet this issue emits
  will reference a binary that isn't registered yet; this doesn't block
  implementing the emitter itself.
- **`output_dir`/`config_dir` routing conflict for `.mcp.json`'s location.**
  `process_mcp_config()` builds `meta["output_dir"]` as `plugin_root /
  config_dir` (`cli/adapt.py:125-126,140-142`) and passes it into
  `emit_mcp_config(meta)`. But `.mcp.json` must live at the **project root**,
  not inside a host config subdirectory — and `config_dir=".claude"` for the
  new host entry would itself violate `test_text_utils.py::TestMirrorPrefixes`,
  which asserts `.claude/` never appears in `_mirror_prefixes()`. See the
  Option A/B decision recorded under Proposed Solution.
- **Exact current code** (`HostCapabilityEntry`, `adapters/capabilities.py:44-61`):
  `@dataclass(frozen=True)` with five required positional fields (`host`,
  `config_dir`, `skill_output_format`, `command_output_format`,
  `agent_output_format`) followed by defaulted trailing fields
  (`frontmatter_fields_read`, `agents`, `commands`, `hooks`, `subagents`). A
  new field must carry its own default or precede `frontmatter_fields_read`.
- **`HOST_COMPATIBILITY.md`'s intro sentence must be rewritten, not just have a
  row added.** It currently states, verbatim: "the two host key sets are not
  congruent — `claude-code`/`opencode`/`pi` have no adapter-side entry at all"
  (~line 217-230) — directly contradicted the moment `"claude-code"` is added
  to `HOST_CAPABILITIES`.
- **Naming ambiguity, unresolved by precedent**: `host_runner.HostCapabilities`
  (a separate runtime-invocation surface, documented in
  `capabilities.py`'s own module docstring lines 12-24) already has a
  `claude-code` key. No existing adapter-side host has previously mirrored a
  `host_runner` key that also happens to be `claude-code`/`opencode`/`pi`, so
  there's no precedent confirming the new `_EMITTER_MAP`/`HOST_CAPABILITIES`
  key should reuse that exact string (as opposed to a suffixed variant, the
  way `kimi-code` was suffixed per `core.py:49-51`'s comment). Likely reuse
  the exact string given the two surfaces already agree in every other case,
  but flagging since it is not mechanically enforced anywhere today.
- **Test/fixture anchors confirmed at exact locations**: `TestCodexEmitterEmitMcpConfig`
  (`test_adapters.py:655-707`, the 8-test shape: creates-file, marker/content
  checks, dry-run-no-write, returns-adapted, user-authored-not-overwritten,
  up-to-date-skipped, idempotent) is the closest existing test-class shape to
  mirror. `scripts/tests/fixtures/adapt/` currently has only
  `skill_cases.json`/`command_cases.json`/`agent_cases.json` — no
  `mcp_cases.json` exists yet even for the already-merged Codex path, and
  `test_adapt_golden_corpus.py` has no MCP-config test function at all today.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

### Types

- `HostCapabilityEntry` (`adapters/capabilities.py:44-61`) — no new field
  required if Proposed Solution's Option A is taken; a new `"claude-code"`
  entry is constructed with the five required positional fields plus
  `config_dir="."`.

### Signatures

- `emit_mcp_config(self, meta: dict) -> str` — existing `HostEmitter` Protocol
  method (`adapters/core.py:28-43`, `@runtime_checkable`); the new
  `ClaudeCodeEmitter` implements this, following the same
  `meta["output_dir"]`/`meta["apply"]`/`meta["quiet"]` contract every other
  emitter already reads (e.g. `codex.py:375-379`).
- `process_mcp_config(emitter: HostEmitter, output_dir: Path, apply: bool, quiet: bool) -> tuple[int, int, int]`
  (`adapters/core.py:488-525`, already merged, unchanged by this issue) —
  calls `emitter.emit_mcp_config(meta)` exactly once per host, interprets
  `"adapted"`/`"skipped"`/anything-else (incl. caught `AdapterError`) into the
  `(adapted, skipped, errors)` triple.
- `resolve_emitter(host: str) -> HostEmitter` (`adapters/core.py:60-77`,
  unchanged) — a `"claude-code"` entry in `_EMITTER_MAP` is the only wiring
  this function needs; no code inside it changes.
- `atomic_write_json(path: Path, data: Any) -> None`
  (`file_utils.py:35-57`) — the emitter's write primitive: mkdir-parents,
  `json.dumps(..., indent=2, allow_nan=False)`, defensive round-trip
  validation, atomic `os.replace`.

### Call Path

`main_adapt()` (`cli/adapt.py:86,140`) -> `resolve_emitter("claude-code")` ->
`ClaudeCodeEmitter()` ; `main_adapt()` -> `process_mcp_config(emitter,
mcp_output_dir, apply, quiet)` -> `ClaudeCodeEmitter.emit_mcp_config(meta)` ->
read `<project_root>/.mcp.json` if it exists (else `{}`, matching
`merge_settings()`'s `JSONDecodeError`-tolerant load at
`init/writers.py:349-361`) -> merge `data.setdefault("mcpServers",
{})["ll-mcp"] = {"command": "ll-mcp"}` (idempotency sweep: skip the write
if already present and identical, matching `merge_settings()`'s
strip-then-readd shape) -> `atomic_write_json(path, data)` when `apply` is
true, else print a `DRY` line and return `"adapted"`/`"skipped"` without
writing.

### Decision Rules

N/A — no new gap kind, gate, or threshold; this issue registers a host and
implements one Protocol method following the existing `emit_mcp_config`
contract. The one open decision (where the file is written) is recorded as
an Option A/B block under Proposed Solution, not a runtime decision rule.

## Implementation Steps

1. Register `"claude-code"` in `_EMITTER_MAP` (`adapters/core.py:51-56`)
   and add a matching entry to `HOST_CAPABILITIES`
   (`adapters/capabilities.py`).
2. Implement a new Claude Code emitter's `emit_mcp_config` for
   `.mcp.json` output, using merge-not-overwrite semantics (precedent:
   `init/writers.py:merge_settings()`; utility: `file_utils.py:
   atomic_write_json`).
3. Update `docs/reference/HOST_COMPATIBILITY.md`, `docs/ARCHITECTURE.md`,
   `docs/reference/CLI.md`, `cli/adapt.py`'s help text, and `README.md` to
   list the new host.
4. Update `test_verify_host_map.py`'s hard-coded host set alongside the
   `HOST_COMPATIBILITY.md` table row.
5. `ll-adapt --host claude-code` emits a working `.mcp.json` snippet,
   verified to merge into an existing non-empty `mcpServers` key without
   clobbering unrelated entries.
6. `python -m pytest scripts/tests/` passes, including new coverage in
   `test_adapters.py` / `test_adapt_golden_corpus.py` /
   `test_verify_host_map.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/adapters/capabilities.py`'s module docstring
  (lines 4-10) and `scripts/little_loops/adapters/core.py`'s
  `resolve_emitter()` docstring (~line 64) — both enumerate the adapter
  hosts in prose and are already stale/would go stale.
- Add `mcp_config_cases.json` + `test_claude_code_mcp_config_emission_
  matches_golden_corpus` (and retroactively `test_codex_mcp_config_
  emission_matches_golden_corpus`) to `test_adapt_golden_corpus.py` — no
  MCP-config golden coverage exists for any host today.
- Add a `TestMirrorPrefixes` case for `config_dir="."` (`test_text_utils.py`)
  and two merge-collision test cases on the new emitter test class (sibling
  `mcpServers` entry survives; same-key-different-value collision handled
  deliberately) — see Tests subsection above.

## Acceptance Criteria

- `ll-adapt --host claude-code` emits a working `.mcp.json` snippet
  referencing the `ll-mcp` entry point, merging into (not overwriting) any
  existing `mcpServers` content.
- `HOST_CAPABILITIES` and `_EMITTER_MAP` stay in parity
  (`test_verify_host_map.py::test_keys_match_emitter_map`).
- `test_verify_host_map.py::test_finds_documented_hosts` and
  `test_current_tree_has_no_mismatch` pass with `"claude-code"` included.

## Session Log
- `/ll:manage-issue` - 2026-08-09T10:56:00 - `e1d4f818-d458-43e9-ae22-d9b7331001a9.jsonl`
- `/ll:ready-issue` - 2026-08-09T10:22:50 - `eb60483b-ce92-4c2e-b77c-624ccea159fa.jsonl`
- `/ll:confidence-check` - 2026-08-09T10:18:40 - `1d26a521-bd65-436b-a26e-e0448eba5876.jsonl`
- `/ll:verify-issues` - 2026-08-09T10:16:25 - `369ad1da-71ff-4e2c-8952-73c0022f4bf9.jsonl`
- `/ll:wire-issue` - 2026-08-09T10:14:50 - `2ceaacd5-0d47-4497-a2ae-1cb97e558de9.jsonl`
- `/ll:decide-issue` - 2026-08-09T10:04:30 - `bed6d3b5-19f5-4215-8ca0-771eb84e1c1b.jsonl`
- `/ll:refine-issue` - 2026-08-09T10:00:14 - `d1b8e763-54c0-4fef-9041-7e66e0bae44f.jsonl`
- `/ll:issue-size-review` - 2026-08-09T08:53:40 - `1f6bc67b-133e-4fd3-8a20-5c586fca9c77.jsonl`
