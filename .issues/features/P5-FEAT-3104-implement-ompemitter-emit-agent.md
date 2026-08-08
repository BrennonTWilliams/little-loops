---
id: FEAT-3104
title: Implement `OmpEmitter.emit_agent` against the FEAT-2797 `.omp/agents/` contract
type: feature
status: done
priority: P5
parent: FEAT-2787
depends_on:
- FEAT-2260
relates_to:
- FEAT-2797
labels:
- host-compat
- omp
- adapters
verify_verdict: VALID
completed_at: '2026-08-08T11:24:04Z'
confidence_score: 100
outcome_confidence: 85
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 23
---

# FEAT-3104: Implement `OmpEmitter.emit_agent` against the FEAT-2797 `.omp/agents/` contract

## Summary

Implement `OmpEmitter.emit_agent` in `scripts/little_loops/adapters/omp.py`,
replacing its raising stub, plus the matching `HOST_CAPABILITIES["omp"]`
agent fields and tests. Unlike skills/commands (which need FEAT-3103 first),
the agent-artefact format is already documented: FEAT-2797 established that omp
discovers agents via `.omp/agents/` with a frontmatter `output:` key (not a
reused `.claude/agents`/`.codex/agents` path), so this child is unblocked
and can start immediately.

## Current Behavior

`OmpEmitter.emit_agent` (`scripts/little_loops/adapters/omp.py:27-28`)
unconditionally raises `AdapterError(_REMEDIATION)` for every agent, so
`ll-adapt --host omp --apply` cannot process any agent artifacts, and
`HOST_CAPABILITIES["omp"].agents` is `False`.

## Expected Behavior

`OmpEmitter.emit_agent` writes valid `.omp/agents/` artefacts per the
FEAT-2797 contract (native format mirroring `KimiEmitter.emit_agent`),
returning `"adapted"`/`"skipped"` per the shared emitter idempotency
contract. `HOST_CAPABILITIES["omp"].agents` is `True` and
`ll-verify-host-map` passes.

## Use Case

As an omp user, I want `ll-adapt --host omp --apply` to emit real
`.omp/agents/` files instead of raising, so my ll-authored agents are
discoverable by the omp host without a bespoke hand-written step.

## Parent Issue

Decomposed from FEAT-2787: Implement the `omp` host adapter (all
`OmpEmitter` methods currently raise).

## Location

- **File**: `scripts/little_loops/adapters/omp.py` — `OmpEmitter.emit_agent`
  (currently `raise AdapterError(_REMEDIATION)`)
- **File**: `scripts/little_loops/adapters/capabilities.py` —
  `HOST_CAPABILITIES["omp"]` entry (lines 102-118 at discovery), agent-related
  fields only: `config_dir`, `agent_output_format`, `frontmatter_fields_read`
  (if agent-specific keys apply), `agents=True`

## Proposed Solution

1. Implement `OmpEmitter.emit_agent(self, agent_meta: dict) -> str`, writing
   to `.omp/agents/` and populating the `output:` frontmatter key per
   FEAT-2797's documented contract (`docs/task-agent-discovery.md:37,60`).
   Resolve the open agent-routing fork noted in FEAT-2787's research: decide
   whether this is a genuine native format (mirror `KimiEmitter.emit_agent`,
   `adapters/kimi.py:127-158`) or delegates to `core._emit_degraded_agent`
   (the `GeminiEmitter` pattern) — FEAT-2797's contract points toward a
   native format (real `.omp/agents/` output path + real frontmatter key),
   so mirror the Kimi shape unless FEAT-2797 says otherwise.
   Follow the shared idempotency shape used by all three existing emitters:
   compute full target content, return `"skipped"` if the on-disk file
   already matches, else write and return `"adapted"`.
2. Update `HOST_CAPABILITIES["omp"]` (`capabilities.py`): set `config_dir`
   to omp's real config directory, `agent_output_format` to a descriptive
   string (mirroring the `codex`/`kimi-code` entries), populate
   `frontmatter_fields_read` for the `output:` key, and set `agents=True`.
3. Fix `scripts/little_loops/cli/verify_host_map.py:_check_emitter_agreement()`
   (lines 163-168): it currently hard-fails the moment
   `HOST_CAPABILITIES["omp"].agents` is truthy
   (`if omp_entry is not None and (omp_entry.agents or omp_entry.commands):
   raise ...`). Update this check now that `agents=True` is real, and fix
   the module docstring (lines 19-21) asserting "`omp` must stay
   `False`/`False`" to match.
4. Update `scripts/tests/test_verify_host_map.py::TestHostCapabilities::
   test_omp_fully_unimplemented` (lines 34-37): the `entry.agents is False`
   assertion no longer holds; `entry.commands is False` still holds (owned
   by FEAT-3105).
5. Update `scripts/tests/test_adapters.py:940-943`'s class-level docstring
   ("`omp` is explicitly excluded — its emitter is an all-stub") — no
   longer accurate once `emit_agent` is real.
6. Add `OmpEmitter.emit_agent` test coverage in `scripts/tests/
   test_adapters.py`, mirroring `TestKimiEmitterEmitAgent` (native-subagent
   shape, `test_not_degraded_no_inline_preamble`) or
   `TestCodexEmitterEmitAgent` (including
   `test_user_authored_file_not_overwritten`, lines 471-603) — whichever
   matches the routing decision made in step 1.
7. Update `docs/reference/HOST_COMPATIBILITY.md`'s "Adapter Host
   Capabilities" table (agent column only) and `docs/reference/API.md`'s
   agent-related mentions of the `OmpEmitter` stub.

## Acceptance Criteria

- `OmpEmitter.emit_agent` produces valid `.omp/agents/` artefacts per the
  FEAT-2797 contract and returns `"adapted"`/`"skipped"` per the shared
  emitter contract
- `ll-adapt --host omp --apply` no longer raises `AdapterError` on agent
  processing specifically (skill/command may still raise until FEAT-3105)
- `HOST_CAPABILITIES["omp"].agents` is `True` and `ll-verify-host-map`
  passes with the updated `_check_emitter_agreement()` logic
- Tests mirror the existing codex/kimi adapter agent test coverage
  (idempotency, dry-run, user-authored-file-not-overwritten if applicable)

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/adapters/omp.py` — `OmpEmitter.emit_agent` (lines ~16-28) currently `raise AdapterError(_REMEDIATION)`; no shared helpers (`_select_frontmatter_fields`, `Path`, `HOST_CAPABILITIES`) imported yet, unlike every other emitter module
- `scripts/little_loops/adapters/capabilities.py` — `HOST_CAPABILITIES["omp"]` entry (lines 102-118): current values `config_dir=None`, `skill_output_format=None`, `command_output_format=None`, `agent_output_format=None`, `frontmatter_fields_read=()`, `agents=False`, `commands=False`, `subagents="none"`
- `scripts/little_loops/cli/verify_host_map.py` — `_check_emitter_agreement()` (lines 163-168) unconditionally errors when `omp_entry.agents or omp_entry.commands` is truthy; module docstring (lines 19-21) states the same "omp must stay False/False" invariant in prose
- `scripts/tests/test_verify_host_map.py` — `TestHostCapabilities::test_omp_fully_unimplemented` (lines 34-37) asserts `entry.agents is False`
- `scripts/tests/test_adapters.py` — `TestRealAgentsDegradedCoverageGuard` class docstring (~937-944) currently states "omp is explicitly excluded ... its emitter is an all-stub"; needs a new test class (`TestOmpEmitterEmitAgent`) mirroring `TestKimiEmitterEmitAgent` (~1232-1276) or `TestCodexEmitterEmitAgent` (472-603), matching whichever routing this issue's step 1 resolves to
- `docs/reference/HOST_COMPATIBILITY.md` — "Adapter Host Capabilities" table, agent column for `omp`
- `docs/reference/API.md` — `OmpEmitter` stub mentions

### Dependent Files (Callers/Importers)
- `scripts/little_loops/adapters/core.py:409-484` — `process_agents()` builds the `agent_meta` dict (`agent_name`, `agent_path`, `content`, `fm`, `output_dir`, `apply`, `quiet`) and calls `emitter.emit_agent(agent_meta)`; this is the only caller of `OmpEmitter.emit_agent`
- `scripts/little_loops/adapters/core.py:54` — `_EMITTER_MAP` registers `"omp": ("little_loops.adapters.omp", "OmpEmitter")`
- `scripts/little_loops/adapters/core.py:433-441` — `process_agents()`'s `degraded` flag is `True` only when `HOST_CAPABILITIES[emitter.name].subagents == "none"` **and** `agent_output_format is not None`; setting `agent_output_format` to a real string per Proposed Solution step 2 while leaving `subagents="none"` flips this to `True` and reroutes `omp` through `_emit_degraded_agent` instead of the native `OmpEmitter.emit_agent` just implemented — see Program Design → Decision Rules below

### Conventions in Force
- Native emitters compute full target content, then apply either a pure content-equality idempotency check before writing (`KimiEmitter.emit_agent`, `kimi.py:127-158` — no user-authored-file guard) or a generated-marker prefix check for user-authored-file detection (`CodexEmitter.emit_agent`, `codex.py:327-373`; `_emit_degraded_agent`, `core.py:220-271`) — evidence the two idempotency shapes coexist in this codebase and the issue's Proposed Solution step 1 must pick one to mirror
- `HOST_CAPABILITIES[host].frontmatter_fields_read` drives which frontmatter keys an emitter carries through via `_select_frontmatter_fields`, not private per-emitter regex/parsing code (ENH-2883 convention) — evidence: `kimi.py:41-43`'s `_fields_read()` helper

### Tests
- `scripts/tests/test_adapters.py:472-603` — `TestCodexEmitterEmitAgent`, including `test_user_authored_file_not_overwritten` (538-545) and `test_up_to_date_returns_skipped`/`test_idempotent` (547-557)
- `scripts/tests/test_adapters.py:1232-1276` — `TestKimiEmitterEmitAgent`, including `test_not_degraded_no_inline_preamble` (1254-1260) and `test_rerun_with_apply_skips_unchanged` (1273-1276) — no user-authored-file test exists here, since Kimi's native pattern has no such guard
- `scripts/tests/test_verify_host_map.py:34-37` — `test_omp_fully_unimplemented`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_adapters.py:1284-1308` — `TestResolveEmitterKimi::test_process_agents_does_not_route_kimi_to_degraded` — the pattern to mirror for a `TestResolveEmitterOmp` equivalent, verifying `process_agents(OmpEmitter(), ...)` routes to native `emit_agent` (not `_emit_degraded_agent`) once `subagents` is flipped per the Decision Rules note above; asserts `(adapted, skipped, errors) == (1, 0, 0)` and `"degraded mode" not in output` [Agent 3 finding]
- `scripts/tests/test_verify_host_map.py:71-103` — the `bad_map` negative-test fixtures in `TestCheckEmitterAgreement` encode `_check_emitter_agreement()`'s internal-consistency rules (e.g. `agents=True` + `subagents="none"` requires `agent_output_format is not None`; `subagents="native"` + `agents=False` is flagged) — the new omp capability combination (`agents=True`, `subagents="native"`, `agent_output_format=<str>`) must satisfy these rules or `test_current_tree_agrees` (line 68-69) and `TestMainVerifyHostMap::test_clean_state_returns_zero` (113-116) will regress [Agent 3 finding]
- `scripts/tests/test_adapters.py` — no test currently asserts `OmpEmitter().emit_agent(...)` raises `AdapterError` (confirmed via grep), so there is no raise-assertion test to delete; only `test_verify_host_map.py::test_omp_fully_unimplemented` needs rewriting [Agent 3 finding]

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — "Adapter Host Capabilities" table
- `docs/reference/API.md` — `OmpEmitter` mentions
- `docs/task-agent-discovery.md` does not exist in this repository (confirmed via glob) — FEAT-2797's own issue text (lines 55-74) is the only in-repo record of the `.omp/agents/` `output:` frontmatter contract; the path cited in FEAT-2797/FEAT-3104 is inside the upstream `can1357/oh-my-pi` repo, not this one

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_adapt_golden_corpus.py` — module docstring "Named exclusions" bullet (line 14: "`omp` — every `emit_*` method raises `AdapterError` unconditionally") and `test_omp_and_gemini_agent_excluded_from_byte_identity_claim`'s docstring (lines 196-203, same claim) become stale once `emit_agent` no longer raises; the assertion itself (`OmpEmitter().emit_skill({})` still raises, lines 209-210) stays correct since only `emit_agent` changes — narrow the prose to `emit_skill`/`emit_command` only [Agent 2/3 finding]
- `scripts/tests/fixtures/adapt/agent_cases.json` — `_comment` field (line 2: "omp is excluded (emitter raises unconditionally, nothing to snapshot)") repeats the same now-stale claim [Agent 2 finding]

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Types
- N/A — no new data types introduced; `agent_meta: dict` (keys `agent_name`, `agent_path`, `content`, `fm`, `output_dir`, `apply`, `quiet`) is the existing shared input contract built by `process_agents()` (`adapters/core.py:409-484`), identical across all emitters

### Signatures
- `OmpEmitter.emit_agent(self, agent_meta: dict) -> str` — target signature, matching `KimiEmitter.emit_agent` (`kimi.py:127-158`) and `CodexEmitter.emit_agent` (`codex.py:327-373`); returns `"adapted"` or `"skipped"` per the shared emitter contract
- `_select_frontmatter_fields(content: str, agent_name: str, fields: tuple[str, ...])` — existing helper Kimi's implementation uses to derive carried-through frontmatter from `HOST_CAPABILITIES[host].frontmatter_fields_read`; the same mechanism this issue's step 2 change to `frontmatter_fields_read` would feed

### Call Path
`process_agents()` (`adapters/core.py:409-484`) -> `OmpEmitter.emit_agent(agent_meta)` (`adapters/omp.py`) -> `_select_frontmatter_fields(...)` (frontmatter derivation, Kimi-style) -> write `output_dir / f"{agent_name}.md"` under `.omp/agents/`

### Decision Rules
- **Routing fork (already named in Proposed Solution step 1)**: mirror `KimiEmitter.emit_agent`'s native shape vs. delegate to `core._emit_degraded_agent` (the `GeminiEmitter` pattern). FEAT-2797's contract (native `.omp/agents/` path + real `output:` frontmatter key) points to the Kimi shape; the issue already recommends this.
- **New rule surfaced by this research, not currently listed in the issue's field list**: if the Kimi-mirroring route is taken, `HOST_CAPABILITIES["omp"].subagents` must also change from `"none"` to `"native"` alongside `agent_output_format`. `process_agents()`'s `degraded` flag (`core.py:433-441`) is `True` exactly when `subagents == "none"` **and** `agent_output_format is not None`. Proposed Solution step 2 lists only `config_dir`, `agent_output_format`, `frontmatter_fields_read`, `agents=True` as fields to update and omits `subagents`. Leaving `subagents="none"` while giving `agent_output_format` a real string flips `degraded=True` and silently reroutes every `omp` agent through `_emit_degraded_agent` instead of the just-implemented native `OmpEmitter.emit_agent` — the inverse of the routing decision step 1 makes. Escape hatch: none needed beyond setting `subagents="native"` in the same `capabilities.py` edit as `agent_output_format`; this is a completeness gap in step 2's field list, not a defect in the routing decision itself.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_adapt_golden_corpus.py` — narrow the module docstring's "Named exclusions" bullet and `test_omp_and_gemini_agent_excluded_from_byte_identity_claim`'s docstring to scope the "raises unconditionally" claim to `emit_skill`/`emit_command` only (`emit_agent` no longer raises)
- Update `scripts/tests/fixtures/adapt/agent_cases.json`'s `_comment` field to match the narrowed claim
- Add a `TestResolveEmitterOmp`-style test (mirroring `TestResolveEmitterKimi::test_process_agents_does_not_route_kimi_to_degraded`, `test_adapters.py:1284-1308`) confirming `process_agents` routes omp to native `emit_agent`, not `_emit_degraded_agent`
- Confirm the new omp capability combination (`agents=True`, `subagents="native"`, `agent_output_format=<str>`) satisfies `_check_emitter_agreement()`'s internal-consistency rules exercised by `test_verify_host_map.py:71-103`'s `bad_map` fixtures, so `test_current_tree_agrees` and `TestMainVerifyHostMap::test_clean_state_returns_zero` keep passing

## Impact

- **Scope**: Medium

## Status

Open — implementation not started.

## Session Log
- `/ll:manage-issue` - 2026-08-08T11:23:32 - `e081ebcd-af7d-4278-af71-cfbc169b8afa.jsonl`
- `/ll:ready-issue` - 2026-08-08T11:09:26 - `13c8df88-e281-41fb-866d-c15665a142f2.jsonl`
- `/ll:confidence-check` - 2026-08-08T11:07:09 - `4c2d0f57-1d13-4428-99b9-201af1815cbc.jsonl`
- `/ll:verify-issues` - 2026-08-08T11:05:46 - `7e61d5b0-9462-4e4c-9164-f70adf814cf1.jsonl`
- `/ll:wire-issue` - 2026-08-08T11:04:28 - `e01e538c-df3d-4617-805e-c18131ac689c.jsonl`
- `/ll:refine-issue` - 2026-08-08T10:56:34 - `bfaf3502-cc38-4d34-9ef9-0cdada2d53ce.jsonl`
- `/ll:issue-size-review` - 2026-08-08T10:09:55 - `70da93c7-f4f5-4a9e-85c1-cf030ebd11cb.jsonl`
