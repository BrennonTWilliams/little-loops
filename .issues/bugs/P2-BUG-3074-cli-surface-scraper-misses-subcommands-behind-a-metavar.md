---
id: BUG-3074
priority: P2
type: BUG
status: open
discovered_commit: 5d0a711f
discovered_branch: main
discovered_date: 2026-08-05
discovered_by: manual-investigation
labels:
- issues
- linter
- format-check
- cli
testable: true
size: Small
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
`cli/learning_tests.py:180` calls
`parser.add_subparsers(dest="command", metavar="COMMAND")`. The comment's assumption
("no subparsers") is false here: the tool has five.

The returned surface is `{"": {...flags}}`, so `cli_surface_accepts` (`:139`) hits
`if subcommand not in tool_surface: return False` — a **definitive False**, not the
`None` fail-open the function reserves for unscrapable tools. Every backticked
`ll-<tool> <subcommand>` claim against such a tool becomes a `stale_cli_flag` gap.

**Blast radius — four tools pass a subparser metavar:**

| Module | Line | metavar value |
|---|---|---|
| `scripts/little_loops/cli/learning_tests.py` | 180 | COMMAND |
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

- [ ] `ll-issues format-check BUG-3072` reports no `stale_cli_flag` gap for
      `ll-learning-tests check`.
- [ ] `ll-issues format-check ENH-3073` reports no `stale_cli_flag` gap for
      `ll-learning-tests prove`.
- [ ] A test drives `_scrape_tool` against a metavar-using parser's help text and asserts
      the subcommand set is non-empty.
- [ ] A test asserts `cli_surface_accepts` returns `None` (not `False`) when the
      subcommand list cannot be determined from help output.
- [ ] A test covers all four metavar-using tools: every subcommand listed in their
      `--help` is accepted by the index.
- [ ] `python -m pytest scripts/tests/` exits 0.

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

## Related Issues

- BUG-3071 — Program Design gate diagnostic naming a heading its parser rejects
  (same family: linter diagnostics diverging from linter behavior)
- BUG-3072, ENH-3073 — the issues whose valid CLI references surfaced this

## Status

Open. Root cause confirmed and blast radius enumerated.
