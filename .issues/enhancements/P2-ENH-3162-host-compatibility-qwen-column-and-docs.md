---
id: ENH-3162
title: HOST_COMPATIBILITY.md qwen column + docs/qwen/ onboarding
type: ENH
status: done
priority: P2
parent: EPIC-3154
depends_on:
- ENH-3156
- FEAT-3158
- FEAT-3159
captured_at: '2026-08-13T01:28:37Z'
discovered_date: 2026-08-12
discovered_by: capture-issue
labels:
- qwen
- host-compat
- docs
completed_at: '2026-08-13T05:10:00Z'
---

# ENH-3162: HOST_COMPATIBILITY.md qwen column + docs/qwen/ onboarding

## Summary

Final gate of EPIC-3154: complete the qwen column across all
`docs/reference/HOST_COMPATIBILITY.md` tables (hook intents, discovery,
runner capabilities, adapter capabilities, orchestration, config probe,
state, installation) with no unknown cells — every cell ✓, ✗ (with tracking
issue), or N/A — and land the `docs/qwen/` onboarding trio
(`getting-started.md`, `hook-events.md`, `automation.md`) per `docs/kimi/`.
Also `docs/ARCHITECTURE.md` (`QwenRunner` in the component table) and the
README Qwen Code install section.

## Motivation

The parity matrix is the epic's end-state acceptance artifact, and the
onboarding trio is how Qwen users actually adopt ll. Pinning the verified
qwen version in docs (as Kimi docs pin 0.30.0) manages the fast-moving
0.x-upstream risk (R6).

## Implementation Steps

1. Draft cells per §4 of the integration report:
   - **Hook intents:** `session_start` ✓, `pre_compact` ✓,
     `user_prompt_submit` ✓ (blockable), `pre_tool_use` ✓ (blockable),
     `post_tool_use` ✓ (fire-and-forget), `session_end` ✓ (native),
     `post_compact` N/A, `permission_request` deferred (native
     `PermissionRequest`/`PermissionDenied` exist; no ll consumer yet).
   - **Discovery:** slash-commands ✓ (`.qwen/commands/ll/*.md` →
     `/ll:<stem>`), skills ✓ (`.qwen/skills/`, near-1:1).
   - **Runner:** Streaming ✓; Permission skip ✓ (`--yolo`); Agent selection
     ✗ (no `--agent` flag; planned upstream — Gemini posture); Tool allowlist
     ✗ (denylist-only `--exclude-tools`); `json_schema` ✓; `structured_output`
     ✓ (**second host ever**); Token reporting ✓ (verify event shape via R4).
   - **Adapter:** config dir `.qwen`; SKILL.md (name injected); commands
     `.qwen/commands/ll/<stem>.md` (native namespace); agents Markdown
     native (verbatim); subagents native.
2. `docs/qwen/getting-started.md` (install via `qwen extensions install`,
   `ll-init --hosts qwen`), `docs/qwen/hook-events.md` (event→intent table),
   `docs/qwen/automation.md` (`LL_HOST_CLI=qwen ll-auto` etc.). Pin qwen
   0.21.6 as the verified version.
3. `docs/ARCHITECTURE.md` — `QwenRunner` in the component table.
4. `README.md` — Qwen Code install section (mirroring the Kimi section).

## Integration Map

### Files to Modify

- `docs/reference/HOST_COMPATIBILITY.md` — qwen column across all tables + footnote
- `docs/ARCHITECTURE.md` — `QwenRunner` in component table
- `README.md` — Qwen Code install section

### New Files

- `docs/qwen/getting-started.md`, `docs/qwen/hook-events.md`, `docs/qwen/automation.md`

### Dependent Files

- mkdocs.yml navigation (if docs/kimi/ entries exist there, mirror for docs/qwen/)

## Impact

- **Priority**: P2 — final gate; lands after the implementation children.
- **Effort**: S-M — matrix column + three doc pages + two small doc edits.
- **Risk**: Low — docs only; accuracy depends on the implementation children being landed first.
- **Breaking Change**: No.

## Verification Notes

2026-08-12 (DONE): Full qwen column landed across every
`docs/reference/HOST_COMPATIBILITY.md` table (hook intents, discovery,
runner capabilities, orchestration CLI, config probe, state directory,
installation, env vars, adapter locations) plus `[^qwen]`,
`[^qwenheadless]`, `[^qwenwire]`, `[^qwenmarket]` footnotes; stale
footnotes corrected (`[^bgtasks]` five→six, `[^struct]`, `[^tok]`).
`docs/qwen/` onboarding trio written (getting-started, hook-events,
automation — qwen 0.21.6 pinned as the verified version) and registered in
`mkdocs.yml` nav. `docs/ARCHITECTURE.md` component table + tree line
updated; README gained the Qwen Code install section.
`test_verify_host_map.py` doc-parity pin updated (qwen added).
Verification: `ll-verify-host-map` OK; 1466 targeted tests + 262
host-map/evaluator tests passed; conformance 20 passed / 12 skipped;
`mkdocs build` renders the qwen pages (one new relative-link warning,
identical in kind to the pre-existing codex/kimi adapter-link warnings).

## Session Log
- `/ll:capture-issue` - 2026-08-13T01:28:37Z - qwen-code host integration report capture

---

**Done** | Created: 2026-08-12 | Completed: 2026-08-12 | Priority: P2
