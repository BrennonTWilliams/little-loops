---
id: ENH-2953
title: "ll-issues prioritize --apply: priority-rename mechanics out of prioritize-issues.md"
type: ENH
priority: P2
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
testable: true
relates_to:
- ENH-2944
labels:
- cli
- issues
- normalization
---

# ENH-2953: `ll-issues prioritize --apply`

## Summary

`commands/prioritize-issues.md` (233 lines) is discovery + rename bookkeeping around a
single genuine judgment step. Split out of ENH-2944 so it ships independently of
`normalize` (511 lines, the largest file in the epic's scope) rather than waiting on it.

## Current Behavior

`commands/prioritize-issues.md` has **two** modes, both mechanical outside one judgment step:

- **Initial prioritization** (Steps 1–4, L52–67 + L145–209): glob + `^P[0-5]-` regex
  discovery (L54–67), `git mv` prepend (L169–173), fixed report table (L177–209).
- **Re-prioritization** (Steps 1.5/2-RE/3-RE/4-RE, L69–141): fires when *all* issues
  already carry a prefix — re-evaluates every active issue, renames only those whose
  priority changed by **replacing** the existing `P[X]-` prefix (L108–112), and emits a
  second fixed report table (L118–139). Gated by a mandatory `AskUserQuestion` call
  (L73–83) unless `AUTO_MODE`.
- Narrated check-mode exit codes (L48–50), which makes any FSM
  `evaluate: type: exit_code` gate over this command model-dependent.
- Only Steps 2 / 2-RE (assigning P0–P5 from impact/severity/effort) are judgment.
- Notably the command uses no `ll-issues` subcommand at all today.

## Expected Behavior

- `ll-issues prioritize [--check] [--all] [--json]` — discovery + report data. Default
  lists **unprioritized** issues (no `^P[0-5]-` prefix); `--all` lists every active issue
  with its `current_priority`, which is what the re-prioritize mode consumes.
- `--check` is a deterministic exit-code gate (0 = every active issue carries a prefix /
  1 = one or more unprioritized), per the EPIC convention that no `--check` exit is
  LLM-narrated. `--check` ignores `--all` (re-prioritization is never a gate failure).
- `ll-issues prioritize --apply -` — reads a `{"ENH-2953": "P2", ...}` JSON map from
  stdin, performs all renames, returns `{id, old_path, new_path, old_priority}` per
  entry. Handles both **prepend** (no existing prefix) and **replace** (`P[X]-` → `P[Y]-`);
  an entry already at its target priority is a no-op, not an error.
- `/ll:prioritize-issues` shrinks to ~60 lines: call `--json` (or `--all --json`), judge
  priorities, pipe the map to `--apply -`.

## Proposed Solution

Discovery reuses `issue_parser.find_issues()`; the "is it prioritized" test is a narrow
`^P[0-5]-` match, **not** `is_normalized()` (see Codebase Research Findings — that
predicate checks the whole filename and would misclassify a prefixed-but-malformed file
as unprioritized, causing a double prefix). Renames go through the shared
`git_mv_with_fallback()` helper in `issue_lifecycle.py` (ENH-2944 owns creating it;
whichever issue lands first extracts it, under exactly that name).

`--apply` reads a JSON map from stdin rather than a `k=v` comma string: there is no
`ID=P2,...` precedent in `ll-issues` (`set-scores` is per-issue flags), stdin matches the
`set-flags --from-notes -` convention from ENH-2946, and it avoids shell-quoting hazards
when an FSM `shell:` body drives the call.

## Codebase Research Findings

_Verified 2026-08-01 against the working tree._

- **No `ID=P2,...` precedent exists.** `scripts/little_loops/cli/issues/set_scores.py`
  and its parser (`cli/issues/__init__.py:705-730`) take `set-scores ISSUE_ID
  --confidence N --outcome N ...` — per-issue flags. Nothing in `ll-issues` parses a
  comma-separated `k=v` map. The stdin-JSON shape above replaces it.
- **`is_normalized()` is the wrong predicate.** `issue_parser.py:94` matches the entire
  filename against `^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}-[a-z0-9-]+\.md$`. A file with a
  malformed ID or non-slug tail is "not normalized" while already carrying a `P2-` prefix
  — prioritize would prepend a second one. ID/slug defects are ENH-2944's job.
- **The git-mv block to reuse** is `issue_lifecycle.py:966-990`, inside `skip_issue()`:
  `_is_git_tracked()` (line 393, via `git ls-files`) → `git mv`, with `atomic_write()` +
  `Path.rename()` fallback for untracked files or on `git mv` failure/timeout. A bare
  `subprocess` `git mv` fails on untracked issue files. `skip_issue()` itself is **not**
  reusable — it appends a `## Skip Log` section. `docs/reference/CLI.md:1772` already
  names the extracted helper `git_mv_with_fallback()`; ENH-2944 line 141 claims ownership
  of creating it. Import it, do not duplicate.
- **`re.sub(r"^P\d-", ...)`** (`cli/issues/skip.py:47`) is the existing prefix-replace
  idiom — but it is a no-op on an unprefixed file, so `apply_priorities()` needs an
  explicit prepend branch.
- **Status filtering**: `find_issues(status_filter=None)` skips `done/cancelled/deferred`
  (`issue_parser.py:1876-1878`). That default is **correct here** — prioritization only
  concerns active work. This deliberately differs from ENH-2944, which passes
  `status_filter=set(_ALL_STATUSES)` so terminal issues with malformed filenames aren't
  skipped; the divergence is intentional, not an oversight.
- **Sibling to model**: `cli/issues/format_check.py` — `--check` exit-code convention
  (0 clean / 1 violations), scan-vs-apply split, and `add_*_parser(subs)`
  self-registration.

## Implementation Steps

1. `prioritize` discovery (`--json`, `--all`) + `--check` exit code.
2. `--apply -` stdin JSON map parsing; prepend/replace renames via
   `git_mv_with_fallback()`.
3. Slim `commands/prioritize-issues.md` (233 → ~60): keep the P0–P5 criteria table, the
   judgment step, and the `AskUserQuestion` re-prioritize gate; delete flag-parsing bash,
   glob discovery, `git mv` blocks, both report tables, and the narrated `--check` exits.
4. Docs + mirrors (see Integration Map).
5. Tests (see Acceptance Criteria).

## Program Design

### Types

- `PrioritizeEntry: dataclass`
  - `id: str`
  - `path: Path`
  - `current_priority: str | None`  # `None` only in the unprioritized listing

- `RenameResult: dataclass`
  - `id: str`
  - `old_path: Path`
  - `new_path: Path`
  - `old_priority: str | None`

### Signatures

- `scan_prioritize(config: BRConfig, *, include_prioritized: bool = False) -> list[PrioritizeEntry]`
- `apply_priorities(config: BRConfig, mapping: dict[str, str]) -> list[RenameResult]`
- `cmd_prioritize(config: BRConfig, args: argparse.Namespace) -> int`

### Call Path

- `scan_prioritize()` -> `find_issues()` (existing, `issue_parser.py:1855`) -> `^P[0-5]-`
  prefix match
- `apply_priorities()` -> `_resolve_issue_id()` (existing, `cli/issues/show.py`) ->
  prefix prepend/replace -> `git_mv_with_fallback()` (`issue_lifecycle.py`, extracted from
  `skip_issue()`)

## Integration Map

- **`ll-action` bridge**: `prioritize-issues` is one of the nine `ll-action`-bridged
  verifiers writing `verdict_events` (`docs/ARCHITECTURE.md:697`,
  `docs/guides/HISTORY_SESSION_GUIDE.md:118`). `ll-action invoke prioritize-issues
  --output json` must still work after slimming.
- **`docs/reference/CLI.md`**: has **no** `prioritize` section today (unlike ENH-2944's
  prewritten one) — add a new one alongside `ll-issues skip` (L1419).
- **`.claude/CLAUDE.md`**: the `ll-issues` bullet enumerates every subcommand — add
  `prioritize`.
- **`docs/guides/LOOPS_GUIDE.md:1004`** lists `prioritize-issues` among skills whose
  `--check` needs `evaluate: type: exit_code`; it becomes a CLI `--check`, so update.
- **Host mirror**: `.kimi-code/skills/ll-prioritize-issues/SKILL.md` is git-tracked and
  duplicates the full 233-line body (incl. the `--check` narration at L221). Regenerate
  via `ll-adapt`; `scripts/tests/test_adapt_golden_corpus.py` covers this surface.
  (`.gemini/skills/` is untracked — ignore.)
- **`scripts/tests/test_verify_skill_prose.py:19`** `BASELINE_COUNT = 23`. This issue
  removes exactly 2 findings (`prioritize-issues.md:110` and `:171`, both
  `git_mv_glob_loop` — confirmed by running `ll-verify-skill-prose`). Ratchet to 21,
  coordinating with ENH-2944's own decrement.
- **ENH-2944**: shares `git_mv_with_fallback()`. Not a hard dependency — whichever lands
  first extracts the helper under that exact name.

## Scope Boundaries

- In scope: the `prioritize` subcommand (`--json`, `--all`, `--check`, `--apply -`),
  slimming `commands/prioritize-issues.md`, and the doc/mirror updates above.
- Out of scope: the P0–P5 taxonomy itself, priority *judgment* (stays LLM), `normalize`
  (ENH-2944), `ll-issues skip`'s existing priority-bump path, and any change to the
  `AskUserQuestion` re-prioritize UX (it stays in the command, unchanged).

## Impact

- **Priority**: P2 - Thin, independently shippable, and removes a narrated exit-code gate
- **Effort**: Small - Discovery + a rename map, plus doc/mirror follow-through
- **Risk**: Low-Medium - `--check` previews and renames go through the tracked/untracked
  fallback helper, but the re-prioritize (prefix-replace) mode is easy to drop silently;
  it is the main regression surface and is explicitly covered by AC 3 and AC 6

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Acceptance Criteria

- [ ] `ll-issues prioritize --check` exit code is the FSM-usable gate (0 = all active issues prefixed / 1 = one or more unprioritized), with no LLM narration
- [ ] `--json` lists unprioritized issues; `--all --json` lists every active issue with its `current_priority` (the re-prioritize mode's input)
- [ ] `--apply -` **prepends** a prefix to an unprioritized file and **replaces** `P[X]-` with `P[Y]-` on an already-prioritized one; an entry already at its target priority is a reported no-op, not an error
- [ ] Renames preserve git history for tracked files — asserted via `git log --follow` continuity across the rename — and fall back to `atomic_write()` + `Path.rename()` for untracked files without raising
- [ ] `--apply` is idempotent: re-applying the same map reports no further change and leaves files byte-identical (model on `scripts/tests/test_ll_issues_format_check.py::TestFormatCheckFix`)
- [ ] `commands/prioritize-issues.md` ≤ ~60 lines, containing no glob/regex discovery, no `git mv`, no report tables, and no narrated exit codes — while still supporting **both** initial prioritization and re-prioritization, and retaining the `AskUserQuestion` re-prioritize gate
- [ ] `ll-action invoke prioritize-issues --output json` still succeeds against the slimmed command
- [ ] `ll-verify-skill-prose` reports no findings in `commands/prioritize-issues.md`, and `BASELINE_COUNT` in `scripts/tests/test_verify_skill_prose.py` is ratcheted down accordingly
- [ ] pytest coverage in `scripts/tests/test_ll_issues_prioritize.py` (fixture tree of prioritized/unprioritized/terminal-status issues; `done`/`cancelled`/`deferred` issues are excluded from discovery)
- [ ] Docs updated: new `ll-issues prioritize` section in `docs/reference/CLI.md`, `ll-issues` bullet in `.claude/CLAUDE.md`, `docs/guides/LOOPS_GUIDE.md:1004`, and `.kimi-code` mirror regenerated via `ll-adapt`
