---
id: FEAT-2332
title: 'll-issues epic-consistency: detect and reconcile EPIC body/parent drift'
type: FEAT
priority: P2
status: open
decision_needed: false
captured_at: '2026-06-26T22:37:02Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
relates_to:
- BUG-2333
- ENH-2330
- ENH-2331
- BUG-2029
decision_ref:
- ARCHITECTURE-065
labels:
- captured
- epic
- issue-management
- tooling
- parent-child
confidence_score: 96
outcome_confidence: 80
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 22
---

# FEAT-2332: `ll-issues epic-consistency` — detect & reconcile EPIC drift

## Summary

Add an `ll-issues epic-consistency` subcommand that detects, reports, and
(with `--fix`) reconciles divergence between an EPIC's authoritative `parent:`
child set and its body `## Children` section. This is the keystone that makes
the parent:-source-of-truth model (ARCHITECTURE-065) enforceable instead of
hand-maintained.

## Use Case

**Who**: A little-loops maintainer reconciling EPIC drift — the same person who ran
the 2026-06-26 EPIC audit and is working through fixes on
`audit/epic-consistency-fixes`.

**Context**: After issues are reparented or an EPIC's `## Children` list is
hand-edited, the body view drifts from the authoritative `parent:` backref set.
Today the only way to find this is a full manual audit across all 32 EPICs, then
hand-editing each drifting body.

**Goal**: Detect every drifting EPIC in one command and mechanically reconcile the
safe (category-a) cases without touching sub-epic prose or human-decision cases.

**Outcome**: `ll-issues epic-consistency --all` surfaces the 18 drifting EPICs with
(a)/(b)/(c) categorization; `--all --fix` drives category-(a) drift to zero while
leaving sub-epic prose, non-issue tokens, and category-(b) decisions untouched.

## Motivation

The 2026-06-26 EPIC audit
(`thoughts/audits/2026-06-26-epic-issue-management-audit.md`) found **18/32
EPICs** with genuine drift between their body `## Children` list and the set of
issues carrying `parent: EPIC-####`. There is currently **no tool** that
detects this — `ll-deps validate` checks blocked_by/relates_to/depends_on
integrity but not EPIC body↔parent consistency, so drift is fixed by hand one
EPIC at a time (see the manual reconciliations on `audit/epic-consistency-fixes`).

Per ARCHITECTURE-065, `parent:` is the single source of truth for membership,
`## Children` is a derived view, and `relates_to:` is non-membership only.

## Current Behavior

- No `epic-consistency` subcommand exists in
  `scripts/little_loops/cli/issues/`.
- `compute_epic_progress` (`scripts/little_loops/issue_progress.py:87`) already
  resolves children via `parent:` backrefs — the exact set this tool must
  reconcile the body against — but nothing compares it to `## Children`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Anchor precision**: `compute_epic_progress` is defined at
  `scripts/little_loops/issue_progress.py:67`; the authoritative child-resolution
  expression `child_ids = {i.issue_id for i in all_issues if i.parent == epic_id}`
  is at `:87`. Resolution is one level deep (direct `parent:` only; `relates_to`
  is intentionally excluded per its docstring). It returns an `EpicProgress`
  dataclass (`issue_progress.py:18`) with a `children: list[IssueInfo]` field —
  the exact set to diff against `## Children`.
- **`ll-deps validate` always exits 0** — even when violations are found
  (`scripts/little_loops/cli/deps.py:431` branch; every path returns 0 at
  `:452` JSON, `:456` clean, `:508` after printing the report). It confirms the
  issue's claim that it does *not* check EPIC body↔parent consistency, **but**
  it also means simply emitting drift from `validate` will not gate anything
  (see AC#6 — a non-zero exit path must be added, which is the wiring decision
  flagged in Proposed Solution).

## Expected Behavior

`ll-issues epic-consistency` exists as a subcommand. Run report-only (default), it
diffs each EPIC's authoritative `parent:` backref set against its body
`## Children` and reports drift in three categories (a/b/c) plus a sub-epic
advisory. Run with `--fix`, it rewrites `## Children` to match the `parent:` set
for category-(a) drift only, leaving prose, non-issue tokens, and category-(b)
entries intact. New drift is caught going forward via a wired-in validation gate.

## Proposed Solution

`ll-issues epic-consistency [EPIC-ID | --all] [--fix] [--format text|json]`

**Detect (report-only default).** For each EPIC, compute the `parent:` backref
set (reuse the `compute_epic_progress` resolution path) and diff it against the
real issue IDs in the body `## Children` section. Report three categories:

- **(a) `parent:` child missing from body** — a real child not documented.
- **(b) body-listed real issue with no `parent:` backref** — documented but not
  actually a child; needs a human decision (add `parent:` or remove from body).
- **(c) `relates_to:` entry that is also a `parent:` child** — membership
  leaking into the cross-reference channel (flag for cleanup; see ENH-2330).

**Body grammar (must-handle).**
- **Skip non-issue tokens** in `## Children` (e.g. `MR-1`, `CT-0`, `EG-4` —
  rule/example identifiers that are not issues).
- **Treat `EPIC-*` body refs as sub-epic prose** — allowed, never flagged as
  needing a `parent:` backref (per the "sub-epics via relates_to + prose"
  convention; see `reference_epic_progress_non_recursive`).
- Also surface, as an advisory, EPICs that carry `parent: EPIC-####` on another
  EPIC (e.g. EPIC-2258 → EPIC-2257) since sub-epics are meant to be tracked via
  relates_to + prose, not `parent:`.

**`--fix`.** Rewrite each EPIC's `## Children` to match its `parent:` set:
- Add missing category-(a) children (one bullet each, preserving any existing
  per-child description text on rewrite).
- Preserve existing sub-epic prose lines and non-issue lines untouched.
- Category-(b) entries (body-listed but no `parent:`) are **reported, not
  silently dropped** — fixing them requires a membership decision a human/skill
  must make.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **The existing ID regex is not sufficient on its own.** `ISSUE_ID_PATTERN`
  (`scripts/little_loops/issue_parser.py:26`,
  `^[-*]\s+\*{0,2}([A-Z]+-\d+)`) handles the bullet + bold form and is the right
  primitive, but it matches **any** `[A-Z]+-\d+` token — there is no type
  whitelist, so it would capture `MR-1`, `CT-0`, `EG-4`, and `EPIC-2258` too.
  The "skip non-issue tokens" and "treat `EPIC-*` as sub-epic prose"
  requirements therefore need an **explicit type filter** layered on top:
  keep `{BUG, FEAT, ENH}` for the (a)/(b) child diff, route `EPIC-*` to the
  sub-epic advisory, and drop everything else (`MR-*`/`CT-*`/`EG-*`).
- **Real `## Children` grammar is the bold form**: `- **FEAT-1855** — prose`
  (bold ID, ` — ` em-dash, free-text description). Across the sampled EPICs the
  plain `- FEAT-1855` form did not appear; `--fix` must preserve the existing
  per-child description after the em-dash on rewrite. The issue's body-grammar
  examples (`- FEAT-1234 — description`) should be read as the bold variant.
- **Reusable section helpers for the body parser and `--fix` rewriter**:
  `_extract_section(content, heading)` in
  `scripts/little_loops/issue_history/doc_synthesis.py` and the equivalent
  `IssueParser._parse_section` (`issue_parser.py:758`) both use the
  "find `## Heading` → find next `##` → slice" pattern. Replacement is a splice:
  `content[:start] + new_section + content[end:]`. Write back via
  `file_utils.atomic_write` (tempfile + `os.replace`) for safety, matching the
  pattern used elsewhere for in-place issue edits.
- **Idempotency model**: `--fix` re-run must be a no-op. Achieve this by making
  the rewriter deterministic (regenerate `## Children` from the sorted `parent:`
  set, re-attaching preserved descriptions) so a second pass produces byte-identical
  output — see the marker-guard idempotency pattern in
  `scripts/little_loops/recursive_finalize.py:_append_decomposition_note`.

### Decision required: where to wire the drift gate (AC#6)

Research surfaced that `ll-deps validate` returns exit 0 even on violations
(see Current Behavior findings). So "wire the detector in so new drift is caught
going forward" is not a drop-in — it forces a choice about which exit-code
contract to touch. Three viable options, with materially different blast radius:

- **Option A — Standalone gate (lowest blast radius).** `epic-consistency`
  owns its own non-zero exit in report-only mode and is invoked from a
  session-start / pre-commit hook. `ll-deps validate`'s always-0 contract is
  left untouched. Self-contained; nothing else changes behavior.

  > **Selected:** Option A — Standalone gate — maps exactly onto the existing
  > `ll-verify-*` linter pattern (3 templates) with zero callers on `ll-deps
  > validate`'s always-0 contract, so nothing else changes behavior.
- **Option B — Fold into `validate_dependencies`.** Add a
  `body_parent_drift` field to `ValidationResult`
  (`scripts/little_loops/dependency_mapper/models.py:54`) and a detection block
  in `validate_dependencies` (`dependency_mapper/analysis.py:416`), **and**
  change the `deps.py:431` validate branch to return non-zero on `has_issues`.
  Most centralized, but it flips a long-standing always-0 contract that existing
  callers/CI may rely on.
- **Option C — Opt-in strict flag.** Keep default `ll-deps validate` at exit 0;
  add the new drift check behind `ll-deps validate --strict` (or a dedicated
  `--check epic-consistency`) that returns non-zero only for the new class.
  Preserves the default contract while still offering a gate.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-26.

**Selected**: Option A — Standalone gate (lowest blast radius)

**Reasoning**: `epic-consistency` owns its own non-zero exit and is wired
through a hook, leaving `ll-deps validate`'s always-0 contract untouched. This
maps directly onto the established `ll-verify-*` linter pattern
(`verify_design_tokens.py`, `verify_package_data.py`, `verify_triggers.py` all
use `return 1 if violations else 0`), so the detector copies a proven template
with proven exit-code tests rather than inventing new contracts. Options B and C
both touch `ll-deps validate`'s exit behavior — B flips the always-0 contract
(breaking `test_cli_deps.py:186,197` and inverting `ENH-2249`'s success
criterion), and C introduces a `--strict` convention that exists nowhere else in
the CLI. Option A is the only choice that adds the gate without changing any
existing behavior.

**Gate-wiring refinement** (research correction to Option A's stated mechanism):
the "session-start / pre-commit hook" phrasing must be adjusted at implementation
time — Claude Code `SessionStart` hooks are required to exit 0
(`scripts/little_loops/hooks/session_start.py:222`), so a hard block there would
break session startup, and no pre-commit git-hook infrastructure exists in the
repo. The viable blocking mechanism is the existing **PreToolUse deny** precedent
(`hooks/scripts/check-duplicate-issue-id.sh` — denies Write/Edit on a consistency
violation), with an advisory (exit-0, stderr) SessionStart report as the
non-blocking complement. The `ll-issues epic-consistency` subcommand itself still
owns the non-zero exit for direct/manual invocation.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — Standalone gate | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| B — Fold into `validate_dependencies` | 1/3 | 1/3 | 1/3 | 0/3 | 3/12 |
| C — Opt-in `--strict` flag | 1/3 | 2/3 | 2/3 | 2/3 | 7/12 |

**Key evidence**:
- **A**: Three working `ll-verify-*` linter templates use `return 1 if violations
  else 0` as standalone entry points; `epic_progress.py:16-52` gives the exact
  `ll-issues` subcommand registration + own-exit shape; reuse score 3/3; zero
  automation call sites depend on `ll-deps validate`'s always-0 contract.
- **B**: `ValidationResult.has_issues` (`models.py:74`) is a clean extension hook,
  but `validate_dependencies` (`analysis.py:416`) does no file I/O (body drift
  needs filesystem reads), the change breaks `test_cli_deps.py:186,197`, and it
  inverts `ENH-2249`'s `ll-deps validate exits 0` success criterion; reuse 1/3.
- **C**: `add_json_arg` shape and `verify_triggers` thresholds are reusable, but
  `--strict`/`--check` exist nowhere in the CLI layer, it departs from the
  `ll-verify-*` always-non-zero convention, and it layers two strictness concepts
  onto one subcommand; reuse 1/3.

## Acceptance Criteria

- `ll-issues epic-consistency --all` lists all 18 currently-drifting EPICs with
  the correct (a)/(b)/(c) categorization (matches the audit baseline).
- `ll-issues epic-consistency --all --fix` drives category-(a) drift to zero
  across all 32 EPICs without touching sub-epic prose or non-issue tokens.
- `--format json` emits a machine-readable per-EPIC report.
- Unit tests cover: a clean EPIC, an (a)-only EPIC, a (b)-only EPIC, an EPIC
  with sub-epic prose + non-issue tokens (asserts they are preserved/ignored),
  and `--fix` idempotency (running twice is a no-op).
- Detector is wired into `ll-deps validate` (or a session/pre-commit hook) so
  new drift is caught going forward.

## API/Interface

```
ll-issues epic-consistency [EPIC-ID | --all] [--fix] [--format text|json]
```

- `EPIC-ID` — check a single EPIC; `--all` — check every EPIC under
  `.issues/epics/`.
- `--fix` — rewrite each EPIC's `## Children` to match its `parent:` set
  (category-(a) only). Default is report-only.
- `--format text` (default) — human-readable per-EPIC report;
  `--format json` — machine-readable.

Per-EPIC JSON shape:

```json
{
  "epic": "EPIC-2257",
  "missing_from_body": ["FEAT-1234"],      // (a) parent: child not in body
  "body_without_parent": ["BUG-0099"],     // (b) body-listed, no parent: backref
  "relates_to_is_child": ["ENH-0042"],     // (c) membership leaking into relates_to
  "sub_epic_advisory": ["EPIC-2258"]       // EPIC carrying parent: EPIC-####
}
```

Exit code: non-zero when drift is found in report-only mode (so it can gate
`ll-deps validate` / a hook); zero after a successful `--fix`.

## Integration Map

- New: `scripts/little_loops/cli/issues/epic_consistency.py` (model on
  `scripts/little_loops/cli/issues/epic_progress.py`).
- Reuse: `compute_epic_progress` child resolution
  (`scripts/little_loops/issue_progress.py:87`), `find_issues`, and the issue
  parser (`scripts/little_loops/issue_parser.py`).
- Register the subparser alongside the other `ll-issues` subcommands.
- Tests: `scripts/tests/test_issues_cli.py` (or a new
  `test_epic_consistency.py`).
- Docs: add to the `ll-issues` subcommand list in `.claude/CLAUDE.md` and
  `docs/reference/API.md`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete anchors from codebase analysis:_

- **Subcommand registration pattern** (model exactly on `epic_progress.py`):
  define `add_epic_consistency_parser(subs)` + `cmd_epic_consistency(config, args) -> int`
  in the new module; call `add_config_arg(p)` and `p.set_defaults(command="epic-consistency")`.
  Wire it in `scripts/little_loops/cli/issues/__init__.py` at **two sites**:
  the import + `add_epic_progress_parser(subs)` registration call (`:718`) and the
  `if args.command == "epic-progress":` dispatch branch (`:776`).
- **Loading all issues** (incl. terminal): `find_issues(config, status_filter=_ALL_STATUSES)`
  — `find_issues` is at `scripts/little_loops/issue_parser.py:845`; `IssueInfo`
  dataclass at `:211` exposes `issue_id`, `parent: str | None`, `path`, `status`, `title`.
- **JSON output**: `print_json(data)` from `scripts/little_loops/cli/output.py`
  (`json.dumps(data, indent=2)`); branch on `fmt = getattr(args, "format", "text") or "text"`.
  `EpicProgress.to_dict()` (`issue_progress.py`) is the model for the per-EPIC dict shape.
- **`--fix` rewrite + idempotency helpers**: `doc_synthesis._extract_section`,
  `issue_parser.ISSUE_ID_PATTERN` (`:26`), `file_utils.atomic_write`. See the
  type-whitelist caveat in the Proposed Solution findings — `ISSUE_ID_PATTERN`
  alone over-matches.
- **AC#6 wiring target**: `validate_dependencies`
  (`scripts/little_loops/dependency_mapper/analysis.py:416`) returning
  `ValidationResult` (`dependency_mapper/models.py:54`), invoked from the
  `validate` branch at `scripts/little_loops/cli/deps.py:431`. **The validate
  branch returns 0 on all paths today** — adding a non-zero exit is a
  prerequisite for any gate routed through `validate` (Options B/C above).
- **Test model**: `scripts/tests/test_issues_cli.py::TestIssuesCLIEpicProgress`
  (~`:4700`) — fixture `issues_dir_with_epic_progress` builds an EPIC + children
  at varied statuses; invocation patches `sys.argv` and calls `main_issues()`,
  asserting exit code + `capsys` JSON. Idempotency model:
  `scripts/tests/test_recursive_finalize.py::test_idempotent` (assert second
  call produces no duplication). Compute-layer tests: `test_issue_progress.py`.

## Implementation Steps

1. Add `scripts/little_loops/cli/issues/epic_consistency.py`, reusing
   `compute_epic_progress` child resolution and the issue parser.
2. Implement the body `## Children` parser: extract real issue IDs, skip
   non-issue tokens (`MR-*`/`CT-*`/`EG-*`), treat `EPIC-*` refs as sub-epic prose.
3. Compute the (a)/(b)/(c) diff plus the sub-epic advisory; render `text` and
   `json` formats.
4. Implement `--fix` to rewrite `## Children` for category-(a) drift only,
   preserving per-child descriptions, sub-epic prose, and non-issue lines.
5. Register the subparser and wire the detector into `ll-deps validate`
   (or a hook) so new drift fails going forward.
6. Add tests (clean / a-only / b-only / prose+non-issue preservation / `--fix`
   idempotency) and update `.claude/CLAUDE.md` + `docs/reference/API.md`.

## Out of Scope

- Auto-resolving category-(b) entries (a membership decision, not mechanical).
- Changing reader semantics in `review-epic` (BUG-2333) or writer behavior in
  `scope-epic`/`link-epics` (ENH-2330).

## Impact

- **Priority**: P2 — Keystone that makes the ARCHITECTURE-065
  parent:-source-of-truth model enforceable; the 2026-06-26 audit found 18/32
  EPICs drifting with no tool to catch it. Not P1 because drift is currently
  being reconciled by hand on `audit/epic-consistency-fixes`.
- **Effort**: Medium — Reuses `compute_epic_progress` resolution and the existing
  issue parser; new surface is one subcommand, a body `## Children` parser, the
  `--fix` rewriter, and tests.
- **Risk**: Medium — `--fix` rewrites EPIC body content, but the report-only
  default, category-(a)-only scope, prose/non-issue preservation, and `--fix`
  idempotency test bound the blast radius.
- **Breaking Change**: No — new subcommand; report-only by default.

## Status

**Open** | Created: 2026-06-26 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-06-27T03:09:15 - `7d2aa461-8f7c-47a4-be7f-63378073ab98.jsonl`
- `/ll:confidence-check` - 2026-06-26T23:45:00 - `d398aa33-03ed-4b1a-b141-77db75682f71.jsonl`
- `/ll:decide-issue` - 2026-06-26T23:25:25 - `9638d775-3967-4517-9cef-a97510938e46.jsonl`
- `/ll:refine-issue` - 2026-06-26T23:03:37 - `53786629-d9b8-4f2a-8643-10c3f08458a2.jsonl`
- `/ll:format-issue` - 2026-06-26T22:53:47 - `912502f5-b03b-4128-acad-4241a97f2415.jsonl`
