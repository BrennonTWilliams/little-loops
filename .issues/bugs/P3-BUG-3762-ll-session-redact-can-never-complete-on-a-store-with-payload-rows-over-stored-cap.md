---
id: 3762
title: ll-session redact can never complete on a store with payload rows over STORED_CAP
type: BUG
priority: P3
status: open
discovered_date: '2026-10-06'
labels: []
---

## Summary

`ll-session redact` (ENH-3752) refuses any `raw_events` payload column whose stored size exceeds `STORED_CAP` (1 MiB). It never inspects that row. Afterwards it prints `Failed: N row(s) left as found` and `Incomplete: rerun after resolving the above.` — but the operator has nothing to resolve. Rerunning refuses the same rows, so a store with even one large transcript row can **never** reach a complete redaction. The command can't tell "this row is unsafe" apart from "this row is too big to look at".

The 1 MiB / 4 MiB bounds are deliberate ENH-3752 design limits (page-size and wire-size safety). This issue does not ask to remove them. It asks for a path to completion and an honest, actionable report.

## Steps to Reproduce

1. Use a store with at least one `raw_events` row whose `raw_line` or `parsed_json` is over 1 MiB stored (zlib-compressed). A user turn carrying a large pasted or attached payload can reach this size.
2. Run `ll-session redact --dry-run -j`.
3. Observe `problems` entries `{"row_id": N, "column": "raw_line"|"parsed_json", "reason": "resource_limit"}`, `complete: false`, and the text-mode "Incomplete: rerun…" line. Rerun: the result is identical.

Observed on a consumer project's store under v1.167.0. Six rows (1.1–3.3 MB stored, 1.5–4.7 MB decoded, all `type: user`) were refused on every run. Decoded by hand and passed through `pii.redact_history_text`, all six contained **zero** matches. They were clean, yet the run can never report complete.

## Current Behavior

- `STORED_CAP = 1 << 20` (`scripts/little_loops/session_store/raw_redaction.py:93`). The page SELECT projects a column's value only when it is at most the cap (`:266`), and the plan step refuses larger values with `resource_limit` (`:391`).
- `cli/session.py:573` prints "Incomplete: rerun after resolving the above." with no indication that a `resource_limit` row cannot be resolved by rerunning, and no remedy.
- `DECODED_CAP = 4 << 20` (`raw_redaction.py:94`) would itself reject the largest observed row (4.7 MB decoded). The fix must also account for rows above the decoded bound.

## Expected Behavior

Either every row is actually scanned, or the report clearly separates rows that were verified clean or redacted from rows that cannot be verified, names the reason, and tells the operator exactly what to do about each one.

## Proposed Direction (options, not prescriptive)

1. **Process oversized rows separately, one at a time**, outside the 8-row page. Fetch each one with `substr()`/blob chunks under its own byte budget, decode and scan it, and write it back in a single-row request. That keeps the page and wire bounds intact.
2. **Treat a refused row as verified when it can be decoded within an explicit, larger opt-in bound** (e.g. `--max-row-bytes`) and scans clean, so the run reaches `complete: true`.
3. **At minimum**, report `resource_limit` rows as a distinct `unverifiable_oversize` outcome with row ids and sizes and a concrete remedy (e.g. the opt-in flag, or `ll-session prune`/`compact` for the affected sessions), rather than "rerun".

**Also check:** does ingest-time sanitization (ENH-3751) apply the same size bound? If an incoming row over the cap is stored unsanitized rather than refused or sanitized in chunks, write-time redaction has the same gap for new data, and this issue's fix should cover both paths.

## Acceptance Criteria

- [ ] A store whose only refusals are oversized-but-clean rows can reach `complete: true` through a documented path (default or opt-in).
- [ ] An oversized row that does contain a match is redacted (or left as found and clearly reported as unverified), never silently counted as clean.
- [ ] The text and JSON reports tell an unresolvable size refusal apart from other failures, and give an actionable remedy instead of "rerun after resolving the above."
- [ ] Page and request byte bounds stay enforced (existing `TestWireBounds` still passes).
- [ ] Ingest-time behavior for payloads over the cap is confirmed and covered by a test; if it stores unsanitized data, that path is fixed too.
- [ ] Tests use a synthetic over-cap row (clean and dirty variants) and fail on the current code.
