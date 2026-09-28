---
id: BUG-3640
type: BUG
title: Generated host mirrors ship Claude model aliases as the model
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-28'
captured_at: '2026-09-28T20:15:06Z'
completed_at: '2026-09-28T21:43:07Z'
parent: EPIC-3563
labels:
- multi-host
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 85
score_complexity: 20
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 18
---

# BUG-3640: Generated host mirrors ship Claude model aliases as the model

## Summary

`ll-adapt` copies Claude Code model aliases (`sonnet`, `haiku`) from `agents/*.md` and `skills/*/SKILL.md` frontmatter verbatim into the generated mirrors for non-Claude hosts. The shipped `.codex/agents/*.toml` files declare `model = "sonnet"`, which is not a Codex model, and the `.gemini/`, `.qwen/`, `.kimi-code/` agent and skill mirrors carry `model: sonnet` / `model: haiku`. Split out of ENH-3533, which builds its `model_hint` resolution on top of this fix.

## Current Behavior

- `CodexEmitter.emit_agent` (`scripts/little_loops/adapters/codex.py:444`) does `model = str(fm.get("model") or "")` and `_format_agent_toml` always writes `model = "<value>"` — e.g. `.codex/agents/codebase-analyzer.toml:4` is `model = "sonnet"`.
- `KimiEmitter.emit_agent` (`kimi.py:111-126`), `QwenEmitter.emit_agent` (`qwen.py:128-145`) and every host's `emit_skill` run frontmatter through `_select_frontmatter_fields` (`adapters/core.py:119`), which only injects/strips `name` and `metadata.short-description`; any `model:` line passes through byte-for-byte (e.g. `.qwen/skills/wire-issue/SKILL.md:4`, `.gemini/skills/wire-issue/SKILL.md:4`, `.kimi-code/agents/codebase-analyzer.md:13`).
- Affected sources: 9 `agents/*.md` (all `model: sonnet`) and 20 `skills/*/SKILL.md` (`model: sonnet`, one `model: haiku`).
- Existing tests pin the passthrough as intended behavior: `test_adapters.py:635-638` (`TestCodexEmitterEmitAgent.test_toml_contains_model`), `test_adapters.py:2155-2162` (`TestQwenEmitterEmitAgent.test_claude_frontmatter_passes_through_verbatim`, asserts `"model: sonnet" in content`), `test_adapters.py:1500-1504`, and the golden corpus `scripts/tests/fixtures/adapt/agent_cases.json`.

## Steps to Reproduce

1. `grep -n '^model' .codex/agents/codebase-analyzer.toml .qwen/skills/wire-issue/SKILL.md .kimi-code/agents/codebase-analyzer.md`
2. Observe `model = "sonnet"` / `model: sonnet` — Claude Code aliases in artifacts consumed by Codex, Qwen and Kimi.
3. `ll-adapt --host codex` (dry run) reproduces the same value from `agents/codebase-analyzer.md:13`.

## Expected Behavior

A Claude Code model alias (a key of `host_runner.MODEL_ALIASES`: `fable`, `opus`, `sonnet`, `haiku`) or a concrete `claude-*` ID is never emitted into a non-Claude host's generated artifact. The model field is omitted so the host uses its configured default. A non-Anthropic literal `model:` value (an author deliberately targeting that host) still passes through unchanged.

## Proposed Solution

- Add one shared predicate in `adapters/core.py`, e.g. `_is_claude_model(value: str) -> bool` (`value.strip().lower() in MODEL_ALIASES or value.startswith("claude-")`).
- `CodexEmitter.emit_agent`: pass `""` when the predicate matches; make `_format_agent_toml` omit the `model = ...` line entirely when the model is empty (Codex treats an absent key as "use default"; an empty string is not a valid model either).
- `_select_frontmatter_fields`: strip a top-level `model:` line whose value matches the predicate. This covers kimi/qwen agents and every host's skill mirrors in one place.
- Regenerate all mirrors with `ll-adapt --host <codex|gemini|kimi-code|qwen> --apply` in the same change so `test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale` stays green.
- Update the pinned tests above to assert the alias is dropped, and add a case asserting a non-Anthropic literal (e.g. `model: gpt-5-codex`) still passes through.

## Program Design

### Signatures

- `_is_claude_model(value: str) -> bool` — new in `adapters/core.py`; true for a `MODEL_ALIASES` key or a `claude-*` ID.
- `_format_agent_toml(name: str, description: str, model: str, body: str, fm: dict) -> str` — existing (`codex.py:230`); omits the `model` line when `model` is empty.
- `_select_frontmatter_fields(content: str, name: str, fields_read: tuple[str, ...], short_desc: str = "") -> tuple[str, bool]` — existing (`core.py:119`); also strips a Claude-alias `model:` line.

### Call Path

- `process_agents` → `CodexEmitter.emit_agent` → `_is_claude_model` → `_format_agent_toml` → `.codex/agents/<name>.toml`
- `process_skills` → `QwenEmitter.emit_skill` → `_select_frontmatter_fields` → `_is_claude_model` → `.qwen/skills/<name>/SKILL.md`

## Impact

- **Priority**: P2 — shipped Codex agent definitions name a model Codex does not have.
- **Effort**: Small.
- **Risk**: Low — generated mirrors only; source frontmatter untouched.

## Acceptance Criteria

- [x] No file under `.codex/agents/`, `.gemini/`, `.qwen/`, `.kimi-code/` contains a `model` value that is a `MODEL_ALIASES` key or a `claude-*` ID (enforced by a test walking the committed mirrors).
- [x] A non-Anthropic literal `model:` in source frontmatter still reaches the generated artifact unchanged.
- [x] `test_host_artifacts_are_not_stale` passes with the regenerated mirrors.
- [x] Claude Code's native reading of `agents/*.md` / `skills/*/SKILL.md` is unchanged (source files not edited).

## Blocks

- ENH-3533 — builds its `model_hint` resolution (`_resolve_frontmatter_model`) on top of the alias-stripping seam this issue introduces in `_select_frontmatter_fields` / `CodexEmitter.emit_agent`

## Resolution

Implemented per the Proposed Solution:

- Added `_is_claude_model(value: str) -> bool` in `scripts/little_loops/adapters/core.py` (`MODEL_ALIASES` key or `claude-*` prefix, case-insensitive).
- `_select_frontmatter_fields` (`core.py`) now strips a top-level `model:` line whose value matches `_is_claude_model` — covers Kimi/Qwen agent emission and every host's skill emission in one place.
- `CodexEmitter.emit_agent` (`codex.py`) clears `model` to `""` when it matches `_is_claude_model`; `_format_agent_toml` now omits the `model = "..."` line entirely when `model` is empty, mirroring the existing `sandbox_mode`/`mcp_servers` optional-field pattern.
- Regenerated all mirrors: `ll-adapt --host codex|gemini|qwen|kimi-code --apply`.
- Updated pinned tests to assert the alias is stripped and added non-Anthropic-literal passthrough cases: `test_adapters.py` (`TestCodexEmitterEmitAgent`, `TestQwenEmitterEmitAgent`, new `TestIsClaudeModel` / `TestSelectFrontmatterFieldsModelStripping`), `test_adapt_agents_for_codex.py` (`TestProcessAgents`, `TestRealAgentsIntegrationGuard`), and the `agent_cases.json` golden corpus.
- Added `test_generated_mirrors_do_not_ship_claude_model_aliases` in `test_wiring_skills_and_commands.py`, walking every committed `.codex/`, `.gemini/`, `.qwen/`, `.kimi-code/` mirror — satisfies AC #1 directly, not just via unit coverage.
- Source `agents/*.md` / `skills/*/SKILL.md` files were not edited (AC #4).

## Status

**Done** | Created: 2026-09-28 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-09-28T21:42:51 - `9d03d44d-bf3d-4c2d-8c11-078b67f26820.jsonl`
- `/ll:verify-issues` - 2026-09-28T21:01:34 - `6ee1f8dc-4aaf-4326-9a2c-971c5336e607.jsonl`
- `/ll:confidence-check` - 2026-09-28T20:42:58 - `8c20e11f-c92c-4edc-8c38-39bebd1ef326.jsonl`
- `/ll:verify-issues` - 2026-09-28T20:26:37 - `ad55cfa6-adc7-4f43-81d2-899456dc7a54.jsonl`
