---
id: BUG-3194
type: BUG
title: ll-issues format-check emits systematic false positives from kwarg-polluted
  symbol index and slash-joined file refs
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
testable: true
decision_needed: false
captured_at: '2026-08-15T18:17:37Z'
confidence_score: 100
outcome_confidence: 70
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# BUG-3194: ll-issues format-check emits systematic false positives from kwarg-polluted symbol index and slash-joined file refs

## Summary

Validating the BUG-3186..3192 issue set surfaced two noisy `ll-issues format-check` gap
classes; investigating them turned up four distinct findings, three real and one
working-as-designed:

1. **`mislocated_symbol_ref` over-fires on any common word.** The symbol index admits
   keyword arguments and local variables as def-sites, so "exists elsewhere" is satisfied
   for essentially any token and every bare backticked word becomes a mis-attribution.
2. **`stale_file_ref` misparses a slash-joined pair of filenames** as one path.
3. **`stale_file_ref` on gitignored-but-present files is correct** — "not git-tracked" is
   the intended predicate. Only the label misleads. No logic change warranted.
4. **Section lookup is fence-unaware and last-occurrence-wins**, so a `## Section` heading
   quoted inside a code fence silently overrides the real section. This one inverts the
   linter's verdict — issues with fully written sections are reported `empty:` and
   `boilerplate:` — and `format-check` is consumed as a gate by `/ll:confidence-check`,
   `/ll:ready-issue`, `/ll:refine-issue`, `/ll:wire-issue`, and `/ll:format-issue`.

Findings 1, 2, and 4 are independent fixes in three different modules; they are filed
together because they were found together and share the `format-check` surface.

## Implementation Order

**Finding 4 must land first, and should be implemented on its own.** It is the only one
of the four that inverts a verdict rather than adding noise, and three things depend on
it:

- It gates `/ll:confidence-check`, `/ll:ready-issue`, `/ll:refine-issue`,
  `/ll:wire-issue`, and `/ll:format-issue`. A false `empty:`/`boilerplate:` points
  `format-issue` at rewriting sections that are already correct.
- It removes BUG-3193's downstream harm before BUG-3193 itself is touched (the trailing
  placeholder scaffold wins the section lookup only because last-occurrence-wins is
  fence-unaware).
- Until it lands, `format-check`'s verdict on this issue, BUG-3192, and BUG-3193 cannot
  be trusted — all three quote markdown containing `##`-shaped lines. BUG-3193 currently
  escapes a false `empty: Summary` only by luck: the last `## Summary` in its fenced
  repro happens to be followed by non-boilerplate prose.

Findings 1, 2, and 3 are noise-level and can be batched together afterwards in any order.

**Recommended split**: promote Finding 4 to its own P2 issue and leave 1/2/3 here at P3.
Bundled under one P3, Finding 4 gets scheduled as noise.

### Split decision (2026-08-15 review)

**The split should happen, and the reason is now concrete rather than stylistic:**
BUG-3193 carries `depends_on: [BUG-3194]`, but its real dependency is Finding 4 alone. As
long as all four findings live in one issue, that edge blocks BUG-3193 on three unrelated
symbol-index and file-ref fixes — the edge over-blocks by construction, and no amount of
prose in either issue makes the dependency resolver see it.

Two ways to discharge this, in preference order:

1. **Split (preferred).** File Finding 4 as its own P2, repoint BUG-3193's `depends_on` at
   it, and leave Findings 1/2/3 here at P3 with the `depends_on` edge removed entirely.
2. **If the split does not happen**, land Finding 4 as the first commit under this issue
   and treat BUG-3193's edge as satisfied at that commit rather than at issue closure. This
   is a scheduling convention, not something the tooling enforces — it will read as blocked
   until this whole issue closes.

Not yet split — this block records the decision so it survives whichever path is taken.


## Current Behavior

Reproduced against the live issue set:

```
$ for i in 3186 3190 3191 3192; do ll-issues format-check $i; done
  mislocated_symbol_ref: ec (claimed in scripts/little_loops/cli/issues/epic_consistency.py)
  mislocated_symbol_ref: codex (claimed in scripts/little_loops/init/cli.py)
  mislocated_symbol_ref: install_qwen_adapter (claimed in scripts/little_loops/init/cli.py)
  stale_file_ref: ARCHITECTURE.md/CONTRIBUTING.md
  stale_file_ref: .ll/ll-continue-prompt.md
  stale_file_ref: docs/demo/scenarios.md
  mislocated_symbol_ref: enabled (claimed in scripts/little_loops/cli/learning_tests.py)
```

### Finding 1 — `mislocated_symbol_ref`: the symbol index admits kwargs and locals (real)

`_MODULE_CONSTANT_RE` (`scripts/little_loops/issues/symbol_claims.py:40`) is
`^[ \t]*([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=\n]+)?=(?!=)` — line-anchored with optional
leading whitespace. BUG-3063 D1 widened it deliberately, to admit indented class
attributes and dataclass fields, and the comment at `:33-39` records local-variable
admission as an accepted precision trade.

What that comment does not anticipate is **keyword arguments in multi-line calls**, which
match the same shape and are far more common than either locals or dataclass fields:

```
scripts/little_loops/config/features.py:351:            enabled=data.get("enabled", True),
scripts/little_loops/config/automation.py:76:            enabled=data.get("enabled", False),
scripts/little_loops/config/core.py:701:            enabled=src.enabled,
```

`enabled` is therefore indexed as a "symbol" in a dozen-plus files. The consequence is
structural: `symbol_resolves_elsewhere` (`symbol_claims.py:325`) is satisfied for
essentially **any** common English word, so the check collapses to "this bare backticked
token is not at a def-site in the cited file" — and reports it as a confident
mis-attribution. `ec` and `codex` fail the same way.

Note `install_qwen_adapter` in the same output is a *legitimate* hit — the class is noisy,
not worthless, so blanket suppression would lose real signal.

This module already treats systematic false-positive classes as defects worth pinning
(`_LINE_NUMBER_REF_RE` at `:56` for `L519`-style citations, `_EXTENSION_LIKE_RE` at `:65`
for backticked filenames misparsing as dotted claims, `_MAX_ATTRIBUTION_DISTANCE` at
`:78`). This is the next one in that series.

### Finding 2 — `stale_file_ref` on a slash-joined pair (real)

`ARCHITECTURE.md/CONTRIBUTING.md` is not a path. It comes from BUG-3190's own title —
"ARCHITECTURE.md/CONTRIBUTING.md directory trees list …" — where the slash is a
conjunction. The ref extractor reads the whole span as one repo-relative path, finds it
untracked, and reports it. Both real files exist and are tracked.

### Finding 3 — `stale_file_ref` on gitignored-but-present files (working as designed)

`docs/demo/scenarios.md` (`.gitignore:76`) and `.ll/ll-continue-prompt.md`
(`.gitignore:110`) both exist on disk and are correctly *not* git-tracked:

```
$ git check-ignore -v docs/demo/scenarios.md .ll/ll-continue-prompt.md
.gitignore:76:docs/demo         docs/demo/scenarios.md
.gitignore:110:.ll/ll-continue-prompt.md    .ll/ll-continue-prompt.md
```

`stale_file_ref` means "not git-tracked" by design, and that verdict is correct here. **No
behavior change is warranted for this finding.** The only defect is the label: `stale_`
reads as "this file is missing or outdated", and acting on that reading is what produced
the false claim corrected in BUG-3190 last session. This is a wording fix, not a logic
fix.

### Finding 4 — section lookup is fence-unaware and last-occurrence-wins (real, highest impact)

Found while validating this issue and BUG-3193: `_section_body_with_offset`
(`scripts/little_loops/issue_parser.py:239`) resolves a section with

```
pattern = rf"^##\s+{re.escape(heading)}\s*$"
matches = list(re.finditer(pattern, content, re.MULTILINE))
match = matches[-1]
```

Three properties combine badly:

- **No fence awareness.** A `## Summary` line inside a fenced code block is
  indistinguishable from a real heading. Nothing in this function or its callers strips
  fences first.
- **Last occurrence wins** — a deliberate contract (docstring at `:245-248`, to support
  repeatedly-appended `## Confidence Check Notes`).
- **The end-boundary scan is separately fence-unaware.** `re.search(r"^##\s",
  content[start:], re.MULTILINE)` (`issue_parser.py:259`) picks the section's terminator
  by the same fence-blind pattern.

So any issue that *quotes* markdown containing a `## <Section>` line — routine for issues
about issue formatting, templates, or docs — has that quoted heading silently override its
real section. Demonstrated on the first draft of BUG-3193, whose Current Behavior section
quotes a rendered template:

```
$ ll-issues format-check 3193
  empty: Summary
  boilerplate: Current Behavior
```

Both are false: Summary was written and Current Behavior was several paragraphs. The
quoted block won. Both issues in this pair had to have their reproduction fences rewritten
with a `>>` prefix purely to work around this.

#### Finding 4 has a second, wider symptom: the enclosing section is truncated

The fence-blind end-boundary scan is a distinct failure from "the quoted heading wins",
and it fires more often. Measured against a synthetic body whose `Current Behavior`
section contains a fenced block quoting a `Summary` heading (headings written with a `>>`
prefix here so this issue does not reproduce the bug on itself):

```
content:
  >> ## Summary            (real)
  >> Real summary.
  >> ## Current Behavior   (real)
  >> Prose before the fence.
  >> ```
  >> ## Summary            (quoted, inside the fence)
  >> placeholder junk
  >> ```
  >> More prose after the fence.
  >> ## Impact             (real)

_section_body(content, "Current Behavior")
  -> '\nProse before the fence.\n\n```\n'          <-- truncated at the fence

_section_body(content, "Summary")
  -> '\nplaceholder junk\n```\n\nMore prose after the fence.\n\n'
```

The second line is the already-documented symptom. The first is new: `Current Behavior`
is cut off at the opening fence, because the quoted heading terminates it. This fires
**even when the quoted heading is not itself a checked section** — any fenced
`##`-shaped line truncates whatever section encloses it, and short-truncated sections are
what `boilerplate:` and `empty:` actually grade. Both halves are fixed by the same
fence-aware pass, but a fix that only disambiguates *which* heading match wins, without
also making the terminator scan fence-aware, leaves this half firing.

The same mechanism is what converts BUG-3193's duplicate scaffold from cosmetic to
verdict-inverting: the trailing placeholder copy wins the lookup, so format-check grades
the placeholder instead of the real content. Fixing Finding 4 removes the downstream harm
of BUG-3193 even before BUG-3193 itself is fixed — the two are independent but
compounding.

> **Note for anyone running `format-check` on this issue.** It reports
> `stale_file_ref` on `ARCHITECTURE.md/CONTRIBUTING.md`, `docs/demo/scenarios.md`, and
> `.ll/ll-continue-prompt.md` — the three refs quoted above as evidence. Those are the
> very false positives this issue documents (Findings 2 and 3), so the gaps are expected
> and must not be "fixed" by removing the evidence. This issue is otherwise structurally
> compliant. Relatedly, BUG-3193's reproduction block had to be rewritten with a `>>`
> prefix instead of literal `## ` headings purely to work around Finding 4.

## Steps to Reproduce

**Findings 1-3** — against the issues as filed:

```bash
for i in 3186 3190 3191 3192; do ll-issues format-check $i; done
```

Expect `mislocated_symbol_ref` on `ec`, `codex`, `enabled` (Finding 1 — false),
`install_qwen_adapter` (a true positive, must keep firing), `stale_file_ref` on
`ARCHITECTURE.md/CONTRIBUTING.md` (Finding 2 — false), and on `docs/demo/scenarios.md` /
`.ll/ll-continue-prompt.md` (Finding 3 — correct verdict, misleading label).

Confirm Finding 3's files are present-but-ignored rather than missing:

```bash
git check-ignore -v docs/demo/scenarios.md .ll/ll-continue-prompt.md
ls -l docs/demo/scenarios.md
```

**Finding 2, brace-expansion shape** — run against BUG-3193, whose wiring pass emitted
three brace-expanded refs:

```bash
ll-issues format-check 3193
```

Expect `stale_file_ref` on `.gemini/skills/{capture-issue,scope-epic}/SKILL.md` and its
`.kimi-code`/`.qwen` siblings. All three directories exist; the braces are the defect.

**Finding 1, measuring a candidate discriminator** — confirm any proposed narrowing
actually drops `enabled` below the resolves-elsewhere threshold before implementing it:

```bash
python - <<'PY'
import re, pathlib
wide = re.compile(r"^[ \t]*([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=\n]+)?=(?!=)")
files = {str(p) for p in pathlib.Path('scripts/little_loops').rglob('*.py')
         for ln in p.read_text(errors='ignore').splitlines()
         if (m := wide.match(ln)) and m.group(1) == 'enabled'}
print(len(files), "files admit 'enabled' as a def-site")
PY
```

Baseline is 10. The `\s+=\s+` narrowing takes it to 8 — still resolving, still firing.

**Finding 4** — write any issue whose body quotes a markdown block containing a
`## Summary` line inside a code fence, then run `ll-issues format-check <id>`. It reports
`empty: Summary` even though the real Summary is written, because the fenced heading is
the last match.

## Program Design

Four independent change sites in three modules. They share only the `format-check`
reporting surface, so they can be implemented and landed separately.

### Signatures

```python
def extract_symbol_claims(body: str, ref_index: RefIndex) -> set[SymbolClaim]
def symbol_resolves_elsewhere(index: SymbolIndex, file: str, symbol: str) -> bool
def _extract_symbols(path: Path) -> set[str] | None
def _section_body_with_offset(content: str, heading: str) -> tuple[str, int] | None
def _print_gaps(gaps: FormatGaps) -> None
```

**Finding 1** has two candidate homes, and the choice is a blast-radius trade:
`extract_symbol_claims` (`scripts/little_loops/issues/symbol_claims.py:131`) parses
backticked spans into `SymbolClaim`s via three pinned grammar forms (`_EXPLICIT_RE:50`,
`_DOTTED_RE:51`, `_BARE_SYMBOL_RE:52`), and a claim-shaped filter belongs there beside the
existing `_LINE_NUMBER_REF_RE` / `_EXTENSION_LIKE_RE` exclusions. A definition-shaped
filter instead goes in `_MODULE_CONSTANT_RE` (`:40`) / `_extract_symbols` (`:203`), which
narrows the index for every consumer. `symbol_resolves_elsewhere` (`:325`) is the third
option — a resolves-in-N-files cap.

**Finding 2** is admitted by `resolve_ref_path` / `RefIndex`
(`scripts/little_loops/text_utils.py`), which resolves a cited path token to a tracked
repo-relative path and accepts the slash-joined span as one path.

**Finding 3** is the `stale_file_ref` branch of `_print_gaps`
(`scripts/little_loops/cli/issues/format_check.py:157`). Note the invariant recorded in
`cmd_format_check`'s docstring (`:198`): every `FormatGaps` class must have a matching
loop in `_print_gaps`, so renaming the key means touching `FormatGaps`, both enumerations
(`:64`, `:193`), and `_print_gaps` together. Rewording is a one-line change.

**Finding 4** is `_section_body_with_offset` (`scripts/little_loops/issue_parser.py:239`).
Fence-stripping goes there so every section-resolving caller inherits the fix.

### Types

`FormatGaps` (`scripts/little_loops/issue_parser.py:276`) — the per-class gap lists;
only Finding 3's optional rename touches it. `SymbolClaim` (`symbol_claims.py:93`) and
`SymbolIndex` (`:283`) carry Finding 1's claim and index sides respectively.

### Call Path

- `cmd_format_check` — CLI entry; calls `check_format_gaps` then `_print_gaps`.
- `check_format_gaps` — populates `FormatGaps`; calls `_section_body` for every required
  section (Finding 4's blast radius) and drives the symbol/file-ref checks.
- `_section_body` → `_section_body_with_offset` — Finding 4 change site.
- `build_symbol_index` → `_build_reverse_index` → `_extract_symbols` — Finding 1's index
  side.
- `extract_symbol_claims` → `symbol_resolves_elsewhere` — Finding 1's claim side.
- `_in_fence` and `_CODE_FENCE` — the existing fence-span helpers to reuse for Finding 4.
- `_print_gaps` — Finding 3 change site.

Consumers that would inherit any fix: `/ll:confidence-check`, `/ll:ready-issue`,
`/ll:refine-issue`, `/ll:wire-issue`, `/ll:format-issue`.

### Codebase Research Findings — Program Design

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

- **Test coverage gap (all four findings)**: `scripts/tests/test_symbol_claims.py` covers claim-grammar forms, fence exclusion for claims, and `symbol_resolves_elsewhere` against hand-built indices, but no test constructs a kwarg-call-argument-shaped line (e.g. `enabled=data.get("enabled", True)`) and asserts whether `_extract_symbols`/`_MODULE_CONSTANT_RE` admits it (Finding 1). `scripts/tests/test_text_utils.py` has no test of the shape `"A.md/B.md"` against `resolve_ref_path`/`suffix_match_candidates` (Finding 2). No test exercises `_section_body_with_offset` with a fenced code block quoting a `## Heading` line (Finding 4) — `_strip_code_fences` has coverage only for the `IssueParser` methods that already call it, not for `_section_body_with_offset`.
- **Related prior issues on this surface**: BUG-3063 (stale-symbol-ref forward-looking design claims) and ENH-3064 (checked directly — cancelled, addressed `stale_symbol_ref` *scoping* away from forward-looking sections, a different mechanism than this issue's `mislocated_symbol_ref` kwarg-index-pollution; no overlap). BUG-2956 (format-check ignores `program_design_not_applicable` opt-out) touches the same `format_check.py` orchestrator but a different gap class.
- **Finding 4 downstream blast radius confirmed**: `_symbol_claim_scope_text()` (`issue_parser.py:952-959`, feeds `stale_symbol_ref`/`mislocated_symbol_ref`) and `_behavior_parity_scope_text()` (`:930-940`, feeds `missing_behavior_parity`) both concatenate sections via the same fence-unaware `_section_body`, so Finding 4's fix affects those gap classes too, not only the `empty:`/`boilerplate:` verdicts already cited.

_Wiring pass added by `/ll:wire-issue`:_
- **`_section_body`/`_section_body_with_offset` consumers beyond `format-check`**: `scripts/little_loops/cli/issues/normalize.py:195,205`, `scripts/little_loops/cli/issues/check_acceptance_criteria.py:59,61`, and `scripts/little_loops/cli/issues/size.py:82,85` all import and call `_section_body` directly — each inherits Finding 4's fence-awareness fix (or lack thereof) for its own section resolution, confirmed by direct grep.
- **`check_format_gaps` consumers beyond the five named skills**: `scripts/little_loops/cli/issues/check_design.py:31,38` (Program Design specificity gate, "mirroring `check_format_gaps()`'s existing fail-open" per its own docstring) and `scripts/little_loops/cli/issues/sequence.py:18` ("mirrors the drift half of `issue_parser.check_format_gaps()`'s" gap detection) both confirmed by grep to call/reference `check_format_gaps` directly, independent of `cmd_format_check`.
- **`stale_symbol_ref` is scored, not just reported**: `skills/confidence-check/SKILL.md:196,201` and `skills/confidence-check/rubric.md:247` key on `stale_symbol_ref` (and `stale_cli_flag`) by name and apply a hard scoring cap (row value `10`) regardless of otherwise-higher scores — confirmed by direct grep. Since `stale_symbol_ref` shares the same fence-unaware `_symbol_claim_scope_text()` helper Finding 4 fixes, this fix changes confidence-check's real-world cap-trigger frequency even though no literal string in `rubric.md` needs editing.
- **`docs/reference/API.md`'s `check_format_gaps` doc block** (`#### check_format_gaps`, prose describing all twenty-one gap classes) — confirmed present and asserts, for `stale_file_ref`: "a `/`-qualified path with no exact or unique-suffix match against tracked files, i.e. genuine drift" (directly contradicted by Finding 3's relabeling) and for `stale_symbol_ref`/`mislocated_symbol_ref`: "matched by H2 span — BUG-3063 A1" with no fence-awareness caveat (incomplete after Finding 4). Needs a parallel update alongside any `docs/reference/CLI.md` change.
- **Second consumer of `resolve_ref_path`/`classify_file_ref` beyond format-check**: `scripts/little_loops/issues/research_triage.py` (backs `/ll:refine-issue` Step 3 axis triage, ENH-2971) — its coverage-fraction computation changes for any issue body containing a slash-joined filename pair, a behavioral side effect of Finding 2's fix independent of `format-check`'s own output.
- **`_section_body_with_offset` also backs option-locating helpers** not named in the issue: `locate_enumerable_options`/`_locate_directive_alternatives`/`count_enumerable_options` (`issue_parser.py:1251,1319,1328`), consumed by `scripts/little_loops/cli/issues/check_decidable.py`, `scripts/little_loops/cli/issues/locate_options.py`, and `scripts/little_loops/issues/fold_research_findings.py`. Finding 4's fence-stripping changes option-counting/location behavior for any issue whose `## Proposed Solution` (or fallback sections) quotes a fenced block containing `##`-shaped lines.

## Expected Behavior

**Finding 1** — a bare backticked token should not produce a `mislocated_symbol_ref` when
the "resolves elsewhere" half is satisfied only by index pollution.

**Measured, not assumed.** An earlier draft of this issue led with the kwarg-exclusion
discriminator ("real assignments carry spaces around `=`, kwargs do not — requiring
`\s+=\s+` for the no-annotation branch removes the largest source cheaply"). That was
measured over `scripts/little_loops/**/*.py` and **does not fix the reported case**:

```
files admitting `enabled` as a def-site today:   10
still admitting it after the \s+=\s+ change:      8
```

The reason is that the change only narrows the *no-annotation* branch. The annotated
branch of `_MODULE_CONSTANT_RE` (`(?::[^=\n]+)?=`) is untouched, and it admits
**function-signature keyword parameters** — `def f(*, enabled: bool = False)`,
`max_clients: int = 32` — identically to the indented dataclass fields BUG-3063 D1
deliberately let in. The two are not distinguishable by regex on a single line. With 8
files still resolving, `symbol_resolves_elsewhere` stays true and
`mislocated_symbol_ref: enabled` still fires. Signature parameters are a second pollution
source, independent of kwargs and not named in the original analysis.

#### The suppression must happen at the claim layer, not inside `symbol_resolves_elsewhere`

An earlier draft recommended a **bounded resolution count** applied inside
`symbol_resolves_elsewhere` — require the symbol to resolve in fewer than N files, on the
reasoning that a token appearing at "def-sites" in 8-15 files is index noise. The breadth
signal is right; the change site is wrong, and applying it there makes the reported output
strictly worse.

The gap-emitting call site (`issue_parser.py:785-791`) is an if/else with no third arm:

```python
if symbol_exists_in_file(symbol_index, claim.file, claim.symbol) is False:
    if symbol_resolves_elsewhere(symbol_index, claim.file, claim.symbol):
        gaps.mislocated_symbol_ref.append(...)
    else:
        gaps.stale_symbol_ref.append(...)
```

Making `symbol_resolves_elsewhere` return `False` for `enabled` does not suppress the
claim — it **routes it to `stale_symbol_ref` instead**. Both branches are fed by the same
`_symbol_claim_scope_text()` scope, so nothing filters it out downstream. And per the
wiring findings below, `skills/confidence-check/SKILL.md:196,201` and
`skills/confidence-check/rubric.md:247` apply a hard scoring cap (row value `10`) keyed on
`stale_symbol_ref` by name, which `mislocated_symbol_ref` does not carry. The "fix" would
convert a noisy advisory gap into a confidence-gate failure on the same issues.

#### Measured: no single discriminator covers the reported hits

Measured over every symbol gap in `.issues/` (352 total: 263 `mislocated_symbol_ref`, 89
`stale_symbol_ref`). Claim shapes among the 263 mislocated:

```
dotted   (state.action, config.prompt)   107
bare     (enabled, FSMExecutor)          154
explicit (file.py:sym)                     2
```

The three reported hits split across **two different mechanisms**:

```
symbol                 resolves in   breadth cap?   bare shape floor?
enabled                  19 files        kills           no
ec                        2 files         no            kills
codex                     2 files         no            kills
install_qwen_adapter      1 file         keeps ✓        keeps ✓   (true positive)
```

This corrects an earlier draft of this issue, which asserted the breadth cap was "the only
candidate that demonstrably kills the reported `enabled`, `ec`, and `codex` hits". It is
not: `ec` and `codex` resolve in **2 files each** and sail under any usable cap. They are
short common-word tokens, killable only by a shape/length floor.

**Second correction (2026-08-15 review): the table's last column is wrong for `enabled`.**
`enabled` is a bare all-lowercase token with no underscore, no internal capital, and no
`()` suffix — so the bare-form floor kills it too (4 of its claims are bare-form). All
three reported hits fall to the floor. The cap does **not** need to exist to clear the
reported output, and any acceptance check written against `enabled`/`ec`/`codex` will pass
with the cap unimplemented.

The cap is still worth keeping, but for a different reason than "it is what kills
`enabled`". Measured incrementally — kills the floor does *not* already cover, over all
`.issues/` mislocated claims:

```
after bare-form floor: 157 of 264 remain
  cap N=3  → 50 more    worktree_copy_files, completed_at, on_error, remote_name
  cap N=5  → 30 more    completed_at, on_error, request_path, issue_id
  cap N=8  → 22 more    completed_at, on_error, issue_id, blocked_by, exit_code, action_type
  cap N=12 → 12 more    issue_id, blocked_by, exit_code, action_type, run_dir
```

The N=8 survivors it removes are frontmatter and config field names (`completed_at`,
`blocked_by`, `on_error`, `exit_code`) — snake_case, so they clear the floor, and correct
to drop. That is the cap's real justification. Note `worktree_copy_files` (n=8) sits right
at the boundary and is a genuine symbol, which independently supports N=8 over N=3.

Breadth-cap threshold curve (claims dropped when resolving in more than N files):

```
N=1  drop 155/263    N=3  drop 129    N=5  drop 100    N=8  drop 87    N=12  drop 52
```

Survivors at N≤3 are overwhelmingly genuine symbols (`FSMExecutor`, `_resolve_db_path`,
`check_format_gaps()`, `cmd_install()`). The n=4-8 band holds ~25 noise claims against two
known true positives — `build_streaming()` and `build_blocking_json()`, both n=4, real
`host_runner` methods — which is what sets the threshold below.

**Third pollution source, not previously named: `_DOTTED_RE` admits config paths.** The
107 dotted claims are dominated by FSM/YAML config keys parsed as `module.attr` symbol
claims — `state.action` (n=117), `config.prompt` (n=28), `parallel.timeout_per_issue`
(n=7), `learning_tests.scan_dirs` (n=4). `_DOTTED_RE` (`:51`) never checks that the left
side is a real module or a PascalCase class, so any `namespace.key` in prose becomes a
symbol claim. This is the single largest class, and it is what fills the cap's boundary
band.

### Decision (resolved 2026-08-15)

**All three predicates, layered, with the breadth cap at N=8.** Each is applied as a
*claim drop* — the claim never reaches the exists/resolves branch, so no gap of either
class is emitted:

1. **Dotted left-side predicate** — decline a `_DOTTED_RE` claim whose left side is
   neither a tracked module name nor PascalCase. Clears the 107-claim config-path mass,
   including the n=117 `state.action` head.
2. **Breadth cap at N=8** — drop a claim whose symbol resolves in more than 8 files other
   than the cited one. Kills `enabled` (19). N=8 rather than N=3 deliberately: N=3 would
   drop 129 hits instead of 87, but takes `build_streaming()`/`build_blocking_json()`
   (n=4) with it. With predicate 1 clearing the dotted band, the looser cap costs little.
3. **Bare-form floor** — require a `_BARE_SYMBOL_RE` claim to be ≥3 characters *and* carry
   an underscore, an internal capital, or a `()` suffix. Kills `ec`, `codex`, **and
   `enabled`**; keeps `install_qwen_adapter`, `FSMExecutor`, `check_format_gaps()`.

   **Measured false-negative check (2026-08-15).** The floor drops 107 of the 264
   backlog-wide mislocated claims. Inspected in full, the dropped set is noise with no
   visible true positive — top tokens `jsonl` (12), `parallel` (6), `action` (5), `stderr`
   (4), `prompt` (4), `main` (4), `enabled` (4), `target` (3), `done` (3), `extract` (3),
   then a long tail of `tree`, `create`, `tools`, `error`, `resume`, `output`, `model`,
   `sqlite`, `list`, `check`, `apply`, `fix`. The stated hazard for this predicate —
   losing genuine single-word lowercase function names such as `main` or `execute` — is
   real in principle but does not appear in practice at any measurable rate; all four
   `main` hits are prose, not def-site claims. Re-run this measurement after implementing
   and confirm the dropped set still contains no genuine symbol.

All three must be wired as claim drops, **not** by changing what
`symbol_resolves_elsewhere` returns — see the routing hazard above.

Each follows the module's exclusion convention: a named module-level constant with a
comment naming the false-positive class it guards, applied as a guard at the point of use
(matching `_LINE_NUMBER_REF_RE` / `_EXTENSION_LIKE_RE`). None touches
`_MODULE_CONSTANT_RE`, so BUG-3063 D1's deliberate widening stays intact.

Reproduce the measurement above after implementing, and confirm the reported `enabled`,
`ec`, and `codex` hits disappear entirely rather than reappearing under the other gap key.

**Finding 4** — strip fenced code blocks before resolving section headings, for **both**
the heading match and the end-boundary scan (see the second-symptom subsection above).
The codebase already has fence-span machinery to reuse: `_CODE_FENCE`
(`little_loops/text_utils.py`, used by `symbol_claims._in_fence` at `:102`) and the
fence-blanking pass at `issue_parser.py:2389`. Keep the last-occurrence-wins contract for
real headings — it is load-bearing for `## Confidence Check Notes` — and only exclude
fenced matches.

**Implementation constraint — the returned body must be sliced from the original
content.** `_section_body_with_offset` returns `(body, start_offset)` where *body* is a
slice of the input. If the fix blanks fences and then slices the *blanked* text, every
section whose content is predominantly a code block comes back near-empty, and
`check_format_gaps` reports `empty:` on it — trading one systematic false positive for
another, on exactly the issue-about-tooling bodies this finding is meant to rescue. Use
the fence-blanked text **only to locate the heading offset and the terminator offset**,
then slice `content` (the original) at those offsets. Both offset-preserving idioms
catalogued below (span-exclusion via `_in_fence`, line-blanking via `_strip_code_fences`)
support this; `text_utils.strip_code_fences` does not, because it shifts offsets.

**Finding 2** — a backticked span that is not a single well-formed path should not resolve
as one. Scope this as **"decline on any span containing shell/glob metacharacters"**, not
as "split on `/`" — the slash-joined pair is one shape of a recurring class, not the whole
class. Brace expansion is a second, confirmed live shape:

```
$ ll-issues format-check 3193
  stale_file_ref: .gemini/skills/{capture-issue,scope-epic}/SKILL.md
  stale_file_ref: .kimi-code/skills/{capture-issue,scope-epic}/SKILL.md
  stale_file_ref: .qwen/skills/{capture-issue,scope-epic}/SKILL.md
```

Those three came from `/ll:wire-issue`'s own output on BUG-3193, which means the shape is
generated by tooling on a recurring basis rather than being a one-off authoring slip — the
same reason Finding 1's class is worth pinning. A `/`-only fix leaves all three firing.

Recommended predicate: if the span contains `{`, `}`, `*`, `?`, or resolves to more than
one extension-bearing component, decline to claim (fail-open), consistent with the
module's fail-open stance for unsupported languages (`_SUPPORTED_SYMBOL_EXTENSIONS`,
`:45`). Splitting and checking each side is acceptable for the slash case but does not
generalize to brace expansion without implementing expansion itself, which is not
warranted here.

**Finding 3** — rename the class or reword the message so it states the actual predicate.
`untracked_file_ref`, or keep the key and change the printed line
(`cli/issues/format_check.py:157`) to something like:

```
untracked_file_ref: docs/demo/scenarios.md (not git-tracked; it may exist on disk but
gitignored — verify before treating as missing)
```

Renaming the key touches `FormatGaps`, the two help/docstring enumerations
(`format_check.py:64` and `:193`), and any consumer keying on the JSON field; rewording
alone is a one-line change. Prefer the reword unless a consumer audit is cheap.

### Codebase Research Findings — Expected Behavior

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

- **Finding 1 exclusion-constant convention**: every existing false-positive exclusion in `symbol_claims.py` (`_LINE_NUMBER_REF_RE:53-56`, `_EXTENSION_LIKE_RE:59-65`, `_MAX_ATTRIBUTION_DISTANCE:73-78`) is a separately named module-level `re.compile(...)` constant, preceded by a comment naming the false-positive class it guards against, and applied as an early-continue/guard at the point of use rather than folded into the defining regex itself. A new kwarg-exclusion filter should follow this same shape (named constant + comment + guard-site application), matching how `_MODULE_CONSTANT_RE`'s own BUG-3063 D1 comment documents its accepted precision trade-offs.
- **Two coexisting, non-identical fence idioms** are available for Finding 4, and they are not interchangeable: (1) span-exclusion — `_CODE_FENCE.finditer(body)` once, then a small `_in_fence(start, end, fence_spans)` predicate tests candidate match positions (independently reimplemented in both `symbol_claims.py:102-103` and `issues/prose_deps.py`, imported into `issue_parser.py:709-716` for the `soft_dep_hard_edge` scan); (2) line-based blanking — `IssueParser._strip_code_fences` (`issue_parser.py:2369-2392`) replaces fenced lines with blank lines while preserving line numbers, used ahead of two other extraction methods (`:2291`, `:2333`) but not ahead of `_section_body_with_offset`. A third variant, `text_utils.strip_code_fences` (`:58-65`), collapses fence text to nothing rather than preserving line positions — offsets shift, unlike the other two. `_section_body_with_offset` returns a `(body, start_offset)` tuple consumed positionally by callers, so an offset-preserving approach (span-exclusion or line-blanking) fits its existing contract; `text_utils.strip_code_fences`'s offset-shifting approach would not.
- **Finding 3 rewording precedent**: `FormatGaps` field names have never been renamed in the codebase's history (only additions, each with a comment citing the introducing issue ID — mirrored in `test_ll_issues_format_check.py`'s pinned expected-JSON fixture). Entry-string wording is added at one of two independent sites depending on whether it needs to appear in JSON output too: baked into the value at construction time (`issue_parser.py:787-791`, e.g. `stale_symbol_ref`/`mislocated_symbol_ref` entries), or appended only at print time as text-only supplementary guidance (`format_check.py:167-183`, e.g. the existing `mislocated_symbol_ref`/`soft_dep_hard_edge` parentheticals). A pure reword (Finding 3's stated preference) fits the print-time-only pattern; a key rename would touch all three synchronized sites (`FormatGaps` field, `to_dict()`, `_print_gaps`) plus the pinned JSON fixture.

## Impact

- **Priority**: P3 - Driven by Finding 4. `format-check` is not advisory: it gates
  `/ll:confidence-check`, `/ll:ready-issue`, `/ll:refine-issue`, `/ll:wire-issue`, and
  `/ll:format-issue`, and a false `empty:`/`boilerplate:` verdict points `format-issue` at
  rewriting sections that are already correct. Findings 1-2 are noise-level on their own
  (P4-ish) but have already caused one real downstream error — the false claim corrected
  in BUG-3190. Finding 3 needs a wording change only.
- **Effort**: Small - Finding 3 is a few lines and Finding 2 a fail-open predicate. Finding
  4 is a fence-strip reusing `_CODE_FENCE`/`_in_fence`. Finding 1 is a resolves-in-N-files
  cap plus test cases; the module has an established pattern for exactly this kind of pin.
  Note Finding 1's effort estimate assumes the cap — the cheaper-looking regex narrowing
  was measured insufficient (see Expected Behavior) and would be effort spent for no
  change in the reported output.
- **Risk**: Low - All four narrow what is reported. The stated risk is losing a true
  positive: Finding 1's discriminator must keep `install_qwen_adapter`-class hits firing,
  and Finding 4 must preserve last-occurrence-wins for genuine repeated headings
  (`## Confidence Check Notes`).
- **Breaking Change**: No, unless Finding 3 is resolved by renaming the gap key rather
  than rewording the message.

## Acceptance Criteria

Grouped by finding, since they land separately (see Implementation Order).

**Finding 4 (lands first, on its own):**

- [ ] A `##`-shaped line inside a fenced code block does not win section resolution over a
      real heading of the same name — `_section_body_with_offset` returns the real one.
- [ ] A fenced `##`-shaped line does not terminate the section that encloses it: the
      enclosing section's body extends past the fence to the next *real* heading.
- [ ] The returned body is sliced from the original content, not from fence-blanked text —
      a section whose content is entirely a code fence is not reported `empty:`.
- [ ] Last-occurrence-wins is preserved for genuine repeated headings
      (`## Confidence Check Notes`).
- [ ] `ll-issues format-check` on this issue, BUG-3192, and BUG-3193 reports no
      `empty:`/`boilerplate:` gap for a section that is in fact written.

**Finding 1:**

- [ ] The reported `enabled`, `ec`, and `codex` claims produce **no gap of either class** —
      verified explicitly against `stale_symbol_ref` as well as `mislocated_symbol_ref`, so
      each predicate suppresses rather than reroutes. All three fall to the **bare-form
      floor** (see the correction in Expected Behavior); do not use them to verify the cap.
- [ ] A dotted config-path claim (`state.action`, `parallel.timeout_per_issue`) produces no
      gap — the `_DOTTED_RE` left-side predicate declines it.
- [ ] The **cap** is verified against a claim the floor does not already catch — e.g.
      `completed_at`, `on_error`, `blocked_by`, `issue_id`, or `exit_code` (all snake_case,
      so they clear the floor; all resolve in >8 files). Without this, the cap can be
      omitted entirely and every other Finding 1 criterion still passes.
- [ ] `build_streaming()` and `build_blocking_json()` (n=4 each) still fire — the cap is at
      8, not 3, specifically to preserve them.
- [ ] An `install_qwen_adapter`-class true positive — a genuine multi-word snake_case
      symbol claimed against a file that does not define it but that resolves at a real
      def-site elsewhere — still fires `mislocated_symbol_ref`.
- [ ] Each new filter follows the module's exclusion convention: a named module-level
      constant with a comment naming the false-positive class it guards, applied as a guard
      at the point of use (matching `_LINE_NUMBER_REF_RE` / `_EXTENSION_LIKE_RE`).
- [ ] Backlog-wide mislocated count drops from its measured **264** baseline (re-measured
      2026-08-15; the earlier 263 predates one issue edit); re-run the measurement and
      record the new number.

**Finding 2:**

- [ ] `resolve_ref_path("ARCHITECTURE.md/CONTRIBUTING.md", index)` declines rather than
      resolving as one path.
- [ ] `resolve_ref_path(".gemini/skills/{capture-issue,scope-epic}/SKILL.md", index)` also
      declines — a `/`-split-only fix passes the first case and fails this one.

**Finding 3:**

- [ ] The printed line for a present-but-gitignored ref states the actual predicate (not
      git-tracked), rather than implying the file is missing or outdated.
- [ ] If the reword-only path is taken, `test_ll_issues_format_check.py`'s pinned
      expected-JSON fixture needs no edit; if the key is renamed instead, `FormatGaps`,
      `to_dict()`, `_print_gaps`, both enumerations (`format_check.py:64`, `:193`), and
      that fixture are updated together.

**All findings:**

- [ ] `docs/reference/API.md`'s `check_format_gaps` prose and `docs/reference/CLI.md`'s
      gap-class list match the shipped behavior.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Key Documentation

- `docs/reference/CLI.md` — `ll-issues format-check` gap-class list, if a key is renamed.
- `scripts/little_loops/issues/symbol_claims.py:25-90` — the existing false-positive pins
  and their rationale comments; a new filter belongs alongside them, documented the same
  way.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` (`#### check_format_gaps` prose block) — the `stale_file_ref` bullet's "genuine drift" framing and the `stale_symbol_ref`/`mislocated_symbol_ref` bullets' "matched by H2 span" framing both go stale under Findings 3 and 4 respectively; update alongside `docs/reference/CLI.md`.
- `scripts/little_loops/issue_parser.py:943-949` — the `_STALE_SYMBOL_SCOPE_H2_SECTIONS` allowlist comment ("only claims inside their H2 span... matching the behavior-parity helper's H2 branch") asserts the pre-Finding-4, fence-unaware framing; update alongside the fence-stripping fix so the in-code comment doesn't contradict the new behavior.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_symbol_claims.py` (`repo`/`build_symbol_index` fixture, lines 30-40, 160-180) — new test to write: a kwarg-call-argument-shaped line (e.g. `enabled=data.get("enabled", True),`), asserting `_extract_symbols`/`symbol_exists_in_file` does not admit it as a symbol (Finding 1). Follow the fixture shape used at lines 160-180.
- `scripts/tests/test_text_utils.py::TestMirrorTieBreak` (lines 266-382, inline `RefIndex(by_basename={...})` construction) — new test to write: `resolve_ref_path("ARCHITECTURE.md/CONTRIBUTING.md", index)` should not resolve as a single path (Finding 2). Model on `test_genuine_non_mirror_ambiguity_still_declines` (lines 301-312)'s two-assertion pattern. **Add a second case for the brace-expansion shape** — `resolve_ref_path(".gemini/skills/{capture-issue,scope-epic}/SKILL.md", index)` must also decline; a `/`-split-only fix passes the first case and fails this one, so both are needed to pin Finding 2's corrected scope.
- `scripts/tests/test_issue_parser.py::test_with_offset_returns_start_of_last_match` (~4352-4363) — shows the exact direct-import call shape (`from little_loops.issue_parser import _section_body_with_offset`) to reuse for a new fenced-heading test (Finding 4): construct `content` with a `## Summary` line inside a fenced code block plus a real `## Summary` section, assert the returned body/offset points at the real one. Add a companion test confirming last-occurrence-wins is preserved for genuine (un-fenced) repeats, e.g. `## Confidence Check Notes`.
- `scripts/tests/test_ll_issues_format_check.py::test_clean_issue_json_output` (lines 302-362) — exact-dict-equality fixture over all `FormatGaps` keys with empty-list values; confirmed **not** sensitive to Finding 3's message-wording reword (only to a key rename, which the issue's stated preference avoids). No edit needed under the print-time-only reword path.
- `scripts/tests/test_symbol_cli_claim_sweep.py::test_symbol_and_cli_flag_claim_sweep_report_only` (line 72) — repo-wide ceiling assert (`total_symbol_hits <= 18`); Finding 1's fix will lower the real count but won't fail this `<=` ceiling. Its docstring's measured-baseline comment (lines 7-13) becomes a stale number worth updating (not test-enforced).
- No existing test guards that `install_qwen_adapter`-class true positives keep firing after Finding 1's discriminator narrows kwarg/local noise — new regression test to write alongside `test_feat3048_symbol_cli_claim_gaps.py`'s existing `mislocated_symbol_ref` tests (~144-171, 225-315): a real multi-word snake_case symbol claimed against a file that doesn't define it but resolves via a genuine def-site elsewhere, asserting `gaps.mislocated_symbol_ref` still fires.
- **Finding 1's suppression test must assert on both gap keys.** `issue_parser.py:785-791` is an if/else, so a discriminator implemented in the wrong place reroutes a suppressed `mislocated_symbol_ref` into `stale_symbol_ref` and a test asserting only `symbol not in gaps.mislocated_symbol_ref` passes on a regression. Assert absence from `gaps.stale_symbol_ref` in the same test.
- **Finding 4 needs a third test beyond the two above**: a section whose body is entirely a fenced code block must not be reported `empty:` — this is what catches a fix that returns the fence-blanked body instead of slicing the original. Pair it with a test asserting the *enclosing* section is not truncated at a fenced `##`-shaped line (the end-boundary half), which is separate from the which-heading-wins assertion.

## Status

**Open** | Created: 2026-08-15 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-15T20:01:26 - `4eb27027-e6df-4ea9-a6cc-2ca5e6e40c15.jsonl`
- `/ll:wire-issue` - 2026-08-15T18:50:55 - `fbae9292-fc5e-470b-b261-173e14415c63.jsonl`
- `/ll:refine-issue` - 2026-08-15T18:31:06 - `705a3268-face-42d3-8ebd-956f7b640ea6.jsonl`
