---
id: BUG-3150
type: BUG
title: issue-file mutators write unlocked and non-atomically (set-status, link, append-log)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-11'
captured_at: '2026-08-11T18:29:27Z'
labels:
- issues-cli
- concurrency
relates_to:
- FEAT-3149
- EPIC-3127
size: Small
testable: true
---

# BUG-3150: issue-file mutators write unlocked and non-atomically (set-status, link, append-log)

## Summary

`ll-issues set-status` and `ll-issues link` perform read-modify-write on issue
files with **neither a lock nor an atomic write**, despite `file_utils` providing
both (`acquire_lock`, `atomic_write`) and despite `create`/`scaffold-epic`
already using them correctly.

`path.write_text(...)` truncates the target before writing, so the failure mode
is not merely a lost update — an interleaved or interrupted write can leave a
**torn or empty issue file**.

## Current Behavior

| Command | Lock | Atomic write | Worst case |
| --- | --- | --- | --- |
| `create` (`cli/issues/create.py:202`) | yes (`.issues/.id-alloc.lock`) | exclusive-create `open(path,"x")` | safe |
| `scaffold-epic` (`cli/issues/scaffold_epic.py:83`) | yes | — | safe |
| `set-status` (`cli/issues/set_status.py:127`, `:209`) | **no** | **no** (`write_text`) | torn / empty file |
| `link` (`cli/issues/link.py:149`, `:170`, `:202`) | **no** | **no** (`write_text`) | torn file; half-linked graph |
| `append-log` (via `session_log.py:245`) | **no** | yes (`atomic_write`) | lost update only |

Two distinct defects:

1. **Non-atomic writes** (`set-status`, `link`) — a crash or concurrent write
   mid-`write_text` corrupts the issue file. This is data loss, not a race
   policy.
2. **Unlocked read-modify-write** (all three) — two writers interleave and one
   update is silently lost.

`link` additionally writes source and target as two independent unprotected
writes (`:149`/`:170` then `:202`), so an interruption between them leaves the
source claiming a link the target has no backlink for.

## Steps to Reproduce

Both defects are races, so reproduction is probabilistic rather than
deterministic; the concurrency test in AC 4 is the reliable form.

1. Pick any issue, e.g. `ENH-3148`.
2. Run many concurrent status flips against it:
   ```bash
   for i in $(seq 1 50); do
     ll-issues set-status ENH-3148 open &
     ll-issues set-status ENH-3148 deferred &
   done; wait
   ```
3. Inspect the file. Expected: a valid file with one of the two statuses.
   Observed (intermittently): a truncated or empty file, or a file whose
   frontmatter fails to parse.

For the `link` half-write, interrupt the process between its source and target
writes (`link.py:170` and `:202`) and observe that `ll-deps validate` reports a
missing backlink for the pair.

## Root Cause

- **Files**: `scripts/little_loops/cli/issues/set_status.py` (lines 127, 209),
  `scripts/little_loops/cli/issues/link.py` (lines 149, 170, 202),
  `scripts/little_loops/session_log.py` (line 245).
- `set_status.py` and `link.py` call `Path.write_text()` directly instead of
  `little_loops.file_utils.atomic_write()`, and none of the three mutation paths
  takes `little_loops.file_utils.acquire_lock()` around its read-modify-write.
- `create.py:202` demonstrates the correct pattern already in use in this
  codebase.

## Why it surfaces now

Tier 1 of EPIC-3127 was read-only, so this never came up. The CLI's implicit
safety property was "one human runs one command at a time." FEAT-3149 exposes
these same three mutations as MCP tools, which removes that assumption: multiple
hosts can call concurrently, and any of them can race a local `ll-auto` /
`ll-parallel` run. An MCP-layer lock cannot fix this — it would not serialize
against a direct CLI invocation — so the fix belongs here, at the CLI layer.

This is a pre-existing defect independent of MCP; FEAT-3149 only makes it
reachable in normal use. FEAT-3149 `depends_on` this issue.

## Expected Behavior

- `set-status`, `link`, and `append-log` each perform their read-modify-write
  under `acquire_lock`, and write via `atomic_write` rather than `write_text`.
- `link`'s source and target updates happen under a single lock hold so the
  backlink invariant cannot be broken by an interruption between them.

## Proposed Solution

Reuse the existing primitives exactly as `create.py` does — do not introduce a
new locking mechanism.

1. Replace `write_text` with `atomic_write` in `set_status.py` and `link.py`.
2. Wrap each mutator's read-modify-write in `acquire_lock`.
3. Hoist `link`'s two writes into one lock hold.

Lock granularity is settled as a **single `.issues/`-wide lock**, matching the
existing `.id-alloc.lock` convention: these are sub-millisecond writes, so the
concurrency a per-file lock would buy is not worth a second locking scheme to
audit.

## Program Design

### Types

No new types. The change is confined to the write path of three existing
commands.

### Signatures

- `little_loops.file_utils.acquire_lock(path: Path, timeout: float = 10.0)` —
  existing context manager, reused unchanged.
- `little_loops.file_utils.atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None`
  — existing, reused unchanged.

### Lock file

`.issues/.mutate.lock`, a sibling of the existing `.issues/.id-alloc.lock`. Kept
distinct from `.id-alloc.lock` so a long `scaffold-epic` allocation does not
serialize unrelated status flips, and so neither lock's contention profile
changes the other's.

### Call Path

`ll-issues set-status` →
`little_loops.cli.issues.set_status.cmd_set_status()` →
`little_loops.file_utils.acquire_lock()` (new) →
`little_loops.file_utils.atomic_write()` (replaces `Path.write_text`)

`ll-issues link` →
`little_loops.cli.issues.link.cmd_link()` →
`little_loops.file_utils.acquire_lock()` (new, one hold spanning source+target) →
`little_loops.file_utils.atomic_write()` ×2

`ll-issues append-log` →
`little_loops.cli.issues.append_log.cmd_append_log()` →
`little_loops.session_log.append_session_log_entry()` →
`little_loops.file_utils.acquire_lock()` (new) →
`little_loops.file_utils.atomic_write()` (already present)

Reference implementation of the same pattern:
`little_loops.cli.issues.create.create_issue()`.

### Call sites changed

- `cli/issues/set_status.py:127` and `:209` — the second is the child-issue
  write in the same command and must sit inside the same lock hold as the first,
  or a partially-applied cascade is possible.
- `cli/issues/link.py:149`, `:170`, `:202` — all three under one hold.
- `session_log.py:245` — already `atomic_write`; add the lock only.

### Ordering constraint

`link` mutates two files under one lock. Because the lock is `.issues/`-wide
rather than per-file, there is no lock-ordering hazard and no deadlock risk
between concurrent `link` invocations.

## Acceptance Criteria

1. `set-status` and `link` write via `atomic_write`; no `write_text` call remains
   on an issue-file mutation path.
2. All three mutators hold `acquire_lock` across read-modify-write.
3. `link` updates source and target under one lock hold.
4. A concurrency test asserts that N concurrent `set-status` invocations against
   one issue leave a valid, parseable file with exactly one winning status (no
   torn or empty file).
5. A test asserts `link` cannot leave a source-without-target backlink state when
   interrupted between its two writes.
6. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 — data loss (corrupted issue files) is possible today, but
  requires concurrent writers, which is currently rare in practice.
- **Blast radius is wide**: every project on this machine is `local-editable`
  against this checkout, so these mutators go live everywhere with no reinstall
  step. Changes here need the full suite green before landing.
- **Blocks FEAT-3149**: shipping guarded mutation tools onto a substrate that can
  produce torn issue files is unsound.

## Status

open
