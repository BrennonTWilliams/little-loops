---
id: FEAT-2392
title: GeminiEmitter implementation (FEAT-2188 + FEAT-2189)
type: feature
status: done
priority: P4
discovered_date: 2026-06-29
completed_at: 2026-06-29 06:29:10+00:00
discovered_by: issue-size-review
parent: EPIC-2257
labels:
- host-compat
- adapters
- gemini
relates_to:
- FEAT-2188
- FEAT-2189
- FEAT-2391
- FEAT-2260
confidence_score: 89
outcome_confidence: 77
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 18
score_change_surface: 22
---

# FEAT-2392: GeminiEmitter implementation (FEAT-2188 + FEAT-2189)

## Summary

Implement `GeminiEmitter` to cover FEAT-2188 (Gemini skill frontmatter adaptation) and FEAT-2189 (Gemini commands `.toml` output), allowing FEAT-2188 and FEAT-2189 to be closed as superseded once this lands. Can run in parallel with FEAT-2391.

## Current Behavior

`ll-adapt` has no `--host gemini` support. Gemini skill and command adaptation (originally tracked in FEAT-2188 and FEAT-2189) remain unimplemented. Running `ll-adapt --host gemini` fails with an unrecognized host error.

## Expected Behavior

`ll-adapt --host gemini --apply` produces valid output in `.gemini/skills/` and `.gemini/commands/`. `GeminiEmitter` is registered in `_EMITTER_MAP` under `"gemini"`, follows the `HostEmitter` interface, and: injects `name: <dir-stem>` into skill frontmatter when absent; omits `metadata.short-description:` (Codex-only); raises `AdapterError` for agent emission (preview feature); skips `disable-model-invocation: true` skills and commands. FEAT-2188 and FEAT-2189 are superseded once tests pass.

## Use Case

A developer using the Gemini CLI wants ll skills and commands available natively without manual adaptation. They run `ll-adapt --host gemini --apply` and get a `.gemini/skills/` and `.gemini/commands/` directory tree with properly formatted files — the same workflow Codex users already have via `--host codex`.

## Motivation

Gemini CLI is an active host target for little-loops. Without `GeminiEmitter`, Gemini users cannot use the `ll-adapt` pipeline and must adapt skills manually. FEAT-2188 and FEAT-2189 partially addressed this in fragmented form; consolidating them under a single `GeminiEmitter` (following the emitter pattern established in FEAT-2391) closes the gap cleanly and makes future Gemini enhancements a single-file change.

## Acceptance Criteria

- `scripts/little_loops/adapters/gemini.py` implements `GeminiEmitter` registered in `_EMITTER_MAP` under `"gemini"`.
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
- `scripts/little_loops/adapters/core.py` — add `"gemini": ("little_loops.adapters.gemini", "GeminiEmitter")` to `_EMITTER_MAP` (lazy-import registry; no direct `from .gemini import` needed — `resolve_emitter` loads via importlib).
- `scripts/tests/test_adapters.py` — add `TestGeminiEmitter` class (can be in same file as FEAT-2391's tests since the test file is created there; coordinate timing or add to the file after FEAT-2391 creates it).

### Reference Details (from `thoughts/research/gemini-cli-surface.md`)
- Skill output path: `.gemini/skills/<name>/SKILL.md` (canonical); `.agents/skills/<name>/SKILL.md` is an alias but not the target.
- Command output path: `.gemini/commands/<stem>.toml`.
- Gemini command TOML has exactly: `description = "..."` (optional) and `prompt = "..."` (required).
- `name:` is required in SKILL.md for Gemini (used as slug); most ll skills already have it; `GeminiEmitter.emit_skill()` must inject `name: <dir-stem>` when absent.
- `metadata.short-description:` has no Gemini equivalent; must be omitted from Gemini SKILL.md output.
- Gemini agents are a preview feature; `GeminiEmitter.emit_agent()` should stub with `AdapterError`.

## Integration Map

### Files to Create
- `scripts/little_loops/adapters/gemini.py` — `GeminiEmitter` class

### Files to Modify
- `scripts/little_loops/adapters/core.py` — add `"gemini": ("little_loops.adapters.gemini", "GeminiEmitter")` to `_EMITTER_MAP` (lazy-import; no direct import needed)

### Dependent Files (Callers/Importers)
- `ll-adapt` CLI entry point — registry-driven; no source changes needed once `GeminiEmitter` is registered
- Any code calling `resolve_emitter("gemini")` or iterating `_EMITTER_MAP`

### Similar Patterns
- `scripts/little_loops/adapters/codex.py` — `CodexEmitter` is the reference implementation (FEAT-2391)
- `scripts/little_loops/adapters/omp.py` — `OmpEmitter.emit_agent()` raise pattern for the Gemini agent stub

### Tests
- `scripts/tests/test_adapters.py` — add `TestGeminiEmitter` class

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — may need a Gemini row in the host support table

### Configuration
- N/A

## Implementation Steps

1. Implement `GeminiEmitter` in `adapters/gemini.py` with the three `emit_*` methods per the spec above.
2. Add `"gemini": ("little_loops.adapters.gemini", "GeminiEmitter")` to `_EMITTER_MAP` in `adapters/core.py`.
3. Add `TestGeminiEmitter` tests to `scripts/tests/test_adapters.py`.
4. Verify `ll-adapt --host gemini --apply` runs clean.
5. Run `python -m mypy scripts/little_loops/` and `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P4 — Gemini CLI support is valuable but not blocking critical workflows; can land after FEAT-2391 stabilizes.
- **Effort**: Small-Medium — follows established `HostEmitter` pattern (CodexEmitter reference); one new file, minimal registry change.
- **Risk**: Low — isolated new emitter; no changes to existing Codex or core adapter paths.
- **Breaking Change**: No

## Resolution

Implemented `GeminiEmitter` in `scripts/little_loops/adapters/gemini.py` with:
- `emit_skill`: writes to `.gemini/skills/<name>/SKILL.md`, injects `name:` when absent, strips `metadata.short-description:` (Codex-only)
- `emit_command`: writes to `.gemini/commands/<stem>.toml` with `description` (optional) and `prompt` (required)
- `emit_agent`: raises `AdapterError` with preview-feature message
- Registered `"gemini"` in `_EMITTER_MAP` in `adapters/core.py`
- Added `AdapterError` catching in `process_agents` so stub emitters don't crash the CLI
- 84 tests pass (including 23 new `TestGeminiEmitter` tests)

## Session Log
- `/ll:manage-issue` - 2026-06-29T06:29:10 - implemented FEAT-2392
- `/ll:ready-issue` - 2026-06-29T06:18:25 - `ba910e83-237d-4f1f-bd90-4dd3525615d4.jsonl`
- `/ll:format-issue` - 2026-06-29T06:11:36 - `5ff2400a-52b6-44bf-83bf-a73bf6373f62.jsonl`
- `/ll:issue-size-review` - 2026-06-29T00:00:00 - `1113a873-5cfd-4186-9b3c-13c3306e634d.jsonl`
- `/ll:confidence-check` - 2026-06-29T00:00:00 - `21ef0acd-5c52-4bfb-b86b-08cb3b914dba.jsonl`

## Status

**Open** | Created: 2026-06-29 | Priority: P4
