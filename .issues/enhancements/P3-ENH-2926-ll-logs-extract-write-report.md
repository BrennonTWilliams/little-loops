---
id: ENH-2926
title: 'll-logs extract: report what was written instead of succeeding silently'
type: ENH
status: open
priority: P3
discovered_date: 2026-07-29
discovered_by: scope-review
relates_to:
- ENH-2925
blocked_by:
- ENH-2925
labels:
- ll-logs
- cli-consistency
---

# ENH-2926: `ll-logs extract` — report what was written instead of succeeding silently

## Summary

`_cmd_extract` (`scripts/little_loops/cli/logs.py:666`) walks every discovered
project's JSONL, buckets ll-relevant records by session, writes one file per
session under `logs/<slug>/`, regenerates `logs/index.md`, and returns 0 —
printing **nothing** on the success path. Only errors reach stdout/stderr
(a missing project folder, via `logger.error`).

A user cannot tell from the output whether extract wrote 3 files or 300, which
projects it covered, whether a `--cmd` filter matched anything at all, or which
JSONL files it skipped on `OSError` (silently swallowed at logs.py:702-703).

## Current Behavior

```
$ ll-logs extract --all
$                      # no output; N files appeared under logs/
$ ll-logs extract --all --cmd ll-nonexistent
$                      # no output; nothing written, indistinguishable from success
```

Failure modes hidden today:

- Per-file `OSError` is caught and `continue`d with no diagnostic — an
  unreadable JSONL is silently absent from the extraction.
- A `--cmd` filter that matches zero records produces the same output (none)
  as a filter that matches everything.
- Projects whose folder resolves to `None` under `--all` are skipped without
  the `logger.error` the `--project` path emits.

## Expected Behavior

`extract` prints a summary of what it did, and supports `-j/--json` for the
same payload — bringing it in line with the rest of `ll-logs`, where every
other subcommand emits a structured result.

Text form:

```
$ ll-logs extract --all
little-loops       12 sessions, 3,481 records -> logs/little-loops/
other-project       2 sessions,   204 records -> logs/other-project/
2 projects, 14 sessions, 3,685 records written; 1 file unreadable (skipped)
```

JSON form: one object per project (`project`, `slug`, `out_dir`, `sessions`,
`records`), plus totals and a `skipped` list of unreadable paths.

When a `--cmd` filter matches nothing, say so explicitly rather than exiting 0
silently.

## Motivation

Extract is the entry point for every downstream `ll-logs` workflow
(`sequences`, `stats`, `diff`, `eval-export` all consume what it produces), so
a silent no-op there surfaces later as a confusing empty analysis rather than
an obvious extraction problem. It is also the only `ll-logs` subcommand with no
machine-readable output, which blocks scripting an extract-then-analyze
pipeline.

Split out of ENH-2925's parity sweep because this is a new output surface, not
`add_json_arg` wiring — there is currently no report to serialize.

## Proposed Solution

In `_cmd_extract`:

1. Accumulate a per-project record as the loop runs: resolved project path,
   slug, output dir, session count, record count.
2. Collect `OSError` paths into a `skipped` list instead of discarding them;
   report the count in text mode and the paths in JSON mode.
3. Emit a `logger.warning` (not silent skip) when `--all` encounters a project
   whose session folder does not resolve.
4. Distinguish "filter matched nothing" from "nothing to do" in the summary
   line.
5. Add `add_json_arg(extract_parser)` and a `print_json(...)` branch, matching
   the file's existing convention.

Keep exit code 0 for a successful-but-empty extraction — this is a reporting
change, not a gating one.

## Scope Boundaries

**In scope:** `_cmd_extract`'s success-path reporting, its swallowed `OSError`
diagnostics, and one `add_json_arg(extract_parser)` line.

**Out of scope:** what records `_is_ll_relevant` selects or how sessions are
bucketed (extraction logic is unchanged — only its reporting); `logs/index.md`
generation via `generate_index`; `--project`/`--all` resolution semantics
(ENH-2317); the shared target/window parser extraction and the `--since`/
`--sort`/`--limit` additions (ENH-2925). Exit codes stay as they are — this is
reporting, not gating.

## Impact

- **Priority**: P3 — diagnosability improvement; no workflow is blocked today.
- **Effort**: Small — one function plus one argparse line.
- **Risk**: Low. `extract` currently prints nothing, so any script parsing its
  stdout parses the empty string; adding output is additive. Verify no loop or
  skill captures `ll-logs extract` stdout expecting emptiness.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] `ll-logs extract --project DIR` and `--all` print a per-project +
      totals summary on success.
- [ ] `-j/--json` emits the same data structurally (per-project rows, totals,
      `skipped` paths).
- [ ] Unreadable JSONL files are reported, not silently dropped.
- [ ] A `--cmd` filter matching zero records says so.
- [ ] Under `--all`, an unresolvable project folder emits a warning.
- [ ] Tests cover: multi-project summary, JSON shape, zero-match filter, and
      an unreadable-file skip.
- [ ] `python -m pytest scripts/tests/` exits 0.

---

## Status

**Open** | Created: 2026-07-29 | Priority: P3
