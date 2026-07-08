---
id: ENH-2545
title: Document the full `OUTPUT_STYLING.md` public-API surface (rendering helpers
  + formatters)
type: ENH
priority: P3
status: done
discovered_date: 2026-07-08
captured_at: '2026-07-08T09:20:00+00:00'
completed_at: 2026-07-08 15:28:42+00:00
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
testable: false
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

Completed in two phases (refine-issue research → manage-issue implementation):

1. **Refine-issue research** (see [Codebase Research Findings](#codebase-research-findings) below): enumerated the actual public surface of `scripts/little_loops/cli/output.py` by direct line-anchored reading; flagged four helpers (`truncate`, `format_size`, `parse_color_string`, `bullet_list`) the issue body claimed existed but do not — these are dropped from the doc to avoid creating a documentation contract against non-existent code.
2. **Manage-issue implementation** ([plan](../../../thoughts/shared/plans/2026-07-08-ENH-2545-management.md)): inserted a new `### Public API` subsection inside `## Core Module: output.py` of `docs/reference/OUTPUT_STYLING.md`, immediately after the existing `### Startup configuration` subsection (lines 109-118). The new subsection is grouped into four families:
   - **Status channels** — `success`, `error`, `warning`, `info`, `hint` (stdout/stderr stream, icon, ANSI code per function)
   - **Text helpers** — `format_relative_time`, `print_json` (cross-references the `strip_ansi` doc above; avoids duplication)
   - **Structural formatters (pure strings)** — `table`, `status_block`, `progress`, `sparkline`
   - **Output-mode control** — `set_output_mode`, `get_output_mode`
3. **Cross-references** — the nine functions already documented in the prior Core Module subsections (`terminal_size`/`terminal_width`/`wrap_text`/`strip_ansi`/`configure_output`/`use_color_enabled`/`colorize`/`print_json`/`format_relative_time`) are referenced rather than re-stated.

### Acceptance evidence

- All 20 documented functions importable: `python -c "from little_loops.cli.output import ..."` → `OK`.
- `grep -nE 'truncate|format_size|parse_color_string|bullet_list' docs/reference/OUTPUT_STYLING.md` returns only contextually-correct uses of the word "truncate" (describing the `table` truncation behavior) — none of the four non-existent helpers is claimed as a public API.
- Doc diff: `+76` lines (one new `### Public API` subsection); no other sections touched.

## Out of scope

- Documenting internal-only helpers (those without `__all__` entries).
- Changing any rendering behaviour.
- Adding new public APIs.

## Verification

- All listed functions are actually importable and present at the documented import paths.
- `python -m pytest scripts/tests/` green (this is doc-only).
- A quick `grep -rE 'def (success|error|warning|info|hint)' scripts/little_loops/cli/` corroborates the listed signatures.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on direct reading of `scripts/little_loops/cli/output.py` (line-by-line) and `docs/reference/OUTPUT_STYLING.md`:_

### File-path correction

The issue body references three files — `cli/format_helpers.py`, `cli/output.py`, and `cli/table.py` — but **only `scripts/little_loops/cli/output.py` exists.** `ls scripts/little_loops/cli/` confirms there is no `format_helpers.py` or `table.py` in the cli package. The four "rendering helpers" plus the five status channels, plus `terminal_size` / `wrap_text` / `colorize` / `configure_output` etc., are **all in one module: `cli/output.py`**. The doc-update should rewrite the issue's expected layout to a single import path: `from little_loops.cli.output import ...`.

### There is no `__all__` in `output.py`

`output.py` defines no `__all__` list, so every top-level `def`/`class` is technically public. Convention: underscore-prefixed helpers (`_smart_title` at `:136`, `_all_caps` at `:143`) are internal. The doc should explicitly mark internal-only helpers as such rather than treating the absence of an `__all__` as a public API signal.

### Actual public API in `cli/output.py` (line-anchored)

**Status channels (`output.py:241-277`)** — all use the `_ICONS` dict to prefix the message with a glyph when color is enabled; `success`, `info`, `warning`, `hint` print to stdout; `error` prints to stderr; all use `flush=True`.

| Function | Line | Stream | Icon prefix | Color code |
|----------|------|--------|-------------|------------|
| `success(msg: str)` | 250 | stdout | `✓ ` | `32` (green) |
| `error(msg: str)` | 256 | stderr | `✗ ` | `38;5;208` (orange) |
| `warning(msg: str)` | 262 | stdout | `⚠ ` | `33` (yellow) |
| `info(msg: str)` | 268 | stdout | `ℹ ` | `36` (cyan) |
| `hint(msg: str)` | 274 | stdout | `› ` | `2` (dim) |

All five take a single positional `msg` arg — **no `**kw`** (the issue table suggests `success(msg, **kw)` etc., which is incorrect).

**Terminal / text helpers (`output.py:17-45, 154, 201-218`)**:

| Function | Line | Returns | Notes |
|----------|------|---------|-------|
| `terminal_size(default_cols=80, default_rows=24)` | 17 | `tuple[int, int]` | Calls `shutil.get_terminal_size((dc, dr))` |
| `terminal_width(default=80)` | 27 | `int` | Thin wrapper around `terminal_size()` |
| `wrap_text(text: str, indent: str = "  ", width: int \| None = None)` | 32 | `str` | `width=None` ⇒ auto from `terminal_width()` |
| `strip_ansi(text: str)` | 45 | `str` | Removes `\033[...]m` escape sequences |
| `configure_output(config: CliConfig \| None = None)` | 154 | `None` | Merges `config.cli.colors.{priority,type}` into module dicts; `NO_COLOR` always wins |
| `use_color_enabled()` | 201 | `bool` | Returns `_USE_COLOR` module-global (import-time TTY check + `FORCE_COLOR=1` opt-in) |
| `colorize(text: str, code: str)` | 206 | `str` | No-op when `_USE_COLOR` is False |
| `print_json(data: Any)` | 213 | `None` | Stdout JSON dump |
| `format_relative_time(seconds: float)` | 218 | `str` | e.g. "5m ago", "in 3h" |

**Structural / pure-string formatters (`output.py:285-377`)**:

| Function | Line | Args | Returns |
|----------|------|------|---------|
| `table(headers: list[str], rows: list[list[str]], max_col_width: int = 40)` | 285 | `headers`, `rows`, optional `max_col_width` | `str` — box-drawn table; values exceeding `max_col_width` are truncated with `…` (U+2026) |
| `status_block(items: dict[str, str])` | 333 | **single dict arg** (NOT `(title, lines)`) | `str` — right-padded key/value pairs; empty dict ⇒ empty string |
| `progress(current: int, total: int, width: int = 20)` | 348 | `(current, total)` ints + optional `width` | `str` — bar rendered with `█`/`░` Unicode block characters |
| `sparkline(current: int, total: int, width: int = 16)` | 362 | **(current, total) ints** (NOT `(values)`) | `str` — compact progress indicator |

**Output-mode control (`output.py:380-386`)**:

| Function | Line | Notes |
|----------|------|-------|
| `set_output_mode(mode: Literal["human", "json", "plain"])` | 380 | Switches the global `_OUTPUT_MODE` |
| `get_output_mode() -> Literal["human", "json", "plain"]` | 386 | Reads the current `_OUTPUT_MODE` |

### Functions the issue body claims exist but don't

- **`truncate(s, width)`** — **does not exist** in `cli/output.py`. Grep across `scripts/little_loops/cli/` returns only **module-local** `_truncate_title` / `_truncate` helpers in `issues/list_cmd.py:14`, `issues/refine_status.py:151`, `loop/__init__.py:523`, `loop/info.py:343`. These are **private to their callers** and should not be promoted to "public API" without extracting them.
- **`format_size(n_bytes)`** — **does not exist** anywhere in the `cli/` package. Grep returns zero matches. If size-formatting is needed for external callers, this is a feature, not a doc — file a follow-up.
- **`parse_color_string(spec)`** — **does not exist** anywhere in the `cli/` package. Grep returns zero matches. ANSI color parsing happens inline (`_resolve_color_spec` lives in the config module, not `cli/output.py`).
- **`bullet_list(items)`** — **does not exist** anywhere in the `cli/` package. Grep returns zero matches. The issue's structural-helpers row should drop it.

These four are **stale references** carried over from a hypothetical earlier doc draft. Removing them from the issue's expected-API table (and from the doc) avoids creating a documentation contract that points at non-existent code.

### Color-palette dicts that already **are** documented

The issue's "ANSI Palette" reference is correct: `PRIORITY_COLOR` and `TYPE_COLOR` are exported (per `OUTPUT_STYLING.md:33-55`) and used widely. The doc also covers `CATEGORY_COLOR` (`OUTPUT_STYLING.md:60-75`) and edge-color dicts separately. The new `## Public API` section should reference these tables rather than re-enumerate them.

### `issue_history/formatting.py` (separate from the cli package)

The issue mentions the four `format_*` helpers in `issue_history/formatting.py`. Confirmed: `format_summary_text/json/analysis_text/analysis_json/analysis_yaml/analysis_markdown` live there (`OUTPUT_STYLING.md:340-353`), not in `cli/output.py`. Their import path is `from little_loops.issue_history.formatting import ...` — distinct from `cli.output`.

### Recommended section layout for `OUTPUT_STYLING.md`

1. **Single module reference** — `from little_loops.cli.output import ...`
2. **Subsections matching the table above**, ordered: Status channels → Terminal/text → Structural formatters → Output mode → Color/configuration helpers.
3. Each entry should be one line (signature) + one line (purpose) + one short example invocation, mirroring the count from the original issue (~40 lines).
4. Cross-reference `issue_history/formatting.py` in a separate "Issue-history formatters" subsection (keeping the existing ordering of the file, since the issue notes it was "orphaned").
5. **Insertion point**: between the "ANSI Palette" / edge-color tables (ending around `OUTPUT_STYLING.md:107`) and the "Logo" / "Issue Card" sections (starting at line 122). This keeps the "engine" public API in one block before the higher-level renderers are introduced.

### `__all__` hardening (optional follow-up, not in scope of this issue)

Since `output.py` ships no `__all__`, consider a future hardening ENH to add `__all__ = ["success", "error", "warning", "info", "hint", "terminal_size", "terminal_width", "wrap_text", "strip_ansi", "colorize", "configure_output", "use_color_enabled", "table", "status_block", "progress", "sparkline", "set_output_mode", "get_output_mode", "format_relative_time", "print_json", ...]`. Out of scope for ENH-2545 (doc-only).

Captured by `/ll:audit-docs docs/reference/` Phase 2 review (2026-07-08).


## Session Log
- `/ll:ready-issue` - 2026-07-08T15:22:45 - `7f1fd7a6-62cb-4edc-b4c5-954b0ed4f95e.jsonl`
- `/ll:refine-issue` - 2026-07-08T14:40:51 - `ea1dab68-2ebe-4bc4-99ae-67df8309e565.jsonl`
- `/ll:manage-issue` - 2026-07-08T15:28:42 - `e23b6e66-ab93-4605-82bb-cf83246a9ea2.jsonl`
