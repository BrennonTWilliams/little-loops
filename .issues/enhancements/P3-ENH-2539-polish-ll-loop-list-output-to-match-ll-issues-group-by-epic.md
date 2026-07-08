---
id: ENH-2539
title: Polish `ll-loop list` output to match `ll-issues list --group-by epic`
type: ENH
priority: P3
status: open
discovered_date: 2026-07-08
captured_at: '2026-07-08T01:52:29Z'
discovered_by: capture-issue
decision_needed: false
labels:
- enhancement
- cli-output
- ux
- captured
confidence_score: 99
outcome_confidence: 84
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 23
score_change_surface: 22
---

# ENH-2539: Polish `ll-loop list` output to match `ll-issues list --group-by epic`

## Summary

`ll-loop list` is functionally complete but its human-readable rendering is markedly less polished than the reference rendering produced by `ll-issues list --group-by epic`. Eight concrete polish points bring the loop listing up to the same level of visual hierarchy, column discipline, and information density as the issue listing.

All changes are scoped to `scripts/little_loops/cli/loop/info.py` (the `cmd_list` human renderer at lines 255-329) and the shared color helpers in `scripts/little_loops/cli/output.py` (currently hosting `PRIORITY_COLOR` and `TYPE_COLOR` at lines 72-85).

## Current Behavior

`ll-loop list` outputs:

- Category headers all painted the same cyan (`colorize(f"  ▸ {cat_title}  ({len(group)})", "36;1")` at `info.py:291`), regardless of which loop category is being listed.
- No inline rollup or progress badge on the header — just `(N)`, even though `hidden_counts` (the visibility tier counts for `internal` and `example`) is already collected at `info.py:209-229` but never displayed.
- Loop rows render as `name + description + suffix` with no fixed-width tag column (`info.py:300-328`). Description and label suffixes compete for terminal width with no semantic separation.
- Visibility signal is buried in the suffix as a single trailing `●` for project loops (`info.py:311-312`); built-in loops get no marker at all.
- Every label is colored the same dim green (`colorize(f"[{label}]", "2")` at `info.py:308`) regardless of semantic class.
- Categories with shared name prefixes (e.g., `apo-beam`, `apo-contrastive`, `apo-feedback-refinement` all start with `apo-`) get no visual sub-grouping.
- No closing summary line. The header summary `81 loops · 21 categories · 4 project, 77 built-in` (`info.py:278-281`) is the only count.
- Category titles use naive `cat.replace("-", " ").title()` (`info.py:290`), producing `Apo` for the APO category (should be `APO`), `Hitl` for HITL, `Llm` for LLM.

## Expected Behavior

`ll-loop list` produces output with:

1. **Per-category color** in headers (each category slug maps to a distinct ANSI code from a new `CATEGORY_COLOR` map, mirroring the `TYPE_COLOR`/`PRIORITY_COLOR` pattern).
2. **Inline rollup badge** on each header showing `(N · M built-in · K project)` (or similar) — the `hidden_counts` data is surfaced, not collected-then-discarded.
3. **Column-aligned metadata** with fixed columns: `name | kind | labels | description`. Column widths are computed once from `tw` and held across the entire output.
4. **Visibility as a first-class kind column** — `built-in`, `project`, `internal`, `example` each get a distinct, colored marker. The trailing `●` is replaced.
5. **Semantically color-coded labels** via a new `LABEL_COLOR` map: `[hitl]` cyan, `[comparison]` magenta, `[generated]` yellow, `[meta]` orange, with dim-green fallback for unknown labels.
6. **Subgroup subheads** for categories with shared name prefixes — emit `colorize(f"  Subgroup ({n})", "0;2")` (mirroring the `Sub-EPICs (N)` subhead at `list_cmd.py:279`) and indent leaves underneath.
7. **Closing summary line** mirroring `list_cmd.py:300`: `Total: 81 loops · 21 categories · 4 project, 77 built-in · 2 hidden (internal)`.
8. **Acronym-aware title-casing** via a small `ACRONYMS = {"APO", "HITL", "LLM", "SVG", "FSM", "RLHF", "API"}` set applied to both category titles (`info.py:290`) and any subgroup-prefix subheads (item 6).

Reference visual target — the EPIC-grouped render at `scripts/little_loops/cli/issues/list_cmd.py:174-302`:

```
EPIC-1463: Track deferred Codex CLI interop gaps (3) (25/30 done)
  P3  FEAT-2123  Surface per-invocation token usage from Codex and OpenCode runners
  P4  ENH-1718  Enable `PreToolUse` by default for Codex adapter
  P4  FEAT-2122  Exploit Codex native spawn model (spawn_agents_on_csv) for ll-parallel
```

Target render for `ll-loop list`:

```
  ▸ Harness  (19) · 17 built-in, 2 project

  apo  APO  (6)
    apo-beam                  built-in  [apo]    Beam search prompt optimization (APO tech…
    apo-contrastive           built-in  [apo]    Contrastive prompt optimization (APO t…
  hitl HITL  (2)
    hitl-compare              built-in  [hitl] [comparison]  Human-in-the-loop compare
    hitl-md                   built-in  [hitl] [markdown]    Human-in-the-loop markdown

Total: 81 loops · 21 categories · 4 project, 77 built-in · 2 hidden (internal)
```

## Motivation

`ll-issues list --group-by epic` is a polished, information-dense listing — its header hierarchy (color + bold + rollup badge), column alignment (priority / ID / title / status), and closing summary have become the de facto reference for "what good CLI output looks like" in this project. The loop listing is one of the most-used CLI surfaces in the plugin (every loop audit, every review, every `create-loop` invocation starts with `ll-loop list`), and it currently lags behind in:

- **Information density** — no rollup badge, no closing summary, no visibility tag column.
- **Visual hierarchy** — uniform cyan headers give no signal about category role or weight.
- **Discoverability** — `apo-beam` / `apo-contrastive` / etc. read as a flat list within "Apo" with no signal that they are members of an `apo-*` family.
- **Title accuracy** — `Apo`, `Hitl`, `Llm` look like misspelled proper nouns in a terminal; `APO`, `HITL`, `LLM` look correct.

This is pure CLI polish — no behavioral change, no new flags in the initial pass — but the cumulative effect of all eight points is a listing that reads as a single coherent table instead of a flat name dump.

## Proposed Solution

### 1. Add `CATEGORY_COLOR`, `LABEL_COLOR`, `ACRONYMS` to `output.py`

Mirror the `PRIORITY_COLOR`/`TYPE_COLOR` pattern at `scripts/little_loops/cli/output.py:72-85`:

```python
CATEGORY_COLOR: dict[str, str] = {
    "Api Adoption": "33",        # yellow
    "Apo": "38;5;141",           # purple
    "Code Quality": "32",        # green
    "Data": "34",                # blue
    "Evaluation": "38;5;208",    # orange
    "Gate": "38;5;160",          # red
    "Harness": "35",             # magenta
    "Issue Management": "36",    # cyan
    # ...
}
LABEL_COLOR: dict[str, str] = {
    "hitl": "36",
    "comparison": "35",
    "generated": "33",
    "meta": "38;5;208",
}
ACRONYMS: frozenset[str] = frozenset({"APO", "HITL", "LLM", "SVG", "FSM", "RLHF", "API"})
```

Also extend `configure_output` (`output.py:88-131`) to merge any `categories` block from `CliConfig`, parallel to how `priority` and `type` are merged today.

### 2. Reformat headers in `cmd_list`

Replace `info.py:291` with:

```python
cat_color = CATEGORY_COLOR.get(cat, "36;1")
header_label = f"  ▸ {_smart_title(cat)}  ({len(group)})"
rollup = _category_rollup(group, hidden_counts)
if rollup:
    header_label += f"  {colorize(rollup, '2')}"
print(colorize(header_label, cat_color))
```

### 3. Add `_category_rollup` helper

```python
def _category_rollup(group: list[dict], hidden_counts: dict[str, int]) -> str:
    """Build inline rollup badge: 'M built-in · K project · J internal · N example'.

    Consumes lp['visibility'] (one of 'public'/'internal'/'example') rather than
    the boolean lp['builtin'] so the hidden tiers can be surfaced.
    """
    counts = {"built-in": 0, "project": 0, "internal": 0, "example": 0}
    for lp in group:
        v = lp.get("visibility", "public")
        if v == "public":
            if lp.get("builtin", True):
                counts["built-in"] += 1
            else:
                counts["project"] += 1
        else:
            counts[v] += 1  # 'internal' or 'example'
    parts = [f"{counts['built-in']} built-in"]
    if counts["project"]:
        parts.append(f"{counts['project']} project")
    if counts["internal"]:
        parts.append(f"{counts['internal']} internal")
    if counts["example"]:
        parts.append(f"{counts['example']} example")
    return ", ".join(parts)
```

### 4. Reformat the inner loop with fixed columns

Replace `info.py:292-328` with a column-driven layout:

```python
NAME_COL = 32
KIND_COL = 11
LABEL_COL = 18
indent = "  "
for lp in group:
    name = _truncate(lp["name"], NAME_COL).ljust(NAME_COL)
    kind = lp.get("visibility", "built-in")  # project | built-in | internal | example
    kind_color = {"project": "36;1", "built-in": "2", "internal": "3", "example": "33;2"}.get(kind, "2")
    kind_str = colorize(kind.ljust(KIND_COL), kind_color)
    label_str = _render_labels(lp["labels"], max_chars=LABEL_COL)
    avail = tw - len(indent) - NAME_COL - KIND_COL - LABEL_COL - 4
    desc = _truncate(lp.get("description", "") or "", max(avail, 20))
    print(f"{indent}{colorize(name, '36')}{kind_str}{label_str}  {colorize(desc, '2')}")
```

### 5. Color-coded labels

```python
def _render_labels(labels: list[str], max_chars: int) -> str:
    if not labels:
        return ""
    visible, hidden = labels[:2], len(labels) - 2
    parts = []
    for lab in visible:
        color = LABEL_COLOR.get(lab.lower(), "2")
        parts.append(colorize(f"[{lab}]", color))
    if hidden > 0:
        parts.append(colorize(f"[+{hidden}]", "2"))
    return "  " + " ".join(parts)
```

### 6. Subgroup subheads

Detect a common prefix on `lp["name"]` (split on `-`, look for ≥3 members sharing a 2-3 char prefix). Emit a dim subhead, indent leaves one level deeper:

```python
subgroups = _detect_subgroups(group)
for sub_name, members in subgroups:
    print(colorize(f"    {sub_name}  ({len(members)})", "0;2"))
    for lp in members:
        # ... render leaf indented 4 spaces instead of 2
```

### 7. Closing summary

After the per-category render loop, mirror `list_cmd.py:300`:

```python
print(f"\nTotal: {len(all_loops)} loops · {len(buckets)} categories · "
      f"{n_project} project, {n_builtin} built-in")
if sum(hidden_counts.values()):
    hidden_str = ", ".join(f"{v} {k}" for k, v in hidden_counts.items() if v)
    print(colorize(f"       {sum(hidden_counts.values())} hidden ({hidden_str})", "2"))
```

### 8. Acronym-aware title casing

```python
def _smart_title(slug: str) -> str:
    parts = slug.replace("-", " ").split()
    return " ".join(p.upper() if p.upper() in ACRONYMS else p.capitalize() for p in parts)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — primary renderer changes (header color, columns, rollup, summary, subgroup detection)
- `scripts/little_loops/cli/output.py` — add `CATEGORY_COLOR`, `LABEL_COLOR`, `ACRONYMS`, extend `configure_output`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__main__.py` — entry point invoking `cmd_list`; no signature change needed
- `scripts/little_loops/cli/loop/__init__.py` — arg parser for `ll-loop list`; no flag changes in initial pass (items 9-11 from analysis are deferred)

### Similar Patterns
- `scripts/little_loops/cli/issues/list_cmd.py:174-302` — the reference implementation. Same `colorize` + `TYPE_COLOR` + `_progress_badge` pattern, just ported to a different domain (loops vs issues).
- `scripts/little_loops/cli/output.py:72-85` — `PRIORITY_COLOR` and `TYPE_COLOR` are the direct analog for the new color maps.

### Tests
- `scripts/tests/test_cli_loop_layout.py` — existing test file per `git status`. Add tests for:
  - Each of the 8 polish points (header color, rollup, column alignment, kind column, label color, subgroup detection, summary line, acronym casing)
  - Parameterized at `TW=80`, `TW=120`, `TW=200` confirming no line exceeds `tw` and descriptions retain ≥20 chars at narrow widths
- `scripts/tests/test_cli_output.py` — **confirmed exists**; add tests for new `CATEGORY_COLOR` / `LABEL_COLOR` / `ACRONYMS` exports and `configure_output` merge behavior for the optional `categories` block.
- `scripts/tests/test_ll_loop_commands.py:346-590` — existing `cmd_list` integration tests (use `tmp_path` + `_runnable()` helper + `patch(get_builtin_loops_dir, ...)`). Add integration coverage for the new layout, header colors, and closing summary here.
- `scripts/tests/test_ll_loop_display.py:1718-1724` — display tests; parameterize with `patch(terminal_width, return_value=N)` for TW=80/120/200.
- `scripts/tests/test_loop_layout_alignment.py` — alignment tests; verify no line exceeds `tw` at each width and description floor (≥20 chars) holds.

#### Tests to Update — known-breakage list (added by `/ll:wire-issue`)

_Wiring pass added by `/ll:wire-issue`:_

The integration tests above already cover new test coverage; the following **existing** tests will **hard-fail or go stale** with the new rendering and must be updated as part of the implementation:

- `scripts/tests/test_ll_loop_commands.py:1339-1373` (`test_builtin_vs_project_name_color`) — **HARD FAIL**. Asserts `"\033[36;1mproject-loop"` / `"\033[36mbuiltin-loop"` on the *name* column. The proposed layout hardcodes `colorize(name, '36')` for **all** names (per-category color replaces per-builtin cyan), and the bold/dim distinction is eliminated. Either remove the test or rewrite to assert the new per-category name color (use a fixed `CATEGORY_COLOR` patch to keep the assertion stable).
- `scripts/tests/test_ll_loop_commands.py:1375-1411` (`test_builtin_tag_absent_project_marker_present`) — **HARD FAIL**. Asserts `"●" in project_line` and `"●" not in builtin_line` against the trailing visibility dot. Polish point #4 removes the trailing `●` entirely in favor of the `kind` column (`built-in` / `project` / `internal` / `example` text). Rewrite to assert on the new `kind` column text.
- `scripts/tests/test_ll_loop_commands.py:689-720` (`test_grouped_display_by_category`) — **HARD FAIL**. Asserts `"Apo" in out` and `out.index("Apo") < out.index("Uncategorized")`. After polish point #8 (acronym-aware casing), `"apo"` renders as `"APO"`; `out.index("Apo")` returns `-1` and the order comparison raises `ValueError`. Update substring assertions to `"APO"` and `"META"` (verify any other acronyms in test fixtures).
- `scripts/tests/test_ll_loop_commands.py:1199-1224` (`test_description_truncation_at_narrow_width`) — **COSMETIC RISK**. Asserts `"…" in out` at `TW=60`. The new 4-column layout (`name | kind | labels | description`) eats ~30+ columns of terminal width; at TW=60 the description budget may drop to 0 and the assertion fails. Verify TW=60 still produces a description (or adjust TW to the new minimum that fits).
- `scripts/tests/test_ll_loop_commands.py:1477-1507` (`test_summary_header`) — **COSMETIC RISK**. Asserts `"2 loops" in out` and `out.index("2 loops") < first_cat_pos`. The new closing `Total:` summary at the bottom also contains `"2 loops"`, so `out.index("2 loops")` may return the bottom position (still after categories — assertion may still pass — but verify explicitly).

#### Tests to Extend (added by `/ll:wire-issue`)

- `scripts/tests/test_cli_output.py:175-197` (`TestOrangeDefaultColors`) — add `test_category_color_distinct_per_slug` and `test_label_color_known_labels` parallel to `test_priority_p0_is_orange_not_red`. Also assert `ACRONYMS` is a frozenset containing the expected set.
- `scripts/tests/test_cli_output.py:200-297` (`TestConfigureOutput`) — add `test_configure_custom_category_colors` parallel to `test_configure_custom_priority_colors:257`, using `CliConfig.from_dict({"colors": {"categories": {"apo": "35"}}})` and asserting `CATEGORY_COLOR["apo"] == "35"`. Add `test_configure_no_categories_block_keeps_defaults` to verify entries remain unchanged when `CliConfig` has no `categories` key. Add `setup_method`/`teardown_method` reset logic for the new color maps (parallel to existing PRIORITY_COLOR/TYPE_COLOR resets at lines 203-221).

#### New Tests to Write (added by `/ll:wire-issue`)

_Mirror `_force_color` autouse fixture from `test_cli_loop_layout.py:19-83` and integration patterns from `test_ll_loop_commands.py:341-367` (`_runnable()` + `get_builtin_loops_dir` patch + `capsys.readouterr().out`)._

In `scripts/tests/test_cli_loop_layout.py` (or new sibling file), unit tests:
- `TestSmartTitle` — `"apo"` → `"APO"`, `"hitl"` → `"HITL"`, `"harness"` → `"Harness"`, `"issue-management"` → `"Issue Management"`, mid-string acronym `"apo-something-rlhf"` → `"APO Something RLHF"`, `""` → `""`.
- `TestCategoryRollup` — group with `[public/built-in]` only → `"M built-in"`; mixed public → adds `"K project"`; non-empty `hidden_counts` → adds `"J internal"` / `"N example"`; empty group → `""`.
- `TestRenderLabels` — empty labels → `""`; 2 labels → both visible; 4 labels → 2 visible + `[+2]`; known labels get `LABEL_COLOR` codes (`hitl` → `\033[36`, `comparison` → `\033[35`, `generated` → `\033[33`, `meta` → `\033[38;5;208`); unknown labels fall back to `\033[2`.
- `TestDetectSubgroups` — 6 names all `apo-*` in a category → 1 subgroup `apo (6)` with 6 leaves; mixed names with no shared prefix → flat; 2 of 5 sharing prefix → no subgroup (below ≥3 threshold); "dominates" rule from polish point #6.

In `scripts/tests/test_ll_loop_commands.py`, integration tests mirroring `test_issues_cli.py:1103-1176` patterns:
- `TestCmdListHeaderColor` — seed loops in 2+ categories; patch `CATEGORY_COLOR` to fixed codes; assert each category renders with its own ANSI escape.
- `TestCmdListRollupBadge` — seed 3 loops in one category (2 built-in, 1 project); assert `"(2 built-in · 1 project)"` (or equivalent) appears in the category header.
- `TestCmdListKindColumn` — seed built-in / project / internal / example loops; assert each row contains its kind marker text; run with `_USE_COLOR=False` for predictable column position.
- `TestCmdListAcronymCasing` — seed `category: apo` and `category: meta`; assert `"APO"` in output and `"Apo"` not in output.
- `TestCmdListSubgroups` — seed `apo-beam`, `apo-contrastive`, `apo-feedback-refinement`; assert `"Subgroup"` substring + dim ANSI `\033[0;2` present.
- `TestCmdListClosingSummary` — assert `"Total:"` in output and `out.index("Total:") > out.index(<last_category_header>)`.

Parameterized width tests (new idiom for this codebase):
- `TestCmdListTerminalWidths` — `@pytest.mark.parametrize("tw", [80, 120, 200])` — for each TW, seed a category with a long description, patch `little_loops.cli.loop.info.terminal_width` to that value, assert no line exceeds `tw` and description retains ≥20 chars at TW=80.

### Documentation
- `docs/reference/OUTPUT_STYLING.md` — the CLI styling reference covers `output.py` (lines 9-80) including `terminal_width`, `colorize`, `PRIORITY_COLOR`, `TYPE_COLOR`, `configure_output`. New `CATEGORY_COLOR` / `LABEL_COLOR` / `ACRONYMS` entries would extend the "Default color codes" tables (lines 42-69). The "Adding New Styled Output" recipe at line 327 currently says *"add to `PRIORITY_COLOR` or `TYPE_COLOR` in `output.py`, or define a local dict"* — should mention `CATEGORY_COLOR` and `LABEL_COLOR` as the third shared option. Optional: add a brief note documenting the new `_smart_title` helper.
- `docs/reference/API.md` — **verification note**: the section starting ~line 2550 is `## little_loops.logger`, not `cli.output`. `cli.output` has no dedicated API.md section today; only `OUTPUT_STYLING.md` documents it. `PRIORITY_COLOR` / `TYPE_COLOR` are likewise absent from API.md. **No API.md update required** unless a release-notes entry is desired.
- No user-facing flag changes in initial pass; visual improvement only.

#### Documentation to Update — additional files (added by `/ll:wire-issue`)

_Wiring pass added by `/ll:wire-issue`:_

The files above are issue-listed; the following prose files **also describe the current rendering and will go stale**, requiring updates in this implementation:

- `docs/reference/CLI.md:692-694` — `ll-loop list` section has a detailed paragraph describing the current layout verbatim: *"Loop names are column-aligned for scanability. Descriptions are truncated with `…` at terminal width. Labels appear as `[label]` badges between the description and `[built-in]` tag. Project loops use bold cyan names while built-in loops use dimmer (non-bold) cyan. The `[built-in]` tag is always positioned on the same line as the name."* Every claim becomes false under the new design (no `[built-in]` tag, no bold/dim distinction on names, new column ordering). Needs a prose rewrite.
- `docs/reference/CLI.md:999-1001` — short example block of `ll-loop list` / `--running` / `--json` invocations; human-readable examples need updating to reflect the new columnar layout (`--json` line is unchanged).
- `docs/guides/LOOPS_GUIDE.md:839` — `ll-loop list` one-liner: *"List loops (public tier only by default); `--all`, `--internal`, `--examples`, `--running`, `--builtin`, `--category <cat>`, `--label <tag>`"*. Semantics unchanged but the parenthetical "(public tier only by default)" is more accurately described now that the kind column surfaces the distinction.
- `docs/guides/LOOPS_GUIDE.md:961-991` (`Loop Discovery: category, labels, and visibility` section) — describes the public/internal/example footer as a "summary". The new closing summary line has different formatting (`<N> hidden (<counts>)` vs the current `Hidden: <counts> · all with --all`). Needs a prose refresh.
- `skills/review-loop/SKILL.md:42-66` (`Step 0: Resolve Loop Name`) — runs `ll-loop list` and parses out `<name>` and `<description first line>`. The skill doesn't anchor on specific markers (just reads text from `Bash` output), but the "first line" extraction pattern should be re-validated against the new format since `description` is now in a fixed-width right-side column rather than trailing inline text. JSON path (`--json`) is unchanged.
- `skills/simplify-loop/SKILL.md:53` — *"If no name was given, run `ll-loop list`"*. Same parsing concern as `review-loop`.

Note: `skills/audit-loop-run/SKILL.md:54-59`, `skills/debug-loop-run/SKILL.md:53`, `skills/cleanup-loops/SKILL.md:34`, and `scripts/little_loops/loops/loop-router.yaml:29` all use `ll-loop list --json` and are unaffected (JSON path unchanged).

### Configuration
- `config-schema.json:1184-1258` — `cli.colors` schema (`additionalProperties: false` requires explicit block). If categories are intended to be user-configurable, add a `categories:` block parallel to existing `colors.priority` / `colors.type`. **Out of scope for this issue; defer.**
- `scripts/little_loops/config/cli.py:33-54` — `CliColorsPriorityConfig` template for any future `CliColorsCategoriesConfig` dataclass. **Deferred.**
- `scripts/little_loops/config/cli.py:124-143` — `CliColorsConfig` nested dataclass site. **Deferred.**
- `scripts/little_loops/config/core.py:755-783` — BRConfig rendering block that materializes the color maps as JSON-encoded strings; a `categories`/`labels` block would need parallel addition. **Deferred.**

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (locator, analyzer, pattern-finder):_

**Verified anchors (analyzer):**
- `info.py:67-348` — full `cmd_list` body; per-category render at lines 269-348
- `info.py:33-64` — `_load_loop_meta` returns `{"description", "category", "labels", "visibility"}`
- `info.py:354-360` — `_truncate(text, max_len)` already exists; floor `max_len < 1`
- `info.py:269` — `_MAX_NAME_COL = 32` module-level cap
- `info.py:270` — `_MAX_LABELS = 2` cap on visible labels per loop
- `output.py:27-29` — `terminal_width(default=80)`
- `output.py:139-143` — `colorize(text, code)` (returns plain text if `_USE_COLOR` is False)
- `output.py:72-85` — `PRIORITY_COLOR`, `TYPE_COLOR` (insert new maps after this block)
- `output.py:88-131` — `configure_output` (extend `global` declaration and add `update()` calls)
- `list_cmd.py:174-302` — reference epic-grouped branch
- `list_cmd.py:243-250` — `_progress_badge` (exact analog to `_category_rollup`)
- `list_cmd.py:262` — `f"{TYPE_COLOR.get(parent_prefix, '0')};1"` header color pattern
- `list_cmd.py:279` — `Sub-EPICs ({n})` subhead in `"0;2"` (reset + dim)
- `list_cmd.py:300` — closing summary `Total: {displayed} active issues ...`
- `info.py:1012-1068` — `cmd_show` state overview table (column-math precedent in the same file)
- `info.py:1392-1414` — `cmd_fragments` table (column-math precedent, `desc_col_w = max(20, tw - name_col_w - 6)`)

**Critical detail — visibility field selection:**
- `lp["visibility"]` (one of `public` / `internal` / `example`) is loaded at `_load_loop_meta:54-56` but **never read** in `cmd_list`'s human-render path today — only the boolean `lp["builtin"]` drives the visibility signal at `info.py:311-312`.
- The proposed `_category_rollup` in section "Add `_category_rollup` helper" consumes only `lp.get("builtin", True)` and rolls `n_project = len(group) - n_builtin`. This loses the `internal` and `example` distinctions that the `hidden_counts` dict collects.
- **Correction**: `_category_rollup` should consume `lp.get("visibility", "public")` (mapping `public`/`internal`/`example` to `built-in`/`internal`/`example`) and emit a rollup like `M built-in · K project · J internal · N example` when any hidden tier is non-empty. The `hidden_counts` parameter feeds the non-public tier counts.

**Helper-collision check:**
- The proposed names `_smart_title`, `_category_rollup`, `_render_labels`, `_detect_subgroups` do not collide with any existing symbol in `info.py`, `output.py`, or `loop/layout.py`. All safe to introduce.
- No existing `ACRONYMS` set or `_smart_title` exists in the repo. Grep found 8+ naive `.title()` call sites that would benefit (e.g., `doc_scraper.py:270,288,746`; `issue_history/formatting.py:528`; `parallel/orchestrator.py:737`; `history_reader.py:1307`; `cli/issues/show.py:173`) — but only `info.py:290` is being fixed here.
- No existing subgroup/prefix-detection helper exists; `_detect_subgroups` is net-new code.

**Test patterns to model after:**
- `test_cli_loop_layout.py:19-83` — `_force_color` autouse fixture (`monkeypatch.setattr("little_loops.cli.output._USE_COLOR", True, raising=False)`). Required for any test asserting ANSI codes.
- `test_ll_loop_display.py:1718-1724` — `with _patch("little_loops.cli.loop._helpers.terminal_width", return_value=80):` for forcing narrow terminals. Same module path works for the new `info.py` tests (`_patch("little_loops.cli.loop.info.terminal_width", return_value=N)`).
- `test_issues_cli.py:1224-1235` — `patch("little_loops.cli.issues.list_cmd.terminal_width", return_value=40)` — parallel patch idiom.
- `test_cli_output.py:80-100` — `with patch.object(output_mod, "_USE_COLOR", ...)` for hermetic color tests.
- `test_ll_loop_commands.py:346-367` — baseline integration test pattern: `tmp_path`, `_runnable(...)` (wraps YAML with `initial:` so `is_runnable_loop()` passes), `argparse.Namespace(running=False, status=None, ...)`, `patch(get_builtin_loops_dir, return_value=tmp_path / "nonexistent")`, `capsys.readouterr().out`, assert substrings.

**Subgroup-detection algorithm hint:**
- The reference at `list_cmd.py:279` uses a simple split: leaves are issues whose type prefix ≠ "EPIC", sub-EPICs are those whose prefix == "EPIC". The loop equivalent has no fixed prefix taxonomy.
- A pragmatic algorithm: bucket `lp["name"]` by the first 2-3 chars of the part before `-`. Emit a subhead only when a bucket has ≥3 members AND its members dominate the category (e.g., 3 of 6 in `apo-*`). Below that threshold, leave flat (avoids noise in categories with no real sub-clustering).

## Implementation Steps

1. Add `CATEGORY_COLOR`, `LABEL_COLOR`, `ACRONYMS`, and `_smart_title` to `output.py`. Wire `configure_output` to merge optional `categories` from `CliConfig`.
2. Refactor `cmd_list` in `info.py`: compute column widths once per render, replace inner loop with column-driven layout.
3. Add `_category_rollup`, `_render_labels`, `_detect_subgroups` helpers in `info.py`.
4. Replace the single `colorize(..., "36;1")` header line with per-category color from `CATEGORY_COLOR`.
5. Add closing summary line.
6. Run `ll-loop list` interactively; verify each category is distinctively colored, columns align at TW=80/120/200, and acronyms render correctly.
7. Add tests in `scripts/tests/test_cli_loop_layout.py` covering all eight points at multiple terminal widths.
8. Run `python -m pytest scripts/tests/` and confirm exit 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis (caller-tracer, side-effect-surface, test-gap-finder agents) and must be included in the implementation alongside the original steps._

9. **Update breaking tests in `scripts/tests/test_ll_loop_commands.py`** — three tests will hard-fail under the new rendering and must be updated as part of this work (not deferred):
   - Lines 1339-1373 (`test_builtin_vs_project_name_color`) — rewrite or remove (per-category color replaces per-builtin cyan on the name column).
   - Lines 1375-1411 (`test_builtin_tag_absent_project_marker_present`) — rewrite to assert on the new `kind` column text (`built-in` / `project` / `internal` / `example`) instead of the removed trailing `●`.
   - Lines 689-720 (`test_grouped_display_by_category`) — change substring assertions from `"Apo"` to `"APO"` (and any other acronyms).
10. **Verify cosmetic-risk tests in `scripts/tests/test_ll_loop_commands.py`** — two tests have non-trivial layout interactions:
    - Lines 1199-1224 (`test_description_truncation_at_narrow_width` at TW=60) — confirm the new 4-column layout still fits a description at TW=60; if not, raise the test's TW floor to the minimum the layout supports.
    - Lines 1477-1507 (`test_summary_header`) — verify `out.index("2 loops")` order check still holds when the closing `Total:` summary is added at the bottom.
11. **Extend `scripts/tests/test_cli_output.py`** — add `CATEGORY_COLOR` / `LABEL_COLOR` / `ACRONYMS` assertions to `TestOrangeDefaultColors` (lines 175-197) and `test_configure_custom_category_colors` to `TestConfigureOutput` (lines 200-297), with `setup_method` / `teardown_method` reset logic for the new color maps (parallel to existing PRIORITY_COLOR / TYPE_COLOR resets at lines 203-221).
12. **Write new tests in `scripts/tests/test_cli_loop_layout.py` (or a sibling file)** — add unit tests for the four new helpers: `TestSmartTitle`, `TestCategoryRollup`, `TestRenderLabels`, `TestDetectSubgroups`.
13. **Write new integration tests in `scripts/tests/test_ll_loop_commands.py`** — mirror the `test_issues_cli.py:1103-1176` pattern for: `TestCmdListHeaderColor`, `TestCmdListRollupBadge`, `TestCmdListKindColumn`, `TestCmdListAcronymCasing`, `TestCmdListSubgroups`, `TestCmdListClosingSummary`.
14. **Add parameterized width tests** — `@pytest.mark.parametrize("tw", [80, 120, 200])` (first use of TW-parametrized tests in this codebase; model after `test_fsm_evaluators.py:56-69`). Assert: every line fits `tw`, description retains ≥20 chars at TW=80, all loop names and category headers present.
15. **Update `docs/reference/CLI.md:692-694, 999-1001`** — rewrite the `ll-loop list` description paragraph (current text describes per-builtin cyan and `[built-in]` tag, both eliminated) and refresh the example block to show the new columnar output.
16. **Update `docs/guides/LOOPS_GUIDE.md:839, 961-991`** — refresh the `ll-loop list` one-liner's "(public tier only by default)" parenthetical and rewrite the `Loop Discovery: category, labels, and visibility` section to describe the new closing `Total:` summary format instead of the current `Hidden: <counts>` footer.
17. **Re-validate parsing in `skills/review-loop/SKILL.md:42-66` and `skills/simplify-loop/SKILL.md:53`** — confirm the "first line of description" extraction pattern still works with the new fixed-column layout (the description is now in a right-side column rather than trailing inline text). Update the parsing logic if needed; the JSON path (`--json`) is unchanged and unaffected.
18. **Update `docs/reference/OUTPUT_STYLING.md:42-69, 327`** — add `CATEGORY_COLOR` and `LABEL_COLOR` to the "Default color codes" tables, and mention them as the third shared option in the "Adding New Styled Output" recipe at line 327.

## Impact

- **Priority**: P3 — UX polish, not user-blocking. The current output is functional; this is purely a fidelity upgrade.
- **Effort**: Small — confined to two files (`info.py`, `output.py`), all eight points are mechanical replacements of existing rendering code. Existing helpers (`colorize`, `terminal_width`, `_truncate`) cover most of the primitives needed.
- **Risk**: Low — purely a rendering change; no behavioral semantics, no CLI flag surface change, no data model change. Worst case is a visually weird output if column math is wrong, which is caught by the parameterized TW tests.
- **Breaking Change**: No — output is human-readable, not parsed. JSON output (`--json` flag) is unchanged.

## Acceptance Criteria

- `ll-loop list` headers use distinct colors per category (no two categories share a header color unless intentionally mapped the same).
- Each category header includes an inline rollup showing built-in vs project counts (and `internal` / `example` if any are hidden).
- Loop rows render with aligned `name | kind | labels | description` columns that hold alignment across the entire output at TW ≥ 80.
- Visibility (`built-in` / `project` / `internal` / `example`) is a first-class column, not a trailing dot.
- Labels get distinct colors by semantic class, with dim-green fallback for unknowns.
- Categories with ≥3 members sharing a name prefix get dim subgroup subheads with indented leaves.
- Output ends with a `Total:` summary line including category and visibility counts.
- Acronyms in category titles are uppercased correctly (`APO` not `Apo`, `HITL` not `Hitl`).
- No output line exceeds `tw` at any of TW=80, TW=120, TW=200.
- Descriptions retain ≥20 characters at TW=80.
- All eight changes are covered by tests in `scripts/tests/test_cli_loop_layout.py` (or sibling) using parameterized TW=80/120/200.
- `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **Out of scope**: items 9 (`--group-by category|kind|visibility|label` flag), 10 (`--summary` mode), and 11 (configurable `categories:` in `config-schema.json`) from the original analysis. These are CLI surface changes deserving their own issue; this one is rendering-only.
- **Out of scope**: changing the JSON output shape (`--json`).
- **Out of scope**: refactoring the loop loader or visibility filter logic — only the human renderer is touched.

## Related Key Documentation

- `docs/ARCHITECTURE.md` — CLI output conventions (TBD verify; if sections on CLI styling exist, link here)
- `docs/reference/API.md` — `scripts/little_loops/cli/output.py` reference

## Session Log
- `/ll:wire-issue` - 2026-07-08T02:30:52 - `6e52c632-ce3f-40ce-bcec-9309e5b4ac40.jsonl`
- `/ll:refine-issue` - 2026-07-08T02:04:29 - `24ce96b3-079e-47a2-9920-78567fe3eb7a.jsonl`

- `/ll:capture-issue` - 2026-07-08T01:52:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/20822008-f7d0-4e51-aa0a-634d036931b1.jsonl`

## Status

**Open** | Created: 2026-07-08 | Priority: P3