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
