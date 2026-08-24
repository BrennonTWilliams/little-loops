---
id: ENH-3307
title: State "host owns the journey" as the contract for any artifact that can re-enter
  the FSM
type: ENH
priority: P2
status: open
discovered_date: '2026-08-23'
parent: EPIC-3127
relates_to:
- ENH-3306
- ENH-3035
labels:
- artifact
- fsm
program_design_not_applicable: true
confidence_score: 100
outcome_confidence: 81
score_complexity: 22
score_test_coverage: 15
score_ambiguity: 20
score_change_surface: 24
---

## Summary

Define "host owns the journey" as the contract for any artifact that can route a user interaction back into the FSM executor. The executor already owns state transitions; no artifact type today can route an interaction back into the engine as an event. This defines the vocabulary and rules before any transport-level mechanism (a local SSE bridge, queue-backed command execution, an MCP Apps interactive resource, or any future render target) locks in a de facto contract by accident.

## Current Behavior

No document or vocabulary defines what an artifact may do when a user acts on it, or who owns the resulting FSM transition. The FSM executor is authoritative over state transitions; artifacts today (dashboards, markdown reports) are one-way — a loop renders an artifact and hands it to a human or another agent, with no path back into the engine. Each new render target (a local SSE bridge, queue-backed command execution, an MCP Apps interactive resource such as ENH-3306) risks locking in a de facto re-entry contract by accident, since nothing written down constrains it.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- `FSMExecutor` (`scripts/little_loops/fsm/executor.py`) is the sole routing authority: its `run()` loop consumes only self-produced input (action results from `ActionRunner`, evaluator verdicts, `SignalDetector`-parsed in-band signals) — there is no queue, socket, or callback parameter through which an external actor injects a "resume"/"user interacted" event into a running executor.
- The executor's only outbound channel is `_emit()` → its `event_callback` attribute (`executor.py:235`), typed as `scripts/little_loops/fsm/types.py:124`'s `EventCallback = Callable[[dict[str, Any]], None]` → `EventBus.emit()` (`scripts/little_loops/events.py`) → `Transport` sinks (`scripts/little_loops/transport.py`). Every sink (`JsonlTransport`, `UnixSocketTransport`, `OTelTransport`, `WebhookTransport`, `SQLiteTransport`) is send-only; `UnixSocketTransport` accepts client connections but `_client_loop()` only drains an outbound queue, never reads bytes back from `client.conn`.
- `HandoffHandler` (`scripts/little_loops/fsm/handoff_handler.py`) with `HandoffBehavior.SPAWN` is the closest existing analog to level-2 ("ask-to-run-prompt"): it spawns a new host CLI session to continue a paused loop, but the trigger is a signal the executor detected in its own action output (`SignalDetector`), not a user interacting with a rendered artifact.
- `scripts/little_loops/mcp_server/resources.py`'s `_ResourceEntry` (line 58) has no callback/event field today — confirmed absent, not merely unbuilt (see ENH-3306, which proposes adding the first interactive content type to this surface).
- `scripts/little_loops/loops/html-anything.yaml`'s `html-dashboard` artifact type writes a static, self-contained `index.html` to `${context.run_dir}` as a terminal side effect with no server component or JS callback wiring back into any little-loops process — confirms dashboards are one-way by construction, not by omission.

## Expected Behavior

A written contract — the three-level control taxonomy (notify / ask-to-run-prompt / host-owned) described below — exists as a document/spec artifact that defines, per level, what an artifact may emit, what the host is obligated to do with it, and which layer (host session vs. FSM executor) owns the resulting state change. The contract is protocol- and render-target-agnostic, so it governs htmx-based artifacts over a local bridge, MCP Apps interactive resources (ENH-3306), and any future render target without modification.

**Deliverable location (resolved 2026-08-23 review):** `docs/reference/ARTIFACT_CONTROL_LEVELS.md`, indexed from `docs/index.md` under "Reference" (required, not implementer's call), and cross-linked from `docs/ARCHITECTURE.md` (a short `## Artifact Control Layer` pointer following the Host Runner Layer precedent) and `docs/reference/EVENT-SCHEMA.md`.

**Event naming (resolved):** the doc reserves the level-3 event name `artifact_interaction` and adds a placeholder row for it to `docs/reference/EVENT-SCHEMA.md` (marked *reserved, not yet emitted*) with the field shape `{artifact_id, level, action, payload}`. This is so ENH-3306's view and a future SSE bridge converge on one name rather than each inventing one; no executor code emits or consumes it in this issue.

## Background / Motivation

The FSM executor is authoritative over transitions; artifacts today (dashboards, markdown reports) are one-way — a loop renders an artifact and hands it to a human or another agent, but the artifact cannot re-enter the engine. The event stream the engine already emits is the substrate an interactive artifact would plug into; the missing piece is defining what an artifact is allowed to do when a user acts on it, and who owns the resulting transition.

## Proposed contract: a three-level control taxonomy

This is little-loops' own vocabulary for the contract — informal framing chosen for clarity, not terminology defined by any MCP specification:

1. **notify** — the artifact reports state and owns nothing; there is no re-entry into the FSM.
2. **ask-to-run-prompt** — the artifact asks the host session to run a prompt, releasing responsibility to the host; the FSM engine is not the one acting.
3. **host-owned** — the interaction *is* an event the engine consumes; the executor retains ownership of the resulting transition.

The distinction that matters most is level 2 vs. level 3: level 2 hands control to the host session (a human- or agent-mediated step), level 3 keeps the executor authoritative over the transition with no intermediate hand-off. A queue-backed command-execution path that lets a live artifact trigger execution implies level 3 without saying so explicitly — naming the levels here is what stops that kind of path from defining the contract implicitly, after the fact.

### Per-level obligations (the table the doc must contain)

| Level | Artifact may emit | Host is obligated to | Owner of resulting state change | Existing / planned example |
|---|---|---|---|---|
| 1 notify | Display-only signals (`ui/message`, status text) | Surface it; nothing else | Nobody — no state change | `html-anything.yaml` dashboards; ENH-3306 first view |
| 2 ask-to-run-prompt | A prompt/command request addressed to the host session | Decide whether to run it; if run, run it as its own session action | Host session (human/agent), *not* the executor | `HandoffBehavior.SPAWN` (closest analog) |
| 3 host-owned | An `artifact_interaction` event | Deliver it to the executor's inbound channel unchanged | FSM executor (`FSMExecutor`) | None today — reserved for a future SSE bridge / queue path |

The doc must also state two prohibitions, in the style of the Host Runner "MUST go through `resolve_host()`" rule: (a) a render target MUST declare which level(s) it supports and MUST NOT emit above its declared level; (b) no transport may consume a level-3 event itself — it must hand it to the executor.

## Integration Map

### Files to Modify

- No production code changes — Effort is Small, a document/spec artifact only (`program_design_not_applicable: true` is already set in frontmatter). This codebase's convention places single-topic canonical contract/taxonomy docs under `docs/reference/` (e.g. `docs/reference/EVENT-SCHEMA.md`, `docs/reference/HOST_COMPATIBILITY.md`, `docs/reference/DEFERRAL_CODES.md`) rather than `docs/guides/` (broader narrative "how to build X" docs, e.g. `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`)
- **New**: `docs/reference/ARTIFACT_CONTROL_LEVELS.md`
- `docs/index.md` — add the Reference bullet
- `docs/reference/EVENT-SCHEMA.md` — add the reserved `artifact_interaction` row
- `docs/ARCHITECTURE.md` — add a short `## Artifact Control Layer` pointer section

### Dependent Files (Callers/Importers)

- None today — no code path lets a rendered artifact route an interaction back into `FSMExecutor.run()` (`scripts/little_loops/fsm/executor.py`). `FSMExecutor.event_callback` (`executor.py:235`, typed `EventCallback` — defined `scripts/little_loops/fsm/types.py:124`) is a pure outbound sink; `EventBus.emit()` (`scripts/little_loops/events.py`) fans events to `Transport` sinks (`scripts/little_loops/transport.py`: `JsonlTransport`, `UnixSocketTransport`, `OTelTransport`, `WebhookTransport`, `SQLiteTransport`) that are all send-only — `UnixSocketTransport._client_loop()` only drains an outbound queue; `WebhookTransport` only POSTs outward. This document defines the vocabulary that future call sites (ENH-3306's `ui://` resource, a future local SSE bridge, queue-backed command execution) will need to conform to, not a retrofit of existing callers

### Conventions in Force

- Contract/spec documents open with an H1 title, a purpose paragraph, and either a `> **Related Documentation:**` blockquote (`docs/ARCHITECTURE.md:1-9`, `docs/reference/EVENT-SCHEMA.md:1-8`) or a closing `## Related` section (`docs/reference/DEFERRAL_CODES.md:1-12`) linking sibling docs — the two forms coexist, not unified
- A taxonomy/"levels" doc is rendered as a markdown table (one row per level, parallel columns for identifier/what-it-is/why), followed by prose disambiguating adjacent rows where the boundary is contested — evidence: `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:85-107` (MR-1…MR-14), `:159-170` (Runtime Failure Modes, which explicitly disambiguates two adjacent rows the same way this issue's own text distinguishes level 2 vs. level 3), `docs/reference/HOST_COMPATIBILITY.md:16-56`
- A canonical taxonomy doc explicitly declares itself canonical in prose and states that other docs link to it rather than restating it — evidence: `HOST_COMPATIBILITY.md:18-20` ("This table is canonical... Every other host list in the docs links here"), `DEFERRAL_CODES.md:6-8`
- Drift-enforcement against code is contested, not universal: `HOST_COMPATIBILITY.md`'s table is pytest-enforced against `host_runner.py`'s registry (`scripts/tests/test_wiring_guides_and_meta.py`); `HARNESS_OPTIMIZATION_GUIDE.md`'s MR table and `DEFERRAL_CODES.md` rely on prose cross-linking only, with no automated drift test
- Doc-to-doc and code-to-doc cross-references use a `§ Section Name` citation glyph in prose/comments (`scripts/little_loops/issues/symbol_claims.py:9` etc., `scripts/little_loops/issue_parser.py:787` etc.) or a markdown anchor link (`docs/ARCHITECTURE.md:884`); there is no frontmatter-based document-linking field anywhere in the issue schema — this issue and ENH-3306 currently cross-reference each other only in prose, never via a frontmatter field
- The clearest precedent for documenting a protocol-agnostic contract spanning multiple mechanisms is the Host Runner Layer: a `Protocol` type in code, a dedicated `## <Name> Layer` section in `docs/ARCHITECTURE.md:822-857` stating what it normalizes, and an explicit prohibition telling future call sites what not to do ("New host-CLI call sites MUST go through `resolve_host()`") — the same shape this issue proposes for the three-level taxonomy: name the contract once, document it, and prohibit ad hoc reinvention at each new render target

### Tests

- Minimal existence/structure test only: a new `scripts/tests/test_enh_3307_artifact_control_levels.py` asserting the doc exists, contains the three level identifiers and the `artifact_interaction` name, and that `docs/index.md` links it. Full drift-enforcement against executor event names (the `HOST_COMPATIBILITY.md` precedent) is deferred until an executor actually emits `artifact_interaction`.

### Documentation

- `docs/reference/EVENT-SCHEMA.md` — enumerates every FSM event today (`loop_start`, `state_enter`, `route`, `handoff_detected`, `host_pressure`, etc., under "Subsystem: FSM Executor"); this is the existing outbound vocabulary substrate this contract would sit beside
- `docs/ARCHITECTURE.md` — top-level system design doc; candidate location per the Host Runner Layer precedent above, or a cross-link target if the contract lives under `docs/reference/` instead
- `docs/guides/MCP_SERVER_GUIDE.md` — user-facing docs for `ll-mcp`; would need a cross-link once ENH-3306's `ui://` resource type exists, since that mechanism must conform to this contract

_Wiring pass added by `/ll:wire-issue`:_
- `docs/index.md` — lists `docs/reference/*.md` under "Reference"; **required** new bullet for `ARTIFACT_CONTROL_LEVELS.md` (resolved: index it even though `HOST_COMPATIBILITY.md` / `DEFERRAL_CODES.md` are not — precedent is inconsistent, so follow the stricter path) [Agent 1 finding]
- `docs/guides/LOOPS_REFERENCE.md:1483-1582` and `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:1200` — document `scripts/little_loops/loops/html-anything.yaml`, the concrete level-1 (notify) artifact type this contract's "one-way by construction" example refers to; candidate cross-link once the contract doc exists, though the connection is by example rather than by required coupling [Agent 1 finding]

### Configuration

- N/A — no config changes; this issue is scoped to a document/spec artifact only

## Relationship to MCP Apps (checked against the extension spec, stable release 2026-01-26)

The MCP Apps extension defines a different, narrower axis under similar-sounding territory: tool **visibility** (`_meta.ui.visibility` = `"model"` | `"app"` | both), which is access control over who may invoke a given tool — not a taxonomy of journey-control levels. Do not conflate the two, and do not expect a wire-protocol field that maps 1:1 onto the three-level model above; it must be defined and enforced at little-loops' own contract layer, independent of whatever transport carries the interaction (a local bridge, an MCP Apps interactive resource, or any future render target).

## Impact

- **Priority**: P2 - not blocking today's artifact types (which are all level-1 notify), but should land before a transport mechanism (a local SSE bridge, ENH-3306) ships and defines the contract implicitly.
- **Effort**: Small - a document/spec artifact defining vocabulary and rules; no code changes to the FSM executor itself.
- **Risk**: Low - purely additive documentation; does not change existing artifact or executor behavior.
- **Breaking Change**: No.

## Scope Boundaries

- Out of scope: implementing any transport mechanism (SSE bridge, queue-backed command execution, MCP Apps interactive resource) — this issue defines the contract those mechanisms must follow, not a mechanism itself.
- Out of scope: mapping the three levels onto a specific wire-protocol field; the MCP Apps `_meta.ui.visibility` axis is a different, narrower concern (tool access control) and must not be conflated with journey-control levels.
- Out of scope: retrofitting existing one-way artifacts (dashboards, markdown reports) to a specific level — they already satisfy level 1 (notify) by construction.

## Scope

- The contract must be protocol- and render-target-agnostic: it must hold for htmx-based artifacts over a local bridge, for MCP Apps interactive resources, and for whatever render target follows.
- Write the contract as a document/spec artifact defining, per control level, what an artifact may emit, what the host is obligated to do with it, and which layer (host session vs. FSM executor) owns the resulting state change.
- This should land ahead of the transport mechanisms that will need it, not be reverse-engineered out of a shipped mechanism afterward.

## Acceptance Criteria

- [ ] `docs/reference/ARTIFACT_CONTROL_LEVELS.md` exists, opens with H1 + purpose paragraph + `> **Related Documentation:**` blockquote, and declares itself canonical.
- [ ] Contains the per-level obligations table above (5 columns, 3 rows) followed by prose disambiguating level 2 vs. level 3.
- [ ] States the two prohibitions (declared-level ceiling; transports never consume level-3 events).
- [ ] States explicitly that MCP Apps `_meta.ui.visibility` is a different axis and does not map onto the levels.
- [ ] Reserves the `artifact_interaction` event name with its field shape; `EVENT-SCHEMA.md` gains a matching *reserved* row.
- [ ] `docs/index.md` lists the doc; `docs/ARCHITECTURE.md` cross-links it; `docs/guides/MCP_SERVER_GUIDE.md` gains a one-line forward pointer (ENH-3306 fills it in).
- [ ] `scripts/tests/test_enh_3307_artifact_control_levels.py` passes.
- [ ] Unblocks ENH-3306 (`blocked_by: [ENH-3307]`).

## Related Issues

- ENH-3306 — first mechanism to conform (level 1 only); blocked by this issue.
- ENH-3035 / FEAT-3036 — browser-tab artifact template kit; a level-1 render target by construction, not a dependency.

## Status

Open.


## Session Log
- `/ll:confidence-check` - 2026-08-24T18:31:03 - `fc7f522d-5285-4cfe-80ae-165743f58e1d.jsonl`
- `/ll:refine-issue` - 2026-08-24T18:20:18 - `bf2ea761-d864-4b19-8078-67d47afee296.jsonl`
- `/ll:confidence-check` - 2026-08-24T01:05:48 - `b39154ec-0980-409b-84ab-ed4ad74fd627.jsonl`
- `/ll:wire-issue` - 2026-08-24T00:59:50 - `4cd71d49-8da8-4dc9-852e-8f17b59fed46.jsonl`
- `/ll:refine-issue` - 2026-08-24T00:51:43 - `9c480c31-6e54-4a77-8e21-d400559417c0.jsonl`
- `/ll:format-issue` - 2026-08-24T00:04:16 - `9d912d1c-def8-4ac1-b2d0-73ed036e9de0.jsonl`

## Tests

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- Contested test-file convention: this codebase has two competing shapes for issue-driven doc tests, and both are actively used, not one superseding the other. (a) One-off `test_enh_NNNN_*.py` files per issue — e.g. `test_enh_3171_mcp_project_root.py`, `test_enh_3174_mcp_resources_pagination.py` — but every one of those exercises actual code (CLI parsers, MCP tools), not pure doc existence/structure. (b) A single consolidated `scripts/tests/test_wiring_reference_docs.py` holding parametrized `DOC_STRINGS_PRESENT` (doc_path, expected_string, issue_id) and `DOC_FILES_MUST_EXIST` (doc_path, issue_id) tuples — that file's own docstring says it was produced by consolidating 28 originally-separate per-issue doc-wiring test files (ENH-1963). No pure doc-existence/doc-structure test in the current test suite lives in a standalone `test_enh_NNNN_*.py` file; that shape has moved to the consolidated file. The issue's own Integration Map/Tests section proposes a new standalone `test_enh_3307_artifact_control_levels.py` — that is a valid choice but runs counter to the more recent consolidation precedent; adding parametrized entries to `test_wiring_reference_docs.py` instead is the alternative the implementer should weigh.

## Documentation

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- `docs/index.md` placement is not settled by precedent the way the issue implies: the file's "Reference" section (lines 25-49) does not list `HOST_COMPATIBILITY.md` or `DEFERRAL_CODES.md` at all (both `docs/reference/*.md` files), while `EVENT-SCHEMA.md` — also a `docs/reference/*.md` file — is listed instead under a separate "Developer Documentation" section (line 57), not "Reference". The issue's Integration Map says to add a "Reference bullet" for `ARTIFACT_CONTROL_LEVELS.md`; given `EVENT-SCHEMA.md`'s actual placement under "Developer Documentation" rather than "Reference", confirm which section is intended before adding the index entry — the two existing docs/reference/*.md precedents disagree on which section a reference doc belongs in.
