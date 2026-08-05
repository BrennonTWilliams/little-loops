---
id: FEAT-3048
title: Verify symbol and CLI-flag claims in issue bodies (extend prose-claim gap taxonomy)
type: FEAT
priority: P2
status: done
discovered_by: capture-issue
discovered_date: 2026-08-04
captured_at: '2026-08-04T20:47:11Z'
completed_at: '2026-08-05T17:21:43Z'
parent: EPIC-2938
epic: EPIC-2938
relates_to:
- FEAT-2846
- ENH-2970
- ENH-2951
labels:
- cli
- issues
- gates
testable: true
confidence_score: 98
outcome_confidence: 76
score_complexity: 14
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 22
---

# FEAT-3048: Verify symbol and CLI-flag claims in issue bodies

## Summary

Issue bodies assert things about the codebase in backticks — that a function exists, that a
module owns a write path, that a CLI subcommand accepts a flag — and nothing checks them.
The FEAT-2846/2849/2850 series already built claim-extraction-and-verification for **one**
claim class (prose dependency claims: `extract_prose_deps` in
`scripts/little_loops/issues/prose_deps.py`, the `prose_dep_drift`/`stale_prose_dep` gap kinds
in `check_format_gaps()`, and a repo-wide pytest sweep). This issue generalizes that same
architecture to **symbol** and **CLI-flag** claims.

Scope note: **file-path claims are already covered** by the existing `stale_file_ref` gap kind
(`issue_parser.py` `FormatGaps.stale_file_ref`, populated in `check_format_gaps`). This issue
adds the two claim classes layered on top of a file path — the symbol inside it, and the flag
on a CLI subcommand.

## Current Behavior

No gate verifies a symbol or CLI-flag claim in an issue body. The only instruction that covers
it is prose: `skills/confidence-check/SKILL.md` Criterion 3, detection bullet 5 — *"Verify
claims in the issue against actual code (do referenced files/functions exist? do they behave as
described?)"* — with no CLI behind it. It is the sole prose-only gate in that skill; every other
check there has a CLI (`ll-issues check-design`, `check-open-questions`, the Phase 1.6
Program Design pre-fetch).

Concrete failure that motivated this issue — FEAT-2942 asserts:

> Reuse `ll-issues link` / `frontmatter.update_frontmatter` for writes

but `scripts/little_loops/cli/issues/link.py` defines
`_FIELD_FLAGS = ("blocked_by", "depends_on", "relates_to")` and has no `parent`/`epic` branch,
so `ll-issues link` **cannot** set `parent:` — the field the whole feature is about. The claim
was authored in that file's first commit (`2225b414`) and survived `/ll:refine-issue`,
`/ll:wire-issue`, and `/ll:confidence-check` untouched. `/ll:wire-issue` even edited the
adjacent sentence and hedged on top of the bad premise rather than checking `link.py`.

## Expected Behavior

`check_format_gaps()` grows two gap kinds, reported through the existing `format-check` surface
and swept repo-wide in pytest:

- `stale_symbol_ref` — a backticked `symbol` attributed to a cited file that does not resolve
  in that file (function, class, or module-level constant).
- `stale_cli_flag` — a backticked CLI invocation (`ll-issues link --parent`, `ll-loop run
  --foo`) naming a subcommand or flag that the argparse parser does not accept.

Both follow the `prose_dep_drift`/`stale_file_ref` precedent: extractor in
`little_loops/issues/`, gap-kind fields on `FormatGaps`, printed by `format_check.py`, gated by
a repo-wide pytest sweep per FEAT-2850.

## Motivation

Three review passes and a 93/76 confidence score did not catch a false claim about the core
write path of the feature being specified. Claim verification is mechanical — file, symbol, and
argparse introspection are all deterministic lookups — which makes it exactly the kind of work
EPIC-2938 exists to move out of prose and into a tested CLI. It is also the highest-leverage of
the review-quality fixes: it catches the defect class that survives the most passes, because
existing passes are additive and never re-examine text already in the issue.

## Proposed Solution

Extend, don't scaffold. The pieces already exist:

- **Extractor** — new module beside `little_loops/issues/prose_deps.py`, same shape:
  regex over the body, fence-aware (`_in_fence`), returning structured claims.
- **Gap kinds** — add `stale_symbol_ref` and `stale_cli_flag` to `FormatGaps`
  (`issue_parser.py`), populated in `check_format_gaps()` alongside `stale_file_ref`.
- **Reporting** — add the two kinds to `format_check.py`'s `_print_gaps()` printer, to the
  subparser's static `help=` string, to `cmd_format_check()`'s docstring "Gap classes:" block,
  and to the dispatcher listing in `cli/issues/__init__.py:139` (three duplicated lists; there
  is **no `--kinds` flag** — see Program Design).
- **Symbol resolution** — `little_loops/issues/anchors.py`'s `_ANCHOR_PATTERNS` (the
  per-language def-site regexes) is reusable raw material, but `resolve_anchor()` answers the
  *opposite* question ("what encloses line N"). The forward-existence helper
  (`does symbol X exist in file Y`) is new code built on those patterns.
- **CLI-flag resolution** — see § CLI-Flag Introspection Mechanism below. **This mechanism does
  not exist yet**, and the obvious approach (import the parser) does not work against this
  codebase's CLI shape.

**ENH-2970 correction (verified 2026-08-04):** ENH-2970 is the right conceptual precedent
(*"assert every documented command resolves"*), but its shipped form is **not** argparse
introspection. `scripts/little_loops/cli/verify_cli_docs.py` does not exist, no
`ll-verify-cli-docs` entry point is registered in `scripts/pyproject.toml`, and
`docs/reference/CLI.md` coverage is enforced by **hardcoded substring assertions** in
`scripts/tests/test_wiring_cli_registry.py` (e.g. `("docs/reference/CLI.md", "ll-doctor",
"FEAT-1504")`) — ENH-2972 appears to have absorbed the work when § CLI Tools moved out of
CLAUDE.md. **This issue must build the argparse-introspection helper itself.** Closest existing
shape is `scripts/little_loops/cli/verify_cli_allowlist.py` (entry-point parsing + drift exit
contract), not a flag-level introspector.

### CLI-Flag Introspection Mechanism

**Verified 2026-08-05.** Importing a parser is not viable here: only **six** modules expose an
extractable parser (`_build_parser()` in `cli/session.py:65`, `cli/ctx_stats.py:40`,
`cli/logs.py:2023`, `cli/history_context.py:123`, `cli/config.py:26`,
`cli/compact_session.py:27`). Every other `ll-*` entry point — including `ll-issues`, the CLI in
the motivating example — constructs its `ArgumentParser` *inside* `main_*()` and dispatches in
the same function (`cli/issues/__init__.py:105` builds the parser, `:206` adds the subparsers;
93 inline `ArgumentParser(` sites across `cli/`). There is nothing to import without executing
the command.

Options considered:

| # | Mechanism | Cost | Verdict |
|---|---|---|---|
| a | Subprocess-scrape `<cmd> --help` and `<cmd> <sub> --help`, cache into a JSON surface index | No source refactor; slow (one process per subcommand) so the index must be built once per `format-check` invocation | **Chosen** |
| b | Extract `_build_parser()` out of every `main_*()` | ~50-file refactor across `cli/` | Correct long-term; **split to a follow-up ENH**, out of scope here |
| c | Monkeypatch `ArgumentParser.parse_args` to raise a sentinel carrying `self`, call `main_*()` | Cheap | Rejected — fragile, executes arbitrary `main` prologue |

This issue implements **(a)**: a `build_cli_surface_index()` helper mirroring
`build_ref_index(root)`'s once-per-invocation build-and-thread shape, returning
`{tool: {subcommand: set[flag]}}`, threaded into `check_format_gaps()` via a new optional
kwarg. Fail-open when the index is `None` (the function's existing convention). A tool whose
`--help` cannot be scraped contributes no claims rather than false ones.

**False-positive control** is the main design risk: issue bodies backtick plenty of things that
are not symbols (`--json`, `P2`, prose nouns, planned-but-unbuilt APIs). Measured surface on the
current backlog (2026-08-05): **2,966 issue files**, ~523,000 backticked spans, ~30,500
`foo()`-shaped tokens. Controls:

- Only verify a symbol claim when it is attributed to a cited file that itself resolves
  (reuses the `stale_file_ref` resolution that already runs).
- Reuse the existing `<!-- ll-prose-ok: ... -->` suppression convention from
  `cli/verify_skill_prose.py:111` (`_SUPPRESS_RE`).
- **Report-only first.** Ship both gap kinds reporting through `format-check` without the
  pytest sweep failing the suite; measure precision on a sampled slice of the backlog; wire the
  sweep to fail only once precision clears the bar in the Acceptance Criteria. This gives the
  backlog-triage step a definition of done.

**Rejected mitigation — section-based exemption.** An earlier draft proposed exempting claims
inside `## Program Design` / `## Expected Behavior` as "proposed, not yet existing." **This is
wrong and would have blinded the gate to the defect that motivated this issue**: FEAT-2942's
false `ll-issues link` claim lived in `## Expected Behavior` and `## Proposed Solution`. What
makes a claim aspirational is grammatical mood ("Reuse X for writes" asserts existing code;
"add `--foo` to X" does not), not which section it sits in. Do not implement a section
allowlist; rely on cited-file resolution plus the explicit suppression marker.

### Claim Grammar (must be pinned before implementation)

The extractor's accepted claim forms are the single largest driver of the false-positive rate
and are specified here rather than left to implementation:

- **Symbol claim** — a backticked identifier in one of these forms, and no others:
  - `` `symbol()` `` or `` `Class` `` appearing in the same sentence as a backticked file path
    that resolves via the existing `RefIndex` → claim is (symbol, that file).
  - `` `module.attr` `` / `` `module.func()` `` dotted form where the dotted prefix resolves to
    a repo file via `RefIndex` → claim is (attr, that file).
  - `` `path/to/file.py:symbol` `` explicit form.
  - Bare backticked words with no file attribution are **never** claims.
- **CLI-flag claim** — `` `ll-<tool> <subcommand> [--flag ...]` `` where `ll-<tool>` is a
  registered console script in `scripts/pyproject.toml`. Subcommand and each long flag are
  checked independently; short flags are ignored (ambiguous in prose).
- **Language scope** — the symbol resolver covers the languages already in
  `anchors.py:_ANCHOR_PATTERNS`. Cited files in a language outside that set produce no claim
  (fail-open), never a gap.

## Integration Map

### Files to Modify
- `scripts/little_loops/issues/` — new claim-extractor module (peer of `prose_deps.py`).
- `scripts/little_loops/issue_parser.py` — `FormatGaps` fields, `to_dict()`, `has_gaps`,
  `check_format_gaps()` population.
- `scripts/little_loops/cli/issues/format_check.py` — `_print_gaps()` blocks, the subparser's
  static `help=` string, and `cmd_format_check()`'s docstring "Gap classes:" block (no `--kinds`
  flag exists — see Program Design).
- `scripts/tests/` — unit tests per claim class + repo-wide sweep (FEAT-2850 pattern).
- `docs/reference/CLI.md` — document the new gap kinds.

_Wiring pass added by `/ll:wire-issue`; counts re-verified 2026-08-05:_
- `docs/reference/API.md:862` — `check_format_gaps()`'s doc block enumerates the gap classes by
  name. It currently reads **"eighteen gap classes"** (not sixteen — `soft_dep_hard_edge` and
  `malformed_dep_id` have since landed) and already carries the instruction *"re-derive this
  count from `dataclasses.fields(FormatGaps)` rather than trusting the number written here"*.
  Work needed: bump eighteen → twenty and add `stale_symbol_ref`/`stale_cli_flag` description
  entries in the existing per-kind style. [Agent 2 finding]
- `scripts/little_loops/cli/issues/__init__.py:139` — the top-level `format-check` subcommand
  help string in the dispatcher's usage listing hardcodes the same gap-kind list a third time
  (independent of `format_check.py`'s subparser `help=` and `cmd_format_check()` docstring); it
  currently ends `.../soft_dep_hard_edge/malformed_dep_id)`. Must gain
  `stale_symbol_ref`/`stale_cli_flag` too or the dispatcher-level help drifts from the
  subcommand's own help. [Agent 1 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/check_design.py:38` — calls `check_format_gaps(path)`
  positionally (no `ref_index`/new kwargs). Confirmed no change required: the function's
  fail-open convention means the two new gap kinds simply don't populate for this caller: it
  only inspects `program_design_nonspecific` via `design_gate_failed(gaps)`. Listed for
  awareness, not as an action item. [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_prose_deps.py` — extractor unit-test shape to clone for the new
  symbol/CLI-flag claim extractor: flat function-level tests per behavior (positive matches,
  `@pytest.mark.parametrize`'d synonym/pattern sweeps, fenced-code exclusion via `_in_fence`,
  section-scoped extraction, empty-body/multi-match edge cases). [Agent 3 finding]
- `scripts/tests/test_issues_anchors.py` — `resolve_anchor()`'s per-language test-class shape
  (`TestResolveAnchorPython`, `TestResolveAnchorTypeScript`, etc., each writing a small source
  file via `tmp_path` and asserting the exact anchor string) is the sibling pattern for testing
  the new inverse "does symbol X exist in file Y" resolver. [Agent 3 finding]
- `scripts/tests/test_ll_issues_format_check.py::test_every_format_gaps_field_is_rendered` —
  self-updating structural guard: iterates `dataclasses.fields(FormatGaps)` and asserts every
  field renders via `_print_gaps()`. No test edit needed, but it will fail automatically if
  `_print_gaps()` doesn't grow matching loop blocks for `stale_symbol_ref`/`stale_cli_flag` —
  confirms the `_print_gaps` invariant cited in Program Design below. [Agent 3 finding]
- `scripts/tests/test_verify_cli_allowlist.py` — closest existing test scaffolding for the new
  `stale_cli_flag` introspector: `TestRun.test_dirty_state_returns_one_with_missing_tool`
  monkeypatches the entry-point/tool-set function via `unittest.mock.patch` to inject synthetic
  drift and asserts the resulting diff shape. Underlying mechanism differs (entry-point/text
  parsing, not argparse action-walking), so only the injected-drift test pattern carries over,
  not the introspection code itself. [Agent 3 finding]
- `scripts/tests/test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo` — the
  exact FEAT-2850 repo-wide sweep function to clone: walks `find_issues(config)` (active issues
  only), calls `check_format_gaps(..., ref_index=...)` per issue, accumulates failures into a
  `dict[str, list[str]]`, one aggregate `assert`. [Agent 3 finding]

### Similar Patterns
- `FEAT-2849` — shared extractor + gap taxonomy + skill wiring; the direct template.
- `FEAT-2850` — repo-wide sweep gated in pytest.
- `ENH-2946` — precedent for extending `format-check` with new gap kinds.
- `cli/verify_skill_prose.py` — marker/suppression convention.

## Program Design

### Deviations

_Added by `/ll:manage-issue` — 2026-08-05:_

- **`build_cli_surface_index()` is lazy, not eager.** The design specified
  scraping every registered `ll-*` tool's `--help` up front, once per
  `format-check` invocation. Implemented instead: `build_cli_surface_index()`
  returns an empty `CliSurfaceIndex` instantly; `cli_surface_accepts()`
  scrapes and caches a given tool's surface on its *first* query, so a body
  naming zero or one `ll-*` command triggers zero or one subprocess batch
  instead of ~50. Two concrete problems drove this: (1) eager scraping added
  10-15s to every single-issue `format-check` call regardless of whether the
  body cited any CLI command, a real interactive-latency regression; (2) it
  broke 15 existing tests in `test_ll_issues_format_check.py` that monkeypatch
  `little_loops.text_utils.subprocess.run` for unrelated `git ls-files`
  mocking — since `text_utils` and `cli_surface` both do a bare `import
  subprocess`, patching `text_utils.subprocess.run` patches the same shared
  module object, and the eager build was tripping that mock with mismatched
  (bytes vs. text) fixture data. The lazy design is inert for any test/call
  that never queries a CLI-flag claim, which is the common case.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

### Types
- `FormatGaps` (issue_parser.py) gains two new `list[str]` fields — `stale_symbol_ref`, `stale_cli_flag` — mirroring the existing `stale_file_ref`/`prose_dep_drift` shape (one human-readable string per gap instance). Every new field must land in three places to stay consistent: the dataclass field, the `has_gaps` OR-chain, and `to_dict()`'s dict literal — `stale_file_ref`/`prose_dep_drift`/`stale_prose_dep` all appear in the same order across all three today.
- `extract_prose_deps()` (prose_deps.py) returns a flat `set[str]` with no file-citation pairing. A symbol claim ("symbol X is claimed to live in file Y") cannot be represented by a bare string set — the new extractor needs a structured return type carrying (symbol, cited_file) pairs, not a reuse of `set[str]`. This is new surface, not reuse.

### Signatures
- `extract_prose_deps(body: str) -> set[str]` — prose_deps.py's extractor shape to clone: regex `.finditer(body)` over fence-detected spans, `_in_fence(start, end, fence_spans) -> bool` filters matches inside code fences using the shared `_CODE_FENCE` regex from `little_loops/text_utils.py:25`. A new symbol/CLI-flag extractor should import `_CODE_FENCE` the same way rather than redefine it.
- `resolve_anchor(file_path: str, line_number: int) -> str | None` — issues/anchors.py backwards-scans from a **known line number** to find the enclosing function/class. It answers "what encloses line N", not "does symbol X exist anywhere in file Y" — there is no existing inverse-lookup function. `_ANCHOR_PATTERNS` (the per-language def-site regexes it scans against) is reusable raw material for a new forward-existence helper, but `resolve_anchor` itself does not answer the claim FEAT-3048 needs checked.
- `check_format_gaps(issue_path: Path, templates_dir: Path | None = None, issue_statuses: dict[str, str] | None = None, ref_index: RefIndex | None = None) -> FormatGaps` — issue_parser.py; the new gap kinds require a new optional parameter (mirroring `ref_index: RefIndex | None = None`), not mutation of existing parameters. Convention in this function: fail-open — when the enabling parameter is `None`, the corresponding gap lists stay empty, no exception. All imports inside this function are local/lazy (e.g. `from little_loops.issues.prose_deps import extract_prose_deps`), a pattern the new claim-extractor import should follow.
- `build_ref_index(root: Path) -> RefIndex` — text_utils.py; built once per `format-check` invocation (`git ls-files -z`, indexed by basename) and threaded via the `ref_index=` kwarg into every `check_format_gaps()` call site. A symbol/CLI-flag equivalent (an argparse-parser cache, or a per-file symbol index) needs the same once-per-invocation build-and-thread shape to avoid re-parsing the repo or reconstructing argparse parsers per issue.
- `_print_gaps(gaps: FormatGaps) -> None` — cli/issues/format_check.py; one `for entry in gaps.<field>: print(f"  <kind>: {entry}")` block per gap category, in dataclass field order. New `stale_symbol_ref`/`stale_cli_flag` kinds need matching blocks; the function's own docstring flags "every class in FormatGaps must have a matching loop here" as an invariant (citing the ENH-2946 `testable`-field regression as the cautionary precedent).

`verify_cli_allowlist.py`'s `_all_ll_entry_points() -> set[str]` and `_run() -> tuple[int, dict[str, list[str]]]` are the closest *existing* CLI-introspection code, but resolve at entry-point-**name** granularity only (is `ll-foo` a registered console script, listed in two presets) — no `add_argument`/`add_subparsers` walk exists anywhere in that file. A flag-level introspector (does subcommand X accept flag `--bar`) is new code; only the "exit 1 on any drift, dict-of-lists missing report" contract shape carries over.

No literal `--kinds` flag exists in `format_check.py` today — new gap kinds are appended as prose to the subparser's static `help=` string (re-verified 2026-08-05: **18** kinds, ending `.../soft_dep_hard_edge/malformed_dep_id`) and to `cmd_format_check()`'s docstring "Gap classes:" block, which repeats the same list a second time; `cli/issues/__init__.py:139` repeats it a third. All three need updating; `to_dict()` changes propagate to `--format json` automatically with no extra wiring in `format_check.py`. **Wherever this issue's prose says "`--kinds` help", read "those three help strings."**

### Call Path
Existing `stale_file_ref` pattern (to mirror):
`cmd_format_check(config, args)` → `build_ref_index(config.project_root)` → `check_format_gaps(path, templates_dir, issue_statuses, ref_index=ref_index)` → `classify_issue_refs(content, ref_index)` → `gaps.stale_file_ref.append(ref)` / `gaps.ambiguous_file_ref.append(...)` → `gaps.to_dict()` / `_print_gaps(gaps)`.

Analogous new chains:
`cmd_format_check()` → `build_cli_surface_index()` [new, once per invocation, subprocess `--help` scrape per § CLI-Flag Introspection Mechanism] + per-file symbol index [new, once per invocation, lazily populated per cited file] → `check_format_gaps(..., cli_index=..., symbol_index=...)` → `extract_symbol_claims(body)` / `extract_cli_flag_claims(body)` [new module beside `prose_deps.py`] → `symbol_exists_in_file(file_path, symbol_name) -> bool` [new helper, built on `anchors._ANCHOR_PATTERNS`] → `cli_surface_accepts(tool, subcommand, flag) -> bool` [new helper, no existing equivalent] → `gaps.stale_symbol_ref.append(...)` / `gaps.stale_cli_flag.append(...)`.

**Both indexes are built once per `format-check` invocation and threaded**, mirroring
`build_ref_index`. Neither may be constructed inside `check_format_gaps()`: the repo-wide sweep
calls it 2,966 times, and per-issue subprocess spawning or repo re-walking would make the gate
unusable. Both fail open when their kwarg is `None`.

## Implementation Steps

1. Symbol-claim extractor (per § Claim Grammar) + `symbol_exists_in_file()` +
   `stale_symbol_ref` gap kind + tests.
2. `build_cli_surface_index()` (subprocess `--help` scrape, option (a)) +
   `cli_surface_accepts()` + `stale_cli_flag` gap kind + tests.
3. `format-check` reporting: `_print_gaps()` blocks, subparser `help=`,
   `cmd_format_check()` docstring, dispatcher listing at `cli/issues/__init__.py:139`, and the
   `docs/reference/API.md:862` doc block.
4. Repo-wide sweep in **report-only mode**: it walks the backlog and prints, but does not fail
   the suite. Sample and measure precision.
5. Triage the measured false positives — fix genuinely wrong claims, add
   `<!-- ll-prose-ok: -->` for intentional ones — then flip the sweep to failing once the
   precision bar in the Acceptance Criteria is met.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/reference/API.md:862` — bump the **"eighteen gap classes"** count to twenty and
  add `stale_symbol_ref`/`stale_cli_flag` description entries alongside the existing
  `prose_dep_drift`/`stale_file_ref` prose.
- Update `scripts/little_loops/cli/issues/__init__.py:139` — add the two new gap kinds to the
  dispatcher-level `format-check` help string (third duplicate site beyond `format_check.py`'s
  subparser `help=` and `cmd_format_check()` docstring).

## Use Case

A maintainer runs `/ll:refine-issue` on an issue asserting `ll-issues link --parent`; the refine
pass now fails the format-check gate with
`stale_cli_flag: ll-issues link --parent (no such flag)`, and the false premise is corrected
before implementation instead of after review. (This is exactly the FEAT-2942 defect, caught at
authoring time rather than three review passes later — see § Current Behavior. FEAT-2942 itself
has since been hand-corrected, which is why the regression test pins the original text as a
fixture rather than reading the live file.)

## Acceptance Criteria

- [x] `stale_symbol_ref` and `stale_cli_flag` gap kinds populated by `check_format_gaps()`
- [x] `build_cli_surface_index()` resolves subcommand + long flags for every `ll-*` console
      script registered in `scripts/pyproject.toml` via subprocess `--help` scrape; a tool whose
      help cannot be parsed is recorded as unscrapable and contributes **no** gaps
- [x] Both indexes built once per `format-check` invocation and threaded as kwargs; a test
      asserts `check_format_gaps()` spawns no subprocess and performs no repo walk
      (⚠ Superseded — see § Program Design § Deviations: `cli_index` is now lazily
      populated per tool on first query rather than eagerly for every tool; the test
      covers the pre-cached case, which is `check_format_gaps()`'s actual contract)
- [x] Reported via `format-check` text and `--format json`; the two new kinds appear in all
      three help strings (subparser `help=`, `cmd_format_check()` docstring,
      `cli/issues/__init__.py:139`) and in `docs/reference/API.md:862`
- [x] Claim grammar implemented exactly as specified in § Claim Grammar; bare backticked words
      with no file attribution produce no claim, and no section-based exemption exists
- [x] Repo-wide pytest sweep lands **report-only** (`test_symbol_cli_claim_sweep.py`); flipping
      to failing is deferred — this repo's active backlog (77 issues) is below the ≥100-issue
      sample the precision bar requires, and measured hit rates (~45-47%) are far from the ≥95%
      bar, so triage (fix genuinely wrong claims, suppress intentional ones) is follow-up work
- [x] Documented suppression path for intentional/aspirational claims
      (`<!-- ll-prose-ok: -->`)
- [x] Regression fixture pins FEAT-2942's **original** claim text from commit `2225b414`
      (*"Reuse `ll-issues link` / `frontmatter.update_frontmatter` for writes"*) and asserts
      `stale_cli_flag` fires on it. Do **not** assert against the live FEAT-2942 file — it has
      since been corrected and no longer contains the bad claim
- [x] pytest coverage in `scripts/tests/`

## Impact

- **Priority**: P2 — matches EPIC-2938; catches the defect class that survives the most passes
- **Effort**: Medium — extractor + `--help`-scrape introspector + sweep triage. Does **not**
  include the `_build_parser()` extraction refactor (option (b)), which is a follow-up ENH.
- **Risk**: Medium — false-positive rate on the 2,966-issue backlog (~523k backticked spans,
  ~30.5k `foo()`-shaped) is the main unknown; the report-only rollout stage exists to measure it
  before the gate can block anyone.

## Follow-up (out of scope here)

- **ENH (to file):** extract `_build_parser()` out of each `main_*()` in `cli/` so parsers are
  importable without executing a command. Six modules already do this; ~50 do not (93 inline
  `ArgumentParser(` sites). Would let `build_cli_surface_index()` drop the subprocess scrape for
  a direct in-process walk of `_subparsers`/`choices`/`option_strings`, and benefits
  `ll-verify-cli-allowlist` and doc-coverage checks too.

## Related Key Documentation

- `.claude/CLAUDE.md` — adds gap kinds to the `ll-issues format-check` surface
- `docs/reference/CLI.md` — sole home of the documented CLI surface

## Status

**Open** | Created: 2026-08-04 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-05T17:21:24 - `1bd81a51-f515-46ff-83f3-75b453145d8d.jsonl`
- `/ll:confidence-check` - 2026-08-05T16:30:05 - `78d861d7-3143-45d9-95dd-e1e10f0e6420.jsonl`
- `/ll:confidence-check` - 2026-08-05T04:03:42 - `888aba7c-0cc1-4cb1-95ef-7a0d27ed23c5.jsonl`
- `/ll:wire-issue` - 2026-08-05T03:33:29 - `5ae88258-173f-462a-b863-05a1549fb4c3.jsonl`
- `/ll:refine-issue` - 2026-08-05T03:21:59 - `dc32c72f-7a77-428d-ab7c-bf171330b8f1.jsonl`
- `/ll:capture-issue` - 2026-08-04T20:50:26 - `2a9240a9-e6df-4ed5-ad2a-73a280bc7d8b.jsonl`
