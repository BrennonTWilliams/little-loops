---
id: ENH-2970
title: Verify CLAUDE.md's documented CLI surface resolves to real commands
type: ENH
priority: P2
status: open
captured_at: '2026-08-01T16:02:14Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- BUG-2963
- ENH-2944
- ENH-2946
testable: true
labels:
- cli
- docs
- gates
---

# ENH-2970: Verify CLAUDE.md's documented CLI surface resolves to real commands

## Summary

`.claude/CLAUDE.md`'s § CLI Tools section documents subcommands and flags that
do not exist. Nothing checks it, so the drift is only ever caught by a human
reading the file against `--help` output. Add an `ll-verify-*` CLI, gated by
the local pytest suite, that asserts every documented command resolves — and,
in the other direction, that every `pyproject.toml` entry point is documented.

## Current Behavior

CLAUDE.md is loaded into every session's context, and as of 2026-08-01 it
described three commands that were never implemented or had been removed:

| Documented claim | Reality |
|---|---|
| `ll-issues normalize` (`--check`/`--auto`/`--json`) | Absent — wiring stripped in `3e76f972` because its modules were uncommitted (ENH-2944) |
| `ll-issues set-flags` (`--from-notes <file\|->`, `--dry-run`, `--depth-moderate-or-deep`, `--json`) | Never implemented (ENH-2946) |
| `ll-issues format-check --next` | Never implemented (ENH-2946); real flags are `--all`/`--format`/`--fix`/`--apply` |

Both introductions came from commits for *unrelated* issues: `46969c7c`'s
subject and body are entirely about ENH-2949 (`ll-loop audit --json`), and
`3e76f972` removed already-documented wiring without touching its docs. The
failure is bidirectional and neither direction is caught.

The reverse gap also exists today: four entry points in
`scripts/pyproject.toml` have no CLAUDE.md entry — `ll-help`,
`ll-verify-host-map`, `ll-adapt-agents-for-codex`,
`ll-adapt-skills-for-codex`. `ll-verify-host-map` is the notable one, since it
sits alongside the fully-documented `ll-verify-*` family.

## Expected Behavior

A verifier that fails the local test suite when CLAUDE.md's CLI Tools section
and the actual CLI surface disagree:

- Every `ll-*` tool named in CLAUDE.md exists as an entry point.
- Every subcommand attributed to a tool appears in that tool's argparse
  choices.
- Every flag attributed to a subcommand appears in its `--help`.
- Every entry point in `scripts/pyproject.toml` has a CLAUDE.md entry
  (WARN-or-ERROR — see Open Question).

## Motivation

This is not cosmetic doc rot. CLAUDE.md is the always-loaded project context,
so a phantom command is an instruction to every agent in every session to call
something that will fail with an argparse rejection. The cost is a wasted
tool call plus whatever recovery the agent improvises.

It has already happened twice in recent history, and both times the
introducing commit was for a different issue — meaning per-issue review does
not catch it. This is the same structural failure BUG-2963 describes
(scoped-completion commits landing work attributed to the wrong issue), seen
from the documentation side.

Verifying by hand is mechanical and takes minutes; the whole point is that
nobody does it on a schedule.

## Proposed Solution

Add `ll-verify-cli-docs`, modeled on the existing `ll-verify-*` family
(`ll-verify-cli-allowlist` is the closest structural precedent — it already
reconciles `pyproject.toml` entry points against another artifact and exits 1
on drift).

Sketch:

1. Parse CLAUDE.md's CLI Tools section for `- \`ll-<tool>\`` bullets.
2. For each, extract candidate subcommand tokens (the comma-separated
   parenthetical list) and flag tokens (backticked `--foo`).
3. Shell out to `<tool> --help`, parse argparse's `{a,b,c}` choices block, and
   assert membership. For flags, assert the literal appears in the relevant
   `--help` text.
4. Report every mismatch, exit 1 on any.

Parsing prose is the awkward part — see Open Question. A deliberately
conservative extractor that only recognizes the established formatting
conventions, and reports what it *skipped*, is preferable to a clever one that
silently misses claims.

Reference implementation: the ad-hoc sweep run during this session correctly
identified all three false claims and produced no false positives across the
other 44 documented tools, using exactly the argparse-choices approach above.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/` — new `verify_cli_docs.py` module.
- `scripts/pyproject.toml` — register the `ll-verify-cli-docs` entry point.
- `scripts/tests/test_verify_cli_docs.py` — the pytest gate (per project
  policy: no hosted CI; the suite *is* CI).
- `.claude/CLAUDE.md` § CLI Tools — add the new tool's own entry, and the four
  currently-undocumented entry points.

### Similar Patterns
- `ll-verify-cli-allowlist` (BUG-2764) — reconciles `pyproject.toml` entry
  points against `skills/configure/areas.md` and `writers._LL_PERMISSIONS`,
  exits 1 on drift. Closest precedent for both the shape and the exit
  contract.
- `ll-verify-docs` — verifies documented counts match actual file counts;
  same "docs must match reality" family, different subject.
- `ll-verify-skill-prose` (ENH-2951) — precedent for a suppression comment
  (`<!-- ll-prose-ok: reason -->`) when a finding is a deliberate exception.
  Useful if CLAUDE.md ever needs to intentionally name an unshipped command.

## Program Design

### Types

- `DocClaim: dataclass` — one parsed assertion from CLAUDE.md.
  - `tool: str` (e.g. `"ll-issues"`)
  - `subcommand: str | None` (`None` for a tool-level claim)
  - `flag: str | None` (e.g. `"--next"`)
  - `line: int` — for the drift report's file:line anchor
- `ClaimDrift: dataclass` — one failed claim.
  - `claim: DocClaim`
  - `kind: str` — `"unknown_tool"` / `"unknown_subcommand"` / `"unknown_flag"` /
    `"undocumented_entry_point"`
  - `severity: str` — `"error"` / `"warn"` (see Open Question)
- `SkippedClaim: dataclass` — text the parser declined to interpret; reported,
  never silently dropped.

`EpicDrift` (`cli/issues/epic_consistency.py`) is the structural precedent
for a per-category drift dataclass with a derived `has_drift` and a
`to_dict()` for `--json`; `FormatGaps` (`issue_parser.py:232`) is the same
shape. Follow whichever the implementer finds closer — but note the
`FormatGaps` lesson from the `testable` regression: **every category must have
a matching branch in the text renderer**, or a non-zero exit prints nothing.

### Signatures

- `parse_cli_section(md_path: Path) -> tuple[list[DocClaim], list[SkippedClaim]]`
  — conservative extractor over the § CLI Tools bullets.
- `probe_tool(tool: str) -> tuple[set[str], str] | None` — returns
  (argparse subcommand choices, raw `--help` text), or `None` when the entry
  point does not resolve. Caches per tool; one subprocess per tool, not per
  claim.
- `verify_claims(claims: list[DocClaim]) -> list[ClaimDrift]`
- `find_undocumented_entry_points(claims: list[DocClaim]) -> list[ClaimDrift]`
  — **reuses `_all_ll_entry_points()`
  (`cli/verify_cli_allowlist.py:46`)** rather than re-parsing
  `scripts/pyproject.toml`; that helper already returns the entry-point set
  this check needs to diff against, and duplicating it would create a second
  parser to keep in sync.
- `main_verify_cli_docs() -> int` — the entry-point function, named to match
  `main_verify_cli_allowlist()` (`cli/verify_cli_allowlist.py:109`) and
  registered the same way in `scripts/pyproject.toml`
  (`ll-verify-cli-allowlist = "little_loops.cli:main_verify_cli_allowlist"`,
  `L113`). Exit 1 on any `error`-severity drift; `--json` for machine
  consumption.

### Call Path

`main_verify_cli_docs` → `parse_cli_section` → `probe_tool` (per tool, cached)
→ `verify_claims` + `find_undocumented_entry_points` → `_all_ll_entry_points`
→ drift report → exit code

`verify_cli_allowlist._run()` (`L84`) is the shape to mirror for the
report-plus-exit-code split: it returns `tuple[int, dict[str, list[str]]]` so
the CLI and the pytest gate consume the same result without re-running the
check. The pytest gate calls the entry point in-process and asserts 0, matching
how the other `ll-verify-*` gates are wired into the suite.

## Implementation Steps

1. Write the CLAUDE.md CLI-section parser (tools, subcommands, flags) with a
   conservative extractor that reports skipped/unparseable claims rather than
   silently dropping them.
2. Add the `--help`-probing verifier and the drift report.
3. Add the reverse check (entry point with no CLAUDE.md entry).
4. Register the entry point; add the pytest gate.
5. Fix the four currently-undocumented entry points so the new gate passes on
   a clean tree.
6. Add the new tool to CLAUDE.md's own CLI Tools list.

## Scope Boundaries

**In scope:**
- CLAUDE.md § CLI Tools ↔ actual CLI surface, both directions.
- Subcommand names and flag literals.

**Out of scope:**
- Verifying prose *descriptions* are accurate — only that named commands and
  flags exist. Semantic accuracy is not mechanically checkable.
- `docs/reference/CLI.md` and `docs/reference/API.md` — same class of drift,
  but a different corpus with different conventions; file separately if
  wanted.
- Skill/command markdown (`commands/*.md`, `skills/*/SKILL.md`) — covered by
  `ll-verify-skill-prose` for a different concern.
- Fixing ENH-2944's `normalize` or ENH-2946's `set-flags` — this issue only
  ensures the docs stop claiming they exist.

## Open Question

**Should an undocumented entry point be an error or a warning?** Erroring
means every new `ll-*` tool must land with its CLAUDE.md entry in the same
commit — desirable, but it hard-blocks a work-in-progress entry point. A warn
tier plus an explicit opt-out list is the softer option. Recommend starting at
WARN for the reverse direction and ERROR for the forward direction (a
documented-but-absent command is unambiguously wrong; an undocumented tool may
be deliberate).

## Impact

- **Priority**: P2 — the drift misleads every session, has recurred twice, and
  per-issue review demonstrably does not catch it. Not P1 because the failure
  mode is a wasted tool call, not data loss or a broken build.
- **Effort**: Small-Medium — one parser, one probe loop, one gate. The
  ad-hoc version was written and validated in a single session.
- **Risk**: Low — a read-only verifier. The main risk is a noisy or
  over-eager parser, mitigated by reporting skipped claims explicitly.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:capture-issue` - 2026-08-01T16:04:25 - `f9ef973a-acd3-40a7-a313-5e7a001f9a16.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P2
