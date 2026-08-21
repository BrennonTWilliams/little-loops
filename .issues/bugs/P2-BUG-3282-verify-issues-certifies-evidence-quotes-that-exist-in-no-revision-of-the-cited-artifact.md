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
confidence_score: 95
outcome_confidence: 70
score_complexity: 16
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
missing_artifacts: true
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

This issue is not exempt from its own subject. Its fixture spec originally asserted, without
checking, that `**Option A**` "genuinely exists in ENH-3277" — a claim that is false in every
revision of that file, and that a reviewer caught only by grepping (2026-08-21 review pass). The
first artifact `ll-verify-evidence` should be run against is BUG-3282.

It will not pass clean, and that is expected rather than a defect: this issue's `## Current
Behavior` reproduces the two fabricated spans verbatim, in an in-scope section, under an ENH-3277
attribution — *because reporting a fabricated quote requires quoting it*. That is the
**counter-example class** (Decision Rules → Counter-example quotes), and it is what the
`<!-- ll-evidence-ok: -->` hatch is for. Implementation must annotate that block and treat a clean
run on this file, post-annotation, as the acceptance signal.

## Proposed Solution

Add an evidence-existence check to the verification pass. It is deterministic and cheap enough to
run as a Python gate rather than an LLM judgement:

1. **Scope to evidence-bearing sections first.** Only `## Current Behavior`, `## Steps to
   Reproduce`, `## Root Cause`, `## Motivation`, and `### Codebase Research Findings` are in
   scope. `## Proposed Solution`, `## Expected Behavior`, `## Implementation Steps`,
   `## Integration Map`, and `## Program Design` are hard-excluded: they quote code that
   intentionally does not exist yet, so a presence check against a cited artifact is meaningless
   there. See Decision Rules for why this is load-bearing rather than an optimization.
2. **Extract candidate spans, by attribution — following parenthetical first, then nearest
   preceding mention, section-bounded.** Within those sections, fenced blocks and inline-backtick
   runs that inherit either the path/ID in a **parenthetical immediately following the span** or,
   failing that, the **nearest preceding file-path or issue-ID mention in the same `##` section**,
   minus command-output blocks. Both span forms matter: the BUG-3278 fabrications were
   inline-backtick runs, not fenced blocks. A stricter same-line/preceding-line window is *not*
   sufficient — it has zero recall on this issue's own flagship fixture and makes the
   command-output exclusion dead code; and nearest-preceding *alone* misattributes the pervasive
   ``symbol (`path`)`` prose idiom. See Decision Rules → Attribution rule, which works the fixture
   line by line.
3. **Resolve the cited artifact.** Issue ID -> path via the existing resolver; file paths as
   given. An artifact that does not resolve, or resolves to an untracked path, is skipped with no
   finding (see Decision Rules → Fail-open).
4. **Match spans against the artifact, artifact-major, one process per tier.** For each artifact,
   fetch its history once, normalize once, then test every candidate span against that cached text
   — not span-major, which costs O(spans x revisions) blob reads. Short-circuit in order **working
   tree -> HEAD -> history**; the overwhelmingly common case resolves at the first. Normalize span
   and artifact text identically before matching (Decision Rules → Normalization: whitespace **and**
   markdown emphasis/decoration — whitespace alone is not enough, and the fixture's flagship
   true-negative is the proof); skip spans below a minimum length. The history tier is
   `git log -p`, not a `git log` + per-revision `git show` loop — see Decision Rules → History
   enumeration for the measured reason. **Patch text must have its diff line prefixes stripped
   before normalization** or every multi-line span false-positives at that tier (Decision Rules →
   Patch-text preparation; measured).
5. **Fail on zero hits**, naming the span and the artifact.
6. **Three invocation modes, mirroring `verify_private_refs`'s three enforcement points — the
   pytest gate is `--all`.** The precedent splits three ways and this checker follows it exactly:
   `--all` vs baseline is the **pytest CI gate** (`test_verify_private_refs.py:325`);
   `--added-only FILE...` is the **pre-commit** invocation (`.pre-commit-config.yaml:17`, the only
   caller of `staged_added_lines()`); plain changed-files mode on explicit paths is the **skill /
   host-hook** invocation. Earlier drafts of this issue put the pytest gate on changed-files mode;
   that is vacuous — see Implementation Steps step 3b.
7. **Baseline the full-scan mode, keyed on issue ID.** `--all` reports only findings beyond a
   tracked baseline, with `--update-baseline` to regenerate. The baseline keys on the **anchored
   numeric issue ID, not the file path** — issue files are renamed constantly, and a path-keyed
   baseline turns every re-prioritization into a spurious regression (see Implementation Steps
   step 4). Because the pytest gate is `--all`, the baseline is **on the critical path**: the gate
   cannot land green without it. The tiering and parallelism in step 4 keep that seeding scan to a
   few minutes rather than an overnight chore.

This lands as `ll-verify-evidence`, a new deterministic CLI invoked from the skill (testable by
subprocess), not as prose added to `commands/verify-issues.md`.

## Integration Map

### Files to Modify

- `commands/verify-issues.md` — extend the validation phase beyond `:129`'s code-snippet scope to
  cover artifact-attributed evidence quotes
- `scripts/little_loops/cli/verify_evidence.py` — new deterministic checker, `main_verify_evidence`,
  entry point `ll-verify-evidence` in `scripts/pyproject.toml`. **The name is settled** (it was a
  `ll-verify-<name>` placeholder through the refine/wire passes): module `verify_evidence.py`,
  entry point `ll-verify-evidence`, tests `scripts/tests/test_verify_evidence.py`, baseline
  `.ll/evidence-baseline.json`
- `.ll/evidence-baseline.json` — new tracked baseline for `--all` mode, keyed on numeric issue ID
  (see Implementation Steps step 4). Required for the pytest gate, not optional
- `.pre-commit-config.yaml` — new `--added-only` hook entry alongside the existing
  `ll-verify-private-refs --added-only` at `:17`

_Wiring pass added by `/ll:wire-issue`:_
- `skills/configure/areas.md` — the "All ll- commands" preset that
  `_areas_md_preset_tools()` (`scripts/little_loops/cli/verify_cli_allowlist.py:62`) reads; the new
  entry point must be listed here or `main_verify_cli_allowlist()`
  (`scripts/little_loops/cli/verify_cli_allowlist.py:109`) fails the CI gate
- `scripts/little_loops/init/writers.py` — `_LL_PERMISSIONS`, the second preset
  `_writers_preset_tools()` (`scripts/little_loops/cli/verify_cli_allowlist.py:74`) reads; same gate,
  same failure mode if omitted
- `docs/reference/CLI.md` — needs a new `### ll-verify-evidence` section documenting the checker,
  following the `ll-verify-skill-prose` / `ll-verify-private-refs` shape; also required by
  `scripts/tests/test_wiring_cli_registry.py`'s `DOC_STRINGS_PRESENT` check (see Tests)

### Tests

- **Real regression fixture (highest value — the motivating artifact is in git).** Run the checker
  against `baa553d9:.issues/bugs/P2-BUG-3278-decide-issue-clears-decision_needed-while-lower-precedence-decision-blocks-stay-unresolved.md`.
  Assert an **exact finding set**, not just "flags the fabrications" — this fixture is what pins
  both precision and recall, and every clause below was re-verified against the blob and against
  all 17 revisions of ENH-3277 (both its pre- and post-rename paths) on 2026-08-21.
  **Pin both sides of the fixture.** The BUG-3278 side is pinned at `baa553d9`, but ENH-3277 is a
  live, `status: open` file whose history keeps growing (12 revisions when this issue was captured,
  17 by the pre-implementation review). If the checker resolves ENH-3277 through
  `resolve_issue_path()` against the working tree, the test is non-hermetic: any future edit that
  quotes these strings into ENH-3277 — a session log, a cross-reference to this issue — silently
  flips the flagship must-flags into passes and the regression test stops testing. Either pin the
  ENH-3277 side to a rev as well, or materialize both blobs into a synthetic temp repo
  (`test_blob_reader.py:25-42`'s `repo()` fixture shape) and run the checker there. Do not assert
  against live history:
  - **Must flag**, all three attributed to ENH-3277 and all three absent from *every* revision of
    it — `- **(a) Make the documented override real.**` (`:38`),
    `- **(b) Drop the knob.**` (`:38`, same line), and
    `**DECISION — pick one before step 4 touches this file:**` (`:40`, `:60`).
  - **Count**: the `DECISION` span occurs **twice** in in-scope sections — `:40` in
    `## Current Behavior` and `:60` in `## Steps to Reproduce`; the two `(a)`/`(b)` spans share
    `:38`. Expected findings are therefore **4 occurrences / 3 distinct spans**. Pick one and
    assert it: dedupe by normalized span text (3 findings, each carrying its occurrence lines) —
    the report is more readable and the baseline counts stay stable when an issue is reflowed.
  - **Must not flag** `` `**Option A**` `` / `` `**Option B**` `` / `` `**Option C**` `` at `:37`.
    These sit in the same numbered list, in the same section, under the same ENH-3277 attribution
    as the fabrications. **This true-negative holds only under emphasis-normalized matching**
    (Decision Rules → Normalization) and is the fixture clause that pins it: the literal
    `**Option A**` appears in **zero** revisions of ENH-3277 — what actually fired the `bold_label`
    tier is `**Option A — permanently exempt both. SELECTED.**`, which does not contain that
    literal. Normalize emphasis away and `Option A` matches; match raw text and the checker flags
    its own designated true-negative. (The character floor happens to exclude `**Option A**` at 12
    chars, but resting the clause on the floor would make precision here an accident of length —
    assert the normalized match, and cover the floor separately below.)
  - **Must not flag** the fenced block at `:44-49` (the `count 3  pattern bold_label …` listing),
    introduced by the invocation line at `:42`. It is *output of*
    `ll-issues locate-options ENH-3277 --json`, not a quote from ENH-3277, and it appears in no
    revision of that file. Under the nearest-preceding attribution rule this block **does** inherit
    ENH-3277 (from `:35`), so the command-output exclusion is the only thing that saves it — this
    clause is what proves that exclusion is live rather than decorative. **Note `:43` is blank**:
    the exclusion must reach the next fence past intervening blank lines, not only an immediately
    adjacent one, or it is dead code on the very fixture that justifies it. See Decision Rules →
    Attribution rule.
  - **Must not flag** any span attributed by a *following* parenthetical. Not exercised by this
    blob, but see the `read_blob_at_ref()` case in Decision Rules → Attribution rule, which is a
    live false positive on **this issue's own** `### Codebase Research Findings`; cover it with the
    synthetic fixture below.
  The synthetic fixtures below cover the mechanics around it.
- Fixture issue quoting a string present in the cited artifact -> passes
- Fixture issue quoting a string absent from the cited artifact -> fails, names span + artifact
- Fixture quoting a string absent at HEAD but present in an earlier revision -> passes (history is
  in scope; a repro can legitimately cite a since-edited file). **Document the limitation this
  buys**: it is the rule that makes the checker weakest — an issue can cite a revision that never
  existed on any branch and still pass if a similar string appears anywhere in history. Accepted,
  but state it so a later reader does not mistake a pass for proof of provenance.
- Fixture quoting a span in an excluded section (`## Proposed Solution`) that matches nothing ->
  passes, no finding (section-scope guard; see Decision Rules)
- Fixture quoting a span in an *unlisted* section (`## Impact`, `## Session Log`) that matches
  nothing -> passes, no finding. Pins the allowlist default (Decision Rules → Section scope): a
  section that is in neither list is out of scope, so adding a new section to the issue template
  can never silently widen the checker
- Fixture with command output attributed by an invocation line (`` `ll-issues show ENH-1 --json`
  returns: `` followed by a **blank line** and then a fenced block that matches nothing) -> passes,
  no finding. Synthetic twin of the `:44-49` case in the real fixture above; the blank line is
  load-bearing, matching `:43`
- **Following-parenthetical attribution**: a span followed immediately by ``(`path/b.py`)`` and
  preceded earlier in the same section by a mention of `path/a.py` is checked against **b**, not
  **a**, and passes when it exists in b. The direct unit twin of the `read_blob_at_ref()` false
  positive (Decision Rules → Attribution rule); without this exception the checker flags this very
  issue's `### Codebase Research Findings`
- **Counter-example quote**: a fixture whose in-scope section quotes a span *in order to report
  that it does not exist* ("X claimed `<span>`, which appears nowhere in Y") -> flagged, and
  silenced by `<!-- ll-evidence-ok: -->`. Pins Decision Rules → Counter-example quotes as a
  suppression case rather than a matcher case
- Fixture citing an untracked/gitignored artifact path -> passes, no finding (fail-open guard)
- Fixture with `<!-- ll-evidence-ok: reason -->` above an otherwise-failing span -> passes
- Whitespace/line-wrap normalization: a quote reflowed across lines still matches
- **Emphasis normalization**: a span quoted as `**Foo**` matches an artifact that writes
  `**Foo — bar. SELECTED.**`, and a span quoted as `` `foo_bar()` `` matches unbackticked
  `foo_bar()`. Direct unit-level twin of the `**Option A**` clause in the real fixture above; pins
  the Decision Rules → Normalization contract independently of the char floor
- **Multi-line span through the history tier**: a span spanning two source lines, present only in
  an earlier revision, is found. This fails unless patch text is prefix-stripped before
  normalization (Decision Rules → Patch-text preparation) — the raw-patch form is the natural
  implementation and it is wrong, so this test must exist or the bug ships
- Character-floor boundary: a span at and just below the minimum length. **The floor is measured on
  the raw span text, before normalization** — calibrated against BUG-3278's shortest real
  *fabricated* span (`**(b) Drop the knob.**`, 22 raw chars) with the floor bounded below by the
  shortest designated true-negative (`**Option A**`, 12 raw chars) — i.e. the floor lands in
  `(13, 22]`. Assert the raw-vs-normalized contract explicitly: the same two spans normalize to 18
  and 8 chars, so a floor applied post-normalization would need `(9, 18]` and the two calibrations
  are not interchangeable
- Baseline behavior: `--all` exits 0 when findings equal the tracked baseline, 1 on any increase;
  `--update-baseline` rewrites it (mirror `test_verify_private_refs.py`'s baseline tests). This is
  the **pytest gate's** contract, not a side mode
- **Added-lines filter (pre-commit mode)**: with a staged edit touching an *unrelated* line of an
  issue file that carries a pre-existing unverifiable span, `--added-only` produces no finding; the
  same file with a *new* unverifiable span staged does. Note the fixture must **stage** its edits —
  `staged_added_lines()` reads `git diff --cached`, so an unstaged working-tree edit yields an
  empty added-line map and the test would pass vacuously
- **History tiering**: a span present only in a pre-rename revision misses the `git log --all -p`
  tier and is found by the `--follow` tier, so the tiering is transparent to results and changes
  only cost (Decision Rules → History enumeration)
- **Baseline survives a rename**: baseline an issue file, rename it (`P2-` -> `P1-`, or a title
  change), re-run -> still exits 0. Path-keyed baselines fail this; ID-keyed ones pass. Both rename
  flavors are live in this repo's history (`R099` on `FEAT-3183` for the priority prefix, `R074` on
  `ENH-3264` for a title edit), so this is a regression test, not a hypothetical

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_verify_private_refs.py:314-377` (`class TestRepoGate`) — copy this pattern
  verbatim-shaped for the new checker's CI-gate test class: skip if not a git checkout, shell the
  CLI **with `--all --json`** (`:325`), skip (not fail) on `returncode not in (0, 1)`,
  `pytest.fail()` with a fix-it instruction built from `payload["findings"][:20]`. Copy its two
  companions too — `test_baseline_is_tracked_and_parseable` (the baseline must be tracked and parse
  non-empty, or every file reads as regressed) and the equivalent of its tracked/untracked
  assertion. **No divergence on mode**: an earlier draft had this gate shelling changed-files mode,
  which is vacuous — see Implementation Steps step 3b
- `.pre-commit-config.yaml:17` — the `ll-verify-private-refs --added-only` hook is where
  `staged_added_lines()` is actually consumed; add the parallel `ll-verify-evidence --added-only`
  hook here. This file is not currently named anywhere else in this issue and is the correct home
  for the added-lines filter
- `scripts/tests/spike/git_show_blob_at_ref/test_blob_reader.py:25-42` (`repo()` fixture) — the
  existing pattern for a temp git repo with a base commit and a feature-branch commit; use this
  shape for the "quote present in an earlier revision" fixture rather than inventing a new one.
  Its sibling `test_uses_gitlock_no_bare_subprocess` (lines 81-88) is an AST-walk regression guard
  asserting the module never calls bare `subprocess.run/call/Popen`, only `GitLock.run` — **do not
  copy it.** Decision Rules settles `GitLock` in favor of bare `subprocess.run` (read-only
  `git show`/`git log`, matching every shipped git-history module)
- `scripts/tests/test_wiring_cli_registry.py:71-76` (`DOC_STRINGS_PRESENT`) — add a
  `(docs/reference/CLI.md, "ll-verify-evidence", "BUG-3282")` row; this
  test enforces that `docs/reference/CLI.md` documents every new `ll-verify-*` entry point
- `scripts/tests/test_ll_issues_check_verify_verdict.py` (existing VALID/NON_VALID/PROPOSAL_UNSOUND
  fixtures at lines 78-170) — add parallel `EVIDENCE_UNVERIFIED` fixtures. Required, not
  conditional: the verdict-persistence question is resolved in favor of distinct persistence (see
  Wiring Phase)

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
  (e.g. `:98-99`) and re-exported through `__all__` (e.g. `:147,150`) here;
  `main_verify_evidence` follows this exact registration precedent
- `commands/verify-issues.md`'s `#### C. Determine Verdict` table (confirmed present, currently 10
  rows ending in `PROPOSAL_UNSOUND`) needs a new row for "evidence quote unverifiable against its
  cited artifact" — no existing verdict covers this failure mode, matching the issue's own Program
  Design § Decision Rules note
- `commands/verify-issues.md` § Check Mode Behavior (the persistence rule immediately following the
  verdict table) explicitly special-cases `PROPOSAL_UNSOUND` as distinctly persisted rather than
  collapsed into `NON_VALID`, specifically so `check_proposal_unsound` in
  `refine-to-ready-issue.yaml` can route on it (ENH-3250 precedent). **Decided: `EVIDENCE_UNVERIFIED`
  gets the same distinct-persistence treatment.** Rationale: the entire motivation of this issue is
  that the refine loop *built on* the fiction. Collapsing into `NON_VALID` routes to
  `refine_followup` — the pass that re-derives from the fabricated premise, which is exactly the
  26-minute failure described in Motivation. It must route to `check_reconcile_limit` ->
  `reconcile_issue` instead, with the offending span named so the rewrite has the fabrication in
  hand. State the precedence over `PROPOSAL_UNSOUND` in the same note (Decision Rules → Verdict
  precedence): an issue can qualify for both and the frontmatter field holds one value
- `scripts/little_loops/cli/issues/check_verify_verdict.py:22-44` — the `--proposal-unsound`
  query-flag precedent (ENH-3250); add a parallel `--evidence-unverified` query flag following that
  exact shape (exit 0 if `verify_verdict == EVIDENCE_UNVERIFIED`, 1 otherwise including absent;
  the default VALID/NON_VALID contract is unchanged and `EVIDENCE_UNVERIFIED` still falls through
  it as non-VALID -> exit 1)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:350,353-365` — `check_proposal_unsound`
  gate state (`on_no: check_proposal_unsound` at `:350`, state body at `:353-365`); add a parallel
  `check_evidence_unverified` gate **ahead of** it per Decision Rules → Verdict precedence, i.e.
  repoint `:350` to `on_no: check_evidence_unverified`, whose `on_no` falls through to
  `check_proposal_unsound` and whose `on_error` fails open to `check_refine_limit` (this file's
  convention). Note the existing gate's `on_yes` targets **`check_reconcile_limit`**, not
  `reconcile_issue` directly — the new gate must do the same or it bypasses the reconcile-attempt
  counter

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- The closest existing precedent for this checker's purpose is `verify_skill_prose.py` (`scripts/little_loops/cli/verify_skill_prose.py`, `main_verify_skill_prose`) — it flags prose that should instead point at a canonical owner elsewhere, the same shape as "this quote should exist in a cited artifact." `verify_private_refs.py` (`scripts/little_loops/cli/verify_private_refs.py:527`, `main_verify_private_refs`) is the closest in output/testing machinery (`--json` via `print_json`, baseline/regression support, `TestRepoGate` pytest transport). Neither resolves a match to an external artifact and checks presence there — that composition is new.
- Entry points follow `ll-verify-<name> = "little_loops.cli:main_verify_<name>"` in `scripts/pyproject.toml`, re-exported through `scripts/little_loops/cli/__init__.py`'s `__all__`; existing entries are appended non-alphabetically at wherever they were added chronologically (`scripts/pyproject.toml:108-116`).
- `main_verify_*` entry-point signatures disagree across existing checkers: `verify_private_refs.py`/`verify_skill_prose.py` take `argv: list[str] | None = None`; `verify_docs.py`/`verify_decisions.py` take no `argv` param and parse `sys.argv` directly.
- Tests follow one file per checker (`scripts/tests/test_verify_<name>.py`): unit tests against the checker's internal functions, plus a `TestRepoGate`-style class that shells the CLI out against this repo's own tracked content as the enforced CI gate (`scripts/tests/test_verify_private_refs.py`).
- No shipped module in `scripts/little_loops/` runs `git log --all` plus per-revision content grep. The two nearest primitives — `_git_grep_word()` (`scripts/little_loops/codequery/fallback.py:50`, presence-anywhere-in-tree search) and the FEAT-2652 spike `read_blob_at_ref()` (`scripts/tests/spike/git_show_blob_at_ref/blob_reader.py`, single-ref blob read) — disagree on whether to route through `GitLock`: the spike requires it; every shipped git-history module (`issue_history/parsing.py:_git_completion_date`, `issues/research_triage.py:_git_changes_since`, `codequery/fallback.py`, `issues/program_design.py:git_grep_resolver`) uses bare `subprocess.run` instead.
- `commands/verify-issues.md` does not currently shell out to any `ll-verify-*` binary. Its only deterministic-tool wiring precedent is §B.0's `ll-code` graph-check pattern — an explicit permitted-command allowlist, fail-open silent fallback when the provider is absent, and a rule that a negative/no-hit result may never by itself produce a verdict (`commands/verify-issues.md:74-120`).
- `verify_private_refs` enforces at **three** distinct points, and they use different modes: `.pre-commit-config.yaml:17` runs `--added-only` on staged files (the sole caller of `staged_added_lines()`), `hooks/scripts/check-private-refs.sh:198` runs plain changed-files mode on one file from a PreToolUse hook, and `test_verify_private_refs.py:325` runs `--all --json` vs baseline as the pytest gate. Conflating the pre-commit mode with the pytest gate is what made an earlier draft of this issue's gate vacuous.
- `scripts/little_loops/text_utils.py` has **no inline-backtick extraction primitive** — `fence_spans()`/`in_fence()` locate and classify *fences* only, and `strip_code_fences()` (`:108`) removes them. Since all three of the flagship fixture's must-flag spans are inline-backtick runs, inline extraction is new code; the existing primitives contribute only fence classification.

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

`commands/verify-issues.md` §B check phase -> `ll-verify-evidence`, `main_verify_evidence(argv)`
-> section filter (evidence-bearing sections only, per Decision Rules → Section scope) -> span
extraction: `fence_spans()` / `in_fence()` (`text_utils.py:64`, `:97`) for fenced blocks, plus a
**new inline-backtick regex** (no such primitive exists in `text_utils.py`) -> attribution filter:
following-parenthetical, else nearest-preceding within the `##` section, with the command-output
exclusion (Decision Rules → Attribution rule) -> `resolve_issue_path()`
(`issue_parser.py:92`) to resolve the cited artifact -> **artifact-major** match, tiered: working
tree, then HEAD, then `git log --all -p -n 20`, then — only on a residual miss —
`git log --all --follow -p -n 20`, each tier a single subprocess whose output is
**prefix-stripped** (Decision Rules → Patch-text preparation) and normalized once, then tested
against all of that artifact's candidate spans, short-circuiting on first hit ->
finding emitted in the same `_findings_to_json`-style JSON shape as
`verify_private_refs.py`/`verify_skill_prose.py`

Under `--added-only` (pre-commit mode only) a `staged_added_lines()` filter
(`verify_private_refs.py:297`) runs between span extraction and matching, dropping spans that sit
on unchanged lines. It does **not** run under `--all` (the pytest gate) or under plain
changed-files mode (the skill / host-hook path), both of which scan whole files.

Revision enumeration has no existing helper. The nearest primitives are `_git_grep_word()`
(`scripts/little_loops/codequery/fallback.py:50`, presence-anywhere-in-tree search) and the
FEAT-2652 spike `read_blob_at_ref()` (`scripts/tests/spike/git_show_blob_at_ref/blob_reader.py`,
single-ref blob read). Per Decision Rules the `GitLock` question is settled in favor of bare
`subprocess.run`, matching every shipped git-history module. Note that neither primitive is the
right shape here — see Decision Rules → History enumeration; `read_blob_at_ref()` in particular is
the per-revision `git show` pattern the measurements rule out.

### Decision Rules

- **Gap kind**: a quoted span (fenced block or inline-backtick run) **inside an evidence-bearing
  section** attributed to a named file path or issue ID that resolves to zero hits in that
  artifact's working tree, HEAD, or any `git log --all` revision.
- **Attribution rule (load-bearing — following parenthetical, then nearest preceding mention,
  section-bounded)**: a span is attributed in this order:
  1. **Following parenthetical wins.** A file path or issue ID inside a parenthetical that
     *immediately follows* the span attributes it, overriding anything earlier. This is the
     ``symbol (`path`)`` prose idiom and it is pervasive in `### Codebase Research Findings`, an
     in-scope section. Without this exception nearest-preceding attributes each symbol to the
     *previous* item's path. **Demonstrated on this issue's own body**: `` `read_blob_at_ref()` ``
     (18 raw chars, above the floor) is followed by ``(`scripts/tests/spike/git_show_blob_at_ref/
     blob_reader.py`, …)`` but preceded in the same line by
     `` `scripts/little_loops/codequery/fallback.py:50` ``. Verified 2026-08-21: `read_blob_at_ref`
     occurs in **0** revisions of `fallback.py` and **1** time in `blob_reader.py` — so the
     nearest-preceding-only rule flags a true statement in BUG-3282's own research findings.
  2. **Otherwise, nearest preceding.** The **nearest file-path or issue-ID mention that precedes it
     within the same `##` section**. Section-bounded, so an attribution never leaks across a
     heading.

  Two exclusions apply to the inherited attribution:
  - **Command output.** A line whose backtick run is a shell command (starts with a known `ll-*` /
    `git` / `python` binary) and that ends in a presentation verb (`returns:`, `outputs:`,
    `prints:`, `emits:`, `shows:`) attributes the block below it to **the command's output**, not
    to the artifact the command names — so that block is excluded even though it inherits an
    attribution. The exclusion must reach the next fenced block across **intervening blank lines**:
    in the flagship fixture the invocation is `:42`, `:43` is blank, and the fence opens at `:44`,
    so an adjacency-only implementation makes this exclusion dead code on the one case that
    justifies it.
  - **Suppression.** `<!-- ll-evidence-ok: reason -->` on the span's own or preceding line.

  A stricter **same-line-or-preceding-line window was tried and rejected**: it has *zero* recall on
  the flagship fixture. In `baa553d9:...BUG-3278...md`, `ENH-3277` is named at `:35` and `:58`,
  while every span it attributes sits at `:37`, `:38`, `:40`, and `:60` — `:36` is blank, `:39` is
  `*Dead site — …*`, `:59` is prose. Not one span has an ID on its own or preceding line, so the
  checker would flag nothing while the fixture asserts three. That window also makes the
  command-output exclusion dead code: the `:44` fence's preceding line (`:43`) is blank, so the
  fence is already unattributed and the exclusion never fires. Under the nearest-preceding rule
  both halves work: `:37/:38/:40` and the `:44-49` fence inherit ENH-3277 from `:35`, `:60`
  inherits from `:58`, and the command-output exclusion is what (correctly) drops the fence.
  Section scoping does not substitute for either: `## Current Behavior` is in scope by design.
- **Normalization (load-bearing — whitespace alone is insufficient)**: span text and artifact text
  are normalized **identically** before matching, collapsing (a) whitespace and line wrapping and
  (b) markdown emphasis and decoration — `**`, `*`, `_`, backticks — plus trailing sentence
  punctuation. Matching is containment of the normalized span in the normalized artifact text.
  Whitespace-only normalization breaks the fixture's own designated true-negative: the literal
  `**Option A**` (BUG-3278 `:37`) appears in **zero** revisions of ENH-3277 — the `bold_label` tier
  fired on `**Option A — permanently exempt both. SELECTED.**` — so raw matching flags a span the
  fixture requires be left alone. Emphasis-normalized, `Option A` matches and the true-negative
  holds for the reason it claims. Normalization is deliberately lossy in the direction of *fewer*
  findings, consistent with fail-open.
- **Patch-text preparation (load-bearing — the history tier is not plain text)**: `git log -p`
  output is a *diff*, and each content line carries a leading `+`, `-`, or space. Because
  normalization collapses whitespace, those prefixes end up **between** the joined lines, so a
  multi-line span never matches raw patch text. Measured 2026-08-21 against a span known to be
  present in `text_utils.py`'s own history:

  | Patch handling | Span found |
  |---|---|
  | raw (`+`/`-` prefixes kept) | **False** |
  | prefixes stripped | True |

  So: strip the leading diff prefix from every content line and drop diff metadata (`@@` hunk
  headers, `+++`/`---`, `index …`, `diff --git …`) **before** normalizing. Removed (`-`) lines are
  kept deliberately — content that existed and was later deleted is exactly what the history tier
  is for. Consequence to accept and document: with prefixes stripped and whitespace collapsed,
  line boundaries are gone, so a span can in principle match across a hunk join. That is
  fail-open-directional, consistent with Normalization, and preferable to false-positiving every
  multi-line quote.
- **Counter-example quotes — suppression, not matching**: an issue that *reports* a fabricated
  quote must reproduce it, so the quote appears in an in-scope section under the attribution it is
  being accused of. This is a genuine finding by the checker's own definition and must not be
  special-cased in the matcher (there is no reliable negation detection); it is handled by
  `<!-- ll-evidence-ok: -->`. **BUG-3282 is itself an instance**: its `## Current Behavior`
  reproduces the two BUG-3278 fabrications under an ENH-3277 attribution. Implementation annotates
  that block; a clean run on this file *after* annotation is the acceptance signal, not a clean run
  before it.
- **Section scope (load-bearing, not an optimization) — an allowlist, not a denylist**: in scope —
  `## Current Behavior`, `## Steps to Reproduce`, `## Root Cause`, `## Motivation`,
  `### Codebase Research Findings`. **A section in neither list is out of scope.** Named
  exclusions, kept explicit because they are the tempting ones — `## Proposed Solution`,
  `## Expected Behavior`, `## Implementation Steps`, `## Integration Map`, `## Program Design`.
  Those sections quote code that is *proposed*, not *observed*, so a presence check there produces
  guaranteed false positives. This very issue is the proof: its Program Design § Signatures quotes
  `resolve_issue_path(config: BRConfig, user_input: str) -> Path | None` (real) beside
  Implementation Steps' `ll-verify-evidence = "little_loops.cli:main_verify_evidence"` attributed
  to `scripts/pyproject.toml` — which will not exist there until this issue is implemented. Without
  section scoping the checker flags BUG-3282 itself.
  The allowlist default matters beyond tidiness: `## Summary`, `## Impact`,
  `## Related Key Documentation`, `## Confidence Check Notes`, and `## Session Log` are in neither
  list, and several of them routinely carry attributed quotes (this issue's own `## Summary` quotes
  `commands/verify-issues.md:71`). A denylist default would flag them; it would also silently widen
  the checker every time the issue template grows a section.
- **Inputs**: the normalized span text (per Normalization above) and the resolved artifact path
  (via `resolve_issue_path()` / `ll-issues path`).
- **Threshold**: minimum span length measured in **characters, not tokens**. The Proposed
  Solution's original "a 3-token quote is not evidence" floor is wrong in the direction that
  matters: BUG-3278's genuine fabricated span `**(b) Drop the knob.**` is 4 tokens and *is*
  evidence. The floor is bounded on both sides by the flagship fixture: it must admit
  `**(b) Drop the knob.**` (22 chars, must-flag) and it may not be raised so far that it becomes
  the reason `**Option A**` (12 chars) is spared — that clause belongs to Normalization. **Floor
  lands in `(13, 22]`**; measured against the spans at
  `baa553d9:.issues/bugs/P2-BUG-3278-*.md:37-40`.
  **The floor measures the raw span text, before normalization.** Both calibration constants above
  are raw counts, and the two forms are not interchangeable: the same spans normalize to 18
  (`(b) Drop the knob.`) and 8 (`Option A`) characters, so a post-normalization floor would need
  `(9, 18]`. Silently applying the raw bounds to normalized text moves the floor below both
  calibration points and admits short decorative spans wholesale.
- **Fail-open (mirrors §B.0's `ll-code` convention, `commands/verify-issues.md:74-120`)**: an
  artifact that does not resolve, or resolves to a path git does not track, is **skipped with no
  finding**. This is required, not merely lenient: Root Cause names logs and run directories as
  in-scope artifact kinds, but `postmortems/` is gitignored and `.loops/` run dirs are ephemeral,
  so a strict reading would fail on every such citation. A no-hit result may never by itself
  produce a verdict when the artifact was never readable.
- **Escape hatch — decided**: yes, following both siblings. Same-line-or-preceding-line
  `<!-- ll-evidence-ok: reason -->`, matching `verify_private_refs.py`'s `ll-private-ok: reason`
  and `verify_skill_prose.py`'s `<!-- ll-prose-ok: reason -->`. Without it the first false
  positive is only fixable by deleting the quote, which is the opposite of what this issue wants.
- **Verdict precedence — `EVIDENCE_UNVERIFIED` outranks `PROPOSAL_UNSOUND`**: an issue can satisfy
  both (a fabricated premise very often yields an unsound proposal — that is BUG-3278's exact
  shape), but `verify_verdict:` holds a single value. Evidence wins. Rationale is the ordering of
  repairs: `reconcile_issue` rewriting a directive section on top of a fabricated premise re-derives
  the fiction, so the premise must be named first. Both route to `check_reconcile_limit` anyway, so
  the precedence shows up in the persisted value and in *which span the rewrite is handed*, not in
  the routing target. Gate order in `refine-to-ready-issue.yaml` follows: check evidence before
  proposal.
- **`GitLock` — decided**: bare `subprocess.run`. `git show` and `git log` are read-only — they
  touch neither the index nor refs — so the shipped-module precedent
  (`issue_history/parsing.py`, `issues/research_triage.py`, `codequery/fallback.py`,
  `issues/program_design.py`) applies rather than the FEAT-2652 spike's write-path requirement.
  Consequently the `test_uses_gitlock_no_bare_subprocess` AST guard is **not** copied.
- **History enumeration — one process per tier, `--follow` last (measured 2026-08-21)**: content
  is *free* once the log walk is paid for, and `--follow` is the expensive flag. Per artifact,
  20 revisions, this repo:

  | Strategy | Time | Processes |
  |---|---|---|
  | `git log --all --follow` + 20x `git show <sha>:<path>` | 1.50s | 21 |
  | `git log --all --follow -p` | 0.92s | 1 |
  | `git log --all -p` | 0.56s | 1 |
  | `git log -p` | 0.41s | 1 |

  `git log -p -n 20` costs 0.406s against 0.430s for the bare SHAs — the patch text is nearly
  free, so the per-revision `git show` loop pays 21 process spawns for data the walk already
  had. `--follow` costs what it does because it diffs every commit to detect renames across a
  3192-file history. Hence: **`git log --all -p -n 20` first, `--follow` only on a residual miss.**
  Rename-crossing only buys content older than a rename, which matters solely when the cheap tier
  has already missed.
- **Renames**: issue files are renamed constantly — by `/ll:prioritize-issues` (priority-prefix
  changes) and by title edits; both flavors are live in this repo's history. This is why the
  `--follow` tier exists at all. `-n 20` caps every tier so a long-lived artifact does not dominate
  a scan. `--all` and `--follow` combine correctly here (verified: on a `.issues/` path they return
  identical history, and `--follow` does cross the `R0xx` renames); `--follow` takes a single path,
  so enumeration is one invocation per artifact — which is what
  makes the artifact-major loop the right shape. The same rename churn is why the `--all` baseline
  keys on issue ID rather than path (Implementation Steps step 4).

## Implementation Steps

1. The CLI-vs-prose open question in Proposed Solution resolves: a new deterministic checker
   exists with an entry point wired the way every other `ll-verify-*` tool is
   (`ll-verify-evidence = "little_loops.cli:main_verify_evidence"` in `scripts/pyproject.toml`,
   re-exported through `scripts/little_loops/cli/__init__.py`'s `__all__`), since
   `commands/verify-issues.md` performs its checks via LLM judgment today and a deterministic gate
   is what BUG-3278 needed.
2. The checker filters to evidence-bearing sections (Decision Rules → Section scope — an
   **allowlist**; an unlisted section is out of scope) before extracting anything, then extracts
   candidate spans (fenced blocks and inline-backtick runs, each attributed by following
   parenthetical then nearest preceding mention within its `##` section, minus command-output
   blocks — Decision Rules → Attribution rule), resolves the cited artifact via
   `resolve_issue_path()` (`scripts/little_loops/issue_parser.py:92`), and reports zero-hit spans as
   findings in the same `_findings_to_json` shape `verify_private_refs.py` and
   `verify_skill_prose.py` already emit.
   **Fenced-block extraction reuses `scripts/little_loops/text_utils.py` (`fence_spans()` `:64`,
   `in_fence()` `:97`); inline-backtick extraction is new regex** — `text_utils.py` has no inline
   primitive (see Codebase Research Findings), and inline runs are *all three* of the flagship
   fixture's must-flag spans, so this is the majority of the extraction work rather than a corner.
3. Matching is artifact-major with **tiered** working-tree -> HEAD -> `git log --all -p -n 20` ->
   `git log --all --follow -p -n 20` short-circuiting, each tier one `subprocess.run` whose output
   is prefix-stripped and normalized once per artifact (Proposed Solution step 4; Decision Rules →
   Patch-text preparation and → History enumeration). Do **not** enumerate revisions and then
   `git show` each one: that is 21 processes for content the log walk already produced, and it is
   3.7x the cost of the cheap tier. Do **not** match against raw `-p` output either — measured
   False on a span that is present (Decision Rules → Patch-text preparation).
3b. **Three modes, matching the precedent's three enforcement points — and the pytest gate is
   `--all`.** An earlier draft made the pytest gate shell changed-files mode with the added-lines
   filter; that gate never fires. `staged_added_lines()` runs `git diff --cached`, so on a clean
   checkout the added-line map is empty and every span is filtered out; and changed-files mode with
   no paths hits `parser.error("provide one or more paths, or use --all")`
   (`verify_private_refs.py:603`) -> rc 2 -> the ported `TestRepoGate` *skips* rather than fails.
   Wire it the way `verify_private_refs` actually does:
   - `--all` vs baseline -> the **pytest CI gate** (`test_verify_private_refs.py:325`)
   - `--added-only FILE...` -> **pre-commit** (`.pre-commit-config.yaml:17`)
   - plain changed-files mode on explicit paths, whole-file -> the **skill** invocation from
     `commands/verify-issues.md` §B and any PreToolUse hook
     (`hooks/scripts/check-private-refs.sh:198` shape). Whole-file is correct here: verifying one
     issue means checking that issue's evidence regardless of who authored which line, and the
     skill edits unstaged so an added-lines filter would see nothing anyway.
   Port `staged_added_lines()` regardless — it is in the module being ported and the pre-commit
   hook needs it — but do not let the gate depend on it.
4. **Key the `--all` baseline on issue ID; it is on the critical path.** Because step 3b puts the
   pytest gate on `--all`, the baseline must land *with* the gate, not in a later commit. `git
   ls-files '.issues/**/*.md'` returns 3194 tracked files, most of which carry an issue-ID
   reference; a first full scan will surface a large finding set on pre-existing issues nobody will
   retro-fix.
   Port `verify_private_refs.py`'s mechanism — `BASELINE_PATH` (`:66`), `load_baseline()` (`:418`),
   `regressions()` (`:446` — note the function is `regressions`, not `filter_regressions`),
   `write_baseline()` (`:461`), counts-only so the baseline stays portable and never stores matched
   text — to `.ll/evidence-baseline.json`, with `--update-baseline`.
   **One required divergence from that port:** `verify_private_refs` keys its baseline dict on the
   file path, which is safe there because source paths are stable. Issue paths are not — the repo
   renames them routinely (`R099 P2-FEAT-3183-… -> P1-FEAT-3183-…` on re-prioritization,
   `R074` on a title edit of `ENH-3264`). A path-keyed baseline treats every such rename as a file
   with zero baseline and fails CI on findings that were already accepted. **Key on the anchored
   numeric issue ID** (`3183`), falling back to path for non-issue artifacts.
   **Runtime**: a `--all` run is not free. Hits short-circuit at the working tree for ~nothing, but
   *misses* — which is precisely the baselined population, re-derived on every run — walk history.
   Three levers, all measured or mechanical, take the seeding scan from an overnight chore to a
   few minutes:
   - **Tiered, single-process history** (step 3): 1.50s -> 0.56s per history-walking artifact.
   - **Parallelize the scan** across artifacts with a process pool. Safe by construction: the git
     calls are read-only and `GitLock` is already ruled out (Decision Rules → `GitLock`). At 8
     workers, ~3194 artifacts x 0.56s is ~4 minutes rather than ~80.
   - **Seed in the same commit as the gate, but seed it last.** The gate *is* `--all`, so the
     baseline cannot be deferred to a follow-up commit — the ~4-minute scan is a step in landing
     this issue, not an optional cleanup. Budget it, do not schedule around it.
   Set the `-n <k>` history cap explicitly (k = 20 is the measured basis). `--all` exits 1 only
   beyond baseline, and it is what the pytest gate shells (Integration Map → Tests).
5. `commands/verify-issues.md` §B gains a numbered check (parallel to existing checks 1-6) that
   invokes the new CLI and folds a non-clean result into the verdict table, adding the
   `EVIDENCE_UNVERIFIED` verdict value — no existing verdict in the `#### C. Determine Verdict`
   table (currently 10 rows ending in `PROPOSAL_UNSOUND`) covers this failure mode.
6. Coverage matches the fixtures named under Integration Map → Tests — including the real
   `baa553d9` BUG-3278 regression fixture, pinned on **both** sides (Integration Map → Tests) —
   via `scripts/tests/test_verify_evidence.py` with the same two-layer shape as
   `test_verify_private_refs.py`: unit tests against the extraction/matching functions, plus a
   `TestRepoGate`-style class shelling `--all --json` as the enforced CI gate.
6b. **Annotate this issue's own counter-example block.** Add `<!-- ll-evidence-ok: … -->` to
   BUG-3282's `## Current Behavior` fence, which reproduces the two BUG-3278 fabrications in order
   to report them (Decision Rules → Counter-example quotes). Then run
   `ll-verify-evidence .issues/bugs/P2-BUG-3282-*.md` and require it clean — that run, not the
   pre-annotation one, is the acceptance signal Motivation asks for.
7. `python -m pytest scripts/tests/` passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Register the `ll-verify-evidence` entry point in `scripts/little_loops/cli/__init__.py`
  (import + `__all__`) and `scripts/pyproject.toml`, following the exact pattern of
  `main_verify_private_refs` / `main_verify_skill_prose`
- Add the entry point to `skills/configure/areas.md`'s "All ll- commands" preset and
  `scripts/little_loops/init/writers.py`'s `_LL_PERMISSIONS` — `main_verify_cli_allowlist()`
  (`scripts/little_loops/cli/verify_cli_allowlist.py:109`) fails CI if either is skipped
- Document the checker in `docs/reference/CLI.md` with a `### ll-verify-evidence` section; add the
  corresponding `DOC_STRINGS_PRESENT` row in `scripts/tests/test_wiring_cli_registry.py:71-76`
- Add an `EVIDENCE_UNVERIFIED` row to `commands/verify-issues.md`'s `#### C. Determine Verdict`
  table, and the matching distinct-persistence note in § Check Mode Behavior alongside the existing
  `PROPOSAL_UNSOUND` special case — including the precedence sentence (Decision Rules → Verdict
  precedence: evidence outranks proposal when both apply)
- Implement the resolved verdict-persistence decision: `EVIDENCE_UNVERIFIED` is distinctly
  persisted (not collapsed into `NON_VALID`), gets an `--evidence-unverified` query flag on
  `scripts/little_loops/cli/issues/check_verify_verdict.py:22-44`, and a
  `check_evidence_unverified` gate in `scripts/little_loops/loops/refine-to-ready-issue.yaml`
  following the `:350,353-365` `check_proposal_unsound` pattern but placed **ahead** of it
  (Decision Rules → Verdict precedence), routing `on_yes` to `check_reconcile_limit` — the existing
  gate's actual target, not `reconcile_issue` directly — and falling through `on_no` to
  `check_proposal_unsound`. Add parallel fixtures to
  `scripts/tests/test_ll_issues_check_verify_verdict.py`
- Port `staged_added_lines()` (`scripts/little_loops/cli/verify_private_refs.py:297`) along with
  the baseline machinery and wire it to `--added-only` in `.pre-commit-config.yaml`, its only
  consumer in the precedent (`:17`). It does **not** gate the pytest path — Implementation Steps
  step 3b explains why a gate built on it never fires
- Seed `.ll/evidence-baseline.json` (issue-ID-keyed, per Implementation Steps step 4) **in the same
  change as the gate**. Because the pytest gate is `--all`, the baseline is a prerequisite for a
  green suite, not a follow-up nicety; budget the ~4-minute parallel scan as an implementation step

## Impact

- **Priority**: P2 — silent, and it corrupts every downstream pass in a refine loop rather than
  failing one step
- **Effort**: Medium — span extraction (including a new inline-backtick extractor) plus baseline
  seeding, which is now on the critical path, and the loop-routing wiring
- **Risk**: Medium — over-eager span extraction produces false failures on illustrative snippets
  that were never claimed to be verbatim quotes. Unmitigated this is the *default* outcome, not an
  edge case: forward-looking sections quote code that intentionally does not exist yet, so a
  proximity-only rule flags nearly every refined issue (including this one). Six mitigations are
  load-bearing and specified in Decision Rules — the **attribution rule** (following parenthetical,
  then nearest preceding, section-bounded) with its command-output exclusion, section scoping as an
  allowlist, emphasis-aware **normalization**, **patch-text preparation**, a raw-character minimum
  span length, and fail-open on unresolvable artifacts — plus the `<!-- ll-evidence-ok: -->` escape
  hatch for whatever survives them, which the counter-example class needs by construction. Four now
  have demonstrated failure cases rather than hypotheticals, three of them on this issue's own
  text: the attribution *window* governs whether the checker finds anything at all (a same-line
  window scores zero recall on the flagship fixture); the attribution *override* governs whether it
  flags `read_blob_at_ref()` in its own research findings; normalization governs whether it spares
  `**Option A**`; and patch-text preparation governs whether every multi-line span false-positives
  at the history tier (measured False on raw `-p` output). Each is worked through in Decision Rules.
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


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-21_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 64/100 → MODERATE

### Outcome Risk Factors
- Three unresolved design decisions could cause mid-implementation churn: whether the checker needs an `ll-private-ok`-style suppression marker, whether the new verdict gets `PROPOSAL_UNSOUND`-style distinct persistence + a `refine-to-ready-issue.yaml` routing gate versus collapsing into generic `NON_VALID`, and whether revision enumeration routes through `GitLock` or uses bare `subprocess.run` (every shipped git-history module today uses the latter).
- Mitigation: resolve these three explicitly at the start of implementation rather than deferring — the issue's own Decision Rules section already flags them, so silent resolution during coding risks an inconsistent choice that later needs a follow-up fix.

_Update — 2026-08-21, review pass:_ all three are now resolved in Decision Rules and Wiring Phase —
escape hatch **yes** (`<!-- ll-evidence-ok: reason -->`), verdict persistence **distinct**
(`EVIDENCE_UNVERIFIED`, routing to `reconcile_issue`), `GitLock` **no** (bare `subprocess.run`,
read-only git). Two risks the original pass did not surface were added: the `--all` gate cannot
land green across ~3190 issue files without a seeded baseline _(superseded by the mitigation pass
below — the gate shells changed-files mode and, with `staged_added_lines()`, never depended on the
baseline)_, and section scoping is load-bearing against false positives rather than an
optimization.

_Update — 2026-08-21, pre-implementation review (claims re-verified against the repo):_ seven
changes, three of which were blocking.
1. **Attribution rule replaces proximity** _(the direction was right; the window this pass chose
   was too narrow — superseded by the second review pass below)_. The "fenced block within N lines
   of an issue ID" rule
   flags `baa553d9:...BUG-3278...md:44-49` — `ll-issues locate-options` output, not a quote — so
   the flagship regression fixture failed on precision as specified. Rule is now same-line /
   preceding-line attribution with a command-output exclusion (Decision Rules → Attribution rule).
2. **Checker named.** `ll-verify-<name>` was an unresolved placeholder in ten places including two
   wiring rows and the test filename; settled as `ll-verify-evidence` / `verify_evidence.py` /
   `main_verify_evidence` / `test_verify_evidence.py`.
3. **Baseline keys on issue ID, not path.** `verify_private_refs`'s path-keyed baseline is safe for
   source files but not for `.issues/` — both rename flavors are live here (`R099` priority-prefix
   on `FEAT-3183`, `R074` title edit on `ENH-3264`), and each would fail CI on already-accepted
   findings.
4. **Fixture expectation made exact** _(superseded by the second review pass below — the correct
   count is 4 occurrences / 3 distinct spans, and the `**Option A**` rationale was wrong)_:
   3 occurrences / 2 distinct spans, plus two named
   true-negatives (`**Option A**` at `:37`, which does exist in ENH-3277; the `:44-49` output
   block).
5. **Section scope is an allowlist** — unlisted sections (`## Summary`, `## Impact`,
   `## Session Log`, …) are out of scope, so a template change cannot silently widen the checker.
6. **`--all` runtime budgeted** _(figure superseded by the mitigation pass below: 1.50s measured
   for that strategy, 0.56s for the tiered single-process one that replaced it)_: ~1.1s per
   history-walking artifact (measured, 20 revisions), and misses are exactly the baselined
   population. _(Gate-mode claim superseded by the fourth review pass below: the pytest gate is
   `--all`; changed-files mode would be vacuous.)_
   History cap fixed at `-n 20`.
7. Fixed `filter_regressions()` → `regressions()` (`verify_private_refs.py:446`); dropped the
   unwired "reusable by `capture-issue`" claim.
Also confirmed sound and left alone: `git log --all --follow` behaves correctly on `.issues/`
paths and crosses renames, and every other cited anchor resolves (`issue_parser.py:92`,
`text_utils.py:64/97/229`, `verify_private_refs.py:66/418/461/527`,
`check_verify_verdict.py:22-44`, `refine-to-ready-issue.yaml:350`, the 10-row verdict table).

_Update — 2026-08-21, second pre-implementation review (fixture spec re-verified against the
`baa553d9` blob and all 12 ENH-3277 revisions):_ three corrections, two of which made the flagship
fixture unsatisfiable as previously written.
1. **Attribution window widened to nearest-preceding, section-bounded.** The same-line /
   preceding-line rule from the prior pass has **zero recall** on the flagship fixture: `ENH-3277`
   is named at `:35` and `:58`, every span it attributes is at `:37/:38/:40/:60`, and no span has
   an ID on its own or preceding line. It also made the command-output exclusion dead code (the
   `:44` fence's preceding line is blank, so the fence was already unattributed). The
   nearest-preceding rule restores recall *and* gives that exclusion its stated job.
2. **Normalization contract added, and it is load-bearing.** The prior pass's designated
   true-negative was factually wrong: the literal `**Option A**` appears in **zero** revisions of
   ENH-3277 (checked across both the pre- and post-rename paths); the `bold_label` tier fired on
   `**Option A — permanently exempt both. SELECTED.**`. Under whitespace-only normalization the
   checker flags its own must-not-flag span. Matching now normalizes markdown emphasis and
   decoration on both sides. The char floor would incidentally spare `**Option A**` at 12 chars,
   but resting the clause there would make precision an accident of length — the floor is now
   bounded in `(13, 22]` and the true-negative rests on normalization.
3. **Must-flag set corrected to 4 occurrences / 3 distinct spans.** `- **(b) Drop the knob.**` was
   missing from the list despite being on the same line as `(a)`, equally absent from every
   ENH-3277 revision, and already used elsewhere in this issue as the floor-calibration span. The
   `(a)` span's line was also wrong — `:38`, not `:39`. Corrected occurrences: `:38` (×2), `:40`,
   `:60`.
_Update — 2026-08-21, seeding-risk mitigation pass (git strategies benchmarked on this repo):_ the
"`--all` baseline seeding is a long pole" risk is largely dissolved, via four changes.
**Changes 1 and 4 of this pass are superseded by the fourth review pass below** — they moved the
pytest gate onto changed-files mode, which does not fire. Changes 2 and 3 (tiering, parallelism)
stand and are what keep the now-required seeding scan cheap.
1. **`staged_added_lines()` is now part of the port** (Implementation Steps step 3b). The prior
   spec ported the baseline machinery from `verify_private_refs.py` but not this function, leaving
   changed-files mode strict against whole files — so every refine pass over a legacy issue would
   fire on fabrications its author never wrote. That was the real exposure, and it recurs forever
   rather than being a one-time seeding cost.
2. **History enumeration is tiered and single-process** (Decision Rules → History enumeration).
   Measured: the spec's `git log --follow` + 20x `git show` costs 1.50s/artifact, while
   `git log --all -p` costs 0.56s and includes the content — `git log -p -n 20` is 0.406s against
   0.430s for the bare SHAs, so patch text is nearly free and the `git show` loop was paying 21
   process spawns for data already in hand. `--follow` is the expensive flag and now runs only on
   a residual miss.
3. **Seeding parallelizes** — read-only git, `GitLock` already ruled out. ~80 min serial becomes
   ~4 min at 8 workers.
4. **Resolved a contradiction**: step 4 said "seed the baseline before wiring the gate / without
   this the gate cannot land green" while Integration Map → Tests said the gate shells
   changed-files mode. With change 1 the Tests version is correct; the baseline is what makes
   `--all` useful and now lands in its own follow-up commit.
Also re-confirmed: 3192 tracked `.issues/**/*.md` files today (issue said ~3190 — drift only, now
corrected in step 4),
`regressions()`/`load_baseline()`/`write_baseline()`/`BASELINE_PATH` anchors, the
`--proposal-unsound` flag shape, `refine-to-ready-issue.yaml:350,353-365`, and the
`PROPOSAL_UNSOUND` verdict row (`verify-issues.md:223`) plus its distinct-persistence note
(`:276-278`).

_Update — 2026-08-21, fourth pre-implementation review (every load-bearing claim re-run against the
repo):_ four blocking corrections and seven smaller ones. Two of the blockers were self-demonstrated
on this issue's own body.

**Blocking**
1. **The pytest gate as specified was vacuous.** The prior pass put it on changed-files mode with
   the added-lines filter. `staged_added_lines()` reads `git diff --cached`, so on a clean checkout
   the added-line map is empty and every span is filtered out; and changed-files mode with no paths
   hits `parser.error(...)` (`verify_private_refs.py:603`) -> rc 2 -> the ported `TestRepoGate`
   *skips*. The precedent it cites actually enforces at three separate points with three different
   modes — `.pre-commit-config.yaml:17` (`--added-only`),
   `hooks/scripts/check-private-refs.sh:198` (changed-files, one file),
   `test_verify_private_refs.py:325` (`--all --json` vs baseline, **the CI gate**). Corrected
   throughout: gate is `--all`; `--added-only` moves to `.pre-commit-config.yaml` (a file this
   issue had never named); the skill path scans whole files. Consequence accepted: the baseline
   returns to the critical path, at ~4 min with the tiering and parallelism already specified.
2. **`git log -p` output is a diff, and matching it raw never finds a multi-line span.** With
   whitespace collapsed, the `+`/`-` line prefixes land *between* the joined lines. Measured on a
   span known to be present in `text_utils.py`'s history: raw -> **False**, prefix-stripped ->
   True. Every multi-line quote would have false-positived at the history tier. New Decision Rules
   → Patch-text preparation, plus a fixture that fails without it.
3. **Nearest-preceding attribution misfires on the ``symbol (`path`)`` idiom** — pervasive in
   `### Codebase Research Findings`, an in-scope section. Demonstrated on this issue: line 305's
   `` `read_blob_at_ref()` `` (18 raw chars, above the floor) inherits
   `codequery/fallback.py:50` from earlier in the same line. Verified — 0 occurrences in any
   revision of `fallback.py`, 1 in the `blob_reader.py` its own following parenthetical names. A
   following parenthetical now overrides nearest-preceding.
4. **BUG-3282 self-flags, by construction.** Its `## Current Behavior` reproduces the two BUG-3278
   fabrications, in an in-scope section, under an ENH-3277 attribution — because reporting a
   fabricated quote requires quoting it. Named as the **counter-example class**; handled by the
   escape hatch, not by the matcher (no reliable negation detection). Implementation step 6b
   annotates the block, and the post-annotation clean run is the acceptance signal Motivation asked
   for.

**Smaller**
5. **Inline extraction is new code.** `text_utils.py` has no inline-backtick primitive —
   `fence_spans()`/`in_fence()` handle fences only. Step 2 said "rather than new regex", but all
   three flagship must-flag spans are inline runs, so this is the bulk of extraction.
6. **Char floor is measured on raw text.** `(13, 22]` holds for raw; the same spans normalize to 18
   and 8, so a post-normalization floor would need `(9, 18]`. Stated explicitly and pinned by a
   test, since applying raw bounds to normalized text drops the floor below both calibration
   points.
7. **Fixture was non-hermetic.** ENH-3277 is `status: open` and its history keeps growing — 12
   revisions at capture, **17** now (the "all 12 revisions" phrasing was stale in four places). If
   the test resolves ENH-3277 live, any future edit quoting these strings into it silently flips
   the must-flags into passes. Both sides must be pinned, or materialized into a temp repo.
8. **Command-output exclusion must cross blank lines**: invocation at `:42`, blank `:43`, fence
   opens at `:44`. Adjacency-only makes the exclusion dead code on the one case that justifies it.
9. **`:43-49` -> `:44-49`** in three places; the fence opens at `:44`.
10. **Verdict precedence was unspecified.** An issue can be both `PROPOSAL_UNSOUND` and
    `EVIDENCE_UNVERIFIED` (BUG-3278 is exactly that shape) and the frontmatter holds one value.
    Decided: evidence outranks proposal, and the new gate is placed *ahead* of
    `check_proposal_unsound`.
11. **Loop routing target corrected**: `check_proposal_unsound.on_yes` targets
    `check_reconcile_limit`, not `reconcile_issue`. Routing straight to `reconcile_issue` would
    bypass the reconcile-attempt counter.

Re-verified and left standing: every code anchor cited by this issue resolves
(`verify_private_refs.py:66/297/418/446/461/527`, `text_utils.py:64/97/229`, `issue_parser.py:92`,
`check_verify_verdict.py:22-44`, `verify_cli_allowlist.py:62/74/109`,
`test_wiring_cli_registry.py:71-76`, `refine-to-ready-issue.yaml:350,353-365`, the 10-row verdict
table); the flagship fixture's line numbers `:35/:37/:38/:40/:42/:44-49/:58/:60` are exact against
the `baa553d9` blob; the three must-flag spans occur in **zero** revisions of ENH-3277; and
`Option A`, `Option B`, and `Option C` all match under emphasis normalization, so all three
designated true-negatives hold for the stated reason. Tracked `.issues/**/*.md` is now 3194.

## Session Log
- `/ll:confidence-check` - 2026-08-21T21:21:25 - `f6b03c29-ff65-4857-8be4-439d590930d1.jsonl`
- `/ll:confidence-check` - 2026-08-21T19:15:15 - `6e72bea6-f81f-494d-91ee-89b15f1562c6.jsonl`
- `/ll:confidence-check` - 2026-08-21T18:50:00 - `c9ef2e6f-97ff-48c5-ab63-1c421d2aa389.jsonl`
- `/ll:confidence-check` - 2026-08-21T18:24:15 - `50bb079c-e6a6-43cf-afbb-5f557001b12e.jsonl`
- `/ll:wire-issue` - 2026-08-21T18:11:26 - `de2bc4f7-6272-4f52-a9cb-998af08752f1.jsonl`
- `/ll:refine-issue` - 2026-08-21T17:44:39 - `169e7cf4-cd6f-42a2-b69c-b77a2737901b.jsonl`
- `/ll:capture-issue` - 2026-08-21T17:30:50 - `fa57a84b-34e0-4018-9e9e-dd57ed7ef3f3.jsonl`
