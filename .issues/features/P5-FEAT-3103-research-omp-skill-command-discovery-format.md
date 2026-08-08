---
id: FEAT-3103
title: 'Research spike: oh-my-pi (omp) native skill/command discovery format'
type: feature
status: done
priority: P5
parent: FEAT-2787
labels:
- host-compat
- omp
- research
verify_verdict: VALID
program_design_not_applicable: true
confidence_score: 95
outcome_confidence: 78
score_complexity: 25
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 25
completed_at: '2026-08-08T10:51:01Z'
---

# FEAT-3103: Research spike: oh-my-pi (omp) native skill/command discovery format

## Current Behavior

Oh-my-pi's native on-disk discovery format for skills and slash commands
(directory layout, file naming, frontmatter shape, foreign-key tolerance) is
undocumented anywhere in this codebase or `thoughts/research/`.
`OmpEmitter.emit_skill`/`emit_command` (FEAT-2787) therefore cannot be
implemented without guessing.

## Expected Behavior

`thoughts/research/omp-skill-command-surface.md` exists, documenting omp's
skill discovery layout, command discovery layout, and frontmatter tolerance
for both, backed by evidence from the actual oh-my-pi tool/docs.

## Use Case

A developer picking up FEAT-3105 (`OmpEmitter.emit_skill`/`emit_command`)
opens `thoughts/research/omp-skill-command-surface.md` first and finds the
exact directory layout, file format, and frontmatter rules oh-my-pi expects
— sourced from the real tool, not inferred from other hosts' formats — so
the emitter implementation doesn't need its own format-discovery pass or
risk a rewrite once verified against the real tool.

## Summary

Determine oh-my-pi's native artefact discovery format for skills and slash
commands — the blocking unknown for `OmpEmitter.emit_skill`/`emit_command`
(FEAT-2787). Analogous prior spikes: FEAT-2911 (kimi-cli surface), FEAT-2179
(Gemini), FEAT-1483 (Codex) — each landed a `thoughts/research/*.md` artifact
before the corresponding emitter implementation issue started.

## Parent Issue

Decomposed from FEAT-2787: Implement the `omp` host adapter (all
`OmpEmitter` methods currently raise). FEAT-2787's own Codebase Research
Findings flagged this as the blocking unknown: "Nowhere in the codebase or
`thoughts/research/` is omp's native skill/command/agent *discovery* file
format ... recorded. This must be established (via oh-my-pi's own
docs/source at https://github.com/can1357/oh-my-pi) before
`emit_skill`/`emit_command`/`emit_agent` can be implemented."

Note: the agent-artefact case is already resolved by FEAT-2797 (`.omp/agents/`
+ `output:` frontmatter contract) and is out of scope here — this spike
covers skills and commands only.

## Motivation

`thoughts/research/omp-headless-flags.md` (from FEAT-1850) only covers
omp's CLI *invocation* flags (`--mode json`, `--tools <comma-list>`) and
explicitly excludes "Conformance + skill/command adaptation" from its scope
(lines 93-98). Without the actual on-disk skill/command layout oh-my-pi
discovers, `emit_skill`/`emit_command` cannot be written correctly —
guessing the format risks a full rewrite once verified against the real
tool, the same rework FEAT-2787's Confidence Check flagged as its top
ambiguity risk (score_ambiguity: 0/25).

## Proposed Solution

1. Consult oh-my-pi's own docs/source (https://github.com/can1357/oh-my-pi)
   and/or a local install to determine:
   - Where oh-my-pi looks for skill definitions on disk (directory layout,
     file naming, required frontmatter keys)
   - Where oh-my-pi looks for slash-command definitions (directory layout,
     file format — Markdown vs TOML vs other, frontmatter shape)
   - Whether either surface tolerates extra/foreign frontmatter keys
     (relevant to `core._select_frontmatter_fields`)
2. Write findings to `thoughts/research/omp-skill-command-surface.md`,
   modeled on `thoughts/research/omp-headless-flags.md`'s structure.
3. Update FEAT-2787's decomposed child (skill/command implementation issue)
   with a link to the new research artifact once this spike is `done`.

## Acceptance Criteria

- `thoughts/research/omp-skill-command-surface.md` exists and documents:
  omp's skill discovery directory/file layout, omp's command discovery
  directory/file layout, and frontmatter tolerance for both
- Findings are backed by evidence from the actual oh-my-pi tool/docs, not
  inference from other hosts' formats
- The skill/command implementation child issue (FEAT-3105) is updated to
  reference the artifact once this spike completes

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Files to Modify
- None — this is a research-only issue; no source code changes (see Impact section). The only artifact this issue produces is the new file `thoughts/research/omp-skill-command-surface.md`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/adapters/omp.py` — `OmpEmitter.emit_skill`/`emit_command` currently raise `AdapterError` unconditionally via a shared `_REMEDIATION` stub message; FEAT-3105 replaces these using this spike's findings.
- `.issues/features/P5-FEAT-3105-implement-ompemitter-emit-skill-and-emit-command.md` — `depends_on: [FEAT-2260, FEAT-3103]`; explicitly blocked on this spike's artifact landing.
- `scripts/little_loops/adapters/capabilities.py:102-118` — `HOST_CAPABILITIES["omp"]` stub entry (all fields at zero-value: `config_dir=None`, `*_output_format=None`, `frontmatter_fields_read=()`, `agents=False`, `commands=False`) that FEAT-3105 populates once the format is known.
- `scripts/little_loops/cli/verify_host_map.py` — `_check_emitter_agreement()` currently hard-fails if `omp_entry.agents or omp_entry.commands` is truthy; will need updating alongside FEAT-3105 once the capability entry changes.

_Wiring pass added by `/ll:wire-issue`:_
- `.issues/features/P4-FEAT-2797-omp-structured-output-surface-audit-and-agent-output-schema.md` — sibling issue that already resolved the analogous *agent*-discovery question (`.omp/agents/` directory, `TASK_AGENT_CONFIG_SOURCE = ".omp"` frontmatter contract); its `.omp`-scoped discovery precedent is directly relevant prior art for reasoning about where oh-my-pi likely scans skills/commands from too. [Agent 1 finding]
- `.issues/epics/P4-EPIC-2258-oh-my-pi-omp-host-adapter-tracking.md` (Children list, lines ~63-72) — does not yet list FEAT-3103 or FEAT-3105 among the epic's decomposed children; informational, not this issue's job to fix. [Agent 2 finding]

### Conventions in Force
- Codebase convention for an undocumented external tool format: a dedicated research-spike issue precedes the emitter issue, producing a standalone `thoughts/research/*.md` artifact before implementation starts — evidence: `thoughts/research/kimi-cli-surface.md` (FEAT-2911), `thoughts/research/gemini-cli-surface.md` (FEAT-2179), `thoughts/research/codex-command-discovery.md` (FEAT-1483).
- The prior omp-specific research artifact `thoughts/research/omp-headless-flags.md` (FEAT-1850) uses a topic-sectioned structure (`## Binary and install`, `## Flag translation table`, ..., ending `## Out of scope here`) rather than the numbered-question structure used by the kimi/gemini spikes. FEAT-3103's own Proposed Solution already designates `omp-headless-flags.md` as the structure to model the new artifact on.
- Contested convention: FEAT-2797 resolved the analogous *agent*-discovery problem by documenting findings directly in its own issue body and directing that `omp-headless-flags.md` gain a new section, rather than producing a dedicated new research file — this diverges from the FEAT-1850/FEAT-2911/FEAT-2179/FEAT-1483 pattern, each of which produced a brand-new file from a dedicated research-spike issue. Both conventions exist in this codebase; FEAT-3103's own Proposed Solution has already chosen the dedicated-new-file path.
- Downstream implementation issues are wired via `depends_on`, not `relates_to` — evidence: FEAT-3105 frontmatter `depends_on: [FEAT-2260, FEAT-3103]`.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/HOST_COMPATIBILITY.md` carries two separate omp-relevant tables: the "Adapter Host Capabilities" table (already cited above) and a distinct "Slash-command and skill discovery" table (~lines 117-129) whose header row enumerates Claude Code/OpenCode/Codex CLI/Gemini CLI/Kimi Code — omp has no column in this second table at all. FEAT-3105 will need to extend this specific table once this spike's findings land. [Agent 2 finding]

### Tests
- `scripts/tests/test_adapters.py` (~lines 89-92) — covers all emitters, including the current stub-era omp test; new coverage for real `emit_skill`/`emit_command` behavior lands with FEAT-3105, not this issue.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` (`DOC_FILES_MUST_EXIST`/`DOC_STRINGS_PRESENT` parametrized lists, ~lines 20-176 and 320-348) — the established mechanism for pinning a `thoughts/research/*.md` spike artifact's existence/content in the test suite; used by the Codex spike (FEAT-1483) but *not* by the more recent Gemini (FEAT-2179) or Kimi (FEAT-2911) spikes, both of which shipped as pure doc-artifact issues with zero test changes. This issue's own "no test changes" scope is consistent with the more recent (Gemini/Kimi) precedent; extending this file with an `omp-skill-command-surface.md`/`FEAT-3103` row remains optional, not required. [Agent 3 finding]

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — omp column/footnotes; updated by FEAT-3105 after this spike lands, not by this issue.
- `thoughts/research/omp-headless-flags.md` — sibling omp research artifact (FEAT-1850); explicitly excludes "Conformance + skill/command adaptation" from its scope (lines 93-98) — the exact gap `omp-skill-command-surface.md` fills.
- `docs/task-agent-discovery.md:37,60` — cited by FEAT-2797 as the upstream oh-my-pi doc establishing `TASK_AGENT_CONFIG_SOURCE = ".omp"` and the `output:` frontmatter contract for agents; the analogous upstream doc/source this spike must consult for skills/commands is oh-my-pi's own repo (https://github.com/can1357/oh-my-pi), not this repo-local path.

## Impact

- **Scope**: Small — this is a research-only issue producing a
  `thoughts/research/` artifact; no source code changes.


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-08_

**Readiness Score**: 95/100 → PROCEED (raw) — overridden to STOP — ADDRESS GAPS
**Outcome Confidence**: 78/100 → MODERATE

### Gaps to Address
- `## Program Design` section is missing entirely (not present-but-nonspecific — `format-check` lists it under `missing`, and `ll-issues check-design FEAT-3103` fails). The Program Design gate is armed in this project (`.ll/program-design-cutover.json` present) and this issue is not marked `program_design_not_applicable: true`, so the gate hard-overrides the otherwise-passing 95/100 raw readiness score to STOP. Remedy: since this is a research-only spike producing a `thoughts/research/*.md` artifact with no source code changes, set `program_design_not_applicable: true` in frontmatter rather than authoring a Program Design section for non-existent code.

### Outcome Risk Factors
- Test coverage (10/25): the artifact this issue produces (`thoughts/research/omp-skill-command-surface.md`) has no automated pinning test. `scripts/tests/test_wiring_skills_and_commands.py` is the established mechanism for this (used by the Codex spike, FEAT-1483) but is optional per the more recent Gemini/Kimi spike precedent already noted in this issue's own wiring pass — low risk, but worth a deliberate call rather than an oversight.

## Status

**Open** | Priority: P5

## Session Log
- `/ll:manage-issue` - 2026-08-08T10:51:00 - `2d37327b-3f1d-42ec-8a35-392640b8efbb.jsonl`
- `/ll:ready-issue` - 2026-08-08T10:31:23 - `9951a6bf-4756-4cc9-a947-0415b4e9a177.jsonl`
- `/ll:confidence-check` - 2026-08-08T10:27:20 - `2b7cdc0f-e30d-48c8-bb0e-8bf21d0f593f.jsonl`
- `/ll:verify-issues` - 2026-08-08T10:25:23 - `daea927e-5357-4f0a-aa51-f7da7d4d6af9.jsonl`
- `/ll:wire-issue` - 2026-08-08T10:23:23 - `b31f2860-914e-4815-863c-8ddbe96d021a.jsonl`
- `/ll:refine-issue` - 2026-08-08T10:16:22 - `8ebc972c-05c8-48e6-a497-14df0978fc40.jsonl`
- `/ll:issue-size-review` - 2026-08-08T10:09:55 - `70da93c7-f4f5-4a9e-85c1-cf030ebd11cb.jsonl`
