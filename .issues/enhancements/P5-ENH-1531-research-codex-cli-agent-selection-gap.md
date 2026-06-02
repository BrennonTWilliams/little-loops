---
id: ENH-1531
title: Research Codex CLI agent-selection gap and workarounds
priority: P5
type: ENH
status: done
captured_at: '2026-05-16T23:44:25Z'
discovered_date: '2026-05-16'
discovered_by: capture-issue
parent: EPIC-1463
relates_to:
- EPIC-1463
- FEAT-1462
- FEAT-1526
labels:
- codex
- host-compat
- tracking
- research
decision_needed: false
confidence_score: 100
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# ENH-1531: Research Codex CLI agent-selection gap and workarounds

## Summary

When Codex is the active host, `ll-auto --agent <name>` (and all other
orchestration CLIs that accept `--agent`) emits a `CapabilityNotSupported`
warning and silently drops the flag. Codex does not expose a `--agent`-style
CLI switch; subagents are model-spawned via `.codex/agents/*.toml` files, not
selected at invocation time. This issue tracks research into whether a
workaround exists or whether the gap is a permanent host-level difference.

## Current Behavior

`CodexRunner.build_streaming()` emits `CapabilityNotSupported` for `agent`:

```
# host_runner.py — CodexRunner.build_streaming()
if agent:
    warnings.warn(
        "Codex does not support CLI agent selection; subagents are "
        "model-spawned via .codex/agents/*.toml. Dropping --agent.",
        CapabilityNotSupported,
    )
```

`describe_capabilities()` reports `agent_select: unsupported`. Every
orchestration CLI (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop`) passes
the `--agent` value through `resolve_host().build_streaming(agent=...)`, so
the warning fires and the agent hint is lost.

## Expected Behavior

One of:

1. **Workaround found** — A supported Codex mechanism (prompt injection,
   system-prompt prepend, `.codex/` config stanza, or environment variable)
   lets the caller steer which `.codex/agents/*.toml` profile the session
   adopts. `CodexRunner` implements the workaround and upgrades
   `agent_select` from `unsupported` to `partial` or `full`.

2. **Gap confirmed permanent** — Research concludes no CLI-level mechanism
   exists. Document the finding, update `HOST_COMPATIBILITY.md` with a clear
   rationale footnote, and close this issue without code changes.

## Motivation

`ll-auto --agent code-reviewer` is a first-class workflow on Claude Code.
Codex users lose this without any explanation beyond a `CapabilityNotSupported`
warning. Knowing definitively whether this is fixable or permanent lets us
either improve the UX or write an honest "this will never work on Codex"
note in the docs.

## Proposed Solution

Research spike. Steps:

1. **Read Codex CLI docs / source** — check whether `codex exec` (or any
   subcommand) accepts a flag that selects a `.codex/agents/*.toml` profile
   by name.
2. **Test prompt injection** — try prepending `"Use the <name> agent."` to
   the prompt payload and observe whether Codex loads the matching
   `.codex/agents/<name>.toml` system prompt.
3. **Check environment variables** — inspect Codex CLI env-var surface for
   any `CODEX_AGENT` or similar override.
4. **Check `.codex/` config stanzas** — review whether a per-session config
   key (`.codex/config.toml`?) can pin an agent profile.
5. **Write up findings** — add a research note to
   `thoughts/research/codex-agent-selection.md` with verdict + evidence.
6. **Act on verdict** — either implement the workaround in `CodexRunner` or
   update `HOST_COMPATIBILITY.md` / `docs/codex/usage.md` with the permanent
   gap note.

## Implementation Steps

1. Research Codex CLI docs/source for any agent-selection flag, config stanza, or env-var mechanism — consult `thoughts/research/codex-headless-invocation.md` and `thoughts/research/codex-command-discovery.md` as starting points; no `CODEX_AGENT` env-var exists in this codebase so focus is external CLI surface
2. Test prompt injection — prepend the persona's `developer_instructions` content (from `.codex/agents/<name>.toml`) to the `prompt` string in `CodexRunner.build_streaming()`; observe whether Codex adopts the persona
3. Write up verdict in `thoughts/research/codex-agent-selection.md` — document evidence, tested approaches, and conclusion
4. **Workaround path**: Implement in `host_runner.py:CodexRunner.build_streaming()` following the ENH-1530 pattern (`build_blocking_json` json_schema tempfile workaround); update `describe_capabilities()` `CapabilityEntry("agent_select", ...)` from `"unsupported"` to `"partial"` with updated note; `HostCapabilities.agent_select` bool stays `False` (partial ≠ full); update `HOST_COMPATIBILITY.MD` `agent_select` row
5. **Gap path**: Add permanent-gap footnote to `docs/reference/HOST_COMPATIBILITY.md` and `docs/codex/usage.md` agent-selection section; no code changes needed
6. **Workaround path only** — add tests in `scripts/tests/test_host_runner.py::TestCodexRunner` following these patterns:
   - Pattern C (warning suppression): use `warnings.catch_warnings(); simplefilter("error", CapabilityNotSupported)` to prove no warning fires when workaround is active (mirrors `test_build_blocking_json_json_schema_no_warning`)
   - Pattern D (consistency): assert `describe_capabilities()` status matches the new warning behavior
   - Pattern A (describe_capabilities lookup): use `{e.name: e for e in report.capabilities}` dict idiom; assert `by_name["agent_select"].status == "partial"`

## Integration Map

### Files Potentially Modified

- `scripts/little_loops/host_runner.py` — upgrade `agent_select` capability
  and implement workaround in `build_streaming()` (workaround path only)
- `docs/reference/HOST_COMPATIBILITY.md` — update `agent_select` row in
  Codex column (either ✓/◐ or a permanent-gap footnote)
- `docs/codex/usage.md` — add or update the agent-selection section

### New Files

- `thoughts/research/codex-agent-selection.md` — research notes and verdict

### Tests (workaround path only)

- `scripts/tests/test_host_runner.py::TestCodexRunner` — new test asserting
  the workaround mechanism is applied when `agent` is provided; mirror the
  pattern in `test_codex_runner_agent_select_unsupported`

_Wiring pass added by `/ll:wire-issue` — tests that BREAK under workaround path:_
- `scripts/tests/test_host_runner.py:221` — `TestCodexRunner::test_build_streaming_emits_warning_for_agent` — asserts `pytest.warns(CapabilityNotSupported, match="agent")`; warning would be suppressed; must be replaced with Pattern C (no-warning) test [Agent 3 finding]
- `scripts/tests/test_host_runner.py:534` — `TestDescribeCapabilities::test_codex_runner_agent_select_unsupported` — asserts `by_name["agent_select"].status == "unsupported"`; must be updated to assert `== "partial"` [Agent 3 finding]
- `scripts/tests/test_host_runner.py:557` — `TestDescribeCapabilities::test_codex_warnings_consistent_with_describe_capabilities` — asserts (a) warning fires for `agent=` AND (b) `"agent_select" in unsupported`; both break; replace with Pattern D (consistency: no-warn + partial status) [Agent 3 finding]
- `scripts/tests/test_enh1495_doc_wiring.py:159` — `TestCodexUsageContent::test_mentions_capability_not_supported` — asserts `"CapabilityNotSupported" in docs/codex/usage.md`; only breaks if the workaround-path rewrite of the `--agent` section removes the last mention; ensure `CapabilityNotSupported` stays in the doc (e.g., via `--tools` limitation text) [Agent 3 finding]

_Wiring pass added by `/ll:wire-issue` — doc-wiring tests to keep passing:_
- `scripts/tests/test_enh1495_doc_wiring.py` — `TestCodexUsageContent::test_mentions_agent_flag_limitation` (line 153) asserts `"--agent" in usage.md`; safe as long as any `--agent` text remains
- `scripts/tests/test_feat1462_doc_wiring.py` — doc wiring tests covering `HOST_COMPATIBILITY.md` and `docs/reference/API.md` mention of `CapabilityNotSupported`; review after doc edits

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/doctor.py` — calls `describe_capabilities()` in `main_doctor()`; workaround path changes `agent_select` display from `✗` to `○` in `ll-doctor` output; exit code stays 1 (tool_allowlist remains unsupported) [Agent 1 finding]
- `scripts/little_loops/cli/action.py` — calls `describe_capabilities()` in `cmd_capabilities()`; serializes full `CapabilityReport` to JSON; "unsupported" → "partial" is a behavioral change in JSON output for downstream consumers [Agent 2 finding]
- `scripts/little_loops/cli/generate_skill_descriptions.py` — calls `describe_capabilities()` [Agent 1 finding]
- `scripts/little_loops/__init__.py` — re-exports `CapabilityEntry`, `CapabilityNotSupported`, `CapabilityReport`, `HostCapabilities`; no structural change needed but all consumers of the public package surface see the behavioral change [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — CodexRunner row under "Concrete runners" table states "Emits `CapabilityNotSupported` for `agent` / `tools` parameters"; workaround path: update to "Emits `CapabilityNotSupported` for `tools`" only (agent no longer warns) [Agent 2 finding]
- `docs/codex/README.md` — "deferred-features" paragraph explicitly states CapabilityNotSupported fires for agent flag; workaround path: update paragraph to reflect workaround; permanent-gap path: add rationale footnote [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Full agent-parameter call chain (FSM path):**
- `scripts/little_loops/fsm/schema.py` — `StateDefinition.agent: str | None` — agent value originates in loop YAML `agent:` field per-state, NOT from a CLI flag
- `scripts/little_loops/fsm/executor.py:874` — passes `agent=state.agent` when `action_mode == "prompt"`; shell-mode states always get `None`
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()` receives and forwards `agent` parameter
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()` calls `resolve_host().build_streaming(agent=agent)` — this is the call site where `CapabilityNotSupported` fires for Codex

**Correction — `ll-auto`/`ll-parallel` have no `--agent` CLI flag:**
- `scripts/little_loops/cli/auto.py` — `main_auto()` uses `add_common_auto_args()` from `cli_args.py`; no `--agent` argument registered
- `scripts/little_loops/cli/parallel.py` — same: no `--agent` arg
- Agent selection is a per-FSM-state config in `.loops/*.yaml`, not an invocation-time flag

**No `CODEX_AGENT` env-var exists:**
- Searched the entire codebase — no `CODEX_AGENT` or similar env-var is checked anywhere; research step 3 is unlikely to yield a result

**`.codex/agents/*.toml` `developer_instructions` field is the workaround surface:**
- Each generated `.toml` (e.g., `.codex/agents/codebase-pattern-finder.toml`) carries a `developer_instructions` field containing the full persona system prompt from `agents/*.md`
- Prepending the `developer_instructions` content to the `prompt` payload in `CodexRunner.build_streaming()` is the most viable prompt-injection approach for research step 2

**`HostCapabilities.agent_select` is a bool, not tri-state:**
- `HostCapabilities` in `host_runner.py` only has `bool` fields; the `"partial"` status lives exclusively in `CapabilityEntry` returned by `describe_capabilities()`
- Upgrading agent_select to "partial" requires: (1) change `CapabilityEntry.status` from `"unsupported"` to `"partial"`, (2) update the note; `HostCapabilities.agent_select` bool stays `False` until full CLI parity

**Upgrade pattern to follow (from ENH-1530 `json_schema`):**
- `host_runner.py:CodexRunner.build_blocking_json()` — the tempfile workaround for `json_schema` is the model for any capability upgrade
- Three-place change: (1) replace `warnings.warn(CapabilityNotSupported)` with implementation, (2) change `CapabilityEntry` status to `"partial"`, (3) add `cleanup_paths` if temp resources are created

**Second existing research doc found:**
- `thoughts/research/codex-command-discovery.md` — Codex CLI command discovery findings (supplement to `codex-headless-invocation.md`)

## Scope Boundaries

- **In scope**: Investigating Codex CLI's agent-selection mechanism; implementing a CLI-level or prompt-level workaround in `CodexRunner` if viable; documenting findings in `thoughts/research/` and updating `HOST_COMPATIBILITY.md`
- **Out of scope**: Redesigning agent-selection across all hosts; addressing other Codex capability gaps (streaming, JSON schema, etc.); changes to `ClaudeCodeRunner` or other non-Codex host runners

## Impact

- **Priority**: P5 — tracking; no current user demand. Promote if a Codex
  user explicitly asks for `--agent` parity.
- **Effort**: Small (research) + Small-to-Medium (implementation, if a
  workaround is found)
- **Risk**: Low — additive if a workaround lands; doc-only if gap is permanent
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/reference/HOST_COMPATIBILITY.md` | `agent_select` row in Codex column |
| `docs/codex/usage.md` | Agent-selection section |
| `thoughts/research/codex-headless-invocation.md` | Flag translation source of truth; `--agent` row documents current "N/A → CapabilityNotSupported" mapping |
| `thoughts/research/codex-command-discovery.md` | Codex CLI command discovery findings |
| `scripts/little_loops/host_runner.py` | `CodexRunner.build_streaming` + `describe_capabilities` |
| `scripts/little_loops/subprocess_utils.py` | `run_claude_command()` — call site that invokes `build_streaming(agent=...)` |
| `scripts/little_loops/fsm/schema.py` | `StateDefinition.agent` — origin of the agent value in FSM states |

## Labels

`codex`, `host-compat`, `tracking`, `research`

## Status

- [x] Research spike complete (`thoughts/research/codex-agent-selection.md`)
- [x] Verdict: **gap permanent** — no `--agent` CLI flag, no env-var, no prompt-injection path; openai/codex#10067 tracks the feature request (open, no timeline)
- [x] `HOST_COMPATIBILITY.md` updated — `[^agent]` footnote extended with permanent-gap rationale
- [x] Doc note added: `docs/codex/usage.md` `--agent` section rewritten with permanent-gap explanation; `docs/codex/README.md` deferred item updated with rationale

---

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/reference/API.md` — find the CodexRunner row under "Concrete runners" section and change "Emits `CapabilityNotSupported` for `agent` / `tools`" to "Emits `CapabilityNotSupported` for `tools`" (workaround path only)
8. Update `docs/codex/README.md` — find the "deferred-features" paragraph that states CapabilityNotSupported fires for agent; rewrite to reflect workaround (workaround path) or add rationale note (permanent-gap path)
9. Update 3 breaking tests in `scripts/tests/test_host_runner.py` (workaround path only):
   - Replace `test_build_streaming_emits_warning_for_agent` (line 221) with Pattern C no-warning test
   - Update `test_codex_runner_agent_select_unsupported` (line 534) to assert `== "partial"` 
   - Replace `test_codex_warnings_consistent_with_describe_capabilities` (line 557) with Pattern D consistency test
10. Verify `scripts/tests/test_enh1495_doc_wiring.py:159` (`test_mentions_capability_not_supported`) still passes after rewriting `docs/codex/usage.md`; ensure `CapabilityNotSupported` remains present in the doc

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-16_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- **Dual-path uncertainty**: The research spike determines which implementation path applies; each path is fully specified, but the researcher must avoid conflating workaround-path and gap-path steps mid-implementation.
- **Broad enumeration across 3 test sites** (workaround path): 3 breaking tests require coordinated replacement — Pattern C, D, and capability-status assertion must all be updated atomically or the test suite will be in a mixed state mid-PR.
- **Verify doc-wiring test survivability**: `test_mentions_capability_not_supported` (line 159 of `test_enh1495_doc_wiring.py`) is a cross-issue concern — the rewrite of `docs/codex/usage.md` must ensure `CapabilityNotSupported` remains present elsewhere in the doc.

## Session Log
- `/ll:confidence-check` - 2026-05-16T00:00:00Z - `f5d588c7-1ba0-4bcb-a5ba-c8587170e0e5.jsonl`
- `/ll:wire-issue` - 2026-05-17T00:19:49 - `a9fab1fc-477c-4ee2-a2eb-d8dd86332269.jsonl`
- `/ll:refine-issue` - 2026-05-17T00:15:49 - `084e1eff-7d0f-4eff-9e63-fe55c4d7d338.jsonl`
- `/ll:format-issue` - 2026-05-16T23:48:37 - `bfe30d89-0fc5-435c-9b3a-8f2605ed9dab.jsonl`
- `/ll:capture-issue` - 2026-05-16T23:44:25Z - `0206f559-f5c2-4dd0-8164-e7046c404768.jsonl`
