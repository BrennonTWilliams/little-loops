---
id: BUG-3003
title: research-triage marks the analyzer axis covered while the Program Design gate
  is failing, so refine skips the enrichment BUG-3001 added
type: BUG
priority: P2
captured_at: '2026-08-02T18:20:00Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
labels:
- refine-issue
- research-triage
- program-design-gate
relates_to:
- BUG-3001
- BUG-3002
status: open
testable: true
decision_needed: false
confidence_score: 98
outcome_confidence: 90
score_complexity: 21
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 22
---

# BUG-3003: research-triage marks the analyzer axis covered while the Program Design gate is failing, so refine skips the enrichment BUG-3001 added

## Summary

BUG-3001 taught `/ll:refine-issue` to author `## Program Design` — the rule
lives in Step 5a (`commands/refine-issue.md:372-384`), sourced from the
`codebase-analyzer` agent's findings. But Step 5a is unreachable for the exact
population that needs it.

Step 3.0's research triage (`ll-issues research-triage`) evidences the
`analyzer` axis from `## Root Cause` and `## Current Behavior` only
(`scripts/little_loops/issues/research_triage.py:71`). `## Program Design` is
consulted by no axis. So an issue with a resolving, symbol-bearing Root Cause —
which describes every issue that has already been refined once, and therefore
every issue that reaches the Program Design gate a second time — triages
`analyzer: covered`. Step 3.1 (`refine-issue.md:189-193`) then says: with zero
unmet axes, "**skip Steps 4, 5a, and 5b entirely**" and proceed to 5c/6/6.5/6.7.

Step 6.7's gate fires, reports `program_design_nonspecific` still failing, and
its remedy instruction — "Revise that section (written in Step 5a above)"
(`refine-issue.md:752-756`) — has nothing to revise, because 5a was skipped and
no analyzer agent ran to source it from. Refine reports the gate as still armed
and exits without writing the section.

## Steps to Reproduce

1. In a stamped project (`.ll/program-design-cutover.json` present), take an
   issue that has been refined at least once — its `## Root Cause` cites
   resolving paths with backticked symbols — and whose `## Program Design` is
   missing, empty, or prose-only.
2. Run `ll-issues research-triage <ID> --json`. Observe
   `"analyzer": {"covered": true, ...}`.
3. Run `/ll:refine-issue <ID> --auto` (or `--auto --gap-analysis`).
4. Observe the no-op-triage report ("No research needed — all three axes already
   covered"), then Step 8's `## PROSE/PROGRAM DESIGN GATE` block reporting the
   gate still failing.
5. `git diff` the issue file: `## Program Design` is unchanged.

## Current Behavior

`triage_research_axes` (`scripts/little_loops/issues/research_triage.py:250`)
returns one `AxisCoverage` per axis from `_triage_axis` (`:303`), scored purely
from `_AXIS_SECTIONS` / `_AXIS_NEEDS_SYMBOL` reference resolution and staleness.
Nothing in that path reads the Program Design gate verdict.

`--full-rewrite` is the only mode that escapes it (`refine-issue.md:165-167`
sets `TRIAGE=""`, "a full rewrite does not trust what is already in the file"),
but it is the wrong instrument: it consumes `max_refine_count` budget
(`:684`), it re-derives all three axes, and it rewrites sections wholesale —
re-running it on a repeatedly-deferred issue is a rewrite cycle, not a fix.

## Expected Behavior

When the Program Design gate is active for an issue and the section is
missing/empty/boilerplate/non-specific, the `analyzer` axis is reported
**uncovered**, with an evidence string naming the gate as the reason. Refine
then spawns the analyzer agent, Step 5a runs, and the section gets written from
real findings — on the additive `--auto` / `--auto --gap-analysis` paths, with
no budget consumed and nothing removed.

The override is unconditional while the gate fails, so its steady state deserves
naming: an issue whose design genuinely cannot be made specific (a one-line
config change, a docs fix) will re-spawn the analyzer agent on **every**
subsequent refine, because Step 6.7 permits exactly one revision attempt and
never sets the opt-out itself. The escape already exists and is the intended
one — `program_design_not_applicable: true` in frontmatter short-circuits
`program_design_gate_active` (`program_design.py:435-437`), which silences the
override with no new code. That field stays a human decision; refine is
forbidden from writing it (`refine-issue.md:388`) and only recommends it in its
Step 8 report.

## Root Cause

The ENH-2971 triage was designed to answer "is this axis already evidenced by
the issue's own resolving references?" and its section map predates ENH-2852's
`## Program Design` requirement and BUG-3001's enrichment rule. Adding the
section to `_AXIS_SECTIONS["analyzer"]` would be the wrong repair in the
opposite direction — it would let a Program Design section *evidence* analyzer
coverage. The gate verdict has to act as an override that un-covers the axis,
not as another coverage source.

## Program Design

### Signatures

- `triage_research_axes(issue_path: Path, root: Path, *, index: RefIndex | None = None, change_times: ChangeTimeIndex | None = None, check_staleness: bool = True) -> tuple[AxisCoverage, ...]`
  (`scripts/little_loops/issues/research_triage.py:250`) — unchanged signature;
  gains a post-pass over the computed tuple before returning
- `AxisCoverage(axis: ResearchAxis, covered: bool, evidence: str)`
  (`:89`) — frozen dataclass; the override constructs a replacement instance
  rather than mutating
- `program_design_gate_active(issue_path: Path, content: str) -> bool`
  (`scripts/little_loops/issues/program_design.py:415`) — existing per-project
  stamp + grandfathering check, reused verbatim
- `grade_issue_section(issue_path: Path, body: str) -> DesignVerdict`
  (`:444`) — existing grader. Note it takes the **section body**, not the whole
  file, so the helper must extract the section first (see § Section Extraction
  below). `DesignVerdict.is_specific` is the failing predicate; it is *one of
  four* conditions the override fires on, not a drop-in equivalent of
  `program_design_nonspecific` (see § Predicate Scope below)
- `_section_body(content: str, heading: str) -> str | None`
  (`scripts/little_loops/issue_parser.py:222`) — the raw, **non**-fence-stripped
  extractor the grader's parity target uses
- New private helper:
  `_program_design_unmet(issue_path: Path, content: str) -> str` — returns an
  evidence string when the gate is active and the section is
  missing/empty/boilerplate/non-specific, `""` otherwise

### Predicate Scope

The override is **strictly wider** than `format-check`'s
`program_design_nonspecific`, and this is deliberate. In `issue_parser.py`
(`:474-490`), the grading call is reached only after three escapes:

- `for name in sorted(required & headings)` — a **missing** heading never enters
  the loop; it lands in `gaps.missing`
- `if not stripped: gaps.empty.append(name); continue` — an **empty** body never
  reaches grading
- `if template and _normalize_whitespace(stripped) == _normalize_whitespace(template):
  gaps.boilerplate.append(name); continue` — a body identical to the section's
  `creation_template` never reaches grading

So `program_design_nonspecific` covers exactly one of the four states this issue
cares about. The override must fire on all four; the correct parity statement is
against the **union** of `missing ∪ empty ∪ boilerplate ∪ program_design_nonspecific`
for the `Program Design` section.

The boilerplate case is worth naming on its own: Step 6.7 (`refine-issue.md:735-760`)
inspects only `program_design_nonspecific`, so a template-identical Program
Design section is invisible to the gate today. The override catches it (the
grader reads the template as non-specific), which is an improvement — but it
means the two checks are not equivalent and must not be specified as if they
were.

### Section Extraction

`research_triage.py` already carries `_section_text(content, heading)` (`:117`)
and it is the obvious reach for the new helper. **It is the wrong one.** It
returns `strip_code_fences(...)`, and `strip_code_fences`
(`text_utils.py:58-65`) deletes fenced blocks *entirely* — content included, not
just the fence markers.

Program Design's graded material is signature lines and call-path anchors, which
Step 5a's own template (`refine-issue.md:372-384`) demonstrates inside a fenced
block. Feeding a fence-stripped body to `grade_issue_section` therefore yields
`"section is empty"` for a correctly-designed section, the override fires, and
the analyzer agent re-spawns forever on exactly the issues that got it right —
while `format-check`, reading the raw body via `_section_body`, grades the same
section specific.

The helper must use `issue_parser._section_body` (or an equivalent
non-stripping extractor), never `research_triage._section_text`. This divergence
gets its own test.

### Call Path

`cmd_research_triage` (`scripts/little_loops/cli/issues/research_triage.py:45`)
→ `triage_research_axes` (`:250`) → per-axis `_triage_axis` (`:303`) →
**`_program_design_unmet`** (new) → `program_design_gate_active` /
`grade_issue_section` → override the `analyzer` entry to
`covered=False, evidence="Program Design gate: <reason>"`

Consumer side (unchanged code, changed behavior): `/ll:refine-issue` Step 3.0
reads the JSON → analyzer unmet → Agent 2 spawns → Step 4/5a run → Step 5a's
Program Design rule (`refine-issue.md:372-384`) writes the section → Step 6.7's
gate confirms it clears.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `AxisCoverage` (`research_triage.py:88-94`) is confirmed `@dataclass(frozen=True)`
  with exactly `axis: ResearchAxis`, `covered: bool`, `evidence: str`, plus a
  `to_dict()` method returning `{"covered": ..., "evidence": ...}` — `axis` is
  not duplicated inside the serialized value, it is the dict key
  (`cli/issues/research_triage.py:63-65`:
  `print_json({c.axis: c.to_dict() for c in coverages})`). The new helper's
  override must build `{"analyzer": {"covered": false, "evidence": "..."}}`
  through this same shape, not a bespoke one.
- `cmd_research_triage` (`cli/issues/research_triage.py:61`) calls
  `triage_research_axes(path, config.project_root)` — it does **not** pass
  issue `content` separately; `triage_research_axes` already reads the file's
  content itself internally. This confirms the override belongs inside
  `triage_research_axes`/`_triage_axis` (as Implementation Step 2 proposes),
  not as a second post-hoc pass in the CLI layer — the CLI has no `content`
  variable to hand it.
- `_AXIS_SECTIONS` / `_AXIS_NEEDS_SYMBOL` (`research_triage.py:69-78`) contain
  no `"Program Design"` key and no reference to `program_design` anywhere in
  the file today — confirmed via full-file read, not just the two lines the
  issue cites.
- `DesignVerdict` (`program_design.py:115-129`) is `@dataclass(frozen=True)`
  with `is_specific: bool = False` confirmed present, plus `reasons: list[str]`
  that `grade_program_design` populates with per-cause strings (`"section is
  empty"`, `"no signature-shaped line found..."`,
  `"no call-path anchors named..."`, `"no call-path anchor resolves..."`) —
  useful for composing `_program_design_unmet`'s evidence string verbatim from
  `verdict.reasons` rather than re-deriving a message.
- Every existing `AxisCoverage` construction site in `research_triage.py`
  (lines 285, 325, 333, 342, 352) builds a fresh instance via the constructor
  with all three kwargs — none use `dataclasses.replace` to mutate one field
  of an existing instance, even though `dataclasses.replace` is used elsewhere
  in the codebase (`cli/parallel.py:271`, `cli/sprint/run.py:771`, both on
  `config.parallel.epic_branches`, unrelated dataclass). The new post-pass
  should follow the local convention: construct a fresh
  `AxisCoverage(axis="analyzer", covered=False, evidence=...)` rather than
  `dataclasses.replace(existing, covered=False, evidence=...)`.
- The pattern this issue names as the model, `_gate_program_design`
  (`issue_parser.py:129-145`), operates on a `set[str]` (drop/keep a member)
  while `_program_design_unmet`'s override replaces a whole `AxisCoverage`
  record in a tuple — the shared shape is "base value computed independently
  of the gate, then a second function call taking `(issue_path, content)`
  adjusts it," not the exact data structure. Its deferred import
  (`from little_loops.issues.program_design import SECTION_TITLE,
  program_design_gate_active`, line 139) is inside the function body; other
  local imports in this codebase carry cycle-avoidance comments inconsistently
  (`parallel/worker_pool.py:601-610` spells out the full chain,
  `parallel/orchestrator.py:1096-1097` says only "avoid circular dependency",
  `issue_parser.py:139` and `program_design.py:398,422` carry no cycle comment
  at all) — a comment is stylistic here, not load-bearing.

## Integration Map

### Files to Modify
- `scripts/little_loops/issues/research_triage.py` — `triage_research_axes`
  (`:250-300`) post-pass and the new `_program_design_unmet` helper; the
  module docstring (`:1-10`) describes the triage contract and should note the
  override
- `commands/refine-issue.md` — Step 3.0 (`:160-187`) should state that a
  failing Program Design gate forces the analyzer axis unmet, so the skill's
  prose matches the CLI's behavior; Step 3.1's "skip 5a" carve-out (`:189-193`)
  needs a sentence noting this case cannot arise while the gate is failing.
  **The carve-out sentence must be conditional** — the no-op path is still
  entirely normal on unstamped and grandfathered projects, where the gate is
  inactive and the override never fires. Suggested wording: *"On a project where
  the Program Design gate is active, this branch cannot be reached while the
  section is missing or non-specific — Step 3.0's override forces `analyzer`
  unmet."* An unconditional sentence would be false, and Implementation Step 7's
  wiring test would lock the falsehood in.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/research_triage.py:45` — `cmd_research_triage`,
  the `--json` surface refine reads; no change expected
- `scripts/little_loops/issue_parser.py:487-490` — the
  `program_design_nonspecific` producer whose predicate this override must
  mirror; if the two drift, refine and format-check disagree about the same
  issue

### Similar Patterns
- `_gate_program_design` (`scripts/little_loops/issue_parser.py:129-145`) — the
  established shape for "consult the gate, then adjust a computed set", with a
  local import of `program_design` to avoid a module cycle. The new helper
  should follow it, including the deferred import.

### Tests
- `scripts/tests/test_research_triage.py` — unit coverage for
  `triage_research_axes`; add: gate active + section missing → analyzer
  uncovered with non-empty evidence; gate active + section empty → same; gate
  active + section boilerplate (identical to the `creation_template`) → same;
  gate active + section specific → analyzer coverage unchanged; gate active +
  section specific **inside a fenced code block** → analyzer coverage unchanged
  (the § Section Extraction regression — this test fails if the helper reaches
  for `_section_text`); gate active + `program_design_not_applicable: true` →
  analyzer coverage unchanged; gate **inactive** (unstamped/grandfathered
  project) → analyzer coverage unchanged even with no Program Design section
  (the regression that would otherwise fire on every legacy issue). None of the
  existing fixtures in this file stamp `.ll/program-design-cutover.json`, so
  no current test breaks — but a new gate-active test must assert
  `program_design_gate_active(...) is True` in setup (as
  `test_program_design_gate.py:668` does), or a missing stamp would silently
  test the wrong (inactive) branch.
- `scripts/tests/test_ll_issues_research_triage.py` — CLI/JSON surface; assert
  the override is visible in `--json` output. The `triage_project` fixture
  (`:28-50`) never writes a cutover stamp, so add the stamp file directly in
  the new test rather than relying on the fixture.
- `scripts/tests/test_program_design_gate.py` — gate semantics; unchanged, but
  the predicate-parity assertion belongs here or in the triage tests. Assert
  parity against the **union** of `missing`/`empty`/`boilerplate`/
  `program_design_nonspecific` for the `Program Design` section — an assertion
  written against `program_design_nonspecific` alone will fail on the
  missing-section case, which is the issue's primary population.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_refine_issue_command.py` — `TestResearchTriageWiring`
  (`:308-362`) does doc-string assertions (not execution tests, since
  `refine-issue.md` is prose) directly over the Step 3.0/3.1 text this issue's
  Implementation Step 4 plans to edit. Its `_step_3_text()` helper (`:311-315`)
  slices `"### 3. Research Codebase"` through `"### 4. Identify Knowledge
  Gaps"` and asserts on exact substrings — `"covered"`,
  `"Spawn exactly one Task per axis whose `covered` is `false`"`,
  `"fail open"`/`"fail-open"`, `"#### 3.1"`, and that `"4"`, `"5a"`, `"5b"` are
  each named as skipped steps. The new gate-override sentences added to Step
  3.0/3.1 must preserve every one of these substrings verbatim, and a new test
  (alongside `TestProgramDesignGapTaxonomy` at `:365`, which uses the same
  slice-and-assert idiom for BUG-3001's Step 4 prose) should assert the new
  Program Design gate override sentence is present in both sections.

### Documentation
- `docs/reference/API.md` — the `research_triage` section describing axis
  coverage rules
- `docs/reference/CLI.md` — `ll-issues research-triage` description, if it
  enumerates what makes an axis covered

### Configuration
- N/A — the override is gated by the existing
  `.ll/program-design-cutover.json` stamp; no new setting.

### Generated Mirrors (advisory, not hand-edited)

_Wiring pass added by `/ll:wire-issue`:_
- `.kimi-code/skills/ll-refine-issue/SKILL.md` and
  `.gemini/commands/refine-issue.toml` are build artifacts emitted from
  `commands/refine-issue.md` by `ll-adapt` (`scripts/little_loops/adapters/
  kimi.py`, `scripts/little_loops/adapters/gemini.py`, driven by
  `process_commands()` in `scripts/little_loops/adapters/core.py`). Both
  already echo the Step 3 TRIAGE JSON shape (confirmed at
  `.kimi-code/skills/ll-refine-issue/SKILL.md:169` and
  `.gemini/commands/refine-issue.toml:152,164,169,182`). No test in
  `scripts/tests/` asserts these mirrors stay in sync with the source
  command, so editing Step 3.0/3.1 will leave them stale until `ll-adapt` is
  re-run manually — not a blocking gate, but should not be forgotten.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `test_research_triage.py` is fixture-free (module docstring, lines 1-6:
  "Fixture-free tmp_path style, per test_issues_anchors.py"). Its helpers:
  `_make_repo(tmp_path, files) -> Path` (:44, real git repo with committed
  files), `_write_issue(root, body, name=...) -> Path` (:58, writes into
  `root / ".issues" / "enhancements"`), `_by_axis(result) -> dict[str,
  AxisCoverage]` (:66, indexes the returned tuple by axis for per-axis
  assertions), `_session_log(when: datetime | None) -> str` (:73 — `None`
  yields a `/ll:capture-issue`-only log with no refine timestamp; a
  `datetime` yields a `/ll:refine-issue` entry stamped to that time). New
  gate-override tests should reuse `_by_axis` to assert on the `analyzer`
  entry specifically.
- `test_program_design_gate.py`'s stamped-vs-unstamped fixture switch is
  `_make_project(tmp_path, *, stamp_date: str | None = None, body: str | None
  = None, filename=...) -> Path` (:106) — omitting `stamp_date` produces the
  gate-inactive case (no `.ll/program-design-cutover.json` written), passing
  it produces the gate-active case (writes
  `{"sha": "0"*40, "date": stamp_date}`). This is the exact fixture the new
  "gate inactive → analyzer coverage unchanged" regression test
  (Acceptance Criteria #2) should reuse rather than reimplementing a stamp
  writer in `test_research_triage.py`.
- Both test files import the function under test **locally inside each test
  method**, not at module top (`test_program_design_gate.py:137,157,175,...`)
  — matches this codebase's convention of deferred imports for
  `program_design` symbols specifically, independent of the cycle-avoidance
  rationale.

## Implementation Steps

1. Add `_program_design_unmet(issue_path, content) -> str` to
   `research_triage.py`, modeled on `_gate_program_design`
   (`issue_parser.py:129`) including the deferred import: return `""` unless
   `program_design_gate_active(issue_path, content)`; otherwise return an
   evidence string when the `## Program Design` section is absent, empty,
   boilerplate, or `grade_issue_section(...).is_specific` is False.
2. In `triage_research_axes`, apply the result as a post-pass over the computed
   tuple: replace the `analyzer` entry with
   `AxisCoverage(axis="analyzer", covered=False, evidence=<gate reason>)` when
   the helper returns non-empty. Leave `locator` and `pattern_finder` alone.
3. Extract the section body with `issue_parser._section_body` (or an equivalent
   non-stripping extractor) — **not** `research_triage._section_text`, which
   fence-strips and would false-positive on fenced designs (see § Section
   Extraction). Reuse `grade_issue_section` for the specificity verdict; do not
   re-implement the rules. The override's firing set is the union
   `missing ∪ empty ∪ boilerplate ∪ non-specific`, deliberately wider than
   `program_design_nonspecific` (see § Predicate Scope).
4. Update Step 3.0 of `commands/refine-issue.md` to document the override, and
   add the carve-out sentence to Step 3.1.
5. Add the triage unit tests and the CLI/JSON assertion listed above,
   including the gate-inactive no-regression case.
6. Update `docs/reference/API.md` (and `CLI.md` if it enumerates coverage
   rules).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

7. Extend `TestResearchTriageWiring` in `scripts/tests/test_refine_issue_command.py`
   (`:308-362`) with an assertion that Step 3.0's text names the Program
   Design gate override and Step 3.1 carries the carve-out sentence, using the
   file's existing `_step_3_text()` slice-and-assert idiom — without breaking
   any of that class's current substring assertions (`"covered"`, the
   `"Spawn exactly one Task..."` line, `"fail open"`/`"fail-open"`,
   `"#### 3.1"`, and `"4"`/`"5a"`/`"5b"` each named as skipped steps).
8. After editing `commands/refine-issue.md`, run `ll-adapt` to regenerate the
   stale Kimi/Gemini mirrors (`.kimi-code/skills/ll-refine-issue/SKILL.md`,
   `.gemini/commands/refine-issue.toml`) so they don't drift from the new
   Step 3.0/3.1 prose.

## Acceptance Criteria

- [ ] `ll-issues research-triage <ID> --json` reports
      `analyzer.covered == false` with a non-empty `evidence` naming the gate,
      for a stamped-project issue whose Root Cause is fully covered but whose
      `## Program Design` is missing, empty, or prose-only.
- [ ] The same command reports `analyzer` coverage **unchanged** when the gate
      is inactive (unstamped or grandfathered project), so legacy issues see no
      behavior change.
- [ ] The override fires exactly when `format-check` reports the
      `Program Design` section under any of `missing`, `empty`, `boilerplate`,
      or `program_design_nonspecific` — and not otherwise. (Parity is against
      that **union**, not against `program_design_nonspecific` alone: three of
      those four states are unreachable from that key by construction; see
      § Predicate Scope.)
- [ ] A Program Design section whose signatures and call path live inside a
      fenced code block grades **specific** and leaves `analyzer` coverage
      unchanged — the fence-stripping false positive from § Section Extraction
      does not occur.
- [ ] With `program_design_not_applicable: true` in frontmatter, the override
      does not fire and `analyzer` coverage is unchanged, even on a stamped
      project with no Program Design section.
- [ ] `python -m pytest scripts/tests/` exits 0.

**Manual verification** (not automatable in `scripts/tests/` — `refine-issue.md`
is prose, so the suite can only assert its text via the doc-string wiring test
in Implementation Step 7):

- [ ] `/ll:refine-issue <ID> --auto --gap-analysis` on a gate-failing issue
      spawns the analyzer agent, runs Step 5a, and leaves `## Program Design`
      non-identical (`git diff`) — without consuming `max_refine_count` and
      without removing any existing content.

## Impact

This is the reachability half of BUG-3001: the enrichment logic landed but is
skipped for the population it was written for. Until it is fixed, every
`/ll:refine-issue` invocation against an already-refined, gate-failing issue is
a no-op on the section — which is precisely what BUG-3002's Option A remedy
depends on working. **BUG-3002 should not land before this.**

It also removes the pressure to reach for `--full-rewrite` as a workaround,
which would consume refinement budget and risk rewrite cycles on repeatedly
deferred issues.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/issues/research_triage.py` | The axis-coverage rules being overridden |
| `commands/refine-issue.md` | Steps 3.0/3.1/5a/6.7 — the skipped-enrichment path |
| `scripts/little_loops/issues/program_design.py` | The gate and grader the override reuses |

## Status

**Open** | Created: 2026-08-02 | Priority: P2

## Session Log
- `/ll:confidence-check` - 2026-08-02T17:37:11 - `56afd66b-b3f3-426a-83f2-46a061360866.jsonl`
- `/ll:confidence-check` - 2026-08-02T17:30:03 - `c5ef70f3-437f-43be-bb35-1893a372ba4e.jsonl`
- `/ll:wire-issue` - 2026-08-02T17:26:14 - `e2fdaf31-eb6b-4aca-96c8-675e186b4757.jsonl`
- `/ll:refine-issue` - 2026-08-02T17:19:42 - `d4e1a696-c825-4495-8dd3-2bea701b05f3.jsonl`
