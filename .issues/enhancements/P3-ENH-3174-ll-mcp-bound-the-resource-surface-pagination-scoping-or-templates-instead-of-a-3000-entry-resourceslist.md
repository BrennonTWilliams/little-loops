---
id: ENH-3174
type: ENH
title: "ll-mcp: bound the resource surface \u2014 pagination, scoping, or templates\
  \ instead of a 3000-entry resources/list"
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T00:26:15Z'
completed_at: '2026-08-15T08:11:08Z'
parent: EPIC-3127
labels:
- mcp
relates_to:
- FEAT-3134
depends_on:
- ENH-3171
- ENH-3172
---

# ENH-3174: ll-mcp: bound the resource surface — pagination, scoping, or templates instead of a 3000-entry resources/list

## Summary

`resources/list` returns the entire enumeration in one response: every issue file across
all statuses plus every `docs/**/*.md`. On this repository that is over 3,000 entries, and
`docs/` alone contributes ~170 files with no descriptions (there is no frontmatter
convention under `docs/`, so `_docs_entries` sets `description=None`).

`handle_list_resources` accepts `types.PaginatedRequestParams` and ignores it — there is
no cursor, no page size, and no filter. `handle_list_prompts` is the same shape but the
skill catalog is small enough that it is not the problem.

This directly contradicts the epic's own framing of the tool surface. EPIC-3127 rejected
mirroring ~40 CLI subcommands as tools on the grounds that it is "a context-budget
disaster," then shipped a resource surface that hands a client thousands of entries in a
single list response. `docs/guides/MCP_SERVER_GUIDE.md` already warns that "clients that
eagerly fetch every resource will be slow" and steers users to `issues_query` instead —
i.e. the guide's advice is to route around the resource surface.

## Options

1. **Implement the cursor** the SDK's `PaginatedRequestParams`/`nextCursor` already
   defines. Correct, and the client keeps deciding how much to pull. Does not by itself
   reduce total bytes for a client that pages to exhaustion.
2. **Scope what is enumerated at all**, via config: which issue statuses appear
   (open-only by default is a large reduction on a mature project), and which doc paths
   (a glob allow-list rather than all of `docs/**`). This is the change that actually
   shrinks the surface.
3. **Resource templates** (`resources/templates/list`) for the `ll://issues/<ID>` and
   `ll://docs/<path>` families, so a client can construct a URI without the server
   enumerating every instance. This is arguably the primitive the issue surface should
   have used from the start.

2 and 3 are complementary and address the actual cost; 1 is table stakes for protocol
conformance. Whatever is chosen must preserve the access-control property `resources.py`
depends on: the index dict **is** the rejection mechanism for `resources/read`, not path
sanitization. A template-based or lazily-resolved read path has to reintroduce an
equivalent boundary explicitly — this is the one place where a naive implementation
introduces a path-traversal hole into a server that currently cannot have one.

## Relationship to FEAT-3134

FEAT-3134 (`ll-ctx-stats` measuring the MCP surface's context cost, currently `deferred`)
is the measurement half of this question. EPIC-3127's open question 1 explicitly wanted
the granularity decision made "on data," and that data was never gathered. Deciding
between the options above without it repeats the mistake the epic was trying to avoid —
so either revive FEAT-3134 first, or state plainly that this is being decided on judgment.


## Current Behavior

`resources/list` returns every enumerated entry in one response — all issues at every
status plus every file under `docs/` (3,000+ here). `PaginatedRequestParams` is accepted
and ignored; there is no cursor, page size, status filter, or docs allow-list. The guide's
advice is to avoid the surface and use `issues_query` instead.

## Expected Behavior

A client can retrieve the resource catalog incrementally (cursor honored, `nextCursor`
returned), and an operator can bound what is enumerated at all — by issue status and by
doc path — without losing the ability to read a specific resource by URI.

## Program Design

TBD - requires investigation. This issue presents three options (cursor support, scoping
config, resource templates) rather than a single concrete design; a signature-level design
should be written once the option is chosen (see `## Options` above and
`## Relationship to FEAT-3134`).

## Scope Boundaries

- Does not include implementing FEAT-3134 (`ll-ctx-stats`) itself — that is a separate,
  currently-deferred issue this one may depend on for data.
- Does not change `handle_list_prompts` — the skill catalog is small enough that pagination
  is out of scope there per the Summary.
- Does not change `resources/read` behavior for a URI already present in the index — only
  what `resources/list` enumerates and how.
- Whichever option(s) are chosen, `resources.py`'s index-dict access-control boundary must
  be preserved or explicitly reintroduced; relaxing it is out of scope for this issue.

## Impact

- **Priority**: P3 - Real context cost and real client slowness, but the surface is
  usable today by ignoring the list and reading known URIs, and the tool surface covers
  the same data efficiently.
- **Effort**: Medium - Cursor support is mechanical; scoping needs config-schema work,
  and templates are a design change to how issue resources are addressed.
- **Risk**: Medium - `resources.py` relies on the index dict being the entire
  access-control boundary. A template or lazy-resolution path must reintroduce that
  boundary explicitly or it opens a path-traversal hole that cannot exist today.
- **Breaking Change**: No, unless scoping defaults change what an existing client sees —
  in which case default to today's behavior and make narrowing opt-in.

## Resolution

- **Action**: improve
- **Completed**: 2026-08-15
- **Status**: Completed

Implemented options 1 (cursor pagination) and 2 (enumeration scoping) from `## Options`;
option 3 (resource templates) is out of scope — the Expected Behavior section only calls
for cursor support plus status/doc-path bounding, not a URI-construction primitive, and
that stays a candidate for a future issue.

### Changes Made
- `scripts/little_loops/mcp_server/resources.py`: `make_list_resources_handler` now
  honors `PaginatedRequestParams.cursor` unconditionally and caps each response at
  `config.mcp.resources.page_size` (sorted-by-uri, resume-after-cursor pagination),
  returning `next_cursor` when more remain. `_issue_entries`/`_docs_entries` accept
  opt-in scoping (`config.mcp.resources.issue_statuses`, `.docs_globs`) that defaults to
  `None` (unbounded), preserving pre-ENH-3174 behavior for existing clients.
- `scripts/little_loops/config/features.py`: added `McpResourcesConfig`
  (`issue_statuses`, `docs_globs`, `page_size=500`) wired into `McpConfig.resources`.
- `scripts/little_loops/config-schema.json`: documented `mcp.resources.{issue_statuses,
  docs_globs,page_size}`.
- `docs/guides/MCP_SERVER_GUIDE.md`: replaced the "resource list is large" caveat with
  pagination/scoping usage and a config example.
- `scripts/tests/test_enh_3174_mcp_resources_pagination.py`: new — pagination across
  multiple pages, default single-page behavior, status/doc-glob scoping (both unset and
  set), and confirms `resources/read` for an in-scope URI is unaffected.

### Verification Results
- Tests: PASS (`python -m pytest scripts/tests/` — 19334 passed, 46 skipped)
- Lint: PASS (`ruff check scripts/`)
- Types: PASS (`python -m mypy` on both changed source files)
- Run: N/A (no `run_cmd` configured)
- Integration: PASS — access-control boundary (`ResourceIndex.entries` dict membership)
  untouched; scoping only narrows what's enumerated, not what's readable by URI.

## Status

**Done** | Created: 2026-08-15 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-08-15T08:11:08 - `cf9fde7b-5699-4321-a070-ae9593d2013e.jsonl`
- `/ll:ready-issue` - 2026-08-15T07:54:38 - `28dc0d6c-873d-4109-ad07-e4cc0bc3e7f4.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-15T01:18:59 - `6343db1a-2326-4ea0-a5fc-0b0d7d522516.jsonl`
