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
captured_at: '2026-08-15T18:17:37Z'
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

Two properties combine badly:

- **No fence awareness.** A `## Summary` line inside a fenced code block is
  indistinguishable from a real heading. Nothing in this function or its callers strips
  fences first.
- **Last occurrence wins** — a deliberate contract (docstring at `:245-248`, to support
  repeatedly-appended `## Confidence Check Notes`).

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

- **Test coverage gap (all four findings)**: `scripts/tests/test_symbol_claims.py` covers claim-grammar forms, fence exclusion for claims, and `symbol_resolves_elsewhere` against hand-built indices, but no test constructs a kwarg-call-argument-shaped line (e.g. `enabled=data.get("enabled", True)`) and asserts whether `_extract_symbols`/`_MODULE_CONSTANT_RE` admits it (Finding 1). `scripts/tests/test_text_utils.py` has no test of the shape `"A.md/B.md"` against `resolve_ref_path`/`suffix_match_candidates` (Finding 2). No test exercises `_section_body_with_offset` with a fenced code block quoting a `## Heading` line (Finding 4) — `_strip_code_fences` has coverage only for the `IssueParser` methods that already call it, not for `_section_body_with_offset`.
- **Related prior issues on this surface**: BUG-3063 (stale-symbol-ref forward-looking design claims) and ENH-3064 (checked directly — cancelled, addressed `stale_symbol_ref` *scoping* away from forward-looking sections, a different mechanism than this issue's `mislocated_symbol_ref` kwarg-index-pollution; no overlap). BUG-2956 (format-check ignores `program_design_not_applicable` opt-out) touches the same `format_check.py` orchestrator but a different gap class.
- **Finding 4 downstream blast radius confirmed**: `_symbol_claim_scope_text()` (`issue_parser.py:952-959`, feeds `stale_symbol_ref`/`mislocated_symbol_ref`) and `_behavior_parity_scope_text()` (`:930-940`, feeds `missing_behavior_parity`) both concatenate sections via the same fence-unaware `_section_body`, so Finding 4's fix affects those gap classes too, not only the `empty:`/`boilerplate:` verdicts already cited.

## Expected Behavior

**Finding 1** — a bare backticked token should not produce a `mislocated_symbol_ref` when
the "resolves elsewhere" half is satisfied only by index pollution. Candidate
discriminators, none decided here:

- Exclude kwarg-shaped matches from `_MODULE_CONSTANT_RE`. In this ruff-formatted
  codebase real assignments carry spaces around `=` (`_FIELD_FLAGS = (...)`,
  `ec = ...`) and kwargs do not (`enabled=data.get(...)`) — requiring `\s+=\s+` for the
  no-annotation branch removes the largest source cheaply, though it would not catch
  `ec`.
- Require a minimum length or a non-dictionary-word shape for the *bare* claim form
  (`_BARE_SYMBOL_RE`, `:52`) specifically, leaving the explicit `file:symbol` and dotted
  forms unfiltered. This is the closest analogue to the existing `_LINE_NUMBER_REF_RE`
  and `_EXTENSION_LIKE_RE` precedents.
- Require the symbol to resolve in a *bounded* number of files — a token appearing at
  "def-sites" in 15 files is index noise, not a locatable symbol.

Whatever is chosen must keep `install_qwen_adapter`-class hits firing.

**Finding 4** — strip fenced code blocks before resolving section headings. The codebase
already has fence-span machinery to reuse: `_CODE_FENCE` (`little_loops/text_utils.py`,
used by `symbol_claims._in_fence` at `:102`) and the fence-blanking pass at
`issue_parser.py:2389`. Keep the last-occurrence-wins contract for real headings — it is
load-bearing for `## Confidence Check Notes` — and only exclude fenced matches.

**Finding 2** — a backticked span containing `/` between two extension-bearing names
should not resolve as a single path. Either split on the slash and check each side, or
decline to claim (fail-open), consistent with the module's fail-open stance for
unsupported languages (`_SUPPORTED_SYMBOL_EXTENSIONS`, `:45`).

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

### Codebase Research Findings

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
- **Effort**: Small - Findings 2 and 3 are each a few lines. Finding 4 is a fence-strip
  reusing `_CODE_FENCE`/`_in_fence`. Finding 1 is a regex or filter change plus test
  cases; the module has an established pattern for exactly this kind of pin.
- **Risk**: Low - All four narrow what is reported. The stated risk is losing a true
  positive: Finding 1's discriminator must keep `install_qwen_adapter`-class hits firing,
  and Finding 4 must preserve last-occurrence-wins for genuine repeated headings
  (`## Confidence Check Notes`).
- **Breaking Change**: No, unless Finding 3 is resolved by renaming the gap key rather
  than rewording the message.

## Related Key Documentation

- `docs/reference/CLI.md` — `ll-issues format-check` gap-class list, if a key is renamed.
- `scripts/little_loops/issues/symbol_claims.py:25-90` — the existing false-positive pins
  and their rationale comments; a new filter belongs alongside them, documented the same
  way.

## Status

**Open** | Created: 2026-08-15 | Priority: P4


## Session Log
- `/ll:refine-issue` - 2026-08-15T18:31:06 - `705a3268-face-42d3-8ebd-956f7b640ea6.jsonl`
