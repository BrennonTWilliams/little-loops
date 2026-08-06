---
id: BUG-3074
priority: P2
type: BUG
status: done
discovered_commit: 5d0a711f
discovered_branch: main
discovered_date: 2026-08-05
discovered_by: manual-investigation
completed_at: '2026-08-06T04:00:31Z'
labels:
- issues
- linter
- format-check
- cli
testable: true
size: Small
verify_verdict: VALID
confidence_score: 98
outcome_confidence: 90
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 24
---

# BUG-3074: `format-check` reports every subcommand of a metavar-using CLI as "no such subcommand"

## Summary

`ll-issues format-check` flags valid CLI references as stale:

```
stale_cli_flag: ll-learning-tests check (no such subcommand)
stale_cli_flag: ll-learning-tests prove (no such subcommand)
```

Both subcommands exist (`ll-learning-tests --help` lists `check`, `list`, `mark-stale`,
`orphans`, `prove`). The scraper only recognizes subcommands when argparse prints them as
a brace-delimited choices list; a parser that sets `metavar=` on `add_subparsers` prints
the metavar instead, and the scraper concludes the tool has no subcommands at all.

Discovered while filing BUG-3072/ENH-3073, whose accurate `ll-learning-tests check` /
`prove` references were both flagged.

## Current Behavior

`_scrape_tool` (`scripts/little_loops/issues/cli_surface.py:86`):

```python
subs_match = _SUBCOMMAND_CHOICES_RE.search(top_help)
if not subs_match:
    # No subparsers -- top-level flags only, keyed under "".
    return {"": set(_LONG_FLAG_RE.findall(top_help))}
```

with `_SUBCOMMAND_CHOICES_RE = re.compile(r"\{([a-z0-9_,-]+)\}")` (`:35`).

`ll-learning-tests --help` renders `positional arguments: COMMAND` — no braces — because
`cli/learning_tests.py:192` calls
`parser.add_subparsers(dest="command", metavar="COMMAND")`. The comment's assumption
("no subparsers") is false here: the tool has five.

The returned surface is `{"": {...flags}}`, so `cli_surface_accepts` (`:139`) hits
`if subcommand not in tool_surface: return False` — a **definitive False**, not the
`None` fail-open the function reserves for unscrapable tools. Every backticked
`ll-<tool> <subcommand>` claim against such a tool becomes a `stale_cli_flag` gap.

**Blast radius — four tools pass a subparser metavar:**

| Module | Line | metavar value |
|---|---|---|
| `scripts/little_loops/cli/learning_tests.py` | 192 | COMMAND |
| `scripts/little_loops/cli/queue.py` | 746 | COMMAND |
| `scripts/little_loops/cli/harness.py` | 131 | RUNNER |
| `scripts/little_loops/cli/action.py` | 394 | COMMAND |

Every documented subcommand of all four is currently unciteable in an issue without
tripping the gate.

**Related fragility (same root):** the regex takes the *first* brace group anywhere in the
help text. For a tool whose top-level help shows a flag choices list (e.g.
`--format {text,json}`) before the subcommand list, that flag's choices would be scraped
as the subcommand set. Not observed in-tree, but the same unanchored match permits it.

## Steps to Reproduce

1. Reference `` `ll-learning-tests check` `` in any issue's body.
2. `ll-issues format-check <ID>` → `stale_cli_flag: ll-learning-tests check (no such subcommand)`.
3. `ll-learning-tests check --help` → the subcommand exists and runs.

## Expected Behavior

Subcommands are recognized regardless of whether argparse renders a choices list or a
metavar. When the subcommand list cannot be determined, the scraper fails **open**
(returns `None`) rather than asserting every subcommand is absent.

## Root Cause

The scraper infers structure from `--help` *formatting* rather than from the parser, and
conflates two distinct outcomes:

- "this tool genuinely has no subparsers" → subcommand claims should be False
- "I could not find the subcommand list" → subcommand claims should be `None` (fail open)

Both currently return `{"": flags}`, which makes the second indistinguishable from the
first at the `cli_surface_accepts` boundary.

## Proposed Solution

Two independent fixes; both are small and the second is the safety net for any future
formatting variant:

1. **Parse the subcommand list from the positional-arguments block, not a brace group.**
   Under a `positional arguments:` header, argparse indents subcommand entries deeper than
   the metavar/choices line; collect those names. Keeps working for the brace form (the
   listed names still appear beneath it).
2. **Fail open when the list is undetermined.** Distinguish "no subparsers detected" from
   "no subcommand section found": only return `{"": flags}` when the help text has no
   positional-arguments block at all; otherwise return `None` so `cli_surface_accepts`
   yields `None` and the gate does not fire.

Anchoring `_SUBCOMMAND_CHOICES_RE` to the positional-arguments block also closes the
first-brace-group fragility noted above.

## Program Design

**Invariant.** For every installed `ll-*` console script and every subcommand its
`--help` documents, `cli_surface_accepts(index, tool, subcommand)` is not `False`.

### Types

```python
class CliSurfaceIndex:
```

### Signatures

```python
def _scrape_tool(tool: str) -> dict[str, set[str]] | None:
def _tool_surface(index: CliSurfaceIndex, tool: str) -> dict[str, set[str]] | None:
def cli_surface_accepts(index: CliSurfaceIndex, tool: str, subcommand: str, flag: str | None = None) -> bool | None:
def build_cli_surface_index() -> CliSurfaceIndex:
```

### Call Path

- `little_loops.issue_parser.check_format_gaps` (`issue_parser.py:756`) →
  `extract_cli_flag_claims` (`issues/cli_claims.py`) → `cli_surface_accepts`
  (`issues/cli_surface.py:139`) → `_tool_surface` (`:118`) → `_scrape_tool` (`:86`)
- Gap emitted at `issue_parser.py:764`; rendered by
  `little_loops.cli.issues.format_check` (`cli/issues/format_check.py:184`)

## Acceptance Criteria

- [x] `ll-issues format-check BUG-3072` reports no `stale_cli_flag` gap for
      `ll-learning-tests check`.
- [x] `ll-issues format-check ENH-3073` reports no `stale_cli_flag` gap for
      `ll-learning-tests prove`.
- [x] A test drives `_scrape_tool` against a metavar-using parser's help text and asserts
      the subcommand set is non-empty.
- [x] A test asserts `cli_surface_accepts` returns `None` (not `False`) when the
      subcommand list cannot be determined from help output.
- [x] A test covers all four metavar-using tools: every subcommand listed in their
      `--help` is accepted by the index.
- [x] `python -m pytest scripts/tests/` exits 0.

## Impact

The gate produces false positives against four in-tree CLIs, and it is a gate authors are
told to satisfy. Two of the three issues filed in this investigation trip it while being
factually correct, so the honest options are to accept a permanently-failing format-check
or to remove accurate CLI references from issue text — the second degrades the corpus.

False negatives are also possible via the same unanchored regex (a flag choices list
scraped as the subcommand set would accept nonexistent subcommands), though none is
observed in-tree.

## Integration Map

- `scripts/little_loops/issues/cli_surface.py` — scraper and accept predicate (the fix)
- `scripts/little_loops/issue_parser.py:756-773` — gap emission; no change expected
- `scripts/little_loops/cli/issues/format_check.py:184` — rendering; no change expected
- `scripts/little_loops/cli/learning_tests.py`, `scripts/little_loops/cli/queue.py`,
  `scripts/little_loops/cli/harness.py`, `scripts/little_loops/cli/action.py` — the
  affected parsers; not modified (the scraper adapts to them, not the reverse)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_surface.py` — no existing test constructs a literal `--help`-text
  fixture or exercises `_SUBCOMMAND_CHOICES_RE`/`_scrape_tool`'s text-parsing path directly;
  every current test builds a `CliSurfaceIndex` by hand or shells out to `ll-issues` (whose
  subparsers use `help=`, not `metavar=`, so brace form is untouched by this bug). Add: (1) a
  test driving `_scrape_tool` against a literal metavar-style `--help`-text fixture (model on
  `ll-learning-tests --help`) asserting a non-empty subcommand set; (2) a test asserting
  `cli_surface_accepts` returns `None` when the subcommand list can't be determined; (3) an
  integration test extending the shape of `test_build_cli_surface_index_against_real_ll_issues_link`
  (`:71-84`, `@pytest.mark.timeout(120)`) to all four affected tools (`ll-learning-tests`,
  `ll-queue`, `ll-harness`, `ll-action`), asserting every subcommand their real `--help` lists
  is accepted. Naming/docstring convention to follow: `test_<function>_<condition>` /
  `test_<function>_fails_open_for_<reason>`, one test per behavior, docstring only on the
  integration test (matches `test_symbol_claims.py`'s `symbol_exists_in_file` fail-open tests,
  the closest structural analog per this issue's own Codebase Research Findings).
- `scripts/tests/test_symbol_cli_claim_sweep.py` — real corpus-wide sweep using an actual
  `build_cli_surface_index()`; its only pinned assertion covers `stale_symbol_ref`/
  `mislocated_symbol_ref` counts, `stale_cli_flag` hits are explicitly unasserted (comment at
  `:66-71`). No test change required, but expect its printed `cli_hits` count to drop once this
  fix lands (this repo's own BUG-3072/ENH-3073 references are in that swept corpus).
- `scripts/tests/test_feat3048_symbol_cli_claim_gaps.py`, `scripts/tests/test_ll_issues_format_check.py`,
  `scripts/tests/test_cli_claims.py` — all construct `CliSurfaceIndex` fixtures by hand or assert
  on gap shape only; none exercise `_scrape_tool`'s regex path. No change required, confirmed
  unaffected by the fix.
- `cli_surface_accepts`'s docstring (`cli_surface.py:148-151`) currently names two `None`-producing
  causes ("tool was unscrapable or is not a registered `ll-*` console script"); the fix adds a
  third (help text present but subcommand list undetermined). Update the docstring alongside the
  code change for accuracy — not a separate file, but easy to miss since it's prose, not logic.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Conventions in Force

- Fail-open with `None` (vs. definitive `False`) for "undetermined" is an established,
  explicitly-named convention across the issues package, not novel to this fix.
  `cli_surface_accepts()` already documents `None` as "fail open... when *tool* was
  unscrapable" (`scripts/little_loops/issues/cli_surface.py:139-159`) and its module
  docstring names it as "the same fail-open convention as `little_loops.text_utils.RefIndex`"
  (`cli_surface.py:22-24`). `RefIndex`/`build_ref_index` (`scripts/little_loops/text_utils.py:150-165`)
  documents the same "fail-empty-never-raise" rule shared by other `git ls-files` call sites.
  `symbol_exists_in_file()` (`scripts/little_loops/issues/symbol_claims.py:303-322`) is the
  closest structural analog to this bug's fix: it returns `bool | None`, collapsing multiple
  distinct "couldn't determine" causes (unsupported extension, unreadable file) into one
  `None`, contrasted with a resolved `True`/`False`. Consumers agree on how to read it —
  `issue_parser.py:763` and `:768-770` in `check_format_gaps` act only on `is False`; `None`
  and `True` both fall through with no gap recorded. This confirms the issue's own proposed
  `_tool_surface`/`cli_surface_accepts` contract (return `None` when undetermined) matches
  the codebase's existing convention rather than introducing a new one.
- No existing shared parser for the `positional arguments:` help-text block exists to reuse.
  The only text-block extractors in the codebase are markdown-heading extractors keyed on
  `##` (`scripts/little_loops/dependency_mapper/analysis.py:104` `_extract_section()`,
  `scripts/little_loops/issue_history/doc_synthesis.py:129` `_extract_section_mentions()`),
  not argparse/`--help`-text extractors. `cli_surface.py` is the only module that
  subprocess-scrapes `--help` output (module docstring, `cli_surface.py:1-25`); any
  indentation-based block parsing for this fix is new code, not a reuse of an existing utility.

### Tests

- `scripts/tests/test_cli_surface.py` currently has no literal-`--help`-text fixtures. Unit
  tests construct a `CliSurfaceIndex` directly with pre-populated `surface`/`unscrapable`
  dicts (`test_cli_surface.py:16-21`) and assert on `cli_surface_accepts()`, bypassing the
  scraper/regex entirely. The only place real `--help` text is exercised is one
  `@pytest.mark.timeout(120)` integration test
  (`test_build_cli_surface_index_against_real_ll_issues_link`, `:71-84`) that shells out to
  the installed `ll-issues` CLI. Naming convention: one test function per behavior
  (`test_accepts_known_subcommand_and_flag`, `test_rejects_unknown_subcommand`,
  `test_fails_open_for_unscrapable_tool`), docstring only on the integration test.

## Related Issues

- BUG-3071 — Program Design gate diagnostic naming a heading its parser rejects
  (same family: linter diagnostics diverging from linter behavior)
- BUG-3072, ENH-3073 — the issues whose valid CLI references surfaced this

## Resolution

Fixed by anchoring subcommand discovery to the `positional arguments:` block
(`_POSITIONAL_ARGS_SECTION_RE`) and matching 4-space-indented entry lines
(`_SUBCOMMAND_ENTRY_RE`, capturing `aliases=[...]` parens too) instead of the
first brace group anywhere in `--help` text. `_scrape_tool` now returns:
`{"": flags}` only when no `positional arguments:` block exists at all (no
subparsers); `None` (fail open) when the block exists but no subcommand
entries are found beneath it (undetermined — e.g. a plain positional arg);
otherwise the real `{subcommand: flags}` surface. Verified `ll-issues
format-check` no longer flags `ll-learning-tests check`/`prove` on
BUG-3072/ENH-3073. Added unit tests for the metavar-fixture and
undetermined-block cases, plus an integration test sweeping all four
metavar-using tools (`ll-learning-tests`, `ll-queue`, `ll-harness`,
`ll-action`) against their real installed `--help`.

`python -m pytest scripts/tests/` has 48 pre-existing failures unrelated to
this change (session-start hook / adapter tests expecting no headless-mode
banner stdout — confirmed present on `main` before this fix via `git
stash`). `scripts/tests/test_cli_surface.py` (16/16) and the rest of the
suite pass; this fix introduces no new failures.

## Status

Open. Root cause confirmed and blast radius enumerated.


## Session Log
- `/ll:manage-issue` - 2026-08-06T03:59:23 - `21d382ff-bdc5-49b4-b2f0-c3c9027339cd.jsonl`
- `/ll:ready-issue` - 2026-08-06T03:47:31 - `f0e9ad86-a944-4acc-a368-a18a0cfd6c1c.jsonl`
- `/ll:confidence-check` - 2026-08-06T02:14:53 - `2c2ed4b0-a0cc-4b2b-9f94-ec37f4f418d9.jsonl`
- `/ll:verify-issues` - 2026-08-06T02:12:34 - `2ab091b6-a25c-43a8-8b74-306723885800.jsonl`
- `/ll:wire-issue` - 2026-08-06T02:10:37 - `93637b45-3d1c-4823-bb7b-5c884c8a1529.jsonl`
- `/ll:refine-issue` - 2026-08-06T02:04:27 - `5fb7befe-795b-4f3e-889d-7019bc554361.jsonl`
