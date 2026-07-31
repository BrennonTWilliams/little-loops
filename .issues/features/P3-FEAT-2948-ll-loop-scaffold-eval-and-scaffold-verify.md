---
id: FEAT-2948
title: "ll-loop scaffold-eval / scaffold-verify: YAML templating for eval and verification loops"
type: FEAT
priority: P3
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
labels:
- cli
- loops
- eval
---

# FEAT-2948: `ll-loop scaffold-eval` / `scaffold-verify` — FSM YAML templating in Python

## Summary

`skills/create-eval-from-issues/SKILL.md` (482 lines) and `skills/verify-issue-loop/SKILL.md` (212 lines + templates.md) hand-assemble FSM YAML in prose: create-eval carries two full YAML templates (L265–422) including proof-state slugification, `check_proof_t1.on_yes: check_proof_t2` chaining, and `execute.next` rewiring; verify-issue-loop normalizes bullet markers (L129–135) and selects timeouts. Mis-chaining states is a real bug class. Emit the YAML from Python; the LLM supplies only prompt/criteria strings.

## Current Behavior

The LLM reads acceptance criteria via `ll-issues show --json`, then assembles loop YAML by following ~250 lines of templating instructions, validated only after the fact by `ll-loop validate`.

## Expected Behavior

- `ll-loop scaffold-eval --issues FEAT-1,FEAT-2 [--dsl] [--out PATH|--stdout] --json` — reads criteria via `issue_parser.parse_file`, emits schema-valid loop YAML with placeholder slots for the `execute` prompt and per-criterion `llm_structured` prompts; proof-state chaining generated, not narrated.
- `ll-loop scaffold-verify <id> [--adversarial] [--out PATH|--stdout] --json` — same for single-issue verification loops (criteria extraction with bullet-marker normalization, timeout selection).
- Both skills shrink to: synthesize the natural-language prompts/criteria (genuine authoring), fill the placeholders, run `ll-loop validate`.

## Proposed Solution

Reuse the loop schema/validation already in `ll-loop` (`fsm/schema.py`, `fsm/validation.py`) so scaffolds are validated at generation time; criteria extraction shares `issue_parser` section parsing. The two scaffolds share a templating core.

## Implementation Steps

1. Shared scaffold core + `scaffold-verify` (smaller).
2. `scaffold-eval` incl. proof-state chaining; defer `--dsl` growth to a follow-up if it balloons.
3. Slim both skills; keep prompt-authoring guidance only.
4. Tests: generated YAML passes `ll-loop validate` (incl. MR-gates) for fixture issues; chaining correctness for N proof states.

## Use Case

`/ll:create-eval-from-issues FEAT-1234` runs `ll-loop scaffold-eval --issues FEAT-1234 --stdout`, receives schema-valid loop YAML with `<PROMPT>` / `<CRITERION_N>` placeholder slots, writes the two synthesized natural-language strings into them, and validates — the model never assembles states or chains `on_yes` routes by hand.

## Program Design

### Types

- `ScaffoldResult: dataclass`
  - `yaml_path: Path | None`
  - `yaml_text: str`
  - `placeholders: list[str]`
  - `validated: bool`
- `CriterionSlot: dataclass`
  - `index: int`
  - `source_text: str`
  - `state_name: str`

### Signatures

- `extract_criteria(issue: IssueInfo, body: str) -> list[CriterionSlot]` — bullet-marker normalization (`- [ ]`, `- [x]`, `-`, `*`, `1.`; skip sub-bullets)
- `scaffold_eval(issue_ids: list[str], dsl: bool) -> ScaffoldResult` — generates execute + chained `llm_structured` proof states
- `scaffold_verify(issue_id: str, adversarial: bool) -> ScaffoldResult` — timeout selection (1800/2700) in code
- Both validate via `fsm.validation` before returning

### Call Path

- `main_loop()` (existing, `cli/loop/__init__.py`) -> `scaffold_eval()` / `scaffold_verify()`
- `extract_criteria()` -> `find_issues()` (existing, `issue_parser.py`)

## Impact

- **Priority**: P3 - Removes a real mis-chaining bug class, but eval/verify authoring is lower-traffic than issue flow
- **Effort**: Medium - Shared templating core + two frontends
- **Risk**: Low - Output validated at generation time by the existing FSM validator

## Status

**Open** | Created: 2026-07-31 | Priority: P3

## Acceptance Criteria

- [ ] Generated YAML always passes `ll-loop validate` before the LLM touches it
- [ ] Both skills contain no YAML templates or state-chaining instructions
- [ ] Placeholder slots are the only LLM-filled content
- [ ] pytest coverage in `scripts/tests/`
