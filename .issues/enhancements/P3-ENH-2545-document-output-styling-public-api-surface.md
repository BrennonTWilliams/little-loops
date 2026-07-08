---
id: ENH-2545
title: 'Document the full `OUTPUT_STYLING.md` public-API surface (rendering helpers + formatters)'
type: ENH
priority: P3
status: open
discovered_date: 2026-07-08
captured_at: '2026-07-08T09:20:00+00:00'
discovered_by: audit
decision_needed: false
labels:
  - enhancement
  - documentation
  - output-styling
  - public-api
  - follow-up-from-docs-audit-2026-07-08
confidence_score: 90
outcome_confidence: 90
score_complexity: 3
score_test_coverage: 3
score_ambiguity: 2
score_change_surface: 4
---

# ENH-2545: Document the full `OUTPUT_STYLING.md` public-API surface

## Summary

The Phase 1 docs audit fixed the renderable primitives (`colorize`, `strip_ansi`, table column behavior), but `docs/reference/OUTPUT_STYLING.md` still does not enumerate the **public-API surface** of the rendering helpers module (`scripts/little_loops/cli/format_helpers.py` and friends). External callers (custom commands, extension authors, downstream `ll-` tools) need a single-source-of-truth list of:

- The four logger channels (`success`, `error`, `warning`, `info`) and `hint()`.
- Helper utilities: `strip_ansi`, `truncate`, `format_size`, `parse_color_string`.
- Structural helpers: `table(rows, headers)`, `status_block(title, lines)`, `progress(label, current, total)`, `sparkline(values)`, `bullet_list(items)`.
- Format-channels `format_summary_text`, `format_summary_json`, `format_analysis_text`, `format_analysis_json` (already documented but orphaned — see "Fix ordering").

Currently these are scattered across `cli/format_helpers.py`, `cli/output.py`, `cli/table.py`, and various test snapshots. External callers can't discover them without reading source.

## Current Behavior

`OUTPUT_STYLING.md` documents:
- ANSI palette (`cli.colors` config)
- `format_summary_text` / `format_summary_json` / `format_analysis_text` / `format_analysis_json` (issue-history formatters, only)
- `throttle_hard` edge color, issue card width (60 chars), vertical connector chars

It does NOT document the `format_*` helpers, logger channels, or structural renderers — so external callers either reimplement them or grep for `colorize(`.

## Expected Behavior

Add a `## Public API` section to `OUTPUT_STYLING.md` that enumerates the public functions in the output-styling module family. For each, give a one-line signature and a one-line example. Group by category:

| Category | Functions |
|----------|-----------|
| Status channels | `success(msg, **kw)`, `error(msg, **kw)`, `warning(msg, **kw)`, `info(msg, **kw)`, `hint(msg, **kw)` |
| Text helpers | `strip_ansi(s)`, `truncate(s, width)`, `format_size(n_bytes)`, `parse_color_string(spec)` |
| Structural | `table(rows, headers=...)`, `status_block(title, lines, **style)`, `progress(label, current, total, **style)`, `sparkline(values, **style)`, `bullet_list(items, **style)` |

Each entry shows the import path (`from little_loops.cli.format_helpers import ...`) and one example invocation. The total addition is ~40 lines.

## Resolution

1. Grep `scripts/little_loops/cli/` for functions named `def render_*`, `def format_*` (excluding the issue_history formatters), `def table`, `def status_block`, `def progress`, `def sparkline`, `def bullet_list`, and the five `success/error/warning/info/hint` definitions.
2. Verify which are `__all__`-exported (public) vs internal-only.
3. Add `## Public API` section to `OUTPUT_STYLING.md` between the "ANSI Palette" section and the issue-history formatter section.

## Out of scope

- Documenting internal-only helpers (those without `__all__` entries).
- Changing any rendering behaviour.
- Adding new public APIs.

## Verification

- All listed functions are actually importable and present at the documented import paths.
- `python -m pytest scripts/tests/` green (this is doc-only).
- A quick `grep -rE 'def (success|error|warning|info|hint)' scripts/little_loops/cli/` corroborates the listed signatures.

Captured by `/ll:audit-docs docs/reference/` Phase 2 review (2026-07-08).
