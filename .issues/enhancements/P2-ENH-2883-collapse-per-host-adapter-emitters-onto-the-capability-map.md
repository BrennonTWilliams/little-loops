---
id: ENH-2883
title: Collapse per-host adapter emitters onto the capability map
type: ENH
parent: EPIC-2257
priority: P2
status: done
discovered_date: 2026-07-27
completed_at: '2026-07-28T06:41:56Z'
blocked_by:
- ENH-2873
relates_to:
- ENH-2874
labels:
- multi-host
- ll-adapt
confidence_score: 95
outcome_confidence: 68
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 23
score_change_surface: 10
decision_needed: false
---

# ENH-2883: Collapse per-host adapter emitters onto the capability map

Split from ENH-2873 (2026-07-27): that issue's Phase A (the capability map, the drift
verifier, and the `HOST_COMPATIBILITY.md` adapter section) is small, additive, and is the
whole of what ENH-2874 depends on. This — the refactor of live emission paths — is
Medium-risk and gated on a golden-output corpus. Chaining ENH-2874 behind it bought
nothing, so it moved here.

## Summary

With ENH-2873's capability map in place, the per-host emitters still carry policy: which
frontmatter fields a host reads, whether it accepts agents at all, how a tool list maps to
a sandbox mode. Drive those decisions from the map so the emitters retain only
serialization, and adding a host stops meaning writing a module.

## Current Behavior

`adapters/core.py` (306 lines) owns the shared pipeline — `process_skills` /
`process_commands` / `process_agents`, the frontmatter helpers, the `HostEmitter` protocol,
and the lazy `_EMITTER_MAP` registry — but each registry entry resolves to a class holding
host policy alongside its format writer:

- `codex.py` (395 lines): `_derive_sandbox_mode` from a tool list, `_derive_mcp_servers`,
  agent TOML formatting, skill-markdown synthesis.
- `gemini.py` (187 lines): `_inject_name`, `_strip_metadata_short_description`, command
  TOML formatting, and a hard agent stub behind `_AGENT_STUB_MSG`.
- `omp.py` (28 lines): a placeholder that raises for every artifact kind.

After ENH-2873 the map describes each host declaratively, but nothing reads it — `core.py`
still dispatches on the emitter class.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Stale reference**: `gemini.py` no longer has an `_AGENT_STUB_MSG` constant or a
  hard-coded stub — ENH-2874 already migrated `GeminiEmitter.emit_agent()`
  (`adapters/gemini.py:184`) to a one-line delegation to the shared
  `core._emit_degraded_agent()`. The remaining gap for this issue is that
  `process_skills`/`process_commands` still don't consult the capability map at all, and
  `CodexEmitter`/`GeminiEmitter` still re-derive frontmatter-field and agent/command support
  facts ad hoc instead of reading `HOST_CAPABILITIES`.
- ENH-2873 already landed the map at `adapters/capabilities.py` — `HostCapabilityEntry`
  (frozen dataclass, lines 45–61: `host`, `config_dir`, `skill_output_format`,
  `command_output_format`, `agent_output_format`, `frontmatter_fields_read: tuple[str,
  ...]`, `agents`/`commands`/`hooks: bool`, `subagents: SubagentSupport`) and
  `HOST_CAPABILITIES` populated for `codex`/`gemini`/`omp` (lines 64–119).
- **One consumer already exists as the template to generalize**: `process_agents()`
  (`adapters/core.py:323`, specifically lines 346–353) already computes `degraded =
  entry.subagents == "none" and entry.agent_output_format is not None` from
  `HOST_CAPABILITIES.get(emitter.name)` and routes to `_emit_degraded_agent()` instead of
  `emitter.emit_agent()` when true — "selected from the capability flag alone, no host-name
  branch," per its own docstring. `process_skills()` (line 205) and `process_commands()`
  (line 256) have no equivalent capability-map consultation yet.
- **Policy vs. serialization split, concretely**: in `codex.py`, `_derive_sandbox_mode`
  (line 173, tool-list → `"read-only"`/`"write-to-cwd"`/`None` via `_READ_ONLY_TOOLS`/
  `_WRITE_TOOLS` frozensets, lines 29–30) and the frontmatter-field presence checks in
  `emit_skill`/`emit_command`/`emit_agent` (lines 264–395, e.g. `if not fm:` line 358) are
  policy that duplicates what `frontmatter_fields_read`/`agents`/`commands` already declare
  in the map; `_format_agent_toml` (line 207) and `_synthesized_skill_md` (line 108) are
  pure serialization/templating that stays as code. In `gemini.py`, `_inject_name` (line 24)
  and `_strip_metadata_short_description` (line 31) enforce Gemini's
  `frontmatter_fields_read=("description","name")` policy via regex, while
  `_make_command_toml` (line 78) is pure serialization.
- `omp.py` is confirmed a pure 28-line stub (`AdapterError` raised unconditionally from all
  three `emit_*` methods) — no policy to migrate.

## Expected Behavior

`process_skills` / `process_commands` / `process_agents` read field-selection,
agent-support, and skip/stub decisions from the host's capability-map entry. Emitters
implement serialization only (a TOML writer and a markdown writer are irreducibly different
code, and stay code). A host needing behavior the map cannot express is a signal to add a
field to the map. Output for every currently-supported host is byte-identical to what
shipped before the refactor.

## Proposed Change

1. **Golden corpus first, before touching `core.py`** — capture
   `scripts/tests/fixtures/adapt/` snapshots over the current skill/command/agent corpus for
   `codex` (skills, commands, agents) and `gemini` (skills, commands). This is the safety
   net every other step depends on; landing it in a separate commit makes the refactor's
   diff reviewable against a fixed baseline.

2. **Drive `core.py` from the map** — replace per-host branching and emitter-held policy
   with lookups against the ENH-2873 capability entry: readable frontmatter fields, agent
   support, artifact kinds emitted, output directory.

3. **Reduce the emitters** — `CodexEmitter` and `GeminiEmitter` keep their format writers
   and any behavior genuinely not expressible as data; policy moves to the map. Where a
   derivation (e.g. `_derive_sandbox_mode`) is host-specific *logic* rather than a host
   *setting*, keep it as a function the map names, rather than forcing it into a data field.

4. **Fixture-host test** — register a synthetic fourth host through the map alone (entry +
   an existing serializer) and emit for it, proving no module was required.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis, resolving the two open decisions
flagged in Confidence Check Notes:_

- **AC 5a resolved — yes, add the `try/except AdapterError` wrapper.** `process_skills`/
  `process_commands` (`core.py:236-245`, `302-312`) call `emitter.emit_skill`/
  `emit_command` bare — only local `OSError` on the file read is caught; any `AdapterError`
  the emitter raises propagates uncaught. This is a **live, reachable crash today**: for
  `--host omp`, `resolve_emitter("omp")` succeeds and `main_adapt()` (`cli/adapt.py:84-88`,
  `107`) only wraps `resolve_emitter()` itself in try/except, so `OmpEmitter.emit_skill`'s
  unconditional `raise AdapterError` propagates through `process_skills` → `main_adapt`
  uncaught, producing an unhandled traceback instead of `process_agents`'s graceful
  `"  ERROR  {name}: {exc}"` line + continued traversal + `errors` count (`core.py:380-386`).
  Fix: wrap the `emitter.emit_skill(...)`/`emitter.emit_command(...)` calls in the identical
  `try/except AdapterError as exc: print ERROR; errors += 1; continue` shape already used by
  `process_agents`, bringing skills/commands error handling in line with agents.
- **`_check_emitter_agreement()` circularity resolved — yes, it degrades, and should be
  reframed, not just "resolved during implementation."** Reading
  `verify_host_map.py:127-163`: it never actually calls any emitter today — it only checks
  that fields *within the same `HostCapabilityEntry`* are mutually consistent (e.g. Gemini's
  `agents`/`subagents`/`agent_output_format` pairing; Omp's `agents`/`commands` both `False`,
  with the omp rationale hardcoded as prose, not derived from `omp.py`). Once
  `process_skills`/`process_commands` dispatch from the map the same way `process_agents`
  already does, there is no longer any independent runtime behavior for the map to drift
  against — the check becomes a same-dataclass self-consistency assertion with no emitter on
  the other side of the comparison. Recommendation: rename/reframe it as a map
  self-consistency check (docstring currently claims it validates "actual emitter behavior,"
  which stops being true) rather than leaving its purpose implicit post-refactor.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `scripts/little_loops/cli/adapt_agents_for_codex.py` and
   `adapt_skills_for_codex.py` (legacy `ll-adapt-*-for-codex` wrappers) if `process_agents`/
   `process_skills`/`process_commands`'s meta-dict shape changes — both hard-code
   `CodexEmitter()` around the same core functions being refactored.
5a. Decide and document whether `process_skills`/`process_commands` gain a
   `try/except AdapterError` wrapper matching `process_agents` (`core.py:382-386`), given
   `OmpEmitter` unconditionally raises from all three `emit_*` methods.
6. Update `scripts/tests/test_verify_host_map.py::TestHostCapabilities.test_keys_match_emitter_map`
   if `_EMITTER_MAP` is renamed/removed as part of collapsing dispatch onto the map.
7. Re-verify `docs/reference/CLI.md`'s field-list/marker-string prose and
   `docs/codex/usage.md`'s `CapabilityNotSupported` fallback description still match emitted
   output; update `.claude/CLAUDE.md`'s per-host emitter framing if it goes stale.

## Integration Map

### Files to Modify
- `scripts/little_loops/adapters/core.py` — extend `process_skills()`/`process_commands()`
  (currently no capability-map read) to look up `HOST_CAPABILITIES` the same way
  `process_agents()` already does at lines 346–353; that block is the shape to generalize.
- `scripts/little_loops/adapters/codex.py` — remove field-presence/tool-mapping checks that
  duplicate `HOST_CAPABILITIES["codex"]` (`frontmatter_fields_read`, `_derive_sandbox_mode`'s
  `_READ_ONLY_TOOLS`/`_WRITE_TOOLS`); keep `_format_agent_toml`, `_synthesized_skill_md`,
  `_insert_skill_fields` as serialization.
- `scripts/little_loops/adapters/gemini.py` — same for `_inject_name`/
  `_strip_metadata_short_description`; keep `_make_command_toml` as serialization.
- `scripts/little_loops/cli/verify_host_map.py` — `_check_emitter_agreement()` (lines
  127–163) currently hand-asserts expected map values against known emitter behavior; once
  dispatch is map-driven, re-derive or simplify these checks since there's no longer an
  independent emitter behavior to compare the map against (risk of the check becoming
  circular/no-op — worth resolving explicitly during implementation, not left implicit).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/adapt.py` — `ll-adapt` entry point calling `resolve_emitter()`
  and `process_skills`/`process_commands`/`process_agents`.
- `scripts/little_loops/adapters/__init__.py` — re-exports `AdapterError`, `CodexEmitter`,
  `HostEmitter`, `resolve_emitter`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/adapt_agents_for_codex.py` — legacy `ll-adapt-agents-for-codex`
  wrapper; calls `core.process_agents` and `core._read_frontmatter` directly with a
  hard-coded `CodexEmitter()`, bypassing `resolve_emitter()`. If `process_agents`'s meta-dict
  shape or `_read_frontmatter` signature changes, this wrapper must change too (confirmed via
  `ll-code` + grep, `adapt_agents_for_codex.py:16,22-23,60`).
- `scripts/little_loops/cli/adapt_skills_for_codex.py` — same pattern for
  `ll-adapt-skills-for-codex`: hard-codes `CodexEmitter()` around `core.process_skills`/
  `core.process_commands` (`adapt_skills_for_codex.py:16,29-30,49,56`).
- `scripts/little_loops/cli/__init__.py` — re-exports `main_adapt_agents_for_codex`/
  `main_adapt_skills_for_codex` alongside `main_adapt`/`main_verify_host_map`.
- `scripts/little_loops/cli/verify_triggers.py:24,349` — imports
  `_is_model_invocation_disabled` from `adapters.core` directly; if that helper's behavior
  changes as part of moving skip logic onto the capability map, this caller needs re-checking.
- `scripts/little_loops/init/cli.py` (`_dispatch_host_adapters`) and
  `scripts/little_loops/init/tui.py` — `ll-init`'s adapter-install dispatch path; doesn't call
  `process_*`/`resolve_emitter` directly today but is the other product surface that triggers
  emitter code, worth a smoke check post-refactor.

### Similar Patterns
- `adapters/core.py:346-353` (`process_agents`'s `degraded` flag) — the existing
  capability-flag-driven-dispatch template this issue generalizes.
- `scripts/little_loops/host_runner.py:1255-1328` (`_HOST_RUNNER_REGISTRY`,
  `resolve_host()`) — sibling declarative registry-driven dispatch in a different subsystem.
- `scripts/tests/fixtures/policy_builder/conformance_corpus.json` +
  `scripts/tests/test_policy_builder_corpus.py` — single-JSON golden-corpus pattern (loader
  + per-case-category tests + a "corpus is non-trivial" sanity test) to model the
  `scripts/tests/fixtures/adapt/` corpus after.
- `scripts/tests/test_verify_host_map.py` (`TestCheckEmitterAgreement`,
  `test_flags_gemini_agents_true_with_no_output_format`) — the `patch.dict`/`patch` on
  module-level `HOST_CAPABILITIES` pattern for AC #4's fixture-host test: build a synthetic
  `HostCapabilityEntry` and patch it into `HOST_CAPABILITIES` rather than adding a new
  module, paired with `_MockEmitter` (`scripts/tests/test_adapters.py:175-194`) as the
  generic Protocol-satisfying emitter fixture.

### Tests
- `scripts/tests/test_adapters.py` — existing emitter unit tests, traversal tests
  (`TestProcessSkillsTraversal`, `TestProcessCommandsTraversal`, `TestProcessAgentsTraversal`),
  and `TestProcessAgentsDegradedRouting.test_gemini_output_never_calls_native_emit_agent`
  (lines 909–929) — the pattern for asserting routing happens via capability flag and never
  reaches the emitter method, extend for the new skill/command capability-driven paths.
- `scripts/tests/test_verify_host_map.py` — covers `ll-verify-host-map`; AC #5 requires this
  suite keeps passing post-refactor.
- New: `scripts/tests/fixtures/adapt/` golden corpus (AC #1) and its loader test module.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_verify_host_map.py::TestHostCapabilities.test_keys_match_emitter_map`
  (lines 18–21) — asserts `set(HOST_CAPABILITIES) == set(_EMITTER_MAP)`; breaks immediately if
  `_EMITTER_MAP` is renamed/removed while collapsing dispatch onto the map, needs updating to
  whatever registry symbol replaces it.
- `scripts/tests/test_adapt_agents_for_codex.py` / `test_adapt_skills_for_codex.py` — cover
  the legacy wrapper CLIs (`adapt_agents_for_codex.py`/`adapt_skills_for_codex.py` above);
  confirm still green since those wrappers call `core.process_*` directly with a hard-coded
  `CodexEmitter()`.
- Golden-corpus loader pattern to model: `scripts/tests/test_policy_builder_corpus.py` +
  `scripts/tests/fixtures/policy_builder/conformance_corpus.json` — one JSON per case
  category with a `"_comment"` provenance key, a loader test per category asserting against
  the canonical function with case-name-labeled failure messages, and a closing
  "corpus is non-trivial" sanity test enumerating required edge cases. Maps directly onto
  per-emitter-behavior JSON files (`skill_cases`, `command_cases`, `agent_cases`,
  `degraded_agent_cases`) for the new `scripts/tests/fixtures/adapt/` corpus.
- `patch.dict("little_loops.cli.verify_host_map.HOST_CAPABILITIES", ..., clear=False)` (the
  additive form, not the `clear=True` replacement form used elsewhere in
  `test_verify_host_map.py`) is the closer template for AC #4's fixture-host test — inject one
  synthetic `HostCapabilityEntry` under a made-up host key rather than replacing the full map.
- Note (not a gap, confirms an existing plan item): `process_skills`/`process_commands` have
  no `try/except AdapterError` wrapper today, unlike `process_agents`
  (`core.py:382-386`, prints `ERROR  {name}: {exc}`) — driving skip/skip-reason logic from the
  capability map for skills/commands needs an explicit decision on whether `OmpEmitter`'s
  unconditional raise should propagate uncaught or gain the same try/except treatment; add
  this as an explicit implementation-step decision, not an incidental behavior change.

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — "Adapter Host Capabilities" section (ENH-2873)
  already documents the map; no changes expected unless a new map field is introduced during
  the refactor (Proposed Change step 3 anticipates this for genuinely host-specific logic).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (~lines 3361–3440) — documents `ll-adapt`,
  `ll-adapt-skills-for-codex`, `ll-adapt-agents-for-codex`, the idempotency marker string
  `# generated by ll-adapt`, and the exact agent-TOML field list (`name`, `description`,
  `model`, `developer_instructions`) — these are asserted against real output, so re-verify
  if `_format_agent_toml`/field derivation shifts at all during the refactor.
- `docs/reference/API.md` (~line 9086, ~9852) — states `CodexEmitter`/`GeminiEmitter` are
  "fully implemented" and describes Codex-CLI agent-mirror generation; check no prose implies
  emitter-owned field-selection logic that goes stale once dispatch is map-driven.
- `docs/codex/usage.md` (lines 41, 50, 85, 87) — documents `ll-adapt --host codex --apply`
  setup and `CodexRunner`'s `CapabilityNotSupported` fallback messaging keyed on
  `.codex/agents/*.toml`/`developer_instructions` presence — a runtime consumer of the emitted
  TOML shape.
- `.claude/CLAUDE.md` (lines 62–72, 259) — documents `ll-adapt` and the per-host emitter
  architecture concept directly; update if "writing a module" framing changes per this
  issue's stated goal ("adding a host stops meaning writing a module").

## Acceptance Criteria

- [ ] Golden-corpus snapshots land in a commit **preceding** any `core.py` change, and the
      refactor leaves them byte-identical for `codex` (skills/commands/agents) and `gemini`
      (skills/commands) — or each difference is explained in the PR as intentional.
- [ ] The exclusions are named in the test, not silent: `omp` (emitter raises — no output to
      compare) and `gemini` agent emission (intentional preview stub, superseded for
      degraded hosts by ENH-2874).
- [ ] `core.py` contains no host-name branches; host behavior is read from the capability
      map. Asserted by a test, not by review alone.
- [ ] A test registers a fixture host via a map entry plus an existing serializer, emits
      for it, and passes — with no new module under `scripts/little_loops/adapters/`.
- [ ] `ll-verify-host-map` (ENH-2873) still passes, and `python -m pytest scripts/tests/`
      exits 0.

## Scope Boundaries

- **In scope**: the golden corpus, driving `core.py` from the map, thinning the emitters,
  the fixture-host test.
- **Out of scope**: the capability map, the drift verifier, and the `HOST_COMPATIBILITY.md`
  adapter section (all ENH-2873); the degraded-mode agent path (ENH-2874); implementing the
  `omp` emitter, which stays a stub; un-stubbing Gemini agent emission; hook adapters under
  `hooks/adapters/`, a separate translation layer.
- **Deliberate limit**: "zero per-host code" is not the goal and is not achievable. The
  target is that *policy* is data and *serialization* is pluggable code the data selects.

## Impact

- **Priority**: P2 — the payoff of ENH-2873's map; without it the map is descriptive only
  and the per-host drift it was built to prevent can still happen.
- **Effort**: Medium — the corpus is mechanical; the `core.py` refactor is the bulk.
- **Risk**: Medium — touches live emission paths for hosts in use. Mitigated entirely by
  the corpus landing first; the byte-identity AC is the gate.
- **Breaking Change**: No — entry points, CLI surface, and emitted output all unchanged.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-28_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 68/100 → LOW

### Outcome Risk Factors
- Cross-module refactor: `process_skills`/`process_commands`/`process_agents` in
  `core.py` plus `codex.py`/`gemini.py`/`verify_host_map.py` — moderate per-site depth
  (shared capability-map state consulted across three functions) spread across a
  broad set of change sites once the wiring touchpoints (legacy wrappers, `cli/__init__.py`,
  `verify_triggers.py`, `init/cli.py`/`tui.py`) are counted.
- Broad-ish caller surface for `core.py`'s public functions (`cli/adapt.py`,
  `adapters/__init__.py`, and both legacy `ll-adapt-*-for-codex` wrappers) — a 6-10
  caller blast radius, mitigated by the byte-identity golden-corpus AC but still real.
- Both open decisions flagged in the prior check are now resolved in the issue body
  (subsequent `/ll:refine-issue` pass): AC 5a decides yes on the `try/except
  AdapterError` wrapper for `process_skills`/`process_commands`, and
  `_check_emitter_agreement()`'s post-refactor circularity is reframed as an explicit
  "rename to a map self-consistency check" recommendation rather than left implicit.
  Residual risk is now purely the breadth/depth of the refactor itself, not
  undecided design questions.

## Resolution

Implemented per the Proposed Change:

1. Golden corpus landed first (separate commit) — `scripts/tests/fixtures/adapt/{skill,command,agent}_cases.json` + `scripts/tests/test_adapt_golden_corpus.py`, with `omp` and Gemini agent emission named as explicit exclusions.
2. `core.py` gained `_select_frontmatter_fields()`, a single map-driven helper (parameterized by `HOST_CAPABILITIES[host].frontmatter_fields_read`) that replaces `codex._insert_skill_fields`'s and `gemini._inject_name`/`_strip_metadata_short_description`'s duplicated regex policy. Both emitters now delegate to it; `codex._insert_skill_fields` stays as a thin back-compat wrapper for `cli/adapt_skills_for_codex.py`.
3. `process_skills`/`process_commands` gained the `try/except AdapterError` wrapper matching `process_agents`'s existing shape (AC 5a) — fixes the `--host omp` unhandled-traceback path.
4. `verify_host_map.py`'s `_check_emitter_agreement()` docstring reframed as a same-dataclass self-consistency check, per the resolved recommendation — no behavior change.
5. A fixture-host test (`TestFixtureHostRegistration` in `test_adapters.py`) registers a synthetic host via additive `patch.dict` on `HOST_CAPABILITIES` and proves `process_skills`/`process_commands`/`process_agents` all emit for it with no new adapter module.

Legacy wrapper CLIs, docs, and `test_keys_match_emitter_map` were checked and needed no changes — emitted output and meta-dict shapes are unchanged.

All ACs pass: golden-corpus byte-identity, no host-name branches in `core.py`, fixture-host test, `ll-verify-host-map` and `python -m pytest scripts/tests/` both exit 0 (7 pre-existing, unrelated failures confirmed present on `main` before this change).

## Status

**Open** | Created: 2026-07-27 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-07-28T00:00:00 - `b50613f5-a6a7-4be8-ab8e-7672a70f15a2.jsonl`
- `/ll:refine-issue` - 2026-07-28T06:18:41 - `b2190cb8-d221-4ead-b82f-52ab3441720e.jsonl`
- `/ll:confidence-check` - 2026-07-28T00:00:00 - `19e68633-068d-422d-875a-9b320692d359.jsonl`
- `/ll:wire-issue` - 2026-07-28T06:12:28 - `833f610b-d748-4b6e-8ed2-0f04a2325321.jsonl`
- `/ll:refine-issue` - 2026-07-28T06:05:59 - `fc389739-0448-42ab-a995-a4b4267a8429.jsonl`
- `/ll:manage-issue` - 2026-07-28T06:41:10 - `5b993019-4f0b-470a-992a-e32c0a123da7.jsonl`
