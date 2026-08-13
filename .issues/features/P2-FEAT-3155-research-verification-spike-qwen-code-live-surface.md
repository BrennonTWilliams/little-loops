---
id: FEAT-3155
title: 'Research verification spike: live qwen 0.21.6 surface confirmation'
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
- spike
completed_at: '2026-08-13T02:05:00Z'
---

# FEAT-3155: Research verification spike — live qwen 0.21.6 surface confirmation

## Summary

Live-verify the desk-research findings of
`thoughts/qwen-code-host-integration-report.md` (§3, marked **(verify)**)
against the installed qwen 0.21.6 binary. All downstream implementation
children depend on these findings — especially R2 (headless hook firing),
which decides the hook adapter's settings scope.

## Motivation

Desk research (bundled docs + `--help`) established the surface, but five
items need live confirmation before the runner and hook adapter land. The
Kimi precedent (BUG-2921: plugin hooks inert in `-p` print mode) shows
doc-level claims about hook firing can fail silently in headless mode.

## Implementation Steps

Verify each item live and record in `thoughts/research/qwen-code-surface.md`
(`thoughts/` is git-ignored by repo convention, as with prior spikes):

1. **R1** — `--yolo` / `--approval-mode` argv acceptance and interaction
   with `-p` (flags hidden from `--help`; fallback: settings
   `tools.approvalMode: "yolo"`).
2. **R2** — project `.qwen/settings.json` hooks firing under `qwen -p`
   headless. Install a probe hook (`command` executor writing a sentinel
   file) in a scratch project; run `qwen -p "…"` there; check the sentinel.
   DECIDES the FEAT-3158 settings scope (project vs user `~/.qwen/settings.json`).
3. **R3** — marketplace conversion fidelity: `qwen extensions install
   BrennonTWilliams/little-loops:ll` end-to-end — converted hooks, matcher
   translation (`Write|Edit` → `write_file|edit`), `/ll:*` namespace,
   `${CLAUDE_PLUGIN_ROOT}` resolution.
4. **R4** — stream-json event field shapes incl. `usage` payloads for token
   reporting (`{"type":"system"|"assistant"|"result", …}` — pin the shapes
   the runner tests will assert).
5. **R7** — skill frontmatter tolerance for Claude-only keys
   (`disable-model-invocation`, `allowed-tools`).
6. Bonus: exit-code behavior for input errors (Gemini used 42; Qwen
   documents 53/55/130) and `--json-schema` inline acceptance.

## Integration Map

### Files to Modify

- None (research only).

### New Files

- `thoughts/research/qwen-code-surface.md` — spike artifact (git-ignored).

### Dependent Files

- `.issues/features/P2-FEAT-3158-*.md` — settings-scope decision consumes R2.
- `.issues/enhancements/P2-ENH-3156-*.md` — runner argv shapes consume R1/R4.

## Impact

- **Priority**: P2 — gates the epic's critical path.
- **Effort**: S — read-only binary probing plus one scratch-project hook probe.
- **Risk**: Low — no repo code changes.
- **Breaking Change**: No.

## Verification Notes

2026-08-12 (DONE): All spike items live-verified against qwen 0.21.6; artifact
written to `thoughts/research/qwen-code-surface.md`. Headline results:
- R1 ✅ `--yolo` accepted with `-p` (stderr warning; suppress via `QWEN_CODE_SUPPRESS_YOLO_WARNING=1`).
- R2 ✅ project `.qwen/settings.json` hooks fire under `qwen -p` (SessionStart,
  UserPromptSubmit, PreToolUse, PostToolUse, Stop) — **except SessionEnd, which
  does not fire headless** (2 runs). Headless cleanup rides the legacy Stop
  scripts; managed block stays project-scope (no user-scope fallback needed).
- R3 ⚠️ marketplace install works but `hooks/hooks.json` is copied verbatim —
  NO matcher translation (Claude tool names never match Qwen runtime ids) and
  commands flatten to `ll-<stem>` (no colon namespace). Agents load verbatim.
- R4 ✅ stream-json/blocking-json shapes pinned (buffered array; final `result`
  element carries `.result`/`.is_error`/`.usage`; `stream_event` deltas ignorable).
- R7 ✅ Claude-only skill frontmatter keys tolerated; skill loaded + invoked.
- Bonus ✅ inline `--json-schema` verified → `structured_output=True` confirmed;
  session store = `~/.qwen/projects/<cwd with / → ->/chats/<id>.jsonl` (symlink-resolved).
Probe extension uninstalled after inspection; `/tmp/ll-qwen-spike` scratch retained.

## Session Log
- `/ll:capture-issue` - 2026-08-13T01:28:37Z - qwen-code host integration report capture
- spike execution - 2026-08-13T02:05:00Z - live probes completed, artifact written

---

**Done** | Created: 2026-08-12 | Completed: 2026-08-12 | Priority: P2
