---
id: ENH-2874
title: Generate degraded-mode agent fallbacks for hosts without subagent support,
  with mandatory disclosure
type: ENH
parent: EPIC-2257
priority: P2
status: done
discovered_date: 2026-07-27
labels:
- multi-host
- ll-adapt
- agents
confidence_score: 93
outcome_confidence: 71
score_complexity: 14
score_test_coverage: 20
score_ambiguity: 12
score_change_surface: 25
completed_at: '2026-07-28T06:00:57Z'
---

# ENH-2874: Generate degraded-mode agent fallbacks for hosts without subagent support, with mandatory disclosure

Origin: ll-product #ENH-057

Parent EPIC: EPIC-2257 (multi-host generalization — portfolio coordination), which already
owns shared per-host infrastructure including skill/command adapters.

## Summary

little-loops' `agents/*.md` encode roles the host is expected to spawn as subagents. Where
a host cannot spawn one, the role does not adapt at all and the reasoning it encodes is
silently unavailable on that host. Generate a degraded-mode inline-role file from the same
agent source, with a preamble that mandates one-line disclosure so a degraded run never
reads like a delegated one.

## Current Behavior

`adapters/gemini.py` hard-stubs agent emission behind `_AGENT_STUB_MSG` ("gemini agent
emission not yet stable — Gemini agents are a preview feature; open a PR when they exit
preview"), so no Gemini artifact exists for any role in `agents/`. `adapters/omp.py` raises
for every artifact kind. `adapters/codex.py` emits agent TOML with derived sandbox mode and
MCP servers. There is no fallback path anywhere: a host either gets native agent artifacts
or gets nothing, and nothing in the generated output tells a model that a role it cannot
delegate should be run inline.

## Expected Behavior

Every host with a working emitter gets an artifact for every role in `agents/`: the native
format where the host supports subagents, a generated inline-role reference file where it
does not. The degraded file is generated from the same authored source as the native one —
never a hand-maintained parallel copy — and its preamble instructs the model to perform the
role inline **and** to disclose the substitution in one line when it reports.

## Proposed Change

1. **`subagents` capability flag** on ENH-2873's capability map. Start with two values —
   `native` and `none` — and add a third only if step 2 below finds a host that genuinely
   needs it (see Open Question).

2. **Verify the permission-gated premise before building for it.** The origin write-up
   asserts Codex needs an "ask once, then stop" gate. Codex has first-class custom agents;
   the known asymmetry with Claude Code is that invocation is *spawn-based rather than
   flag-based*, which is not the same thing as a permission gate. Confirm against the
   current Codex CLI before implementing a tri-state; if no host needs it, ship the
   two-value flag and drop the gate entirely. Building an ask-once gate for a constraint
   that does not exist is worse than not building it.

3. **Degraded emitter path in `adapters/core.py`** — for a host whose entry declares
   `subagents: none`, `process_agents` writes an inline-role file per `agents/*.md`:
   authored body verbatim, prefixed with a generated preamble. Selected by the capability
   flag, not by a host name check.

4. **The preamble** — a single template (one authored string, not per-host) that (a)
   instructs the model to perform the role inline rather than delegate, and (b) requires a
   one-line disclosure in the report that inline substitution was used.

5. **Output location and discoverability — decide this before implementing.** A generated
   file nothing references is dead weight. Specify, in the capability-map entry: the output
   directory, the filename convention, and how the model reaches the file (referenced from
   the adapted skills? a generated index? the host's own config dir?). Record the choice in
   `HOST_COMPATIBILITY.md`.

## Acceptance Criteria

- [x] The capability map carries a `subagents` flag, and `process_agents` selects native
      vs. degraded emission from that flag alone — no host-name branches in `core.py`.
- [x] For a host declaring `subagents: none` **and having a working emitter**, every file in
      `agents/` produces exactly one inline-role output file. A test enumerates `agents/`
      and asserts one-to-one coverage, so a newly added agent cannot silently miss the
      degraded host. `omp` is excluded while its emitter raises, and the exclusion is named
      in the test rather than implicit.
- [x] The generated preamble contains the inline-execution instruction and the
      one-line-disclosure requirement — asserted **structurally** on the generated file.
      (The behavioral claim "a degraded run actually says so in its report" is model
      behavior at runtime; the local pytest suite cannot gate it. If it is worth checking,
      it belongs in an `ll-harness` eval, tracked separately — not as an AC here.)
- [x] The degraded file's role content derives from the authored `agents/*.md` source; a
      test asserts the body matches the source, so the two cannot drift.
- [x] The output path and discovery mechanism are declared in the capability map and
      documented in `HOST_COMPATIBILITY.md`.
- [x] N/A — step 2 found no host needing permission-gated subagent spawning (see the
      Open Question's resolution note below); shipped the two-value flag with no
      tri-state and no ask-once gate.

## Scope Boundaries

- **In scope**: the `subagents` flag, the degraded emission path in `core.py`, the preamble
  template, the coverage test, and the output-location decision.
- **Out of scope**: implementing the `omp` emitter (ENH-2873 leaves it a stub; this issue
  does not change that); the capability map itself (ENH-2873); runtime enforcement that a
  model actually discloses.
- **Supersedes the Gemini stub deliberately**: `_AGENT_STUB_MSG` in `adapters/gemini.py`
  goes away for degraded emission — Gemini stops raising and starts producing inline-role
  files. That is intended, not a regression of the preview-feature rationale: if Gemini
  agents exit preview later, the host's flag flips to `native` and the native path takes
  over with no change to this work.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Capability map already landed** (ENH-2873 merged): `scripts/little_loops/adapters/capabilities.py:34-51` defines `HostCapabilityEntry` (frozen dataclass) with a `subagents: bool` field (currently boolean, defaults `False`) alongside `agents`/`commands`/`hooks`. `HOST_CAPABILITIES` has three entries: `codex` (`subagents=True`, `agents=True`), `gemini` (`subagents=False`, `agents=False`), `omp` (`subagents=False`, `agents=False`). Step 1's work is to widen this existing bool to the two-value (`native`/`none`) flag described in the Proposed Change — not introduce a new field from scratch.
- **The map is documentation-as-data today — nothing reads it.** The module docstring (`capabilities.py:8-10`) states explicitly: "ENH-2883 will drive `core.py`'s dispatch from these entries; this module is additive only — it does not change emission behavior." Confirmed: `process_agents` in `scripts/little_loops/adapters/core.py:242-306` calls `emitter.emit_agent(...)` unconditionally for every host with no branch on `HOST_CAPABILITIES`. **ENH-2874 would be the first caller to actually branch on this map** — worth noting since ENH-2883 (a sibling/later issue) apparently intends the same wiring; check for overlap/sequencing with ENH-2883 before implementing step 3.
- **Traversal entry point**: `process_agents(emitter, agents_dir, output_dir, apply, quiet, only)` at `core.py:242`. Returns `(adapted, skipped, errors)`. The per-agent `try/except AdapterError` block (`core.py:282-298`) is currently the only place a host's "cannot do agents" signal surfaces — as a per-agent stderr `ERROR` line, not a host-level notice. The degraded path (step 3) should intercept before this raise, not react to it.
- **`_extract_body(text)` helper** (`core.py:91-101`) already extracts the authored Markdown body after frontmatter's closing `---`, and is already imported by both `codex.py` and `gemini.py`. This is the natural helper to reuse for extracting each `agents/*.md` role body verbatim into the degraded output — satisfies the "authored body verbatim" and "test asserts the body matches source" ACs directly.
- **Gemini stub to be superseded**: `adapters/gemini.py:16-19` (`_AGENT_STUB_MSG`) and `GeminiEmitter.emit_agent()` (`gemini.py:186-187`, a one-line unconditional `raise AdapterError(_AGENT_STUB_MSG)`). Confirmed no frontmatter reading or conditional logic exists there today — the whole method needs replacing with the degraded emission call.
- **Omp stays excluded**: `adapters/omp.py:13` (`_REMEDIATION`) — all three `emit_*` methods raise identically; omp has no host-specific behavior at all (EPIC-2258 stub). Existing precedent for naming this exclusion in a test already exists: `scripts/tests/test_adapt_agents_for_codex.py:341-351` (`test_all_real_agents_have_toml_files`) does `if not codex_agents_dir.exists(): return` as an early-out — the AC's "omp excluded and named in the test" should follow this same shape but with an explicit skip reason rather than a silent early-return.
- **Codex is the closest model for the degraded emitter's shape** (not a template to copy output format from, but the code shape): `CodexEmitter.emit_agent` (`codex.py:349-395`) → `_format_agent_toml` (`codex.py:207-247`) prepends a fixed `_MARKER = "# generated by ll-adapt"` (`codex.py:18`) ahead of derived fields, then embeds the verbatim body. The degraded emitter's preamble-then-body structure should mirror this shape (fixed preamble template + `_extract_body()` output), and should reuse the existing idempotency pattern: compare freshly-generated content against the on-disk file and skip if byte-identical (`codex.py:375-384`).
- **Coverage-test precedent to model the new AC test after**: `scripts/tests/test_adapt_agents_for_codex.py` — `TestRealAgentsIntegrationGuard.test_all_real_agents_have_toml_files()` (341-351), `test_all_real_toml_files_have_marker()` (353-361), `test_all_real_toml_files_have_required_fields()` (363-374), and the anti-drift `TestIdempotency.test_changed_source_triggers_rewrite()` (413-430). These are the exact shapes for the "one output file per source agent," "preamble present," and "body matches source" ACs.
- **`ll-verify-host-map` will need a matching update**: `scripts/little_loops/cli/verify_host_map.py`'s `_check_emitter_agreement()` (120-138) currently asserts `gemini_entry.agents` stays `False` because `GeminiEmitter.emit_agent` unconditionally raises. Once Gemini's `emit_agent` starts producing degraded output instead of raising, this check's premise changes — flag as a coupled follow-up change, not a new issue.
- **`HOST_COMPATIBILITY.md` table to extend**: `docs/reference/HOST_COMPATIBILITY.md:209-213` ("Adapter Host Capabilities" section) has the Gemini/omp rows currently reading "N/A — preview stub, raises `AdapterError`" / "N/A — unimplemented stub, raises `AdapterError`" for Agent output — these need updating once Gemini's degraded path lands, plus a new column/cell for the output-location decision (step 5).
- **Codex's own "no persona flag" workaround is itself inline-role injection**: `host_runner.py`'s `CodexRunner.build_streaming(agent=...)` already reads the generated `.codex/agents/<name>.toml`, extracts `developer_instructions`, and prepends `[Persona: <name>]\n<instructions>\n\n---\n\n` to the prompt payload when Codex has no CLI flag to assign a persona to the root session. This confirms the Proposed Change's step 2 premise (Codex's asymmetry is spawn-based, not permission-gated) and is a second existing precedent for "inline role text prepended to a prompt" beyond the Codex TOML emission pattern — worth referencing if the preamble template's exact phrasing needs a working example.

## Wiring Findings

_Added by `/ll:wire-issue` — based on codebase wiring analysis:_

### Dependent Files (Callers/Importers)

- No production code outside `capabilities.py` itself reads `HostCapabilityEntry.subagents`
  today (confirmed by grep across the tree) — widening it from `bool` to a `native`/`none`
  value has no currently-truthy-bool call site to break. The only touch points are the
  dataclass field default and the three `HOST_CAPABILITIES` literal assignments, both
  already in scope. `verify_host_map.py`'s `_check_runtime_contradiction` only diff-checks
  field names shared with `host_runner.HostCapabilities`, which has no `subagents` field, so
  it will not trip on the widened type either. [Agent 1/2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_adapters.py:806-817` (`TestGeminiEmitterEmitAgent.test_raises_adapter_error`,
  `test_error_message_contains_remediation`) — **will break**: both hard-assert
  `GeminiEmitter().emit_agent(...)` raises `AdapterError` on every call, including the
  empty-dict case. Once `emit_agent` produces degraded output instead of raising, rewrite
  these to assert the degraded-file output path instead. [Agent 2/3 finding]
- `scripts/tests/test_verify_host_map.py:23-24`
  (`TestHostCapabilities.test_gemini_agents_false_matches_stub`) — **will break**:
  hard-asserts `HOST_CAPABILITIES["gemini"].agents is False`, tied to a comment at
  `capabilities.py:75-77` that explicitly says this must reflect the raise-only stub. Update
  alongside the capability-map change. [Agent 3 finding]
- `scripts/tests/test_verify_host_map.py:60-75`
  (`TestCheckEmitterAgreement.test_current_tree_agrees`,
  `test_flags_gemini_agents_mismatch`) — **needs review/update**: the second test's fixture
  deliberately sets `agents=True` on a synthetic gemini entry to simulate a mismatch;
  `_check_emitter_agreement`'s docstring/logic (`verify_host_map.py:120-138`) hardcodes
  "declares agents=True but emit_agent unconditionally raises" as the failure condition —
  this premise inverts once gemini's degraded path legitimately makes `agents` truthy.
  [Agent 2/3 finding]
- `scripts/tests/test_adapters.py:471-602` (`TestCodexEmitterEmitAgent`) — pattern to model
  new gemini degraded-emission tests after: creation, content/marker assertions, dry-run,
  user-authored-file protection, and idempotency-pair sub-tests. [Agent 3 finding]
- No existing test reads `HostCapabilityEntry.subagents` at all — the field itself is
  currently untested, so the native/none discriminator work is greenfield with no prior
  assertion to reconcile. [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/cli/verify_host_map.py` module docstring (1-19) and
  `main_verify_host_map`'s `argparse` `description=` (167-171) — user-facing `ll-verify-host-map
  --help` prose repeats "gemini.agents must be False" as an invariant; this is CLI help text,
  not just internal logic, and needs rewriting alongside `_check_emitter_agreement`.
  [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md:215-218` — prose sentence below the capability table
  currently reads "Un-stubbing Gemini agent emission is blocked on the vendor preview...see
  ENH-2874 for the degraded-mode agent path this unblocks" — this describes the pre-change
  state and will read as stale/contradictory once the degraded path ships. [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md:220-224` (`> Last Verified:` banner) — per the file's
  own convention, bump this date after editing the capability table. [Agent 2 finding]
- `.issues/enhancements/P2-ENH-2883-collapse-per-host-adapter-emitters-onto-the-capability-map.md`
  ("Current Behavior", lines 33-44) — this sibling issue (`relates_to: ENH-2874`) narrates
  gemini's hard agent stub as present-tense fact; flag for a reconciliation note once
  ENH-2874 merges, not a code change here. [Agent 2 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints must be included in the implementation:_

1. Rewrite `test_adapters.py`'s `TestGeminiEmitterEmitAgent` tests (806-817) to assert
   degraded-output behavior instead of an unconditional raise.
2. Update `test_verify_host_map.py`'s `test_gemini_agents_false_matches_stub` (23-24) and
   review `TestCheckEmitterAgreement` (60-75) against the new `_check_emitter_agreement`
   semantics.
3. Update `verify_host_map.py`'s module docstring and `--help` description text (1-19,
   167-171) to describe the degraded-emission agreement check instead of "must stay False."
4. Update `HOST_COMPATIBILITY.md` prose at 215-218 (remove the "blocked on vendor preview"
   framing for the degraded path) and bump the `Last Verified` banner (220-224).
5. Leave a reconciliation note for ENH-2883 pointing at this issue's landed state (advisory
   only — not this issue's file to edit).

## Open Question

Does any supported host actually need permission-gated subagent spawning? Resolve in
step 2 before implementing the tri-state. Default assumption if unresolved: two values
(`native` / `none`).

**Resolved during implementation (2026-07-28):** No. Re-confirmed the Codebase Research
Findings' evidence — `host_runner.py`'s `CodexRunner.build_streaming(agent=...)` already
works around Codex's lack of a persona-selection flag by reading the generated
`.codex/agents/<name>.toml`'s `developer_instructions` and prepending it to the prompt as
`[Persona: <name>]\n...`. That is a spawn/selection-flag gap, not a permission gate — Codex
does not ask for one-time approval before running a subagent; it simply has no CLI flag to
pick one for the root session, so the adapter compensates by inlining the persona text.
Nothing in the Codex CLI's documented behavior implies a permission-gated flow. Shipped the
two-value `Literal["native", "none"]` discriminator with no tri-state and no ask-once gate.

## Dependencies

Previously waited on ENH-2873 Phase A (the capability map and its `subagents`
field). **ENH-2873 is now `done`** — the capability map exists at
`scripts/little_loops/adapters/capabilities.py` with the `subagents` field
already in place (see Codebase Research Findings above); this dependency is
satisfied and no longer blocks implementation.

## Impact

- **Priority**: P2 — without it, entire agent roles are invisible on non-Claude-Code hosts,
  and the failure is silent (no artifact, no error, no note).
- **Effort**: Small-to-Medium now that the capability map (formerly ENH-2873 Phase A) has
  landed — one emission branch, one preamble template, one coverage test. The
  output-location decision is the long pole.
- **Risk**: Low — purely additive output; the native path is untouched.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-07-27 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-07-28T00:00:00 - `5448c21b-0520-451b-8395-564604dcc66d.jsonl`
- `/ll:wire-issue` - 2026-07-28T05:46:28 - `523d34d9-b4dd-443e-ab4b-2724d93353fa.jsonl`
- `/ll:refine-issue` - 2026-07-28T05:40:05 - `8e48fa7c-0c4f-4a59-94fa-7400b53f697d.jsonl`
- `implementation` - 2026-07-28T00:00:00 - Widened `HostCapabilityEntry.subagents` to
  `Literal["native", "none"]` (`capabilities.py`); added a shared
  `_emit_degraded_agent` helper in `adapters/core.py` (preamble + verbatim body,
  marker-based idempotency) selected by `process_agents` from the capability flag
  alone (`subagents == "none"` and `agent_output_format is not None`; `omp` excluded
  via its `agent_output_format is None`); rewired `GeminiEmitter.emit_agent` to
  delegate to it instead of raising `_AGENT_STUB_MSG` (removed); fixed `cli/adapt.py`'s
  agent output dir to derive from the capability map's `config_dir` per host instead
  of hardcoding `.codex/agents`; generated and committed the real `.gemini/agents/*.md`
  degraded files via `ll-adapt --host gemini --apply`; updated
  `cli/verify_host_map.py`'s `_check_emitter_agreement` (and docstring/`--help` text)
  for the inverted agreement premise; updated `HOST_COMPATIBILITY.md`'s Adapter Host
  Capabilities table (added a Subagents column, degraded-format cell, discoverability
  prose) and bumped Last Verified; rewrote `TestGeminiEmitterEmitAgent` and added
  coverage/idempotency tests in `test_adapters.py`, and updated
  `test_verify_host_map.py`'s gemini-agents assertions. Resolved the Open Question
  (no tri-state needed) in-line above. Full suite: 16774 passed, 7 pre-existing
  unrelated failures confirmed present on a clean `git stash` baseline (loop-yaml,
  skill-line-limit, and prose-dependency-drift gates — the drift entry naming
  ENH-2874 itself resolves once this issue closes).
