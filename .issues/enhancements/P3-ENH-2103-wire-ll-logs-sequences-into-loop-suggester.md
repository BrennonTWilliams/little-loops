---
id: ENH-2103
title: Wire `ll-logs sequences` output into `/ll:loop-suggester`
type: ENH
priority: P3
status: done
captured_at: '2026-06-12T00:00:00Z'
completed_at: '2026-06-13T14:43:43Z'
discovered_date: 2026-06-12
discovered_by: review-epic
parent: EPIC-1918
relates_to:
- ENH-1919
- FEAT-1309
labels:
- telemetry
- ll-logs
- loops
- integration
confidence_score: 100
outcome_confidence: 87
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 23
---

# ENH-2103: Wire `ll-logs sequences` output into `/ll:loop-suggester`

## Summary

Update `/ll:loop-suggester` to optionally consume `ll-logs sequences` n-gram
output as an alternative (or supplement) to its current message-history
parsing path, so the sequences primitive shipped in ENH-1919 has a real
consumer.

## Current Behavior

`/ll:loop-suggester` reads raw message history exclusively via `ll-messages`.
The `ll-logs sequences` primitive (shipped in ENH-1919) has no consumer at the
loop-suggester integration layer — its n-gram output is never read by any
existing skill or command.

## Expected Behavior

`/ll:loop-suggester` gains a `--from-sequences` mode that reads `ll-logs
sequences` JSONL output and maps repeated command n-grams to loop-suggestion
candidates using the same YAML-generation path as the existing message-history
flow. When sequences output is missing or empty, the skill gracefully falls
back to the message-history path with a notice.

## Motivation

EPIC-1918's first success metric requires "at least one existing feature
consumes an ll-logs telemetry subcommand as a real input." ENH-1919 (done)
built the `sequences` extraction primitive, but its intended consumer —
FEAT-1309's passive notification UX — is deferred. Today nothing consumes
the primitive at the loop-suggester integration layer: `/ll:loop-suggester`
still parses raw message history via `ll-messages`.

Wiring sequences into loop-suggester unblocks the telemetry pipeline without
requiring FEAT-1309's notification surface.

## Acceptance Criteria

- [ ] `/ll:loop-suggester` accepts a mode/flag (e.g. `--from-sequences`) that
  reads `ll-logs sequences` JSONL output instead of (or in addition to)
  `ll-messages` output
- [ ] Repeated command n-grams from sequences are mapped to loop-suggestion
  candidates with the same YAML-generation path as the existing flow
- [ ] Graceful degradation: missing/empty sequences output falls back to the
  message-history path with a notice
- [ ] Skill docs updated (`skills/loop-suggester/SKILL.md` argument table and
  trigger keywords)

## Scope Boundaries

- **In scope**: Adding `--from-sequences` input mode to `/ll:loop-suggester`;
  updating `skills/loop-suggester/SKILL.md` docs; graceful fallback behavior.
- **Out of scope**: Changes to `ll-logs sequences` output format (ENH-1919 is
  done); building FEAT-1309's passive notification surface; changes to other
  skills or commands beyond loop-suggester.

## Integration Map

### Files to Modify
- `commands/loop-suggester.md` — PRIMARY: add `--from-sequences` routing gate, `Bash(ll-logs:*)` to `allowed-tools`, and `## From-Sequences Mode` section; update `argument-hint` frontmatter to `[messages.jsonl|--from-commands|--from-sequences]`
- `skills/ll-loop-suggester/SKILL.md` — update `description:`, trigger keywords, and `argument-hint:` frontmatter
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` — document the sequences-driven path alongside the existing message-history pipeline
- `skills/ll-loop-suggester/agents/openai.yaml` — Codex bridge stub; verify `metadata.short-description` stays aligned with updated SKILL.md description (run `ll-generate-skill-descriptions` or update manually) [Wiring pass]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/logs.py` — READ-ONLY data provider; `_cmd_sequences()` produces the `ll-logs sequences --json` output the new mode consumes; `ChainResult.to_dict()` defines the input schema `{chain: [str], count: int, edges: [{from, to, freq}]}`
- `scripts/little_loops/cli/messages.py` — READ-ONLY fallback; backs the existing `ll-messages` path via `main_messages()`; no changes needed

### Similar Patterns
- `commands/loop-suggester.md:34` — `--from-commands` routing gate is the direct model; pattern: string-match `$ARGUMENTS` and jump to named `## From-Commands Mode` section
- `commands/loop-suggester.md` (Step FC-1 through FC-4) — `## From-Commands Mode` section structure is the structural template for `## From-Sequences Mode`
- `skills/scope-epic/SKILL.md` — `--from-doc <path>` Bash-regex capture (`[[ "$ARGUMENTS" =~ --from-doc[[:space:]]+([^[:space:]]+) ]]`) if `--from-sequences` accepts an optional file path argument

### Tests
- `scripts/tests/test_loop_suggester.py:205` — `TestFromCommandsModeSchema` class is the direct template; add a parallel `TestFromSequencesModeSchema` class with `ChainResult`-shaped fixtures
- `scripts/tests/test_ll_logs.py:911` — `TestSequences.test_sequences_json_output()` has existing JSON schema assertions for `ChainResult` output to reference

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat1896_skill_bridges.py` — add 3 structural assertions following `TestGoNoGoFrontmatter` pattern (line 33 + `_frontmatter()` helper at line 21): (1) `Bash(ll-logs:*)` present in `commands/loop-suggester.md` frontmatter; (2) `--from-sequences` present in body of `commands/loop-suggester.md`; (3) `--from-sequences` present in `skills/ll-loop-suggester/SKILL.md` [Agent 3 finding]
- `TestFromSequencesModeSchema` in `test_loop_suggester.py` — 8 required methods: `test_chain_result_input_required_fields` (chain/count/edges schema); `test_from_sequences_metadata_fields` (keys: source, sequences_file, chains_analyzed, analysis_timestamp, skill); `test_from_sequences_metadata_source_distinguisher` (source == "sequences"); `test_from_sequences_proposal_required_fields`; `test_from_sequences_chain_maps_to_paradigm`; `test_from_sequences_confidence_base`; `test_from_sequences_yaml_config_parseable`; `test_from_sequences_fallback_notice_on_empty_input` [Agent 3 finding]

### Documentation
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` — document the sequences-driven path

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — section `### /ll:loop-suggester` (lines 616–639): Arguments block and Usage code block document `--from-commands` explicitly; add parallel `--from-sequences` entry and update the argument-hint example [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. Add `--from-sequences` flag to `skills/loop-suggester/SKILL.md` argument table
2. Implement JSONL reading from `ll-logs sequences` output and n-gram → candidate mapping
3. Wire graceful fallback to message-history path when sequences output is empty/missing
4. Update skill docs: argument table, trigger keywords, examples
5. Update `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` with sequences-driven path
6. Add tests for the new input mode and fallback behavior

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Primary file is `commands/loop-suggester.md`** (not the skill stub): all logic lives here; update step 1 to target this file
- **`allowed-tools` addition required**: add `Bash(ll-logs:*)` alongside `Bash(ll-messages:*)` in `commands/loop-suggester.md` frontmatter — without this the Bash call to `ll-logs sequences` will be blocked
- **Routing gate pattern** (line 34): `If "--from-sequences" in $ARGUMENTS → skip to ## From-Sequences Mode` — same string-match style as the existing `--from-commands` gate; no argparse involved
- **N-gram → candidate mapping**: `chain` (list of tool names) maps directly to the existing Step 2 "Build Tool Sequences" detection; `count` maps to frequency thresholds in Steps 3/6; `edges[].freq` maps to the "consistency bonus" in Step 6 confidence formula
- **Output metadata**: set `analysis_metadata.source: "sequences"` to distinguish from `"commands-catalog"` (Step FC-4) and the message-history path (`source_file: "live extraction"`)
- **Concrete step order**: (1) update `commands/loop-suggester.md` frontmatter (argument-hint + allowed-tools), (2) add routing gate after line 34, (3) add `## From-Sequences Mode` section modeled on `## From-Commands Mode`, (4) update `skills/ll-loop-suggester/SKILL.md`, (5) update `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md`, (6) add `TestFromSequencesModeSchema` to `scripts/tests/test_loop_suggester.py:205`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/reference/COMMANDS.md` — add `--from-sequences` to the Arguments block and Usage code block under `### /ll:loop-suggester` section (lines 616–639)
8. Update `metadata.short-description` at line 8 of `skills/ll-loop-suggester/SKILL.md` after expanding the `description:` block; run `ll-generate-skill-descriptions` to auto-regenerate or update manually; verify token budget with `ll-verify-skill-budget`
9. Add structural wiring tests to `scripts/tests/test_feat1896_skill_bridges.py` asserting (a) `Bash(ll-logs:*)` in `commands/loop-suggester.md` frontmatter and (b) `--from-sequences` presence in `skills/ll-loop-suggester/SKILL.md`
10. Ensure `TestFromSequencesModeSchema` in step 6 covers all 8 scenarios listed in the Tests subsection above

## Impact

- **Priority**: P3 — satisfies EPIC-1918 success metric 1
- **Effort**: Small — input-mode addition to an existing skill
- **Risk**: Low — additive; existing paths unchanged
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-12 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-06-13T14:31:06 - `ba3df577-e2e2-4da5-96a4-86ef129cf5e9.jsonl`
- `/ll:confidence-check` - 2026-06-13T00:00:00Z - `039b5581-6074-4235-966a-740a7054cc93.jsonl`
- `/ll:wire-issue` - 2026-06-13T14:21:45 - `4d90a007-cbf7-4676-a9b3-c7c378d7f4c5.jsonl`
- `/ll:refine-issue` - 2026-06-13T14:08:12 - `08370739-55b2-494f-8c11-f2199b52c4f3.jsonl`
- `/ll:format-issue` - 2026-06-13T13:59:49 - `0df548d1-097e-4c28-ab0b-0c0e9ac98101.jsonl`
