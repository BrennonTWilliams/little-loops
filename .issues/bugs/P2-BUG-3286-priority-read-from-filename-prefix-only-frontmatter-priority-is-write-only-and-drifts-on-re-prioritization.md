---
id: BUG-3286
type: BUG
title: 'Priority read from filename prefix only: frontmatter priority: is write-only
  and drifts on re-prioritization'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T17:37:01Z'
labels:
- parser
- frontmatter
- planning-hub
- multi-repo
- mcp
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 15
---

# BUG-3286: Priority read from filename prefix only: frontmatter priority: is write-only and drifts on re-prioritization

## Summary

`IssueParser` resolves an issue's priority exclusively from the `P<n>-` filename prefix; the frontmatter `priority:` key is written on every created issue but never read by any code path, so prefix-less issue files silently flatten to P5 and the two sources drift with no reconciliation. Six modules each carry their own filename-priority regex with three different no-priority defaults, and one of those defaults (`normalize`'s `P3`) is written back to the filename — so on a prefix-less repo the declared priority is not merely ignored, it is destroyed.

## Current Behavior

Priority has two sources of truth in little-loops and only one of them is ever read.

**The write side.** `ll-issues create` writes `priority` into the frontmatter dict at `scripts/little_loops/cli/issues/create.py:311` and builds the filename with the same value at `create.py:454`. Both are in sync at creation.

**The read side.** `IssueParser.parse_file` sets priority from `self._parse_priority(filename)` at `scripts/little_loops/issue_parser.py:2883` and nothing else. Nine lines later it calls `parse_frontmatter(content)` at `:2892` and pulls a dozen fields off it — `discovered_by`, `epic`, `size`, `effort`, `impact`, `confidence_score`, `outcome_confidence`, `score_*`, `testable`, `decision_needed` — but never `priority`. `_parse_priority` at `issue_parser.py:3043-3056` does a bare `filename.startswith(f"{p}-")` scan over the priority list from `BRConfig.issue_priorities` (`scripts/little_loops/config/core.py:714`) and falls through to its last element (P5) when no prefix matches. `_ANCHORED_FILENAME_RE` at `issue_parser.py:58` likewise makes the priority group optional and yields `None`.

A grep of every `"priority"` read site across `scripts/little_loops/` confirms the frontmatter key is **write-only**: no module consumes it. In this repo's own `.issues/`, 2,083 files carry a frontmatter `priority:` that no code has ever read.

**Consequence 1 — prefix-less repos flatten to P5.** Reproduced in a throwaway project outside this repo (see Steps to Reproduce) whose sole issue file has no `P<n>-` prefix and a frontmatter `priority: P1`:

```
ENH-279-foo.md -> 'P5'  priority_int=5
```

**Consequence 2 — the two sources drift in this repo already.** `ll-issues prioritize --apply` renames the file and never opens it: `apply_priorities` at `scripts/little_loops/cli/issues/prioritize.py:99-148` computes `new_name`, calls `git_mv_with_fallback(path, new_path)` at `:142`, and returns. `ll-issues skip` (`skip.py:47`) does the same via a bare `re.sub` on the prefix. The frontmatter copy goes stale on every re-prioritization. Four live mismatches in `.issues/` today (filename prefix vs. frontmatter):

| File | Filename says | Frontmatter says |
|---|---|---|
| `P3-BUG-3109-loop-info-show-effective-scope.md` | P3 | P4 |
| `P2-ENH-2746-f3-compaction-shrink-ratio-outside-gate-band.md` | P2 | P3 |
| `P2-ENH-2988-expand-skill-ships-documentation-shaped-prompts-with-no-directive-to-act.md` | P2 | P3 |
| `P2-ENH-3047-confidence-check-consume-claim-and-parity-gaps.md` | P2 | P3 |

**Consequence 3 — six independent readers disagree on the same input.** `ll-issues show` does not use `IssueParser`; it carries its own filename regex at `scripts/little_loops/cli/issues/show.py:80-81` and yields `None` when there is no prefix, where the parser yields `P5`. It is not a pair — there are at least six independent filename-priority regexes across the package, producing three distinct answers for the same prefix-less file:

| Site | Prefix-less result | Notes |
|---|---|---|
| `scripts/little_loops/issue_parser.py:3043` `_parse_priority` | `P5` | the canonical reader |
| `scripts/little_loops/cli/issues/show.py:80` | `None` | card rendering |
| `scripts/little_loops/cli/issues/normalize.py:120` | `P3` | **and writes it to the filename** — see Consequence 4 |
| `scripts/little_loops/sync.py:320` | `None` | wrong/absent GitHub priority label on push |
| `scripts/little_loops/issue_history/parsing.py:58, 744` | `None` | historical analytics |
| `scripts/little_loops/session_store/writers.py:2433` | `None` | session analytics |

**Consequence 4 — `ll-issues normalize --auto` actively destroys the frontmatter priority.** `_priority_and_defaulted` (`scripts/little_loops/cli/issues/normalize.py:118-121`) returns `("P3", True)` when the filename carries no prefix, and that value is interpolated straight into `proposed_path` at `:292` and `:339`. On a prefix-less repo, normalizing `ENH-279-foo.md` (frontmatter `priority: P1`) renames it to `P3-ENH-279-foo.md`. Under this issue's own filename-wins precedence the stamped `P3` then becomes authoritative and the real `P1` is unrecoverable — so fixing only the read path would make this data loss *worse*, not better. `_priority_and_defaulted` must consult frontmatter before defaulting.

## Expected Behavior

- Priority resolution consults the frontmatter `priority:` key when the filename carries no `P<n>-` prefix, and defaults to P5 only when neither source specifies one.
- When a filename prefix and a frontmatter value disagree, the filename wins (see Decision Rules) — deliberately, and documented.
- The fallback lives in **one shared resolver**, not copied per call site; `ll-issues show`, `normalize`, and `sync` call it rather than carrying their own regex.
- `ll-issues normalize --auto` no longer stamps a `P3-` prefix onto a file whose frontmatter declares a different priority.
- `ll-issues prioritize --apply` and `ll-issues skip` update the frontmatter `priority:` alongside the rename, **including when the filename is already at the target priority** (the exact state of today's four mismatches), so the two sources stop diverging.
- A format-check rule reports filename↔frontmatter priority disagreement, and the four existing mismatches are reconciled.
- `ll-issues show` and `IssueParser` agree on the resolved priority for any given file.

## Motivation

Priority is the core planning signal. Every consumer downstream of it — `ll-issues next-issue`, `ll-sprint` sequencing, `backlog_snapshot.by_priority`, ll-mcp `issues_query` summary cards — silently produces meaningless output when every issue ties at P5. There is no crash, so the failure is invisible until someone notices the ordering is arbitrary — and per Consequence 4 there *is* data loss the moment `normalize --auto` runs on such a repo.

Two motivations, not one:

<!-- ll-private-ok: external planning hub demonstrates issue scope -->
1. **Multi-repo generalization.** Any repo using the frontmatter-priority convention without a filename prefix (the ll-product planning hub today, any future planning-hub or convention repo) gets a dead priority ordering.
2. **Internal correctness.** Even in this repo, where the prefix convention holds, little-loops maintains two priority sources, syncs them only at creation, and has no reconciliation or lint between them. Fixing only (1) formalizes a field that goes stale on every re-prioritization — it would make a known-unreliable source authoritative for one class of repo.

## Proposed Solution

Four coordinated changes. (1) alone closes the reported symptom; (2) is required so the fix does not become destructive; (3) and (4) prevent the fix from resting on a field that silently rots.

**1. One shared priority resolver with a frontmatter fallback.** Following the `resolve_issue_path()` precedent (BUG-3229 — duplicate readers consolidated into one shared resolver rather than reconciled after the fact; see Codebase Research Findings), add a **module-level** function in `issue_parser.py` rather than a private method, so every current reader can call it:

```python
def resolve_priority(
    filename: str,
    frontmatter: dict[str, Any],
    config: BRConfig,
    *,
    default: str | None = None,
) -> str | None:
    """Resolve an issue's priority: filename prefix wins, frontmatter is the fallback.

    Returns ``default`` when neither source specifies one, so each caller keeps
    its own no-priority sentinel (parser: ``issue_priorities[-1]``; show: ``None``;
    normalize: ``"P3"``).
    """
    for priority in config.issue_priorities:
        if filename.startswith(f"{priority}-"):
            return priority
    fm_priority = frontmatter.get("priority")
    if isinstance(fm_priority, str) and fm_priority.upper() in config.issue_priorities:
        return fm_priority.upper()
    return default
```

`IssueParser._parse_priority` becomes a thin wrapper passing `default=config.issue_priorities[-1]`. `parse_file` already reads content and calls `parse_frontmatter` — the resolution call moves below that, so no extra file read.

Call sites converted in this issue: `cli/issues/show.py:80-81` (`_parse_card_fields` already receives `config`, so no plumbing needed), `cli/issues/normalize.py:118-121`, and `sync.py:320`. **Out of scope, stated deliberately:** `issue_history/parsing.py:58,744` and `session_store/writers.py:2433` are historical/analytics readers over past filenames, not live planning signal; they keep their filename-only behavior and are noted here so the omission is a decision rather than an oversight.

**2. Stop `normalize` from stamping a wrong prefix.** `_priority_and_defaulted` calls `resolve_priority(..., default=None)` and only falls back to `"P3"` (with `defaulted=True`) when that returns `None`. Without this, step 1's filename-wins precedence promotes normalize's invented `P3` over the real frontmatter value — see Consequence 4.

**3. Keep frontmatter in sync on every prefix rewrite.** Two writers, not one:

- `apply_priorities` (`prioritize.py:99-148`) — use the established rename+write-as-one-operation idiom: `update_frontmatter(content, {"priority": priority})` then `git_mv_with_fallback(path, new_path, content=updated)`. **Critically, the early-return no-op branch at `:134-141` (`new_path == path`) must also reconcile frontmatter** — that branch is the exact state of all four existing mismatches, so leaving it untouched means step 5 cannot be performed with the tool itself.
- `ll-issues skip` (`skip.py:47-56`) rewrites the prefix with a bare `re.sub` and never touches frontmatter — the same defect, with the same already-at-target early return at `:49`. The write itself is cheap: `skip_issue` (`issue_lifecycle.py:1365-1397`) already reads `raw_content` and threads it through `git_mv_with_fallback(content=...)`, so it only needs `update_frontmatter(raw_content, {"priority": <derived from new_path.name>})` folded in ahead of `_build_skip_section`. The `path == new_path` early return in `skip.py:49-56` returns before `skip_issue` is ever called, so it needs its own reconciliation. Without both, `skip` keeps manufacturing exactly the drift step 4 reports.

**4. Drift lint + one-time reconciliation.** A `format-check` rule reporting filename↔frontmatter disagreement, plus a pass over the four existing mismatches to bring them into agreement.

## Integration Map

| File | Change |
|---|---|
| `scripts/little_loops/issue_parser.py` | New module-level `resolve_priority()`; `_parse_priority` becomes a wrapper; call site moves below `parse_frontmatter` |
| `scripts/little_loops/cli/issues/show.py` | `:80-81` regex → `resolve_priority(..., default=None)` so `show` agrees with the parser |
| `scripts/little_loops/cli/issues/normalize.py` | `_priority_and_defaulted` (`:118-121`) consults frontmatter before defaulting to `P3` — stops `--apply` stamping a wrong prefix |
| `scripts/little_loops/sync.py` | `:320` regex → `resolve_priority(..., default=None)` so GitHub labels match the resolved priority |
| `scripts/little_loops/cli/issues/prioritize.py` | `apply_priorities` threads updated content through `git_mv_with_fallback(content=...)`; **no-op branch (`:134-141`) reconciles frontmatter too** |
| `scripts/little_loops/cli/issues/skip.py` | `:47-56` — same frontmatter sync on prefix rewrite, including the already-at-target early return at `:49` |
| `scripts/little_loops/cli/issues/format_check*.py` | New drift gap kind |
| `docs/reference/ISSUE_TEMPLATE.md` | Document the frontmatter `priority:` field and the precedence rule |
| `scripts/tests/test_issue_parser*.py` | Fallback, precedence, and regression coverage |
| `.issues/` (4 files) | Reconcile existing mismatches |

**Explicitly out of scope** (decision, not oversight): `scripts/little_loops/issue_history/parsing.py:58,744` and `scripts/little_loops/session_store/writers.py:2433` keep their filename-only priority regexes — they read historical filenames for analytics, not live planning signal.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_prioritize.py` — `TestApplyPriorities` (lines ~160-256, 8 test methods) calls `apply_priorities` directly; none currently reads or asserts on the frontmatter `priority:` value, so the new `update_frontmatter` call in step 3 has zero coverage until this file is extended [Agent 1/3 finding]
- `scripts/tests/test_show.py` — `TestParseCardFields` (~lines 289-590+, 20+ test methods) exercises `_parse_card_fields` directly, the exact function step 2 modifies; no existing case covers a prefix-less filename with a frontmatter `priority:` present [Agent 1/3 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_prioritize.py::TestApplyPriorities` — existing tests to update: none assert frontmatter content today (`test_already_at_target_priority_is_noop`, `test_apply_is_idempotent`, ~lines 188-209) — add assertions that `priority:` in frontmatter matches the renamed prefix after `apply_priorities` runs [Agent 2/3 finding]
- `scripts/tests/test_show.py::TestParseCardFields` — new test: a prefix-less filename (e.g. `ENH-5200-thing.md`) with frontmatter `priority: P1`, asserting `fields["priority"] == "P1"` instead of today's `None` [Agent 1/3 finding]
- `scripts/tests/test_ll_issues_format_check.py` (~line 349, the `--format json` baseline-shape dict alongside the existing `"malformed_dep_id": []` entry) — **will hard-fail** the moment the new drift gap kind is added to `FormatGaps` unless a matching `"<gap_key>": []` entry (with a `# BUG-3286: ...` comment, following the `malformed_dep_id`/BUG-3059 precedent) is inserted here [Agent 3 finding]
- `scripts/tests/test_issue_parser.py` — new `TestCheckFormatGapsPriorityDrift`-style class mirroring `TestCheckFormatGapsMalformedDepId` (:4369-4458), plus a paired `TestCorpusHasNoPriorityDrift`-style class mirroring `TestCorpusHasNoMalformedDepIds` (:4461-4477) asserting the four reconciled `.issues/` files (step 5) and the rest of the corpus report zero drift [Agent 3 finding]
- `scripts/tests/test_issue_parser.py::TestIssueParser::test_parse_file_without_priority_prefix` (:423-441) — re-verify under the new fallback; this file has no frontmatter `priority:` so its `P3`/last-priority assertion should hold unchanged, but it's the existing regression anchor for the code path being modified [Agent 3 finding]
- `scripts/tests/test_issue_parser_fuzz.py` — optional: the `"no_priority"` filename-structure generator (~lines 93-107) and the frontmatter `priority:` draw (~line 69) currently live in separate generators; composing them into one property test would cover the fallback path under fuzzing [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:2065` — the `ll-issues format-check` docstring paragraph hand-enumerates all `FormatGaps` gap-kind names and states "reports gaps in twenty-five classes"; needs the new drift gap-kind name added to the list and the count incremented [Agent 2 finding]
- `docs/reference/CLI.md:2254` — the `--format json` example output is a literal dict of every gap key; needs the new gap-kind key inserted or the example understates the real payload [Agent 2 finding]
- `docs/reference/API.md:895-920` — an independently-maintained copy of the same "twenty-five gap classes" count and enumerated name list in `check_format_gaps`'s docstring reference, plus one prose bullet per gap kind; needs a matching count/list update and a new bullet following the `malformed_dep_id`/`stale_symbol_ref` precedent of naming the originating issue ID inline [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- **Prefer-source-A-fall-back-to-source-B resolution is an established shape in this module**, with the precedence documented inline rather than left implicit — evidence: `resolve_issue_path()`'s nested `_frontmatter_identity()` helper (`scripts/little_loops/issue_parser.py:213-234`, used at :236-249), where a missing/unparseable frontmatter value is treated as "no opinion" and falls through to the other source unchanged. `_gate_program_design()` (`scripts/little_loops/issue_parser.py:356-372`) is a smaller instance of the same "value present unless overridden" shape.
- **Duplicate independent readers of the same field get consolidated into one shared resolver, not reconciled after the fact** — evidence: `resolve_issue_path()`'s docstring (`scripts/little_loops/issue_parser.py:92-98`) states it is "the single shared ID->path resolver for filename-based lookups (BUG-3229)" specifically because `cli/issues/show.py` and `sprint.py:_find_issue_path` had drifted by computing the same thing independently. This is the same shape BUG-3286 describes between `IssueParser._parse_priority` and `show.py`'s own filename regex (`scripts/little_loops/cli/issues/show.py:80-81`).
- **Filename-vs-frontmatter drift has two prior resolutions in this codebase, not one** — (a) pick a winner via documented precedence (BUG-2806, `_frontmatter_identity`, frontmatter wins when present and non-contradictory, filename otherwise), or (b) leave both sources standing and report disagreement as a `FormatGaps` entry without picking a winner (BUG-2769's `malformed_id` gap, `scripts/little_loops/issue_parser.py:941-948`, which computes a canonical value from the filename and reports `f"{key}: {raw} (expected {canonical})"` when the frontmatter value disagrees). Both are live conventions; this issue's own Decision Rules already commits to option (a) for resolution and a `FormatGaps`-shaped rule for drift reporting, matching (b)'s output shape.
- **`update_frontmatter` + rewrite has three established call idioms**, distinguished by whether a rename is also happening:
  - Rename + frontmatter write as one filesystem operation: `content` is mutated via `update_frontmatter` before the rename, then threaded into `git_mv_with_fallback`'s optional `content=` parameter — evidence: `apply_normalize()` (`scripts/little_loops/cli/issues/normalize.py:432-464`), and `git_mv_with_fallback`'s own docstring (`scripts/little_loops/issue_lifecycle.py:1314-1332`) which documents "the write happens before the git-mv-failure fallback rename, or after a successful `git mv`." `apply_priorities()` (`scripts/little_loops/cli/issues/prioritize.py:100-148`) currently calls `git_mv_with_fallback(path, new_path)` with no `content=` argument and never touches frontmatter.
  - No rename, `update_frontmatter` + `atomic_write` as two calls: evidence — `scripts/little_loops/cli/issues/normalize.py:403-428` (`_rewrite_referencing_edges`), `scripts/little_loops/cli/issues/link.py:205,220`.
  - No rename, `update_frontmatter` + `Path.write_text` inside try/except with a warning log on failure: evidence — `scripts/little_loops/issue_lifecycle.py:594-605`.
  - The `update_frontmatter(content, updates)` immediately followed by a write is otherwise the standard two-line idiom across this codebase — evidence: `scripts/little_loops/cli/issues/set_status.py:137`, `scripts/little_loops/cli/issues/set_scores.py:54`, `scripts/little_loops/cli/issues/size.py:154`, `scripts/little_loops/cli/sprint/run.py:445`.
- **Adding a new `FormatGaps` gap kind touches nine fixed locations**, all present for every existing gap class (e.g. `malformed_dep_id`): the dataclass field (`scripts/little_loops/issue_parser.py:490-522`), the `has_gaps` OR-in (`:524-553`), the advisory-vs-blocking classification (`:483-487, 555-565`), `to_dict()` (`:567-595`), a documented paragraph in `check_format_gaps()`'s "Gap classes:" docstring block (`:654-824`) citing the originating issue ID, the inline detection loop itself, the `--help` text and docstring enumeration in `scripts/little_loops/cli/issues/format_check.py` (lines 63-70, 479-485) plus a matching print loop in `_print_gaps`, a dedicated test class following the `TestCheckFormatGapsMalformedDepId` template (`scripts/tests/test_issue_parser.py:4369-4458`) with a paired corpus self-check test (`TestCorpusHasNoMalformedDepIds`, `:4461-4477`) asserting the new gap kind fires zero times against this repo's own `.issues/` tree, and a baseline-shape entry in `scripts/tests/test_ll_issues_format_check.py` (~lines 339-360).

## Program Design

### Types

No new types. `IssueInfo.priority` (`str`) and `IssueInfo.priority_int` (`int`) keep their current shapes and semantics.

### Signatures

- `resolve_priority(filename: str, frontmatter: dict[str, Any], config: BRConfig, *, default: str | None = None) -> str | None` — **new module-level function** in `issue_parser.py` (not a private method — three CLI modules outside the parser call it). Filename prefix first, frontmatter `priority:` second, caller-supplied `default` last.
- `IssueParser._parse_priority(self, filename: str, frontmatter: dict[str, Any]) -> str` — retained as a thin wrapper over `resolve_priority` with `default=self.config.issue_priorities[-1]`; gains the `frontmatter` parameter.
- `_priority_and_defaulted(filename: str, frontmatter: dict[str, Any]) -> tuple[str, bool]` (`normalize.py`) — gains the `frontmatter` parameter; `defaulted` is `True` only when *neither* source specifies a priority.
- `apply_priorities(config: BRConfig, mapping: dict[str, str]) -> list[RenameResult]` — unchanged signature; body reads content, updates frontmatter, and threads it through the rename.
- `update_frontmatter(content: str, updates: dict[str, Any]) -> str` — existing helper (`scripts/little_loops/frontmatter.py:439`). Note it is a **pure content transform that returns new content**; it does not take a path and does not write. The caller performs the write.
- `git_mv_with_fallback(original_path: Path, new_path: Path, content: str | None = None) -> None` — existing helper (`scripts/little_loops/issue_lifecycle.py:1314`); its optional `content=` parameter is what makes rename+frontmatter-write a single filesystem operation.
- `skip_issue(original_path, new_path, reason=None, event_bus=None) -> None` — existing (`issue_lifecycle.py:1365`); unchanged signature. Already reads `raw_content` and passes `content=` to `git_mv_with_fallback` at `:1397`, so the frontmatter sync folds into the existing content assignment at `:1395`.

### Call Path

- `IssueParser.parse_file` → `_read_content` → `parse_frontmatter` → `IssueParser._parse_priority` → `resolve_priority` → `IssueInfo`
- `_parse_card_fields` (`show.py`) → `parse_frontmatter` → `resolve_priority`
- `_priority_and_defaulted` (`normalize.py`) → `resolve_priority`
- `apply_priorities` → `update_frontmatter(content, ...)` → `git_mv_with_fallback(path, new_path, content=updated)` — one operation, not a write after the rename
- `apply_priorities` (no-op branch) → `update_frontmatter(content, ...)` → `atomic_write` — no rename, so the two-call idiom applies
- `find_issues` → `IssueParser.parse_file` (unchanged; picks up the corrected priority transitively)

### Decision Rules

**Precedence rule.** When both a filename `P<n>-` prefix and a frontmatter `priority:` are present and they disagree, the **filename prefix wins**.

- Inputs: the issue filename and the parsed frontmatter dict.
- Rationale, evidence-backed rather than convention-backed: `apply_priorities` writes the filename and leaves the frontmatter untouched, so for all four existing mismatches in this repo the filename is by construction the fresher signal. Filename-wins also preserves byte-identical behavior for every currently-prefixed repo.
- Frontmatter is consulted only when the filename anchor yields no priority.
- A frontmatter value outside `config.issue_priorities` (malformed, e.g. `priority: high`) is ignored, falling through to the caller's `default` rather than raising.
- Escape hatch: none needed — the rule is total and has a defined result for every input.

**Default-sentinel rule.** `resolve_priority` returns the caller's `default` rather than hardcoding one, because the three live callers legitimately disagree about the no-priority-anywhere case and changing any of them is out of scope here: `IssueParser` returns `issue_priorities[-1]` (P5), `show.py` returns `None` (renders as an empty card field), `normalize.py` returns `"P3"` **with `defaulted=True`**, which drives a user-visible "priority was defaulted" warning. Unifying those sentinels is a separate change; this issue only stops them disagreeing when a source of truth *does* exist.

**Prefix-rewrite sync rule.** Any code path that writes an issue's `P<n>-` filename prefix must write the matching frontmatter `priority:` in the same operation. This binds `apply_priorities`, `skip_issue`, and `normalize`'s rename path.

- **The already-at-target early return is in scope, not excluded.** `apply_priorities:134-141` and `skip.py:49-56` both `return`/`continue` when `new_path == path`. That branch is precisely the state of all four existing mismatches (filename correct, frontmatter stale), so treating it as a pure no-op would leave the tool unable to repair the drift it is being taught to prevent — and would make Implementation Step 6 impossible to perform with `ll-issues prioritize` itself.
- Consequence for existing tests: `test_already_at_target_priority_is_noop` and `test_apply_is_idempotent` (`test_ll_issues_prioritize.py`, ~lines 188-209) are no longer asserting a *filesystem* no-op. They must be restated as "no rename occurs, frontmatter is reconciled" — idempotence still holds at the content level (a second run is a true no-op), which is what those tests should assert.
- `RenameResult` reporting is unchanged; a frontmatter-only reconciliation is still reported as a no-op rename with `old_priority == priority`.

**Drift rule (new format-check gap kind).** Report a gap when a file has both a filename prefix and a frontmatter `priority:` whose values differ. Scoped to the file's own name and frontmatter — no cross-file comparison. Dismissal follows the existing format-check dismissal mechanism; no new opt-out key.

## Implementation Steps

1. Add the module-level `resolve_priority()` with the frontmatter fallback and caller-supplied `default`; reduce `IssueParser._parse_priority` to a wrapper and move the call in `parse_file` below `parse_frontmatter`. Cover with tests for fallback, prefix-wins precedence, malformed frontmatter, and the no-priority-anywhere default.
2. Convert `show.py:80-81` to `resolve_priority(..., default=None)` so `ll-issues show` and `IssueParser` agree; add a test asserting agreement on a prefix-less file.
3. Convert `normalize.py:_priority_and_defaulted` to consult frontmatter before defaulting to `P3`, preserving `defaulted=True` only when neither source specifies one. Test that `normalize --auto` on a prefix-less file with `priority: P1` proposes `P1-…`, not `P3-…`. **This must land with or before step 1** — step 1's filename-wins precedence makes normalize's invented prefix authoritative, so shipping 1 without 3 converts a read bug into data loss.
4. Convert `sync.py:320` to the shared resolver so pushed GitHub priority labels match the resolved priority.
5. Extend `apply_priorities` (rename branch **and** the `new_path == path` branch) and `skip_issue`/`skip.py` to keep frontmatter in sync; restate the two affected no-op/idempotence tests per the Decision Rules. Test that a re-prioritized and a skipped file both end with matching filename and frontmatter.
6. Add the format-check drift rule with tests for the matching and mismatching cases (nine touch points — see Codebase Research Findings).
7. Reconcile the four existing `.issues/` mismatches — with step 5 landed, `ll-issues prioritize --apply` can do this itself; confirm the new rule reports clean afterwards.
8. Update `docs/reference/ISSUE_TEMPLATE.md` to document the field and precedence.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Extend `scripts/tests/test_ll_issues_prioritize.py::TestApplyPriorities` — assert the frontmatter `priority:` key matches the renamed filename prefix after `apply_priorities` runs, **and** restate `test_already_at_target_priority_is_noop` / `test_apply_is_idempotent` (~lines 188-209) as "no rename, frontmatter reconciled" per the Decision Rules
- Add coverage for `ll-issues skip` in `scripts/tests/` — a skipped issue's frontmatter `priority:` must match its new prefix, including the already-at-target path
- Add a `normalize` test — prefix-less file with frontmatter `priority: P1` proposes `P1-…`, not `P3-…`, and reports `defaulted=False`
- Add a `sync.py` test — priority label derived for a prefix-less file uses the frontmatter value
- Add a `TestParseCardFields` case in `scripts/tests/test_show.py` — prefix-less filename with frontmatter `priority:` present, asserting the fallback value is returned
- Add the new gap-kind's `"<gap_key>": []` baseline entry to `scripts/tests/test_ll_issues_format_check.py` (~line 349) — the existing shape-assertion test fails without it
- Add `TestCheckFormatGaps<PriorityDrift>` and `TestCorpusHasNo<PriorityDrift>` classes in `scripts/tests/test_issue_parser.py`, mirroring `TestCheckFormatGapsMalformedDepId`/`TestCorpusHasNoMalformedDepIds` (:4369-4478)
- Update `docs/reference/CLI.md` (:2065, :2254) and `docs/reference/API.md` (:895-920) — increment the gap-class count, add the new gap-kind name to both enumerated lists and the JSON example, and add a documented bullet in API.md

## Impact

<!-- ll-private-ok: external planning hub impact assessment -->
**Priority: P2.** Silent corruption of the core planning signal, no crash and no data loss. It fully disables priority ordering for any prefix-less repo (ll-product: 125 open issues all reading P5) and leaves a latent two-sources-of-truth defect in every repo including this one. Not P1 — the prefix convention means little-loops' own ordering is currently correct in practice, and the four drifts are cosmetic today.

**Effort: 3 (medium-high).** Revised up from 2 after review: nine source files plus docs and tests, not six. The shared-resolver conversion is mechanical, but three of the added sites (`normalize`, `skip`, the two already-at-target branches) are *write* paths rather than read paths, and two existing tests change meaning rather than just gaining assertions. The format-check rule and its nine touch points remain the single largest chunk.

**Risk: medium.** The precedence choice makes the read change byte-identical for every prefixed file, so existing repos see no read behavior change. Three real risks:

1. **Ordering hazard.** Landing the parser fallback (step 1) without the `normalize` fix (step 3) converts a read bug into irreversible data loss on prefix-less repos, because filename-wins promotes normalize's invented `P3`. These must land together.
2. **New write surface.** `apply_priorities` currently never opens files; adding a content write makes it heavier and more failure-prone. Use the `git_mv_with_fallback(content=...)` single-operation idiom rather than a post-rename write, and check staging behavior.
3. **Test semantics change.** `test_already_at_target_priority_is_noop` / `test_apply_is_idempotent` stop being filesystem no-ops. Restating them is intended, not a regression — but it removes the guard that would have caught an accidental rename, so the replacement must still assert no rename occurred.

<!-- ll-private-ok: external planning hub scope documentation -->
**Verification claim.** The reproduction above and the mismatch scan were both executed against this checkout at capture time; the P5 result, the 2,083 write-only frontmatter fields, and the four named mismatches are observed, not inferred. The ll-product figures cited in the originating report (`{P5: 125}`, the `P3:118, P2:109, P4:38, P1:20, P0:13, P5:4` frontmatter spread, the ll-mcp summary cards) are from an external repo and were **not** independently verified here; they match the predicted symptom of the confirmed mechanism.

## Steps to Reproduce

```bash
mkdir -p /tmp/pritest/.issues/enhancements && cd /tmp/pritest
printf -- '---\nid: ENH-279\npriority: P1\nstatus: open\n---\n\n# Test\n' \
  > .issues/enhancements/ENH-279-foo.md
python -c "
from pathlib import Path
from little_loops.issue_parser import IssueParser
from little_loops.config import BRConfig
p = IssueParser(BRConfig(Path('.')))
i = p.parse_file(Path('.issues/enhancements/ENH-279-foo.md'))
print(i.priority, i.priority_int)
"
# actual:   P5 5
# expected: P1 1
```

For the drift half, from this repo's root:

```bash
python3 - <<'EOF'
import re, pathlib
for p in pathlib.Path('.issues').rglob('*.md'):
    m = re.search(r'^priority:\s*(P[0-5])', p.read_text(errors='ignore'), re.M)
    fm = re.match(r'^(P[0-5])-', p.name)
    if m and fm and fm.group(1) != m.group(1):
        print('MISMATCH', p.name, '-> frontmatter', m.group(1))
EOF
```

## Root Cause

`IssueParser.parse_file` (`scripts/little_loops/issue_parser.py`) treats the filename as the sole priority source. `_parse_priority` has no access to the file's frontmatter — it takes a `filename: str`, not a path or parsed content — so the fallback to `issue_priorities[-1]` fires for any file whose name lacks the prefix, regardless of what the frontmatter says.

The drift half has a separate proximate cause: `apply_priorities` in `scripts/little_loops/cli/issues/prioritize.py` performs a pure path operation (`git_mv_with_fallback`) and never reads or rewrites file content, so the frontmatter copy written at creation is never updated on re-prioritization. `ll-issues skip` (`skip.py:47`) has the identical shape.

Both share a root: priority is stored twice with no designated authority and no invariant enforcing agreement. A third consequence follows from the same root — because no reader is canonical, six modules each rolled their own filename regex with three different no-priority defaults (`P5`, `None`, `P3`), and one of those defaults is written back to disk.

## Location

_Line numbers re-anchored 2026-08-21 against the current working tree; prefer the named symbols, which are stable._

- `scripts/little_loops/issue_parser.py:58` — `_ANCHORED_FILENAME_RE`, optional priority group
- `scripts/little_loops/issue_parser.py:2883` — `parse_file` call site (`priority = self._parse_priority(filename)`), sole priority source; sits **above** the `parse_frontmatter` call at `:2892`
- `scripts/little_loops/issue_parser.py:3043-3056` — `_parse_priority` and the `issue_priorities[-1]` (P5) fallback
- `scripts/little_loops/cli/issues/create.py:311` — writes frontmatter `priority` (write-only today)
- `scripts/little_loops/cli/issues/prioritize.py:99-148` — `apply_priorities`; `:134-141` is the already-at-target early return, `:142` the rename without frontmatter
- `scripts/little_loops/cli/issues/show.py:80-81` — independent filename regex, yields `None` not P5
- `scripts/little_loops/cli/issues/normalize.py:118-121` — `_priority_and_defaulted`, defaults to `P3`; consumed at `:292` and `:339` to build the rename target
- `scripts/little_loops/cli/issues/skip.py:47-56` — prefix rewrite via bare `re.sub`, plus its own already-at-target early return at `:49`
- `scripts/little_loops/issue_lifecycle.py:1393-1397` — `skip_issue` reads content and threads it through `git_mv_with_fallback(content=...)`; the natural insertion point for the skip-path sync
- `scripts/little_loops/sync.py:320` — filename-only priority regex feeding GitHub label push
- `scripts/little_loops/frontmatter.py:439` — `update_frontmatter(content, updates) -> str`, a pure content transform (does **not** take a path or write)

## Related Key Documentation

- `docs/reference/ISSUE_TEMPLATE.md` — issue frontmatter reference; does not currently document `priority:`
- `.claude/CLAUDE.md` § Issue File Format — filename convention `P[0-5]-[TYPE]-[NNN]-description.md`

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-21T19:01:50 - `45eaa854-fea1-43c3-8981-1d72e357bd5f.jsonl`
- `/ll:confidence-check` - 2026-08-21T18:58:41 - `eff768cf-ea73-4732-9715-12285ca3175d.jsonl`
- `/ll:wire-issue` - 2026-08-21T18:29:26 - `8dfb1ac4-9c46-4e39-8612-aa72663c1c57.jsonl`
- `/ll:refine-issue` - 2026-08-21T17:42:10 - `c401e0f5-28d0-4d01-95f3-309f5a7b95c5.jsonl`
- `/ll:capture-issue` - 2026-08-21T17:37:13 - `0c91fc4e-e09c-41b9-a77b-d05fa80fd5b1.jsonl`
