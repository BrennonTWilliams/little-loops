---
id: FEAT-3159
title: ll-adapt emitter for qwen
type: FEAT
status: done
priority: P2
parent: EPIC-3154
captured_at: '2026-08-13T01:28:37Z'
discovered_date: 2026-08-12
discovered_by: capture-issue
labels:
- qwen
- host-compat
completed_at: '2026-08-13T04:00:00Z'
---

# FEAT-3159: ll-adapt emitter for qwen

## Summary

Add `scripts/little_loops/adapters/qwen.py` with `QwenEmitter` satisfying
the `HostEmitter` protocol (`name` + `emit_skill`/`emit_command`/`emit_agent`
returning `"adapted"`/`"skipped"`, raising `AdapterError` with a remediation
hint for unsupported surfaces), an `_EMITTER_MAP["qwen"]` entry in
`adapters/core.py`, and a `HOST_CAPABILITIES["qwen"]` row in
`adapters/capabilities.py`. `KimiEmitter` (`adapters/kimi.py`) is the
template to fork. Landed atomically with the matrix adapter row (ENH-3162).
Keyed `qwen` per the epic's Naming Decisions so `ll-verify-host-map`
cross-validates.

## Motivation

`ll-adapt --host qwen --apply` bridges ll's skills/commands/agents into
Qwen-native discovery surfaces. All three are Markdown-native on Qwen, so
this is the cheapest emitter yet: near-1:1 skills, verbatim agents, and
native colon-namespaced commands (no skill-bridging fallback like
Codex/Kimi needed).

## Implementation Steps

1. **Skills** → `.qwen/skills/<name>/SKILL.md`: inject `name:` when absent;
   strip `metadata.short-description`; tolerate/keep other frontmatter.
   Emit-vs-skip policy for `disable-model-invocation` per FEAT-3155 R7
   (Codex precedent honors the flag and skips).
2. **Commands** → `.qwen/commands/ll/<stem>.md`: body verbatim with
   `$ARGUMENTS` → `{{args}}` rewrite; frontmatter `description:` preserved.
   Native colon namespacing yields `/ll:<stem>`.
3. **Agents** → `.qwen/agents/<name>.md`: verbatim (Claude frontmatter
   compatibility is documented upstream). `subagents: "native"` in the
   capability entry, so no degraded-mode emission (ENH-2874 path) applies.
4. `HOST_CAPABILITIES["qwen"]` row: config dir `.qwen`; skill output
   SKILL.md (name injected); command output Markdown
   `.qwen/commands/ll/<stem>.md` (native namespace); agent output Markdown
   native (verbatim Claude-style); subagents native.
5. Tests in `scripts/tests/test_adapters.py` (fixture helpers
   `_make_skill`/`_make_command`/`_make_agent` already exist).
6. Verify `ll-verify-host-map` green and `ll-adapt --host qwen --apply`
   reports adapted/skipped with zero errors.

## Integration Map

### Files to Modify

- `scripts/little_loops/adapters/core.py` — `_EMITTER_MAP["qwen"]`
- `scripts/little_loops/adapters/capabilities.py` — `HOST_CAPABILITIES["qwen"]`
- `scripts/tests/test_adapters.py` — emitter tests

### New Files

- `scripts/little_loops/adapters/qwen.py` — `QwenEmitter`

### Dependent Files

- `ll-verify-host-map` — cross-validates `HOST_CAPABILITIES ∩ _HOST_RUNNER_REGISTRY`
- `docs/reference/HOST_COMPATIBILITY.md` — adapter capability cells (ENH-3162)

## Impact

- **Priority**: P2 — independent track.
- **Effort**: S-M — emitter fork of KimiEmitter plus capability row and tests.
- **Risk**: Low — additive; emit-vs-skip policy for Claude-only skill keys gated on FEAT-3155 R7.
- **Breaking Change**: No.

## Verification Notes

2026-08-12 (DONE): `QwenEmitter` landed in `scripts/little_loops/adapters/qwen.py`
(forked from KimiEmitter): skills → `.qwen/skills/<name>/SKILL.md` (name
injected, `metadata.short-description` stripped, Claude-only keys tolerated
per FEAT-3155 R7); commands → `.qwen/commands/ll/<stem>.md` — TRUE command
emission via native subdirectory namespacing (`/ll:<stem>` live-verified),
`$ARGUMENTS` → `{{args}}` rewrite, description-only frontmatter; agents →
`.qwen/agents/<name>.md` verbatim (CC 2.1.168 compat). `_EMITTER_MAP["qwen"]`
+ `HOST_CAPABILITIES["qwen"]` (config dir `.qwen`, subagents native)
registered under the same key as the runner (naming decision honored —
`ll-verify-host-map` cross-validates). Adapter-host row landed atomically in
`docs/reference/HOST_COMPATIBILITY.md`; `ll-verify-host-map` green.
`ll-adapt --host qwen --apply` ran in-repo: **55 adapted / 53 skipped / 0
errors**; `.qwen/` mirror committed to the wiring-test enforcement
(`SKILL_MIRRORS_MUST_MATCH_SOURCE` extended). Tests: 22 QwenEmitter tests in
`test_adapters.py` (full file 193 passed); wiring suite 225 passed.

## Session Log
- `/ll:capture-issue` - 2026-08-13T01:28:37Z - qwen-code host integration report capture

---

**Done** | Created: 2026-08-12 | Completed: 2026-08-12 | Priority: P2
