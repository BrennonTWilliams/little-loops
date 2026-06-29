---
id: FEAT-2392
title: GeminiEmitter implementation (FEAT-2188 + FEAT-2189)
type: feature
status: open
priority: P4
discovered_date: 2026-06-29
discovered_by: issue-size-review
parent: FEAT-2260
labels:
- host-compat
- adapters
- gemini
relates_to:
- FEAT-2188
- FEAT-2189
- FEAT-2391
---

# FEAT-2392: GeminiEmitter implementation (FEAT-2188 + FEAT-2189)

## Summary

Implement `GeminiEmitter` to cover FEAT-2188 (Gemini skill frontmatter adaptation) and FEAT-2189 (Gemini commands `.toml` output), allowing FEAT-2188 and FEAT-2189 to be closed as superseded once this lands. Can run in parallel with FEAT-2391.

## Parent Issue

Decomposed from FEAT-2260: Generic host-parameterized skill + command adapter

## Acceptance Criteria

- `scripts/little_loops/adapters/gemini.py` implements `GeminiEmitter` registered in `_EMITTER_REGISTRY` under `"gemini"`.
- `GeminiEmitter.emit_skill()` outputs to `.gemini/skills/<name>/SKILL.md`; injects `name: <dir-stem>` when absent from source frontmatter; omits `metadata.short-description:` (Codex-only field).
- `GeminiEmitter.emit_command()` outputs to `.gemini/commands/<stem>.toml` with exactly two fields: `description = "..."` (from frontmatter `description:`) and `prompt = "..."` (full markdown body minus frontmatter). Prompt field is required; description is optional.
- `GeminiEmitter.emit_agent()` raises `AdapterError("gemini agent emission not yet stable — Gemini agents are a preview feature; open a PR when they exit preview")` — stub following OmpEmitter pattern.
- `disable-model-invocation: true` skills and commands are skipped for Gemini output (consistent with shared core filter).
- `ll-adapt --host gemini --apply` produces valid output in `.gemini/skills/` and `.gemini/commands/`.
- Tests in `scripts/tests/test_adapters.py` cover `GeminiEmitter`: `emit_skill` with and without `name:` in source frontmatter, `name:` injection, `metadata.short-description:` omission, `emit_command` TOML field mapping (description + prompt), `emit_agent` raises `AdapterError`.
- FEAT-2188 and FEAT-2189 can be closed as superseded once this implementation passes tests and wires cleanly.

## Proposed Solution

### Files to Create
- `scripts/little_loops/adapters/gemini.py` — `GeminiEmitter(HostEmitter)` implementing:
  - `emit_skill(skill_meta: dict) -> str`: inject `name: <dir-stem>` if absent; strip `metadata.short-description:`; output content is the modified SKILL.md body (frontmatter + content).
  - `emit_command(cmd_meta: dict) -> str`: produce TOML with `description` (optional) and `prompt` (required, mapped from command body).
  - `emit_agent(agent_meta: dict) -> str`: raise `AdapterError` with preview-feature message.

### Files to Modify
- `scripts/little_loops/adapters/core.py` — register `GeminiEmitter` in `_EMITTER_REGISTRY` (import + registry entry).
- `scripts/tests/test_adapters.py` — add `TestGeminiEmitter` class (can be in same file as FEAT-2391's tests since the test file is created there; coordinate timing or add to the file after FEAT-2391 creates it).

### Reference Details (from `thoughts/research/gemini-cli-surface.md`)
- Skill output path: `.gemini/skills/<name>/SKILL.md` (canonical); `.agents/skills/<name>/SKILL.md` is an alias but not the target.
- Command output path: `.gemini/commands/<stem>.toml`.
- Gemini command TOML has exactly: `description = "..."` (optional) and `prompt = "..."` (required).
- `name:` is required in SKILL.md for Gemini (used as slug); most ll skills already have it; `GeminiEmitter.emit_skill()` must inject `name: <dir-stem>` when absent.
- `metadata.short-description:` has no Gemini equivalent; must be omitted from Gemini SKILL.md output.
- Gemini agents are a preview feature; `GeminiEmitter.emit_agent()` should stub with `AdapterError`.

## Implementation Steps

1. Implement `GeminiEmitter` in `adapters/gemini.py` with the three `emit_*` methods per the spec above.
2. Register `GeminiEmitter` in `_EMITTER_REGISTRY` in `adapters/core.py`.
3. Add `TestGeminiEmitter` tests to `scripts/tests/test_adapters.py`.
4. Verify `ll-adapt --host gemini --apply` runs clean.
5. Run `python -m mypy scripts/little_loops/` and `python -m pytest scripts/tests/`.

## Session Log
- `/ll:issue-size-review` - 2026-06-29T00:00:00 - `1113a873-5cfd-4186-9b3c-13c3306e634d.jsonl`
