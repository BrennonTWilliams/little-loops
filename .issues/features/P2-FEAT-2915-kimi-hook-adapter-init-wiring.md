---
id: FEAT-2915
title: Hook adapter — hooks/adapters/kimi + ll-init wiring + shared write_agents_md()
type: FEAT
status: open
priority: P2
parent: EPIC-2910
captured_at: "2026-07-29T15:55:00Z"
discovered_date: 2026-07-29
discovered_by: capture-issue
labels:
- kimi
- host-compat
---

# FEAT-2915: Hook adapter — hooks/adapters/kimi + ll-init wiring + shared write_agents_md()

## Summary

New `scripts/little_loops/hooks/adapters/kimi/` adapter — 4-line shims that
export `LL_HOOK_HOST=kimi-code` and pipe stdin to `python -m
little_loops.hooks <intent>` — plus `ll-init` wiring and a host-shared
`write_agents_md()` writer. Includes the small tolerant payload accessors for
the drift rows found in the FEAT-2911 spike.

## Motivation

Hook intents are what make `session_start`/`pre_compact` (the epic's minimum
acceptance) fire under kimi. kimi's hook payloads are claude-shaped but
drifted on four rows, so handlers need tolerant accessors keyed by host.
`write_agents_md()` is built host-shared from the start — codex also reads
`AGENTS.md` — not as a kimi appendage to `write_claude_md()`.

## Implementation Steps

1. Create `scripts/little_loops/hooks/adapters/kimi/` with 4-line shims
   (export `LL_HOOK_HOST=kimi-code`, pipe stdin to `python -m
   little_loops.hooks <intent>`) for `session_start`, `pre_compact`,
   `user_prompt_submit`, `pre_tool_use`, `post_tool_use`, `session_end`,
   `subagent_start`, `subagent_stop`; README per the codex adapter contract;
   kimi `[[hooks]]` TOML template with a `{{LL_PLUGIN_ROOT}}` placeholder.
2. Add `install_kimi_adapter()` to `init/writers.py` (pattern
   `install_codex_adapter` :465-513).
3. Build `write_agents_md()` in `init/writers.py` as a HOST-SHARED writer —
   create-if-missing + marker-delimited idempotent replace, following the
   `_CLAUDE_MD_SECTION_MARKER` guard at :443 — NOT a kimi appendage to
   `write_claude_md()`; codex also reads `AGENTS.md`.
4. `ll-init` wiring: add `"kimi-code"` to `_KNOWN_HOSTS` (`init/cli.py:36` —
   with a comment that gemini/omp are DELIBERATELY absent, no install wiring;
   also fix the stale "mirrors `_HOST_RUNNER_REGISTRY` keys" comment at :35);
   `_detect_hosts()` (:59-70) appends kimi-code LAST probing `which("kimi")`
   OR `(project_root/".kimi-code").exists()`; `_dispatch_host_adapters`
   (:73-98) kimi branch; TUI checkbox (`init/tui.py:54-60`); `--hosts` help
   (`init/cli.py:742-748`).
5. Handler payload drift fixes (from the spike): `user_prompt_submit.py`
   `prompt` may be a block array; `post_tool_use.py` `tool_output` vs
   `tool_response`; `subagent_start.py`/`subagent_stop.py` `agent_name` vs
   `agent_id`/`agent_type`, `response` inline vs `agent_transcript_path` —
   small tolerant accessors, keyed/tolerant by host.
6. New `scripts/tests/test_kimi_adapter.py` (pattern
   `test_codex_adapter.py`).

## Integration Map

### Files to Modify

- `scripts/little_loops/init/cli.py` — `_KNOWN_HOSTS`, `_detect_hosts()`, `_dispatch_host_adapters()`, `--hosts` help
- `scripts/little_loops/init/tui.py` — host checkbox
- `scripts/little_loops/init/writers.py` — `install_kimi_adapter()`, shared `write_agents_md()`
- `scripts/little_loops/hooks/intents/user_prompt_submit.py`, `post_tool_use.py`, `subagent_start.py`, `subagent_stop.py` — drift-tolerant accessors

### New Files

- `scripts/little_loops/hooks/adapters/kimi/` — shims, README, `[[hooks]]` TOML template
- `scripts/tests/test_kimi_adapter.py`

### Dependent Files

- `scripts/little_loops/hooks/__main__.py` — intent dispatch table
- `kimi.plugin.json` — manifest references the packaged shims (FEAT-2917)
- `docs/reference/HOST_COMPATIBILITY.md` — hook intent cells, flipped by ENH-2919

## Impact

- **Priority**: P2 — critical path; delivers the epic's minimum hook acceptance.
- **Effort**: M — adapter + init wiring + shared writer + handler accessors.
- **Risk**: Medium — touches shared init writers and intent handlers; mitigated by host-keyed tolerant accessors and the marker guard.
- **Breaking Change**: No.

## Session Log
- `/ll:capture-issue` - 2026-07-29T15:55:00Z - kimi-code host adapter planning session

---

**Open** | Created: 2026-07-29 | Priority: P2
