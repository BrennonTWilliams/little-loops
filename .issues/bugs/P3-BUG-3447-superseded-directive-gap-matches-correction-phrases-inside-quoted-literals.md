---
id: BUG-3447
type: BUG
title: superseded-directive gap matches correction phrases inside quoted literals
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-11'
captured_at: '2026-09-11T03:57:18Z'
confidence_score: 95
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3447: superseded-directive gap matches correction phrases inside quoted literals

## Summary

`check_format_gaps`'s `unmarked_superseded_directive` detector matches its closed correction-phrase list as raw case-insensitive substrings over the whole `### Codebase Research Findings` body, so a phrase appearing inside a **quoted string literal or a backtick code span** is treated as an author-asserted correction. Quoting a warning message, error string, or exception text — exactly what a research-findings block should do — trips the gap and fails `ll-issues format-check`, even when the author superseded nothing.

Both available escapes are bad. Adding a `⚠ Superseded` marker to satisfy the gate is not inert: `superseded_marker_count` is consumed by `loops/autodev.yaml` as the ENH-2992 `contradiction` predicate term that routes an issue to `/ll:reconcile-issue`, so the easy fix injects a fabricated contradiction signal into autodev's routing. The alternative is contorting accurate prose to dodge a 7-phrase list.

## Current Behavior

`issue_parser.py:1189-1195`:

```python
findings_bodies = _heading_bodies(content, "Codebase Research Findings")
has_correction = any(
    phrase in body.lower()
    for body in findings_bodies
    for phrase in _SUPERSEDED_CORRECTION_PHRASES
)
```

`phrase in body.lower()` is an unguarded substring test. `_SUPERSEDED_CORRECTION_PHRASES` (`:1462-1470`) is `"is wrong"`, `"does not exist"`, `"will not work"`, `"must be dropped"`, `"target file is wrong"`, `"is stale"`, `"omit entirely"` — all ordinary phrasings that occur naturally inside quoted identifiers, warning names, and error messages.

When `has_correction` is true and none of `## Implementation Steps` / `### Files to Modify` / `## Acceptance Criteria` carries a `⚠ Superseded` marker (`_SUPERSEDED_MARKER_PREFIX`, `:1472`), the gap is appended (`:1201-1202`) and `ll-issues format-check` exits 1.

Verified reproduction — three bodies differing only in whether the phrase is prose, a quoted literal, or a code span, run through `check_format_gaps` on an otherwise-clean BUG file:

```
genuine correction in prose                -> unmarked_superseded_directive = True
phrase inside a quoted literal             -> unmarked_superseded_directive = True
phrase inside a backtick code span         -> unmarked_superseded_directive = True
```

The two false positives are indistinguishable from the true positive. Concretely, the quoted-literal case was a findings bullet reading: `` `test_hook_session_start.py:675` pins that DESIGN.md-sourced projects don't trip the "path does not exist" warning `` — the substring `does not exist` matched inside the quoted warning name.

## Expected Behavior

A correction phrase occurring inside a fenced code block, an inline backtick code span, or a quoted string literal must **not** set `has_correction`. The same phrase in the author's own prose must flag exactly as today. `ll-issues format-check` must exit 0 for an issue whose findings block only quotes artifacts.

The existing four behaviours pinned by `TestUnmarkedSupersededDirective` (`:1355-1468`) — correction without marker flags, marked line does not flag, correction phrasing outside a findings block does not flag, JSON reporting — must all continue to pass unchanged.

## Motivation

A structural linter that fails accurately-written issues teaches authors to distrust it, and this one fails them in the exact place they are being most rigorous. `### Codebase Research Findings` blocks exist to record verified facts about the codebase, and verified facts are quoted: warning strings, exception messages, test names, log lines. Six of the seven phrases in `_SUPERSEDED_CORRECTION_PHRASES` are ordinary English that occurs routinely inside such quotations, so the more precisely an author documents evidence, the more likely the gap fires.

The cost is not just a red lint. The cheapest way to clear it is to add a `⚠ Superseded` marker, and that marker is load-bearing elsewhere: `superseded_marker_count` (`issue_parser.py:2000-2024`) is read by `loops/autodev.yaml:1707` as the ENH-2992 `contradiction` predicate term that routes an issue to `/ll:reconcile-issue`. An author silencing a false positive therefore fabricates a contradiction signal, spending a reconcile dispatch (capped at 2 per issue) on an issue that has nothing to reconcile. The alternative — rewording accurate prose to dodge a closed phrase list — degrades the evidence record the block exists to hold. Both outcomes were observed on 2026-09-11 while editing ENH-3441, where the phrase had to be reworded from a quoted warning name to "the missing-token-path warning" purely to clear the gate.

## Proposed Solution

Strip non-prose spans from each findings body before phrase matching. A minimal approach: remove fenced blocks (``` … ```), inline code spans (`` ` … ` ``), and **double-quoted runs** from a copy of the body, then run the existing substring scan over the residue. Three review refinements constrain the transform:

- **Single-quoted runs are out of scope.** Contractions and possessives (`won't`, `issue's`) put apostrophes mid-prose; a paired-`'` pattern would pair one with the next apostrophe anywhere later in the line and swallow the genuine prose between them — a false negative in exactly the case this fix must not create. No observed false positive involves single quotes (the ENH-3441 repro used double quotes); defer until a real single-quoted repro appears, optionally guarded then (opening `'` preceded by start-of-line, whitespace, or open punctuation — never a word character).
- **Double-quote pattern must accept curly quotes** (U+201C/201D) alongside ASCII `"`. `/ll:refine-issue`-authored findings blocks routinely use typographic quotes; ASCII-only would let the bug resurface on the first curly-quoted warning name.
- **Replace each removed span with a single space, not the empty string.** Empty replacement can join neighbouring fragments into a listed phrase that was never contiguous (`the flag "is" wrong` → `is wrong`); space replacement is the masking hygiene the in-file `template_placeholders` precedent uses.

This is a preprocessing step local to the `has_correction` comprehension; `_SUPERSEDED_CORRECTION_PHRASES`, `_SUPERSEDED_MARKER_PREFIX`, `_heading_bodies`, and `superseded_marker_count` are all unchanged.

Precedent for the shape of the fix: ENH-2999 narrowed `stale_file_ref` after it conflated absent with ambiguous references, and BUG-3147 corrected a matcher whose phrasing assumptions were too narrow. Both are completed; neither touches this gap class.

Care needed: stripping quoted runs must not blind the detector to a genuine correction the author placed in quotes for emphasis. If that trade-off is judged too coarse, an alternative is to require the phrase to appear outside any code/quote span **and** to co-occur with a directive-section identifier — but that is a larger change to ENH-2995's semantics and should be a separate decision.

### Tests

`scripts/tests/test_ll_issues_format_check.py::TestUnmarkedSupersededDirective` (`:1355-1468`) currently covers: correction without marker flags, marked line does not flag, correction outside a findings block does not flag, and single-ID JSON reporting. `TestSupersededMarkerCountKey` (`:1471`) covers the count key.

**Coverage gap**: no test places a listed phrase inside a quoted literal or a code span. Net-new cases: (a) phrase in a double-quoted literal (ASCII `"` and curly U+201C/201D variants) → no flag; (b) phrase in an inline backtick span → no flag; (c) phrase in a fenced block → no flag; (d) phrase in prose in the same file as (a)-(c) → still flags, proving the strip is scoped and not a blanket disable. Single-quoted runs are deliberately untested — the transform does not strip them (see Proposed Solution); if a future revision adds single-quote handling, add its case then.

### Documentation

`docs/reference/CLI.md` describes `format-check`'s gap classes; the `unmarked_superseded_directive` entry should note that quoted and code spans are excluded from phrase matching.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — the `has_correction` comprehension inside `check_format_gaps()` (`:1190-1194`), plus one new module-private stripping helper alongside it. No change to `_SUPERSEDED_CORRECTION_PHRASES` (`:1462-1470`), `_SUPERSEDED_MARKER_PREFIX` (`:1472`), `_SUPERSEDED_DIRECTIVE_SECTIONS` (`:1471`), `_heading_bodies` (`:2220`), `superseded_marker_count` (`:2000`), or the `FormatGaps` dataclass (`:540`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/format_check.py:623,639` — invokes `check_format_gaps` twice per issue (pre-fix and post-`--fix` state); the gap list surfaces verbatim in both text and `--format json` output, so the fix changes what those reports contain without changing their shape
- `scripts/little_loops/cli/issues/check_design.py:39-40` — calls `check_format_gaps(path)` then `design_gate_failed(gaps)`; unaffected, since `design_gate_failed` (`:644`) reads only the Program Design gaps, not `unmarked_superseded_directive`
- `scripts/little_loops/loops/autodev.yaml:1707` — consumes `superseded_marker_count` from the `format-check --format json` payload for the ENH-2992 `contradiction` predicate. Reads the *marker count*, not this gap list, so it is untouched by the fix — but it is the reason the false positive is costly rather than merely annoying, and it must stay unchanged
- `scripts/little_loops/cli/issues/deferred_triage.py:33` — weights `design_gate_failed`; unaffected

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/format_check.py:684,698` — [correction to the entry above] `check_format_gaps` has **four** call sites, not two: `:623`/`:639` are the `--all` sweep path; `:684`/`:698` are the single-issue-ID path — initial check and post-`--fix --apply` re-check — which is the path the repro (`ll-issues format-check <ID>`) and both loop gates exercise. All four share the `ref_index`/`symbol_index`/`cli_index` built once at `:608-612` [Agent 1 finding, confirmed]
- `scripts/little_loops/loops/rn-remediate.yaml:98-119` — the `ensure_formatted` gate: `evaluate: type: exit_code` on plain `ll-issues format-check "$ID"`; exit 1 routes to `format_issue`, exit 0 to `assess`. **Second FSM loop consumer not previously wired.** No edit needed (no code change in the loop) — but the fix changes its routing outcomes [Agent 2 finding, confirmed]
- `scripts/little_loops/issue_parser.py:515-517` — `_ADVISORY_GAP_CLASSES = {"testable", "unapplied_decision_detail", "orphaned_session_log_entries"}` does **not** contain `unmarked_superseded_directive`, so the gap feeds `has_blocking_gaps` (`:605-607`) and `cmd_format_check` returns `1` in all three output modes (`format_check.py:654-679`, `:732`, `:734-740`). This is why the false positive is exit-code-relevant to every gate consumer, not just report noise [Agent 2 finding, confirmed]
- `scripts/little_loops/loops/autodev.yaml:1686` — interaction strengthening the existing `:1707` entry: the capture is `FMT_JSON=$(ll-issues format-check "$ID" --format json 2>/dev/null || echo '{}')`, and single-issue JSON mode exits 1 on blocking gaps, so today a quoted-phrase-only false positive makes the payload unparseable (`{}` appended after the JSON) and the `except` at `:1708-1709` forces `markers = 0`. Post-fix such an issue exits 0 and its `superseded_marker_count` becomes readable on that path [Agent 2 finding, confirmed]
- `scripts/little_loops/cli/issues/__init__.py:152` — the `format-check` subcommand help string enumerates `unmarked_superseded_directive` verbatim among the gap classes. Name-level consumer only; no rename occurs, so no edit needed [Agent 1 finding, confirmed]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:364,494-505` — third loop shell-consumer of `format-check`: `normalize_structure` runs `--fix --apply || true` with no `evaluate` (pass-through by design) and `check_template_placeholders` reads only `template_placeholders` from the JSON. Unaffected [Agent 1/2 finding, confirmed]

### Similar Patterns
- `issue_parser.py:2270-2273` `_TESTABLE_PATTERNS` — precompiled word-boundary guards `(?<![a-z0-9_])...(?![a-z])` added for the ENH-2966 F1b/F1c false-positive class ("doesn't match inside an identifier or underscore-separated filename"). Same *class* of defect, different remedy: boundary guards would not fix this one, because `does not exist` matches with clean word boundaries inside a quoted literal
- `issue_parser.py:2283` `_BOLD_OPTION_MARKER` and `_OPTION_PATTERNS` — the BUG-3285 precedent for converging a matching rule so it is "encoded exactly once"; if a span-stripping helper is added, other substring scanners in this module are candidate follow-up consumers, but converting them is out of scope here
- `issue_parser.py:1903` `_unapplied_decision_pairs` — the ENH-3256 sibling detector, which already exempts paragraphs containing `_SUPERSEDED_MARKER_PREFIX`. It is the nearest example in this module of a matcher that carries an explicit contextual exemption, and is the shape to follow

_Wiring pass added by `/ll:wire-issue`:_
- `text_utils.py:64,97,108` — `fence_spans()` / `in_fence()` / `strip_code_fences()` are the existing fence primitives, **already imported into issue_parser.py at `:21`** (`from little_loops.text_utils import fence_spans, in_fence`). The module's own docstring names `check_format_gaps()` as an intended caller class. `_strip_non_prose_spans` should compose these rather than hand-roll fence handling [Agent 1/2 finding, confirmed]
- `issue_parser.py:2116-2136, 2173-2189` — the `template_placeholders` masking is the exact in-file composition precedent: `masks = fence_spans(content) + inline_spans`, then `in_fence` reused for containment [Agent 2 finding, confirmed]
- `issues/prose_deps.py:42`, `issues/cli_claims.py:19`, `issues/symbol_claims.py:98` — the shared single-backtick idiom `` _BACKTICK_SPAN_RE = re.compile(r"`([^`\n]+)`") ``, documented at prose_deps.py:39-41 (ENH-3061) as deliberately duplicated across the three claim scanners [Agent 1 finding, confirmed]
- `cli/verify_evidence.py:107,232` — `_INLINE_BACKTICK_RE` + `extract_candidate_spans()` is the closest combined fence+inline-backtick extractor; its comment notes text_utils carries no inline-backtick primitive [Agent 1 finding, confirmed]
- **Net-new surface**: no helper anywhere strips double/single-quoted string literals — the fence/backtick coverage is the full existing surface, so only the quoted-run pattern is genuinely new code [Agent 1/2 finding, confirmed by exhaustive search]

### Behavior Parity

Replaces nothing. This narrows one existing gap class's trigger condition; no code path is removed and no public contract changes. `FormatGaps.unmarked_superseded_directive` keeps its type (`list[str]`), its payload shape (issue filenames), and its four currently-pinned behaviors. `loops/autodev.yaml`'s `contradiction` predicate keeps reading `superseded_marker_count`, which counts `⚠ Superseded` markers in directive sections and is computed independently of this detector — so no autodev routing behavior changes. The only observable difference is that issues whose findings block merely *quotes* a listed phrase stop being reported.

### Tests
- `scripts/tests/test_ll_issues_format_check.py:1355-1468` `TestUnmarkedSupersededDirective` — four existing cases (flag without marker, no flag when marked, no flag for correction phrasing outside a findings block, single-ID JSON reporting) must all keep passing unchanged
- `scripts/tests/test_ll_issues_format_check.py:1471` `TestSupersededMarkerCountKey` — subclasses the above and pins the `superseded_marker_count` JSON key that `autodev.yaml` consumes; must stay green
- `scripts/tests/test_issue_parser.py:5146` — covers `superseded_marker_count`'s directive-section scoping
- `scripts/tests/test_autodev_loop.py:88,310` — drives the loop's `contradiction` branch from an injected `LL_FORMAT_CHECK_JSON` payload including `superseded_marker_count`; unaffected but worth running as the downstream consumer
- Net-new: four cases per Proposed Solution § Tests — phrase in a quoted literal, in an inline code span, and in a fenced block each report no gap, while a prose phrase in the same file still reports one

_Wiring pass added by `/ll:wire-issue`:_
- Existing broad consumers of `check_format_gaps`, all verified non-asserting on this gap class (fixtures use plain prose; no fixture relies on the false positive firing) — include in the Step 7 regression run: `scripts/tests/test_program_design_gate.py` (import `:55`, `TestFormatGapsWiring` `:815`), `scripts/tests/test_feat3048_symbol_cli_claim_gaps.py` (import `:10`, ~30 call sites incl. `test_check_format_gaps_spawns_no_subprocess` `:200`), `scripts/tests/test_symbol_cli_claim_sweep.py` (import `:23`, live-corpus sweep) [Agent 1/3 finding, confirmed]
- Conventions for the four net-new cases: follow `_write_bug_with_steps` (`test_ll_issues_format_check.py:1364`, built on `_CLEAN_BUG_BODY`/`_write_issue`/`_invoke`); case (d) mirrors `test_correction_in_preserved_section_not_flagged` (`:1415`) and the ENH-2966 pinned-true-positive convention (`TestTestableKeywordMatchPrecision`, `test_issue_parser.py:4393-4468`); fail-open cases for `_strip_non_prose_spans` follow `test_text_utils.py::TestFenceSpans::test_unterminated_fence_is_dropped_fail_open` (`:41`) [Agent 3 finding, confirmed]
- Verified no breakage: no existing test places a listed phrase inside a quoted literal/code span within a findings block; the JSON full-payload key assertion (`test_ll_issues_format_check.py:339`) pins the key, which is unchanged [Agent 3 finding, confirmed]

### Documentation
- `docs/reference/API.md:912` — the `unmarked_superseded_directive` gap-class entry; add that quoted literals and code spans are excluded from phrase matching
- `docs/reference/CLI.md:2439` — the same gap class described under `ll-issues format-check`; mirror the note
- `docs/reference/API.md:898` and `docs/reference/CLI.md:2338` both state a twenty-eight-class count and instruct re-deriving it from `dataclasses.fields(FormatGaps)`; no class is added or removed, so neither count changes

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:896` — already documents that `check_format_gaps` "backs … the `ensure_formatted` gate in `rn-remediate.yaml`"; corroborates the new Dependent Files entry. No edit needed [Agent 2 finding, confirmed]
- `docs/reference/CLI.md:2549` — the only place the full `--format json` payload shape is spelled out (example enumerates `unmarked_superseded_directive` and `superseded_marker_count`). Key set unchanged, no edit forced [Agent 2 finding, confirmed]
- `docs/reference/CLI.md:2446-2447` — adjacent tension to be aware of when editing `:2439`: this line (and the `check_format_gaps` docstring at `issue_parser.py:762-763`) characterize the gap as a "report-only keyword-inference heuristic (like `testable`)", while the code path treats it as blocking (not in `_ADVISORY_GAP_CLASSES`, feeds `has_blocking_gaps` and the exit code). Reconciling that wording is out of scope here, but the `:2439` edit lands next to it — don't propagate the "report-only" characterization into the new note [Agent 2 finding, confirmed]
- `commands/refine-issue.md:696-701` — conditional coupling only: this command mirrors the `_SUPERSEDED_CORRECTION_PHRASES` guidance verbatim (per the comment at `issue_parser.py:1459-1461`), with generated mirrors at `.kimi-code/skills/ll-refine-issue/SKILL.md:702`, `.gemini/commands/refine-issue.toml:684`, `.qwen/commands/ll/refine-issue.md:685`. The planned fix edits only API.md/CLI.md, so no mirror regeneration is needed; but **if** `commands/refine-issue.md` is edited to document the quoted-span semantics, `scripts/tests/test_wiring_skills_and_commands.py`'s mirror-staleness gate requires regenerating all three mirrors via `ll-adapt --host <qwen|kimi-code|gemini> --apply` [Agent 2 finding, confirmed]

### Configuration
- None — the detector has no config surface, and `.ll/program-design-cutover.json` arms only the Program Design gate, not this one

## Program Design

### Types

None new. `FormatGaps` (`issue_parser.py:540`) is unchanged — `unmarked_superseded_directive: list[str]` keeps its type and payload shape, and the twenty-eight-class count documented at `docs/reference/API.md:898` does not move.

### Signatures

- `check_format_gaps(issue_path: Path, templates_dir: Path | None = None, issue_statuses: dict[str, str] | None = None, ref_index: RefIndex | None = None, symbol_index: SymbolIndex | None = None, cli_index: CliSurfaceIndex | None = None) -> FormatGaps` — existing (`:684`); signature unchanged, the `has_correction` comprehension at `:1190-1194` gains a stripping call
- `_strip_non_prose_spans(text: str) -> str` (new, module-private, `issue_parser.py` beside `_SUPERSEDED_CORRECTION_PHRASES`) — returns *text* with fenced code blocks, inline backtick spans, and double-quoted runs (ASCII `"` and curly U+201C/201D) removed, each removed span replaced with a single space. Named for the transform's full surface, not just quotes — it strips fences and code spans too. Pure string transform, no I/O, no new parameters on any public function. Precompile its patterns at module load, matching `_TESTABLE_PATTERNS`' stated reason (`:2269`: "Precompiled once at module load so an `--all` sweep doesn't recompile … per issue")

### Call Path

`ll-issues format-check` -> `format_check.py:623` / `:639` -> `check_format_gaps()` -> `_heading_bodies(content, "Codebase Research Findings")` (`:1189`, unchanged) -> `_strip_non_prose_spans(body)` (new) -> existing substring scan over `_SUPERSEDED_CORRECTION_PHRASES` -> `gaps.unmarked_superseded_directive.append(issue_path.name)` (`:1202`, unchanged).

Independent path, deliberately untouched: `ll-issues check-design` -> `check_design.py:39` -> `check_format_gaps()` -> `design_gate_failed(gaps)` (`:644`), and `autodev.yaml:1707` -> `superseded_marker_count` (`:2000`).

Constraint: fail-open behavior is preserved. `check_format_gaps` already reports no gaps on an unresolved template or unreadable file rather than blocking; `_strip_non_prose_spans` must not raise on malformed markup (unbalanced backticks or an unterminated fence) — strip what it can recognize and return the residue.

## Implementation Steps

1. Outcome — quoted and code spans stop triggering the gap: `_strip_non_prose_spans` removes fenced blocks, inline backtick spans, and double-quoted runs (ASCII `"` and curly U+201C/201D, each removal replaced with a single space) from each findings body before the `has_correction` scan (`issue_parser.py:1190-1194`), so a bullet that only quotes a warning name, exception message, or test identifier reports no gap. Single-quoted runs are not stripped (contraction/possessive apostrophe-pairing hazard — see Proposed Solution)
2. Constraint — genuine prose corrections still flag: the four cases in `TestUnmarkedSupersededDirective` (`test_ll_issues_format_check.py:1355-1468`) and the `superseded_marker_count` key in `TestSupersededMarkerCountKey` (`:1471`) pass **unchanged**. This is a narrowing, not a disable — if the new tests pass by making the detector never fire, the change is wrong
3. Outcome — new coverage for the false-positive class: four cases added to `TestUnmarkedSupersededDirective` — listed phrase in a double-quoted literal, in an inline backtick span, and in a fenced block each report no gap; and a fourth file carrying the same phrase in prose *alongside* those three forms still reports one, proving the strip is scoped
4. Constraint — downstream consumers untouched: `superseded_marker_count` (`:2000-2024`) and `design_gate_failed` (`:644`) are not modified, so `loops/autodev.yaml:1707`'s ENH-2992 `contradiction` predicate and `cli/issues/check_design.py:39-40` behave identically. Run `scripts/tests/test_autodev_loop.py` to confirm the `contradiction` branch still routes from an injected marker count
5. Outcome — fail-open preserved: `_strip_non_prose_spans` returns the residue rather than raising on unbalanced backticks or an unterminated fence, keeping `check_format_gaps`'s documented fail-open contract. Note the fence check runs per-body: a fence opened inside a findings body but closed after the next heading slices as unbalanced and fails open (content past the slice boundary stays scannable) — that is acceptable and consistent with the contract; do not remap whole-content fence offsets to "fix" it
6. Outcome — docs match behavior: `docs/reference/API.md:912` and `docs/reference/CLI.md:2439` note that quoted literals and code spans are excluded from phrase matching. Neither the twenty-eight-class count nor `dataclasses.fields(FormatGaps)` changes
7. Verification: `python -m pytest scripts/tests/test_ll_issues_format_check.py scripts/tests/test_issue_parser.py scripts/tests/test_autodev_loop.py -v` exits 0, and `ll-issues format-check --all` reports no new `unmarked_superseded_directive` entries against `main` while still reporting the ones `main` legitimately has
8. Verification — the original repro clears: re-running the three-body reproduction (prose / quoted literal / backtick span through `check_format_gaps` on an otherwise-clean BUG file) yields `True / False / False` instead of today's `True / True / True`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Compose `_strip_non_prose_spans` from existing primitives rather than hand-rolling all three span types: fence handling via `text_utils.fence_spans`/`in_fence` (already imported at `issue_parser.py:21`), inline backticks via the shared `` r"`([^`\n]+)`" `` idiom (`issues/prose_deps.py:42` et al.), following the in-file composition precedent at `issue_parser.py:2116-2136`. The genuinely net-new regex surface is only the quoted-run pattern (ASCII `"` plus curly U+201C/201D; no single quotes) — no existing helper strips `"…"` anywhere
- Extend the Step 7 verification run with the three broad `check_format_gaps` consumers verified as non-asserting on this gap: `test_program_design_gate.py`, `test_feat3048_symbol_cli_claim_gaps.py`, `test_symbol_cli_claim_sweep.py`
- No `Update` bullets for the caller hits — none of the newly wired callers (`format_check.py:684,698`, `rn-remediate.yaml`, `autodev.yaml:1686`, `cli/issues/__init__.py:152`, `refine-to-ready-issue.yaml`) requires an edit: the change is confined to the scan predicate inside `check_format_gaps`, no signature or payload shape moves. Their routing *outcomes* change (issues whose only blocking gap was a quoted-phrase match flip exit 0, so `rn-remediate`'s `ensure_formatted` routes them to `assess` instead of `format_issue`, and autodev's `check_reconcile_needed` payload becomes parseable) — that is the intended effect, not a touchpoint
- Mirror-gate guard: the planned doc edits (API.md/CLI.md only) do not trip `test_wiring_skills_and_commands.py`; only editing `commands/refine-issue.md` would, requiring `ll-adapt --host <qwen|kimi-code|gemini> --apply` regeneration of its three mirrors

## Impact

- **Priority**: P3 - A false-positive advisory gate. It blocks nothing silently, but it fails `format-check` on accurately-written issues, erodes trust in the linter, and its cheapest workaround (adding a `⚠ Superseded` marker) feeds a fabricated contradiction signal into `autodev.yaml`'s reconcile routing.
- **Effort**: Small - One preprocessing helper plus four test cases; no changes to the phrase list, marker constant, or public gap keys.
- **Risk**: Low - Narrowing a detector risks false negatives, so case (d) above is required to prove genuine prose corrections still flag. No product-code behavior change.
- **Breaking Change**: No

## Steps to Reproduce

1. Take any issue that passes `ll-issues format-check`.
2. Add to a `### Codebase Research Findings` block a bullet that quotes an artifact containing a listed phrase — e.g. `` - The loader warns `"path does not exist"` and returns `None`. ``
3. Run `ll-issues format-check <ID>`.
4. Observe: exit 1 with `unmarked_superseded_directive: <file>.md`, though no directive was superseded and no correction was asserted.
5. Control: the same bullet with the phrase in plain prose (`- Step 1 does not exist in the current code`) flags identically — the matcher cannot tell the two apart.

## Root Cause

- **File**: `scripts/little_loops/issue_parser.py`
- **Anchor**: `in function check_format_gaps()` — the `has_correction` comprehension at `:1190-1194`
- **Cause**: The phrase list is matched as bare substrings against undifferentiated body text. Nothing strips fenced code blocks, inline code spans, or quoted string literals before matching, so text the author is *quoting* is scored as text the author is *asserting*. The gap class was added by ENH-2995 to detect a findings block that contradicts a directive section; a quotation is not a contradiction.

`_heading_bodies` (`:2220`) matching every `##`/`###` occurrence of the heading regardless of parent is **intentional and not the defect** — it is pinned by `test_ll_issues_format_check.py::TestUnmarkedSupersededDirective::test_all_reports_correction_without_marker`, which places the findings block under `## Implementation Steps` and expects a flag. `/ll:refine-issue` emits one findings block per parent H2 (ENH-2993), so scanning all of them is correct.

Note that the obvious fix does not apply: the neighbouring `_TESTABLE_PATTERNS` (`:2270-2273`) uses word-boundary guards `(?<![a-z0-9_])...(?![a-z])` for a similar false-positive class, but in the reproduction above `does not exist` matches with clean word boundaries inside the quoted literal. Boundary guards would not have prevented it. The needed guard is contextual (strip quoted/code spans), not lexical.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-11 | Priority: P3

## Verification Notes

Verdict at time of check: **VALID** (2026-09-11, `/ll:verify-issues BUG-3447 --auto` — no
findings, so no corrections were applied; this section is a record of what was verified).
- Core claim reproduced live: three bodies (phrase in prose / inside a quoted literal /
  inside a backtick span) run through `check_format_gaps` on an otherwise-clean BUG file
  yield `True / True / True` — the two false positives are indistinguishable from the true
  positive, as stated.
- Anchors spot-checked against the working tree, all exact: `has_correction` comprehension
  `issue_parser.py:1189-1194`, `_SUPERSEDED_CORRECTION_PHRASES` `:1462-1470`,
  `_SUPERSEDED_MARKER_PREFIX` `:1472`, `superseded_marker_count` `:2000`,
  `_ADVISORY_GAP_CLASSES` `:515-517` (confirmed `unmarked_superseded_directive` is NOT in
  it, so the gap is exit-code-blocking), `design_gate_failed` `:644`,
  `_unapplied_decision_pairs` marker-exemption logic `:1903`, the four `check_format_gaps`
  call sites `format_check.py:623,639,684,698`, `check_design.py:39-40`,
  `deferred_triage.py:33`, `cli/issues/__init__.py:152`, autodev `:1686`/`:1707`/`:1708-1709`
  (capture + contradiction predicate + `markers = 0` fallback), `rn-remediate.yaml:98-119`
  `ensure_formatted`, `refine-to-ready-issue.yaml:364`/`:494-505`,
  `TestUnmarkedSupersededDirective` `test_ll_issues_format_check.py:1355` with
  `TestSupersededMarkerCountKey` at `:1471`, `test_autodev_loop.py:88`/`:310`,
  `test_text_utils.py:41`, `text_utils.py:64,97,108`, `prose_deps.py:42`/`cli_claims.py:19`/
  `symbol_claims.py:98` backtick idiom, `verify_evidence.py:107,232`, docs anchors
  `API.md:898,912` / `CLI.md:2338,2439,2446-2447,2549`, and the refine-issue phrase-list
  mirror at `commands/refine-issue.md:696-701` + all three host mirrors.
- `loops/autodev.yaml` (no `scripts/little_loops/` prefix) is the established docs
  shorthand — `docs/reference/API.md:4636` uses it verbatim — not a stale path.
- Negative claim corroborated by grep: no helper anywhere in `scripts/little_loops/` strips
  double/single-quoted string literals (only unrelated `_QUOTED_HEREDOC_START_RE` matches);
  the quoted-run pattern is genuinely net-new surface.
- Motivation claim corroborated: ENH-3441 carries the reworded "missing-token-path warning"
  phrasing and no longer contains the original quoted "path does not exist" warning name.
- `ll-verify-evidence --json`: clean (0 findings). Decisions check: ran; no active required
  rules, so no conflicts. Graph-assisted checks skipped as leads-only — provider=codegraph,
  freshness=stale; every anchor was confirmed by direct read/grep instead.
- Re-verified 2026-09-11 (second pass, later same day): zero drift — no commits touch the
  anchored files since the pass above and `git diff 8fb8cb51f` is empty for `scripts/` and
  `scripts/tests/`, so anchors were spot-checked (all exact) rather than re-read in full.
  Core claim re-reproduced live: prose / quoted-literal / backtick-span yield
  `True / True / True` (fixture must carry a `TYPE-NNN` filename or `check_format_gaps`
  fails open at `:940` before reaching the detector). Negative claim re-confirmed by grep:
  no quoted-literal strip helper exists anywhere in `scripts/little_loops/`. Graph
  available and fresh (provider=codegraph, indexed 06:07Z) but no permitted query surface
  applies — anchors needed no relocation and the negative claim is an existence search,
  not a symbol-caller claim; grep decided. `ll-verify-evidence --json` clean (0 findings);
  decisions check ran clean. Verdict unchanged: **VALID**.

## Session Log
- `/ll:confidence-check` - 2026-09-11T14:57:30 - `82be8173-4732-4b92-b0f1-103080961e6c.jsonl`
- `/ll:verify-issues` - 2026-09-11T14:54:05 - `85f63897-cda3-4d0d-988b-7360d7c6afbe.jsonl`
- `/ll:confidence-check` - 2026-09-11T05:36:04 - `41114809-db81-4f83-950b-bb3150388af6.jsonl`
- `/ll:verify-issues` - 2026-09-11T05:17:23 - `15d5e157-51d9-4474-b082-905dd245a588.jsonl`
- `/ll:wire-issue` - 2026-09-11T04:46:15 - `b797cfc5-353d-4ded-bfc9-3ac3c197ee5c.jsonl`
- `/ll:refine-issue` - 2026-09-11T04:32:18 - `0d1c6be1-1aff-4c28-87b7-94b7fdbe8ea0.jsonl`
- `/ll:format-issue` - 2026-09-11T04:28:22 - `e17af008-b3e3-403f-afb0-6f0bdb764079.jsonl`
- `/ll:capture-issue` - 2026-09-11T04:00:50 - `515fc7bd-e601-4deb-8bd5-084871c22c6f.jsonl`
