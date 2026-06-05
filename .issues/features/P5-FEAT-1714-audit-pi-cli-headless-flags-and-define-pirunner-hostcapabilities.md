---
id: FEAT-1714
title: Audit Pi CLI headless flag surface & define `PiRunner` `HostCapabilities`
type: FEAT
status: open
priority: P5
captured_at: "2026-05-26T02:06:59Z"
discovered_date: 2026-05-26
discovered_by: capture-issue
parent: EPIC-1713
relates_to: [FEAT-1480, FEAT-992]
labels: [feat, captured, pi-adapter, host-compat, research]
---

# FEAT-1714: Audit Pi CLI headless flag surface & define `PiRunner` `HostCapabilities`

## Summary

Run `pi --help` (and any subcommand `--help`s) and produce a written
mapping from Claude Code's headless flag surface to Pi's, so
`PiRunner.HostCapabilities` and `build_*` methods can be wired with
confidence instead of by copy-pasting `CodexRunner` and hoping.

## Motivation

FEAT-1480 Step 1 says, verbatim:

> Run `pi --help` first to verify Pi CLI supports streaming JSON output
> and a bypass-approvals flag before setting `HostCapabilities` identically
> to Codex

That prerequisite research has no dedicated tracking. FEAT-992 step 6
("flesh out `PiRunner`") was explicitly deferred for the same reason.
Without this audit, FEAT-1480 ships speculatively: every downstream caller
(`subprocess_utils`, `ll-action`, `worker_pool`, FSM evaluators, FSM
handoff handler) inherits the speculation.

The audit is small, but its output is load-bearing for any claim of "Pi
as `claude -p` replacement."

## Acceptance Criteria

- A research note (`thoughts/research/pi-headless-cli.md` or equivalent)
  documenting Pi's actual CLI surface for headless invocation
- A capability mapping table covering at minimum:
  - **Streaming output**: does Pi support a `--output-format stream-json`
    equivalent? What does the line schema look like?
  - **Permission bypass**: equivalent of `--permission-mode bypass` /
    `--dangerously-skip-permissions`?
  - **Agent select**: equivalent of `--agent`?
  - **Tool allowlist**: equivalent of `--allowed-tools` / `--disallowed-tools`?
  - **Max turns / step limit**: equivalent of `--max-turns`?
  - **Session resume**: equivalent of `--resume <session-id>` / `--continue`?
  - **System prompt injection**: equivalent of `--system-prompt` /
    `--append-system-prompt`?
  - **MCP config passthrough**: equivalent of `--mcp-config`?
  - **JSON-mode blocking output**: equivalent of `claude -p --output-format json`?
- An explicit `HostCapabilities(streaming, permission_skip, agent_select,
  tool_allowlist)` recommendation for Pi, justified flag-by-flag against
  the audit
- Recommendations recorded as `## Codebase Research Notes` (or equivalent)
  inside FEAT-1480 so the wiring PR can reference them verbatim

## Use Case

A maintainer working on FEAT-1480 opens this issue's research note,
copies the capability tuple, and wires `PiRunner.build_streaming` /
`build_blocking_json` / `build_version_check` / `build_detached` knowing
exactly which flags translate, which silently no-op, and which require
fallback strategies (e.g. tool allowlist via temp config file like
`CodexRunner.build_blocking_json` does).

## Proposed Solution

1. **Install or locate Pi** on a verification machine. If Pi is not
   installable in CI, capture the audit interactively and commit the
   transcript.
2. **Run `pi --help`** and every relevant subcommand's `--help`.
3. **For each Claude Code headless flag** listed in the AC, find Pi's
   equivalent (or confirm absence).
4. **Test streaming output** with a trivial prompt to capture the actual
   JSON line schema, if streaming exists.
5. **Write the research note** with the capability table and per-flag
   prose.
6. **Update FEAT-1480** with the verbatim findings under
   `## Codebase Research Notes`.

## Implementation Steps

1. Install Pi (or run on a machine where it is already installed):
   `npm i -g @earendil-works/pi-coding-agent` (verify exact package name
   against pi-mono README)
2. Capture `pi --help`, `pi --version`, and every subcommand help to a
   transcript file
3. Diff against Claude Code's headless flag surface (cross-reference
   `ClaudeCodeRunner` in `scripts/little_loops/host_runner.py:215-302`
   and Codex's translations in `CodexRunner` at lines 270-418)
4. For streaming: run `pi … --output-format stream-json` (or whatever
   the equivalent is) on a trivial prompt; capture & document the
   actual line schema
5. Author the research note with a capability table + recommendations
6. Cross-link from FEAT-1480 so the wiring PR has zero ambiguity

## Integration Map

### Files to Create
- `thoughts/research/pi-headless-cli.md` — audit + capability table
  (location follows `thoughts/research/codex-command-discovery.md`
  precedent referenced from EPIC-1463)

### Files to Modify
- `.issues/features/P5-FEAT-1480-pi-adapter-wire-pirunner-and-host-runner-tests.md` —
  add `## Codebase Research Notes` section referencing this audit's
  output so the wiring PR can cite specific verified flags
- `docs/reference/HOST_COMPATIBILITY.md` — add Pi rows for CLI-flag capabilities.
  **Coordination note (from `/ll:audit-issue-conflicts` 2026-06-04):** Land this
  issue's `HOST_COMPATIBILITY.md` changes first, then rebase FEAT-1715's hook-event
  parity rows on top. FEAT-1715 will add hook-event rows to the same Pi column;
  the row-type split (CLI flags here, hook events there) prevents overlap within
  the column.

### Reference Files (Read-Only)
- `scripts/little_loops/host_runner.py:215-302` — `ClaudeCodeRunner`
  reference flag surface
- `scripts/little_loops/host_runner.py:270-418` — `CodexRunner` mapping
  precedent (template for how flag translation + capability declaration
  fits together)
- `scripts/little_loops/host_runner.py:653-720` — current `PiRunner`
  stubs to be replaced after this audit

## Out of Scope

- Actually wiring `PiRunner` (that is FEAT-1480's job — this issue
  produces only the research input)
- Recommending `HostCapabilities` changes for any host other than Pi
- Documenting Pi's plugin/extension API (already covered by FEAT-992
  / FEAT-1478)

## Impact

- **Priority**: P5 — matches Pi-adapter tier
- **Effort**: Small (a few hours, gated on having a working `pi` install)
- **Risk**: Very low — pure documentation; no code change

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/reference/HOST_COMPATIBILITY.md` | Audit outputs feed the Pi column |
| `docs/reference/API.md` | `little_loops.host_runner` runner table cites `PiRunner` capabilities |

## Labels

`feat`, `pi-adapter`, `host-compat`, `research`, `captured`

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-01_

**Verdict: OUTDATED** — Research not yet performed:
- `thoughts/research/pi-headless-cli.md` does NOT exist (only 4 Codex research notes present in `thoughts/research/`)
- No Pi capability audit has been performed
- No `PiRunner` `HostCapabilities` defined

## Status

**Open** | Created: 2026-05-26 | Priority: P5

## Session Log
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T20:02:29 - `0860b18c-08b7-4093-862a-cc8046f35aaa.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:55 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-06-01T14:29:19 - `f3a091ba-2869-499e-9de4-7f5c8ca96083.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T21:44:02 - `6805d559-982e-47e7-9513-9c8b17a1c054.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:10 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:14 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-26T02:06:59Z - `3eaac8be-eba9-48b8-a2d9-322df5114921.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Both this issue and FEAT-1715 update `docs/reference/HOST_COMPATIBILITY.md`'s Pi column. To avoid merge conflicts, ownership is divided by row type: FEAT-1714 owns the CLI-flag capability rows (streaming, permission bypass, agent select, tool allowlist, max turns, session resume, system prompt, MCP config, JSON-mode). FEAT-1715 owns the hook-event parity rows (PreToolUse, PostToolUse, UserPromptSubmit, Stop, SessionEnd, post_compact). Coordinate `HOST_COMPATIBILITY.md` PRs to ensure these row sets don't overlap.
