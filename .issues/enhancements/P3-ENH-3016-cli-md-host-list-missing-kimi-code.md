---
id: ENH-3016
title: CLI.md / GETTING_STARTED.md host list omits kimi-code and doesn't flag unimplemented adapters
type: ENH
status: open
priority: P3
discovered_date: 2026-08-02
discovered_by: multi-agent-audit
parent: EPIC-3008
program_design_not_applicable: true
testable: false
labels:
- docs
- ll-init
- host-compat
---

# ENH-3016: `CLI.md`/`GETTING_STARTED.md` host list omits `kimi-code` and doesn't flag unimplemented adapters

## Summary

`docs/reference/CLI.md:37,49` and `docs/guides/GETTING_STARTED.md:101` list
supported `ll-init` hosts as `claude-code, codex, opencode, pi` — omitting
`kimi-code`, even though it has full install wiring in code. Separately, both
docs present `opencode` and `pi` as "supported" on equal footing with
`claude-code`/`codex`, without noting that their adapters are currently
recognized-but-unimplemented stubs.

## Current Behavior

- `kimi-code` is a fully wired host: present in `_KNOWN_HOSTS`
  (`scripts/little_loops/init/cli.py:40`), has a real adapter installer
  (`install_kimi_adapter`, `init/writers.py:712-796`), and its own TUI checkbox
  (`init/tui.py:52-64`) — but is absent from the docs' host lists.
- `opencode` selection prints
  `"[OpenCode] Adapter not yet available — opencode orchestration not yet
  wired."` (`init/cli.py:135`), and `pi` has an analogous not-yet-wired caveat
  (`init/cli.py:137`) — neither caveat is mentioned in the docs, which list
  both as plainly "supported."

## Scope Boundaries

In scope: `docs/reference/CLI.md` and `docs/guides/GETTING_STARTED.md` host
lists. Out of scope: `docs/reference/HOST_COMPATIBILITY.md`, which already
has its own status representation — cross-check for consistency only, don't
restructure it.

## Expected Behavior

Docs' host lists should include `kimi-code`, and should distinguish
fully-wired hosts (`claude-code`, `codex`, `kimi-code`) from
recognized-but-not-yet-implemented ones (`opencode`, `pi`), matching what a
user actually experiences when selecting them.

## Suggested Fix Direction

Update the host list in `docs/reference/CLI.md:37,49` and
`docs/guides/GETTING_STARTED.md:101` to add `kimi-code`, and add a short note
(or a status column, if there's already a table) marking `opencode`/`pi` as
"detected, adapter not yet available." Cross-check
`docs/reference/HOST_COMPATIBILITY.md` for a consistent status representation
already used there.

**Source the list from `_KNOWN_HOSTS`, not `_HOST_RUNNER_REGISTRY`.** The
comment at `scripts/little_loops/init/cli.py:35-40` documents the distinction
explicitly: `_KNOWN_HOSTS` is `{claude-code, codex, opencode, pi, kimi-code}`,
and `gemini`/`omp` are **deliberately absent** because they have no install
wiring and would warn "Unknown host". A doc fix that enumerates from the runner
registry instead would over-list two hosts `ll-init --hosts` actively rejects.

**File-conflict note:** ENH-3017 edits the same `## ll-init` section of
`docs/reference/CLI.md` (the wizard-screen table at `:65-76`). Land this issue
**first**, then ENH-3017 — they are serialized via ENH-3017's `depends_on`. Do
not run them as concurrent epic branches.

## Acceptance Criteria

- [ ] `kimi-code` appears in the host list at `docs/reference/CLI.md:37`, in the
      `--hosts` flag row (`:49`), and in `docs/guides/GETTING_STARTED.md:101`.
- [ ] `opencode` and `pi` are marked as recognized-but-adapter-not-yet-available
      in all three places, matching the runtime messages at `init/cli.py:135,137`.
- [ ] `gemini` and `omp` are **not** added (they are not in `_KNOWN_HOSTS`).
- [ ] The status wording is consistent with `docs/reference/HOST_COMPATIBILITY.md`;
      that file is not restructured.

## Status

**Open** | Created: 2026-08-02 | Priority: P3

## Impact

- **Priority**: P3 — real, user-facing doc inaccuracy (a `kimi-code` user
  wouldn't know it's supported; an `opencode`/`pi` user would expect it to
  work when it doesn't).
- **Effort**: Small.
- **Risk**: None.
- **Breaking Change**: No.
