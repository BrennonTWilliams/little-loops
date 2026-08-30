---
id: ENH-3353
type: ENH
title: Document stdio stdout JSON-RPC frame constraint in MCP server guide
priority: P4
status: done
testable: false
discovered_by: ll-issues-create
discovered_date: '2026-08-28'
captured_at: '2026-08-28T18:42:53Z'
completed_at: '2026-08-30T04:19:39Z'
program_design_not_applicable: true
confidence_score: 100
outcome_confidence: 86
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3353: Document stdio stdout JSON-RPC frame constraint in MCP server guide

## Summary

Document, in `docs/guides/MCP_SERVER_GUIDE.md`, the constraint that an `ll-mcp` tool
handler must never let a `cmd_*` CLI function print: on the stdio transport stdout is
the JSON-RPC frame. The rule is currently stated only in a source comment, where a
contributor adding a tool will not find it.

## Current Behavior

The constraint is recorded at `scripts/little_loops/mcp_server/tools.py:236-244`, in
the tier-2 block comment: `stdout *is* the JSON-RPC frame, so calling them here would
corrupt the protocol.` The two shipped workarounds are both in source only —
FEAT-3149 extracted `apply_status_transition` / `apply_link` so the mutating handlers
wrap non-printing library functions, and `_tool_loop_start` wraps `run_background()`
in `contextlib.redirect_stdout` / `redirect_stderr` because that function prints on
success.

`docs/guides/MCP_SERVER_GUIDE.md` is written for operators and callers: install,
project-root binding, client registration, verifying with `mcp-call`, the mutation
guards, and `tasks/*`. It has no contributor-facing section on adding a tool, and no
mention of the stdout hazard.

Separately, the heading `### The five tools, end to end` (around line 203) is stale
after FEAT-3343 — the tier-1 read surface is now eight tools (the mutating tier-2
surface is the seven), and the inventory table at lines 32-33 already lists all
eight. The walkthrough below the heading still covers five.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- The tier-2 comment block actually spans `tools.py:235-251` (not just 236-244): a
  second paragraph (post-244) documents "Guard 1" (the `apply` required-keyword
  dry-run enforcement) as a related but separate concern from the printing rule —
  the new doc section should not conflate the two.
- Confirmed by repo-wide grep: `cmd_set_status`, `cmd_link`, and `cmd_run` have zero
  import or call sites anywhere in `scripts/little_loops/mcp_server/` — only
  comment/docstring mentions (`tools.py:240`, `tools.py:664`). `_tool_issue_set_status`
  (tools.py:317-370) and `_tool_issue_link` (tools.py:373-420) call
  `apply_status_transition`/`apply_link` directly.
- `_tool_loop_start`'s `redirect_stdout`/`redirect_stderr` wrap (`tools.py:699-705`)
  <!-- ll-prose-ok: stdlib io module's StringIO, not scripts/little_loops/workflow_sequence/io.py -->
  captures both streams into `io.StringIO()` buffers; `stdout_buf` is captured but
  never read (its only purpose is suppressing the success-path prints), while
  `stderr_buf` is read back to build the raised `ValueError` message on non-zero
  `run_background()` return. `run_background` itself lives at
  `scripts/little_loops/cli/loop/_helpers.py:1548` and prints on both its success
  path (1711-1716) and its pre-flight failure path (1579, 1597-1599).
- Repo-wide grep for `redirect_stdout`/`redirect_stderr` across all of
  `scripts/little_loops/` returns only the one occurrence at `tools.py:700` — the two
  mitigations named in this issue (extract a non-printing library function;
  `redirect_stdout`/`redirect_stderr` wrap) are the only two mitigation shapes that
  exist in the codebase today, there is no third pattern to also document.
- `handle_list_tools`'s own docstring (`tools.py:1190-1203`) already states "the
  fixed sixteen-tool catalog in source order" (8 read + 7 tier-2 write + 1 tier-3
  `loop_start` = 16) — a concrete total the refreshed heading/walkthrough can cite.
- `### The five tools, end to end` (line 203) walks through exactly 5 of the 8 read
  tools (`issues_query`, `issue_get`, `history_search`, `deps_check`, `capabilities`);
  `queue_list`, `queue_get`, and `loop_list` have no `mcp-call` walkthrough anywhere
  in that section. `FEAT-3352` (which added `loop_list`) is the change that made this
  heading stale.
- `docs/guides/MCP_SERVER_GUIDE.md` is cross-referenced from `docs/reference/API.md:103`,
  `docs/reference/CLI.md:5145`, `docs/reference/ARTIFACT_CONTROL_LEVELS.md:14`,
  `docs/index.md:47`, and `mkdocs.yml:84`. `scripts/tests/test_wiring_reference_docs.py:213`
  asserts a specific wiring cross-link between this guide and
  `ARTIFACT_CONTROL_LEVELS.md` (ENH-3307) — an existing test that touches this file
  and must keep passing after the edit.
- No test asserts `_TOOL_HANDLERS.keys()` parity against `_TOOLS` tool names (dispatch
  map vs. advertised catalog). `test_no_unguarded_mutating_tool_is_advertised`
  (`scripts/tests/test_mcp_server.py:277-320`) only checks that every advertised
  non-read-only tool name is in `MUTATING_TOOLS` or `TASK_STARTING_TOOLS` — a tool
  added to `_TOOLS` but omitted from `_TOOL_HANDLERS` fails only indirectly (as an
  "Unknown tool" `is_error=True` result) if and when some test happens to call it.

## Expected Behavior

A contributor opening `docs/guides/MCP_SERVER_GUIDE.md` to add a tool finds a short
"Adding a tool" section that states the stdout/JSON-RPC-frame constraint up front,
names both mitigations with pointers to the source that demonstrates each, and lists
the registration steps. No heading in the guide reports a stale tool count.

## Motivation

The failure mode is silent and confusing: a handler that wraps a printing `cmd_*`
corrupts the JSON-RPC frame, and the client reports a parse error that points nowhere
near the offending tool. It is the single most likely defect when adding a tool, and
the guidance exists but is not discoverable from the docs.

## Scope Boundaries

- No code changes: `tools.py`'s comment, guards, and mitigations (`apply_status_transition`/`apply_link` extraction, the `_tool_loop_start` `redirect_stdout`/`redirect_stderr` wrap) stay as-is — this issue documents them, it does not refactor them.
- No new tests: the existing docs-wiring/anchor gates in `python -m pytest scripts/tests/` are the only coverage; this issue adds no test.
- No full per-tool walkthrough rewrite: the stale-heading fix extends/re-scopes `### The five tools, end to end` to match the current eight-tool tier-1 surface, but does not restructure the rest of the guide (mutation guards, `tasks/*` sections) beyond that heading and its immediate walkthrough.
- No third mitigation pattern invented: only the two mitigations that already exist in the codebase (extracted non-printing library function; `redirect_stdout`/`redirect_stderr` wrap) are documented — see Codebase Research Findings.

## Proposed Solution

Promote the existing source comment into a contributor-facing section of the MCP
server guide, and refresh the stale tool-count heading while in the file. Docs-only —
no code change.

### Files to Modify
- `docs/guides/MCP_SERVER_GUIDE.md` — add the "Adding a tool" section; fix the
  `### The five tools, end to end` heading (~line 203)

### Similar Patterns
- `scripts/little_loops/mcp_server/tools.py:236-244` — the tier-2 block comment this
  section promotes
- `_tool_loop_start` in the same file — the `redirect_stdout` / `redirect_stderr`
  mitigation to cite

### Tests
- Docs gates already in `python -m pytest scripts/tests/` (link/anchor checking); no
  new tests.

### Documentation
- This issue is the documentation change.

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- Two structurally coherent placements exist for the new "Adding a tool" `##`
  section, given the guide's current heading order (`## Verifying with mcp-call` →
  `### The five tools, end to end` at 203, then `## The Mutation Surface and Its
  Guards` at 405, then `## Starting, Polling, and Stopping a Run` at 492): before
  "The Mutation Surface and Its Guards" (that section already documents the guard
  mechanics — Guard 1 dry-run, Guard 2 per-transport policy — a new tool must plug
  into), or after it and before "Starting, Polling, and Stopping a Run" (that
  section already discusses `loop_start` in detail, the tool whose
  `redirect_stdout` mitigation the new section must cite). Neither placement is
  forced by any existing anchor or cross-reference.
- The registration checklist should not overclaim safety: no existing test asserts
  `_TOOL_HANDLERS`/`_TOOLS` parity (see Current Behavior findings) — a tool
  registered in `_TOOLS` but missed in `_TOOL_HANDLERS` is only caught if some test
  happens to call it, not by any dedicated gate.
- `scripts/tests/test_wiring_reference_docs.py:213` asserts a specific cross-link
  between this guide and `ARTIFACT_CONTROL_LEVELS.md` (ENH-3307) — the new section
  must not disturb that existing anchor/link.

## Implementation Steps

1. Add a short contributor section to `docs/guides/MCP_SERVER_GUIDE.md` — "Adding a
   tool" — covering: the stdout/JSON-RPC-frame rule; prefer extracting a non-printing
   library function (the FEAT-3149 pattern) over wrapping `cmd_*`; use
   `redirect_stdout` / `redirect_stderr` only when extraction is not practical (the
   `_tool_loop_start` precedent); register in both `_TOOL_HANDLERS` and `_TOOLS`; and
   add write tools to `policy.MUTATING_TOOLS`, never `TASK_STARTING_TOOLS`.
2. Fix the stale `### The five tools, end to end` heading and extend or re-scope the
   walkthrough to match the current tier-1 surface (eight read tools; seven tier-2
   mutating tools — cf. `tools.py:1` and `tools.py:1196`).

## Impact

- **Priority**: P4 - Prevents a confusing silent failure for anyone adding a tool, but
  the rule is already recorded in source and the current handlers all follow it.
- **Effort**: Small - Docs-only; the content already exists as a source comment.
- **Risk**: Low - No code paths touched.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] `docs/guides/MCP_SERVER_GUIDE.md` states the stdout/JSON-RPC-frame constraint
      and names both mitigations, with pointers to the `mcp_server/tools.py` call
      sites that demonstrate each.
- [ ] The tool-registration checklist covers `_TOOL_HANDLERS`, `_TOOLS` source order,
      and the `policy.MUTATING_TOOLS` / `TASK_STARTING_TOOLS` split.
- [ ] No heading or walkthrough in the guide reports a stale tool count.
- [ ] `ll-verify-docs` / the docs gates in `python -m pytest scripts/tests/` pass.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/guides/MCP_SERVER_GUIDE.md` | The file this issue edits |
| `docs/reference/API.md` | `little_loops.mcp_server` module reference |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-29; gaps addressed same day._

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

Both gaps from the initial pass are resolved:
- Program Design hard override: set `program_design_not_applicable: true` in
  frontmatter — this is a docs-only change with no code paths touched, the
  sanctioned exemption case per `enh-sections.json`'s own guidance ("Set
  `program_design_not_applicable: true` ... for trivial issues (one-line config
  change, docs fix)"). `ll-issues check-design ENH-3353` now passes.
- Advisory claim gap: the `stale_symbol_ref` hit on `StringIO` was a resolver
  false positive — `` `io.StringIO()` `` parses as a `module.symbol` claim and
  resolves the bare `io` prefix to the only tracked `io.py` in the repo
  (`scripts/little_loops/workflow_sequence/io.py`), not the stdlib `io` module
  actually meant. Suppressed in place with an `<!-- ll-prose-ok: ... -->` marker
  on the line immediately preceding the claim (the sanctioned suppression
  convention, `symbol_claims.py::_SUPPRESS_RE`).
- Also added the `## Scope Boundaries` section format-check flagged as missing
  (unrelated to either hard-override gap, but cheap to close in the same pass).

`ll-issues format-check ENH-3353 --format json` now reports no gaps in any
category.

## Status

**Open** | Created: 2026-08-28 | Priority: P4


## Session Log
- `/ll:manage-issue` - 2026-08-30T04:19:11 - `2ced93d4-cb98-4480-9d8f-05bf8397f3b5.jsonl`
- `/ll:confidence-check` - 2026-08-30T04:05:52 - `88146606-f2a1-4426-bbe4-fbee395686b0.jsonl`
- `/ll:refine-issue` - 2026-08-30T03:52:40 - `ed7f738d-23a1-4ebc-8ac8-c914ef582fa7.jsonl`
- `/ll:capture-issue` - 2026-08-28T18:43:17 - `51a7dd65-db46-4ad2-be82-40e74f2445d1.jsonl`
