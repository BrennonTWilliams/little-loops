---
id: BUG-3282
type: BUG
title: verify-issues certifies evidence quotes that exist in no revision of the cited
  artifact
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T17:29:50Z'
labels:
- verify-issues
- skills
- evidence
- hallucination
- pipeline
relates_to:
- ENH-3283
- ENH-3284
- BUG-3278
---

# BUG-3282: verify-issues certifies evidence quotes that exist in no revision of the cited artifact

## Summary

`/ll:verify-issues` validates an issue's *code* claims but never checks that quoted **evidence** —
a snippet attributed to another file, usually another `.issues/` file — actually appears in the
artifact it is attributed to. An issue whose code references are all accurate but whose motivating
evidence is fabricated passes verification and receives `verify_verdict: VALID`.

## Current Behavior

`commands/verify-issues.md:71` ("Identify code snippets quoted") and `:129` ("**Validate code
snippets**: Does quoted code match current code?") scope quote-checking to source code. Nothing
in the pass:

- extracts quoted spans attributed to a named `.issues/` file or issue ID
- greps the cited artifact — at HEAD, across history, or in the working tree — for those spans
- checks that a `## Steps to Reproduce` naming a live artifact still reproduces against it

Observed on BUG-3278 (2026-08-21). Its `## Current Behavior` quoted two strings attributed to
ENH-3277:

```
- **(a) Make the documented override real.**
**DECISION — pick one before step 4 touches this file:**
```

Neither string exists in **any** committed revision of ENH-3277 (verified by grepping every
revision returned by `git log --all --format=%h -- .issues/enhancements/P2-ENH-3277*.md`).
ENH-3277's second decision point is prose, not bullets. Two `verify_issue` invocations during a
`refine-to-ready-issue` loop run stamped `verify_verdict: VALID` / `confidence_score: 98` anyway,
because every *code* assertion in the issue (`issue_parser.py:2134`, `:1967`, `:1891`, the
`section_header > bold_label > numbered > bullet` precedence order, the winner-take-all return)
was accurate.

## Expected Behavior

Verification extracts quoted spans that are attributed to a named artifact (file path or issue
ID) and confirms each one exists in that artifact. A span found nowhere in the cited artifact —
at HEAD, in the working tree, or in any revision — fails the pass and is named in the verdict,
regardless of how accurate the issue's code claims are.

## Motivation

An unverified evidence quote is worse than a missing one: it reads as the strongest part of the
issue. Downstream passes treat it as settled ground and build on it. On BUG-3278, `refine_issue`
and `wire_issue` produced roughly 150 lines of Integration Map, dependent-file inventory, docs
list, and test wiring — including a fixture spec and a proposed `--all-tiers` CLI flag — all
derived from a mechanism ("a `bullet`-tier block lost precedence to `bold_label`") that the
fabricated quote invented. The whole 26-minute loop run hardened a fiction.

The failure is silent by construction. Verification currently reports strongest confidence
exactly where its coverage is weakest: an issue with dense, accurate code citations and one
fabricated evidence quote scores higher than a vague but honest one.

## Proposed Solution

Add an evidence-existence check to the verification pass. It is deterministic and cheap enough to
run as a Python gate rather than an LLM judgement:

1. **Extract candidate spans.** Fenced blocks and inline-backtick runs that appear within N lines
   of a file path or issue ID reference, or inside a section that names one.
2. **Resolve the cited artifact.** Issue ID -> path via the existing resolver; file paths as
   given.
3. **`grep -F` each span** against the artifact at working tree, at HEAD, and across
   `git log --all` revisions of that path. Normalize whitespace before matching; skip spans below
   a minimum length (a 3-token quote is not evidence).
4. **Fail on zero hits**, naming the span and the artifact.

Open sub-question for implementation: whether this lands as a new `ll-verify-*` CLI invoked from
the skill (deterministic, testable by subprocess, reusable by `capture-issue`) or as prose added
to `commands/verify-issues.md`. The CLI shape is preferred — it is the only form the capture-side
guard can also call.

## Integration Map

### Files to Modify

- `commands/verify-issues.md` — extend the validation phase beyond `:129`'s code-snippet scope to
  cover artifact-attributed evidence quotes
- A new deterministic checker under `scripts/little_loops/` (module + `ll-*` entry point in
  `scripts/pyproject.toml`) if the CLI shape is taken

_Wiring pass added by `/ll:wire-issue`:_
- `skills/configure/areas.md` — the "All ll- commands" preset that
  `_areas_md_preset_tools()` (`scripts/little_loops/cli/verify_cli_allowlist.py:62`) reads; the new
  entry point must be listed here or `main_verify_cli_allowlist()`
  (`scripts/little_loops/cli/verify_cli_allowlist.py:109`) fails the CI gate
- `scripts/little_loops/init/writers.py` — `_LL_PERMISSIONS`, the second preset
  `_writers_preset_tools()` (`scripts/little_loops/cli/verify_cli_allowlist.py:74`) reads; same gate,
  same failure mode if omitted
- `docs/reference/CLI.md` — needs a new `### ll-verify-<name>` section documenting the checker,
  following the `ll-verify-skill-prose` / `ll-verify-private-refs` shape; also required by
  `scripts/tests/test_wiring_cli_registry.py`'s `DOC_STRINGS_PRESENT` check (see Tests)

### Tests

- Fixture issue quoting a string present in the cited artifact -> passes
- Fixture issue quoting a string absent from the cited artifact -> fails, names span + artifact
- Fixture quoting a string absent at HEAD but present in an earlier revision -> passes (history is
  in scope; a repro can legitimately cite a since-edited file)
- Whitespace/line-wrap normalization: a quote reflowed across lines still matches

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_verify_private_refs.py:314-377` (`class TestRepoGate`) — copy this pattern
  verbatim-shaped for the new checker's CI-gate test class: skip if not a git checkout, shell the
  CLI via `subprocess.run([..., "--all", "--json", "-C", str(repo_root)])`, skip (not fail) on
  `returncode not in (0, 1)`, `pytest.fail()` with a fix-it instruction built from
  `payload["findings"][:20]`
- `scripts/tests/spike/git_show_blob_at_ref/test_blob_reader.py:25-42` (`repo()` fixture) — the
  existing pattern for a temp git repo with a base commit and a feature-branch commit; use this
  shape for the "quote present in an earlier revision" fixture rather than inventing a new one.
  Its sibling `test_uses_gitlock_no_bare_subprocess` (lines 81-88) is an AST-walk regression guard
  asserting the module never calls bare `subprocess.run/call/Popen`, only `GitLock.run` — if the
  new checker's revision enumeration resolves the Program Design's noted `GitLock` ambiguity in
  favor of routing through it, add an equivalent guard; if it follows the shipped-module precedent
  (bare `subprocess.run`, per Codebase Research Findings below) omit it, but the choice should be
  explicit, not silent
- `scripts/tests/test_wiring_cli_registry.py:71-76` (`DOC_STRINGS_PRESENT`) — add a
  `(docs/reference/CLI.md, "ll-verify-<name>", "BUG-3282")` row once the checker is named; this
  test enforces that `docs/reference/CLI.md` documents every new `ll-verify-*` entry point
- `scripts/tests/test_ll_issues_check_verify_verdict.py` (existing VALID/NON_VALID/PROPOSAL_UNSOUND
  fixtures at lines 78-170) — needs parallel fixtures **only if** the new verdict is given
  `PROPOSAL_UNSOUND`-style distinct-persistence treatment (see Wiring Phase below); no change if it
  collapses into generic `NON_VALID`

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/show.py:39` — `_resolve_issue_id()`, thin delegation to the
  shared resolver `resolve_issue_path()` (`scripts/little_loops/issue_parser.py:92`); imported by
  `cli/issues/check_verify_verdict.py`, `set_status.py`, `path_cmd.py`, `set_scores.py`,
  `cli/loop/_scaffold_core.py`, and `mcp_server/tools.py` — a new checker resolving a cited issue
  ID should reuse this resolver rather than re-implementing ID parsing
- `commands/verify-issues.md:58` — already shells out to `ll-issues path "$ISSUE_ID"` (the
  CLI-facing wrapper around the same resolver) for its own issue-selection step

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py:91-152` — every `main_verify_*` entry point is imported
  (e.g. `:98-99`) and re-exported through `__all__` (e.g. `:147,150`) here; the new checker's
  `main_verify_<name>` follows this exact registration precedent
- `commands/verify-issues.md`'s `#### C. Determine Verdict` table (confirmed present, currently 10
  rows ending in `PROPOSAL_UNSOUND`) needs a new row for "evidence quote unverifiable against its
  cited artifact" — no existing verdict covers this failure mode, matching the issue's own Program
  Design § Decision Rules note
- `commands/verify-issues.md` § Check Mode Behavior (the persistence rule immediately following the
  verdict table) explicitly special-cases `PROPOSAL_UNSOUND` as distinctly persisted rather than
  collapsed into `NON_VALID`, specifically so `check_proposal_unsound` in
  `refine-to-ready-issue.yaml` can route on it (ENH-3250 precedent). This is an **open decision**
  the issue's own Decision Rules section flags as unresolved ("Escape hatch: none specified") but
  does not flag for the verdict-persistence question — resolve whether the new verdict gets the
  same distinct-persistence + routing treatment, or collapses into generic `NON_VALID` with no
  further wiring
- `scripts/little_loops/cli/issues/check_verify_verdict.py:22-44` — the `--proposal-unsound`
  query-flag precedent (ENH-3250); if the verdict-persistence decision above goes the distinct
  route, needs a parallel query flag
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:350,353-365` — `check_proposal_unsound`
  gate state (`on_no: check_proposal_unsound` at `:350`, state body at `:353-365`); same
  conditional wiring as the flag above, only needed if distinct persistence is chosen

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- The closest existing precedent for this checker's purpose is `verify_skill_prose.py` (`scripts/little_loops/cli/verify_skill_prose.py`, `main_verify_skill_prose`) — it flags prose that should instead point at a canonical owner elsewhere, the same shape as "this quote should exist in a cited artifact." `verify_private_refs.py` (`scripts/little_loops/cli/verify_private_refs.py:527`, `main_verify_private_refs`) is the closest in output/testing machinery (`--json` via `print_json`, baseline/regression support, `TestRepoGate` pytest transport). Neither resolves a match to an external artifact and checks presence there — that composition is new.
- Entry points follow `ll-verify-<name> = "little_loops.cli:main_verify_<name>"` in `scripts/pyproject.toml`, re-exported through `scripts/little_loops/cli/__init__.py`'s `__all__`; existing entries are appended non-alphabetically at wherever they were added chronologically (`scripts/pyproject.toml:108-116`).
- `main_verify_*` entry-point signatures disagree across existing checkers: `verify_private_refs.py`/`verify_skill_prose.py` take `argv: list[str] | None = None`; `verify_docs.py`/`verify_decisions.py` take no `argv` param and parse `sys.argv` directly.
- Tests follow one file per checker (`scripts/tests/test_verify_<name>.py`): unit tests against the checker's internal functions, plus a `TestRepoGate`-style class that shells the CLI out against this repo's own tracked content as the enforced CI gate (`scripts/tests/test_verify_private_refs.py`).
- No shipped module in `scripts/little_loops/` runs `git log --all` plus per-revision content grep. The two nearest primitives — `_git_grep_word()` (`scripts/little_loops/codequery/fallback.py:50`, presence-anywhere-in-tree search) and the FEAT-2652 spike `read_blob_at_ref()` (`scripts/tests/spike/git_show_blob_at_ref/blob_reader.py`, single-ref blob read) — disagree on whether to route through `GitLock`: the spike requires it; every shipped git-history module (`issue_history/parsing.py:_git_completion_date`, `issues/research_triage.py:_git_changes_since`, `codequery/fallback.py`, `issues/program_design.py:git_grep_resolver`) uses bare `subprocess.run` instead.
- `commands/verify-issues.md` does not currently shell out to any `ll-verify-*` binary. Its only deterministic-tool wiring precedent is §B.0's `ll-code` graph-check pattern — an explicit permitted-command allowlist, fail-open silent fallback when the provider is absent, and a rule that a negative/no-hit result may never by itself produce a verdict (`commands/verify-issues.md:74-120`).

## Program Design

### Types

N/A — no new data types. Findings would be ad hoc violation records analogous to the existing
`ll-verify-*` finding dataclasses (e.g. the rule/finding pair in
`scripts/little_loops/cli/verify_private_refs.py`).

### Signatures

- `resolve_issue_path(config: BRConfig, user_input: str) -> Path | None` — `scripts/little_loops/issue_parser.py:92`, the shared ID→path resolver a new checker calls to resolve a cited issue ID to its file (accepts bare numeric ID, `TYPE-ID`, or `P<n>-TYPE-ID`; matches on the anchored numeric ID only, so a stale type prefix still resolves)
- `main_verify_private_refs(argv: list[str] | None = None) -> int` — `scripts/little_loops/cli/verify_private_refs.py:527`, the closest existing entry-point shape (changed-files mode + `--all` full-scan mode, `--json` via `print_json`) a new `main_verify_evidence`-style entry point would follow
- `build_ref_index(root: Path) -> RefIndex` — `scripts/little_loops/text_utils.py:229`, a single `git ls-files` call producing a basename-indexed tracked-file lookup a new checker could reuse instead of re-resolving file-path attributions itself

### Call Path

`commands/verify-issues.md` §B check phase -> new `ll-verify-*` CLI, `main_verify_evidence(argv)`
-> `resolve_issue_path()` (`issue_parser.py:92`) to resolve the cited artifact -> revision
enumeration (no existing helper; closest precedents are `_git_grep_word()`
(`scripts/little_loops/codequery/fallback.py:50`, presence-anywhere-in-tree search) and the
FEAT-2652 spike `read_blob_at_ref()` (`scripts/tests/spike/git_show_blob_at_ref/blob_reader.py`,
single-ref blob read); the two disagree on whether to route through `GitLock` — the spike requires
it, every shipped git-history module uses bare `subprocess.run`) -> per-revision `git show
<sha>:<path>` + `grep -F` for each candidate span -> finding emitted in the same
`_findings_to_json`-style JSON shape as `verify_private_refs.py`/`verify_skill_prose.py`

### Decision Rules

- **Gap kind**: a quoted span (fenced block or inline-backtick run) attributed to a named file path
  or issue ID that resolves to zero hits in that artifact's working tree, HEAD, or any `git log
  --all` revision.
- **Inputs**: the whitespace-normalized span text and the resolved artifact path (via
  `resolve_issue_path()` / `ll-issues path`).
- **Threshold**: minimum span length — the issue's own Proposed Solution names "a 3-token quote is
  not evidence" as the floor; exact tokenization method is unspecified.
- **Escape hatch**: none specified in the issue. Sibling checkers `verify_private_refs.py` and
  `verify_skill_prose.py` both support a same-line-or-preceding-line suppression comment
  (`ll-private-ok: reason`, `<!-- ll-prose-ok: reason -->`); whether this checker gets an
  equivalent marker is unresolved — no such escape hatch is named in the issue's Proposed Solution
  or Steps to Reproduce.

## Implementation Steps

1. The CLI-vs-prose open question in Proposed Solution resolves: a new deterministic checker
   exists with an entry point wired the way every other `ll-verify-*` tool is
   (`ll-verify-<name> = "little_loops.cli:main_verify_<name>"` in `scripts/pyproject.toml`,
   re-exported through `scripts/little_loops/cli/__init__.py`'s `__all__`), since
   `commands/verify-issues.md` performs its checks via LLM judgment today and a deterministic gate
   is what BUG-3278 needed.
2. The checker extracts candidate spans (fenced blocks and inline-backtick runs attributed to a
   named file path or issue ID) using the existing fence-aware primitives in
   `scripts/little_loops/text_utils.py` rather than new regex, resolves the cited artifact via
   `resolve_issue_path()` (`scripts/little_loops/issue_parser.py:92`), and reports zero-hit spans
   as findings in the same `_findings_to_json` shape `verify_private_refs.py` and
   `verify_skill_prose.py` already emit.
3. `commands/verify-issues.md` §B gains a numbered check (parallel to existing checks 1-6) that
   invokes the new CLI and folds a non-clean result into the verdict table, alongside a new
   verdict value for "evidence quote unverifiable against its cited artifact" — no existing verdict
   in the `#### C. Determine Verdict` table covers this failure mode.
4. Coverage matches the four fixtures already named under Integration Map → Tests, via a
   `scripts/tests/test_verify_<name>.py` file with the same two-layer shape as
   `test_verify_private_refs.py`: unit tests against the extraction/matching functions, plus a
   `TestRepoGate`-style class shelling the CLI out as the enforced CI gate.
5. `python -m pytest scripts/tests/` passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Register the new `ll-verify-<name>` entry point in `scripts/little_loops/cli/__init__.py`
  (import + `__all__`) and `scripts/pyproject.toml`, following the exact pattern of
  `main_verify_private_refs` / `main_verify_skill_prose`
- Add the entry point to `skills/configure/areas.md`'s "All ll- commands" preset and
  `scripts/little_loops/init/writers.py`'s `_LL_PERMISSIONS` — `main_verify_cli_allowlist()`
  (`scripts/little_loops/cli/verify_cli_allowlist.py:109`) fails CI if either is skipped
- Document the checker in `docs/reference/CLI.md` with a `### ll-verify-<name>` section; add the
  corresponding `DOC_STRINGS_PRESENT` row in `scripts/tests/test_wiring_cli_registry.py:71-76`
- Add a new row to `commands/verify-issues.md`'s `#### C. Determine Verdict` table for the
  evidence-unverifiable failure mode
- Resolve the verdict-persistence question: does the new verdict get `PROPOSAL_UNSOUND`-style
  distinct persistence and a `refine-to-ready-issue.yaml` routing gate
  (`scripts/little_loops/cli/issues/check_verify_verdict.py:22-44`,
  `scripts/little_loops/loops/refine-to-ready-issue.yaml:350,353-365`), or collapse into generic
  `NON_VALID`? If distinct, add parallel fixtures to
  `scripts/tests/test_ll_issues_check_verify_verdict.py`

## Impact

- **Priority**: P2 — silent, and it corrupts every downstream pass in a refine loop rather than
  failing one step
- **Effort**: Small-Medium — span extraction is the only non-trivial part
- **Risk**: Low-Medium — over-eager span extraction produces false failures on illustrative
  snippets that were never claimed to be verbatim quotes. Mitigate with a minimum span length and
  by requiring an explicit artifact attribution nearby.
- **Breaking Change**: No

## Steps to Reproduce

1. Author an issue whose code references are all correct but which quotes, in a fenced block or
   inline backticks, a line attributed to another issue file that does not contain it.
2. Run `/ll:verify-issues` on it.
3. Observe `verify_verdict: VALID` — the fabricated quote is never tested.

Historical instance: `git show baa553d9:.issues/bugs/P2-BUG-3278-*.md` is the capture that
contains the fabricated quotes; the loop's two verify passes are recorded in that file's
`## Session Log`.

## Root Cause

`commands/verify-issues.md` frames verification as "does the issue's description of the code match
the code" (`:129`). Evidence attributed to a non-source artifact — another issue file, a log, a
run directory — falls outside that frame entirely, so the pass has no step that could fail on it.

## Related Key Documentation

- `commands/verify-issues.md:71,129` — the code-scoped quote check this issue widens
- BUG-3278 — the issue whose fabricated evidence passed two verification rounds
- ENH-3277 — the artifact the fabricated quotes were attributed to

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-08-21T18:11:26 - `de2bc4f7-6272-4f52-a9cb-998af08752f1.jsonl`
- `/ll:refine-issue` - 2026-08-21T17:44:39 - `169e7cf4-cd6f-42a2-b69c-b77a2737901b.jsonl`
- `/ll:capture-issue` - 2026-08-21T17:30:50 - `fa57a84b-34e0-4018-9e9e-dd57ed7ef3f3.jsonl`
