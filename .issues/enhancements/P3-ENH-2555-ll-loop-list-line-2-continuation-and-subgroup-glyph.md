---
discovered_date: "2026-07-08"
discovered_by: review
confidence_score: 100
outcome_confidence: 95
status: done
completed_at: 2026-07-08T00:00:00Z
---

# ENH-2555: `ll-loop list` line-2 continuation display + subgroup glyph differentiation

## Summary

Two layout improvements to `cmd_list` (`scripts/little_loops/cli/loop/info.py`):

1. **Two-line description display.** Surface the rest of a loop's `description:` field (currently collapsed to line 1 + `…`) as a wrapped continuation row below the loop row. Line 1 stays inline and truncated as before; line 2+ are joined, dedented, and wrapped at `terminal_width - 4` columns, indented 4 spaces, plain text.
2. **Differentiate auto-clustered subgroup headers from real category headers.** Replace the all-caps `  RN (3)` style with `  · rn-* (3)` (bullet + lowercase prefix + glob, dim gray) so prefix-clustered groupings are visually distinct from parent category headings like `  ▸ PLANNING  (4)`.

## Current Behavior

`ll-loop list` over 81 loops shows descriptions truncated mid-word at 30–60 chars (`→ L…`, `whites…`, `Plan -> Rese…`). 77 of 87 builtin loops use multi-line YAML descriptions where line 2+ is either sentence continuation OR author guidance like `Adapt by…`, `Requires…`, `Run as: ll-loop run foo …` — actionable content currently hidden until the user reads the YAML file.

Subgroup headers (prefix clusters with ≥3 members — `rn-*`, `apo-*`, `rl-*`) render at 2-space indent with the same all-caps + paren-count style as parent category headers, so they read as named sub-categories when they are layout artifacts of loop-naming convention.

## Expected Behavior

`ll-loop list` shows:

```
  ▸ APO  (6)
  · apo-* (5)                              ← dim gray, bullet + glob
    apo-beam                          built-in    Beam search prompt optimization (APO technique): ge…
        per iteration, scores all of them against evaluation criteria, selects the highest-scoring
        variant, and writes it back to the prompt file. Repeats until the best score exceeds the
        target or max_iterations is reached. Controlled by beam_width (number of variants per
        round) and target_score (0–100).
    apo-contrastive                   built-in    Contrastive prompt optimization (APO technique): …
        …
```

- Line 1 of `description:` stays on the row, truncated to `desc_col` as today.
- Line 2+ (remaining non-blank lines joined with spaces) wrap below the row at 4-space indent.
- Single-line descriptions: no extra row.
- Empty descriptions: no extra row.
- At `terminal_width < 50`, line 2 is suppressed (no usable wrapping space).

`ll-loop list --json` includes `description_line2` as an additive key alongside the existing required fields (`name`, `path`, `category`, `labels`, `visibility`, `description`).

## Motivation

The description column's only purpose is to give the user a scannable summary of each loop. Today, ~50–80% of descriptions truncate mid-word — the column signals "this is what the loop does" but delivers fragments. Surfacing line 2+ on a wrapped continuation restores the original intent without bloating the row layout (line 1 still fits in one screen-line per loop).

Subgroup headers reading as sub-categories is a UX trap: users scan for `RN`, `APO`, `RL` headings and treat them as searchable categories. They're not — they're auto-detected prefix clusters. The new bullet + glob + dim-gray styling tells the eye "this is a layout grouping, not a category."

## Proposed Solution

### Loader change — `scripts/little_loops/cli/loop/info.py`

`_load_loop_meta` (currently at line 58) returns `description` (line 1, no ellipsis) and a new `description_line2` field:

```python
description = raw_lines[0].rstrip() if raw_lines else ""
description_line2 = ""
if len(raw_lines) > 1:
    tail = [ln.strip() for ln in raw_lines[1:] if ln.strip()]
    description_line2 = " ".join(tail).rstrip()
```

The existing `if len(raw_lines) > 1: desc += "…"` branch (the original ellipsis-on-multi-line behavior) is removed — line 1 is returned as-is and line 2 carries the rest.

### Renderer change — `cmd_list` `_emit_row` (info.py:387)

After the loop row `print(...)`, emit wrapped continuation when `description_line2` is non-empty and terminal is wide enough:

```python
line2 = lp.get("description_line2") or ""
tw_now = terminal_width(default=120)
if line2 and tw_now >= 50:
    wrap_w = max(20, tw_now - 4)
    for cont in _wrap_to_width(line2, wrap_w):
        print(f"{indent}    {cont}")  # 4-space indent, plain text
```

Uses existing `_wrap_to_width` from `scripts/little_loops/cli/loop/layout.py:269` (display-width-aware, returns `list[str]`).

Plain text — no ANSI escape codes. `test_description_text_not_dim` (test_ll_loop_commands.py:1956) forbids dim on description text.

### JSON output — `cmd_list --json` branch (info.py:266)

Add `"description_line2": lp.get("description_line2", "")` to the emitted item dict. Additive — does not break `REQUIRED_FIELDS` in `scripts/tests/test_json_output_contracts.py:45`.

### Subgroup header change — `cmd_list` subgroup branch (info.py:397)

Replace:
```python
sub_label = _all_caps(prefix)
sub_color = f"{cat_color};1"
print(colorize(f"  {sub_label} ({len(members)})", sub_color))
```
with:
```python
print(colorize(f"  · {prefix}-* ({len(members)})", "2"))
```

Only the prefix-clustered branch changes. Parent category headers (`f"  ▸ {cat_title}  ({len(group)})"`) and the rollup badge are untouched.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `_load_loop_meta`, JSON output dict, `_emit_row` row emit, subgroup header rendering
- `scripts/tests/test_ll_loop_commands.py` — update 2 existing tests, add 3 new tests

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/layout.py` — `_wrap_to_width` is the only helper consumed by the new line-2 wrap logic. No change to `layout.py`.

### Codebase Research Findings

- **`_wrap_to_width`** (`layout.py:269`) is display-width-aware (uses `wcwidth.wcwidth`) and returns `list[str]`. It is currently private to `layout.py` but `info.py` already imports from `layout.py` (line 18). Adding `_wrap_to_width` to that import block is symmetric with the existing `_truncate_to_width` import at line 24.
- **`terminal_width`** (`cli/output.py:27`) defaults to 80 but `cmd_list` calls it with `default=120` (info.py:302). The `terminal_width()` no-arg form returns the actual terminal width when stdout is a TTY; piped/CI runs return the default.
- **Helpers `_load_loop_meta`, `_detect_subgroups`, `_category_rollup`, `_render_labels`, `_display_name`** are module-private to `info.py` and only used inside it. No external module imports them. Safe to refactor the loader without coordination.
- **`_emit_row`** is a closure defined inside `cmd_list` (info.py:363); it captures `desc_col`, `name_col`, `kind_col`, `label_col`, and `kind_color_map` from the enclosing scope. Adding the line-2 emission inside this closure keeps the captured state local.
- **Subgroup detection thresholds** (`_detect_subgroups`, info.py:483): unchanged. The new glyph applies only to the `prefix` branch; the `("", flat)` tail branch keeps its existing 2-space leaf indent.

### Similar Patterns

- **`_box_inner_lines`** (`layout.py:351`) already wraps action bodies using `_wrap_to_width` — same primitive, same indent pattern. The `info.py` line-2 emit mirrors this pattern.
- **`test_subgroup_subhead_for_shared_prefix`** (test_ll_loop_commands.py:1798) previously asserted `"Subgroup" in out or "APO" in out` — the loose OR was always passing via the `"APO" in out` branch (the `_all_caps(prefix)` call capitalized `apo` → `APO`). The new assertion `· apo-*` is more specific and matches the new glyph.
- **ENH-2539 polish** (commits `cd745299`, `a3b67724`, `9b03609a`, `94198202`) is the prior art: the `cmd_list` layout has been iterated heavily. The line-2 emission continues the same direction (more info, less visual noise) without disrupting prior polish.

### Tests

Updated `scripts/tests/test_ll_loop_commands.py`:

- `test_multiline_description_gets_ellipsis` (line 1261): now asserts `meta["description"] == "First line."` and `meta["description_line2"] == "Second line."` (was `"…" in meta["description"]`).
- `test_subgroup_subhead_for_shared_prefix` (line 1798): now asserts `· apo-*` in output (was `"Subgroup" in out or "APO" in out`).

Added to `TestCmdListENH2539Polished`:

- `test_description_line2_wraps_below_row`: builds a loop with 2-line YAML description; asserts line 2 content appears with ≥6-space indent (2 leaf + 4 line-2).
- `test_single_line_description_no_extra_row`: builds a single-line description; asserts no 4-space-indented continuation row exists in the output.
- `test_subgroup_header_uses_bullet_glyph`: builds 3 loops sharing `rn-` prefix; asserts `· rn-*` in output, `▸` parent still present, legacy `  RN (` absent.

### Documentation

- No docs change required — the layout is internal to `ll-loop list` output. The plan file at `~/.claude/plans/do-1-and-2-quizzical-moore.md` documents the design for future reference.

### Configuration

- N/A — no new config keys; the changes are pure rendering logic.

## Implementation Steps

1. Extend `_load_loop_meta` to return `description_line2`. Drop the trailing `…` from line 1.
2. Add `description_line2` to JSON output dict in `cmd_list`.
3. Add `_wrap_to_width` to the `layout` import block in `info.py`.
4. Extend `_emit_row` to emit wrapped line-2 continuation when present and terminal is wide enough.
5. Replace the subgroup header print with the bullet + glob + dim-gray version.
6. Update `test_multiline_description_gets_ellipsis` and `test_subgroup_subhead_for_shared_prefix` assertions.
7. Add `test_description_line2_wraps_below_row`, `test_single_line_description_no_extra_row`, `test_subgroup_header_uses_bullet_glyph`.
8. Run `ruff format`, `ruff check`, `mypy`, and the full pytest suite on the touched files.

## Use Case

A developer runs `ll-loop list` to find a loop that does recursive planning. They see `rn-plan` row with line 1 truncated ("Recursive planning loop with self-scoring rubric…") and line 2 wrapping below with usage detail ("Accepts a natural language…"). They also see the `· rn-* (3)` dim-gray subhead under `PLANNING` and immediately understand that's an auto-cluster of three loops, not a named sub-category — so they know to scan all three, not search for "rn-" specifically.

## Acceptance Criteria

- [x] `_load_loop_meta` returns `description_line2` for multi-line YAML descriptions
- [x] Line 2 wraps below the row at 4-space indent when terminal width ≥ 50
- [x] Single-line descriptions do not emit an extra row
- [x] At `terminal_width < 50`, line 2 emission is suppressed
- [x] `ll-loop list --json` includes `description_line2` key
- [x] Subgroup headers render as `· {prefix}-* ({n})` in dim gray
- [x] Parent category headers (`▸ {CATEGORY}  (n)`) unchanged
- [x] Rollup badge unchanged
- [x] All existing `cmd_list` tests pass after assertion updates
- [x] New tests (`test_description_line2_wraps_below_row`, `test_single_line_description_no_extra_row`, `test_subgroup_header_uses_bullet_glyph`) pass
- [x] `ruff format --check` clean
- [x] `mypy` clean
- [x] All 292 tests in `test_ll_loop_commands`, `test_cli_loop_layout`, `test_json_output_contracts` pass

## Impact

- **Priority**: P3 - Useful UX improvement; restores the description column's intended purpose and fixes a category-vs-cluster visual confusion
- **Effort**: Small - Touches one production file and its test file; reuses existing `_wrap_to_width` helper
- **Risk**: Low - Additive JSON key (existing consumers unaffected); renderer changes are guarded by `terminal_width < 50` floor and `description_line2` truthiness check
- **Breaking Change**: No - JSON contract preserved (additive key); text output is additive (no removed fields); only the `…` on multi-line descriptions in JSON `description` field is removed, replaced by full line 1 + new `description_line2` field

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | System design context |
| [docs/reference/API.md](../../docs/reference/API.md) | CLI tool reference |

## Labels

`enhancement`, `cli`, `ll-loop`, `ux`, `layout`

## Resolution

Implemented in `scripts/little_loops/cli/loop/info.py`. Extended `_load_loop_meta` to return `description_line2` (joined, dedented continuation of multi-line descriptions) and removed the trailing `…` from line 1. Threaded `description_line2` into the JSON output dict as an additive key. Imported `_wrap_to_width` from `layout.py` and extended `_emit_row` to emit wrapped continuation rows at 4-space indent when `description_line2` is non-empty and `terminal_width() >= 50`. Replaced the all-caps subgroup header (`  RN (3)`) with a dim-gray bullet-prefix-glob variant (`  · rn-* (3)`). Updated two existing tests for the new behavior (`test_multiline_description_gets_ellipsis`, `test_subgroup_subhead_for_shared_prefix`) and added three new tests covering line-2 wrap rendering, single-line description no-op, and subgroup glyph differentiation. All 292 tests in the touched test files pass; `ruff format --check`, `ruff check`, and `mypy` are clean.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-09T01:29:58 - `1254396c-ad99-4fb4-9ab8-4eef69994e79.jsonl`
- 2026-07-08 — Layout review → design → implementation → verification (single session)

---

**Completed** | Created: 2026-07-08 | Completed: 2026-07-08 | Priority: P3