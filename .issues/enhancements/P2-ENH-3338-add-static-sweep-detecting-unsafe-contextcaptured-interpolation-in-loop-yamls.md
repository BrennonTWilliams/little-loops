---
id: ENH-3338
type: ENH
title: Add static sweep detecting unsafe context/captured interpolation in loop YAMLs
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T17:51:35Z'
parent: EPIC-3336
blocked_by:
- ENH-3337
blocks:
- BUG-3339
- BUG-3340
- BUG-3341
- ENH-3342
confidence_score: 80
outcome_confidence: 81
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 22
---

# ENH-3338: Add static sweep detecting unsafe context/captured interpolation in loop YAMLs

## Summary

Build the recursive, both-host-shape-aware sweep that classifies every
`${context.*}` / `${captured.*}` interpolation site inside a Python body in
`loops/**/*.yaml`, and assert it against a checked-in **ratcheting baseline**.
Each conversion commit shrinks the baseline; the epic is done when its class-A
and class-B entries are empty.

**Build this before the edits.** It is what turns ~145 hand-edits from hopeful
into verifiable, and it is the only way to know the conversion is complete. Its
baseline is also the authoritative site count — EPIC-3336's survey table is a
hand-run estimate that BUG-3339's refinement already contradicted.

## Current Behavior

Nothing detects this class. MR-11
(`_find_unsafe_context_interpolations`,
`scripts/little_loops/fsm/validation/shell_safety.py:148-188`) is the closest
thing and is narrower in four ways that matter here:

1. **Fixed key allowlist** — `_UNSAFE_CONTEXT_INTERP_RE` (`:33-35`) matches only
   `input|goal|description|task|prompt|query|topic`. Class-A keys outside that
   set are invisible.
2. **No `captured` or `prev` namespace at all** — the regex is `\$\{context\.…`
   only, so **class B, the sharper class, is entirely outside MR-11's reach**,
   `${prev.output}` included.
3. **A quoted heredoc is treated as unconditionally safe** (`:178-180`) — true
   from bash's perspective, false once the body is re-parsed as Python. That
   inversion is precisely what this sweep must catch and MR-11 must not.
4. **No `-c "` host-shape awareness** — MR-11 is line-oriented and tracks only
   heredoc markers. A scanner with that shape silently mis-scopes every
   `python3 -c "…"` block; this is how the original survey produced its low
   "~60 total" count.

There is also no in-repo baseline/allowlist **data file** for a ratchet
migration. The one precedent is a Python module-level constant:
`FENCED_BRIEF_SITES` / `KNOWN_UNFENCED_PROMPT_SITES`
(`scripts/little_loops/fsm/fence.py:156-164`), enforced by
`test_completeness_guard`
(`scripts/tests/test_builtin_loops.py:18666-18688`, asserting
`discovered == set(FENCED_BRIEF_SITES) | KNOWN_UNFENCED_PROMPT_SITES`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **Confirmed**: neither `scripts/little_loops/fsm/interp_sweep.py` nor `scripts/tests/data/loop_interpolation_baseline.json` exist yet (unfiltered repo-wide glob, no hits outside `.issues/` prose).
- **Heredoc-tracking bug confirmed with exact anchors**: `shell_safety.py`'s terminator check (inside `_find_unsafe_context_interpolations`, `:169-188`) is `if stripped == heredoc_marker:` (`:172-175`, where `stripped = line.strip()`) — a full-line-content match, not a column-0 anchor. `_QUOTED_HEREDOC_START_RE` (`:41`) is likewise not column-0-anchored on the opener. This confirms the issue's claim about the bug not to inherit.
- **The `test_completeness_guard` ratchet shape exists TWICE, not once** — `TestBriefFencing.test_completeness_guard` (`test_builtin_loops.py:18666`, comparing against `set(FENCED_BRIEF_SITES) | KNOWN_UNFENCED_PROMPT_SITES`) and `TestUntrustedOutputSurvey.test_completeness_guard` (`:18811`, comparing against `UNTRUSTED_OUTPUT_SITES - KNOWN_INDIRECT_UNTRUSTED_OUTPUT_SITES`). Both use the identical shape this issue specifies: plain `discovered == expected` equality, failure message reporting both `discovered - expected` and `expected - discovered`. Both are in-code Python `set`/`list` constants, not a checked-in JSON file — confirming the issue's own note that there is no existing JSON-baseline precedent for this exact (bidirectional, per-site) shape. A *different*, one-directional, per-file-count JSON baseline convention does exist (`.ll/private-refs-baseline.json` via `verify_private_refs.py:418-474`, and its sibling `.ll/evidence-baseline.json` via `verify_evidence.py:83`) — tracked in git, regenerated only by an explicit `--update-baseline` CLI flag, never automatically. Worth knowing as a discovered-but-structurally-different precedent for the checked-in-JSON-file mechanics (git tracking, explicit regeneration flag), even though its comparison shape does not match what this issue needs.
- **Corpus check for ENH-3337's new `:shell:default=` suffix**: exactly 2 live sites today, both in `loop-router.yaml`'s `finalize_present_result` state (`:512-513`, `LL_PROPOSAL_OUT=${captured.new_loop_proposal.output:shell:default=}` / `LL_REVIEW_OUT=${captured.review_result.output:shell:default=}`), both on the bash-token env-var-binding prefix line of a `python3 << 'PYEOF'` invocation — i.e. the safe position, outside the Python heredoc body. These are a live, already-converted example of the pattern this sweep should treat as clean (class B, safe position, not misapplied-remedy), though named `LL_PROPOSAL_OUT`/`LL_REVIEW_OUT` rather than the epic's `LL_ARG_` naming convention.
- **FSMLoop/StateConfig schema confirmed** consistent with the issue's proposed `scan_action`/`scan_corpus` signatures: `StateConfig.action: str | None` and `StateConfig.action_type: str | None` (`scripts/little_loops/fsm/schema.py:693-694`, class at `:621`), `FSMLoop.states: dict[str, StateConfig]` (`:1384`, class at `:1360`).
- **Spot-checks confirmed accurate as written**: `harness-optimize.yaml` state `apply` has `action_type: prompt` at `:145`, with the `python3 -c` block embedded in prompt instructional text at `:160-165` exactly as the issue describes (AC 6). `mechanize-skills.yaml` state `validate_diagnosis` (`:276`, shell-shaped via `fragment: shell_exit`) has the converted `SKILL_FILE="${captured.current_skill.output}"` binding at `:283` (bash-token position, safe) and the raw `${captured.run_dir.output}` interpolation at `:286` (inside the same heredoc's Python body) exactly as the issue describes (AC 7).

## Expected Behavior

A sweep that, given the loop corpus, emits a set of classified sites, and a test
asserting that set **equals** a checked-in baseline:

- a scanned site **not** in the baseline → failure (a new site was introduced)
- a baseline entry that no longer scans → failure (stale entry; delete it in the
  same commit that converts it)

Both directions are load-bearing. The first is the regression guard; the second
is what forces each conversion commit to update the baseline, which is what makes
progress measurable.

The test is **green on `main` at every commit**, from the commit that introduces
it. `python -m pytest scripts/tests/` must exit 0 on `main` (CLAUDE.md *Testing &
CI Policy*; the self-hosted runner gates every push), and BUG-3339/3340/3341 land
as separate commits — a test red for the duration of the epic is not landable.

## Motivation

145 sites across 33 files, edited by hand, in a codebase where a malformed
conversion is invisible until the affected state runs at some later date. Without
a detector, "did we get them all?" is unanswerable and "did we break one?" is
answered by a production loop failure.

## Design decisions

### Baseline format — checked-in JSON data file (not a Python constant)

`fence.py`'s module-level set is the in-repo precedent, but it holds 15 entries.
This baseline starts near **276** and shrinks across ~6 commits. A JSON data file
under `scripts/tests/data/` gives clean, reviewable per-commit diffs and keeps a
large mechanical list out of a source module.

Proposed shape — one object per site, sorted deterministically so diffs are
minimal:

```json
{
  "sites": [
    {
      "file": "loops/loop-router.yaml",
      "state": "discover_loops",
      "line": 34,
      "var": "context.include",
      "class": "A",
      "host_shape": "c-string",
      "count": 1
    }
  ]
}
```

**Anchor on `(file, state, var, class)` — not on line number** for equality.
Line numbers churn on every unrelated edit and would make the baseline a
merge-conflict magnet across the three serial conversion issues. Carry `line` as
an informational field the failure message prints, excluded from the comparison
key.

**The comparison key is exactly those four fields** — `line`, `host_shape`,
and `misapplied_remedy` are all informational (`field(compare=False)` on the
dataclass). An earlier draft excluded only `line`, which would have silently
put `host_shape` and `misapplied_remedy` into the key: a conversion that
changes a site's host shape without fixing the interpolation would then read
as new-site-plus-stale-entry noise instead of an unchanged site.

**Set equality collapses duplicate occurrences.** Two occurrences of the same
`(file, state, var, class)` inside one state (a real pattern — one heredoc in
`mechanize-skills.yaml` carries multiple `${captured.*}` refs) become one
baseline entry, so introducing a *second* occurrence of an already-baselined
site is invisible, and fixing one-of-two shows no baseline movement. Carry an
informational `count` per entry that the failure message prints when it
changes; full multiset equality is not required — the ratchet's endpoint is
zero either way — but the count keeps intra-entry regressions visible.

### Classifier location — `scripts/little_loops/fsm/interp_sweep.py`

A new module, not a test helper, because **ENH-3342 shares this exact
classification rule** for the MR-11 widening. Implement it once, import it from
both. Placing it under `fsm/` (beside `fence.py`) rather than
`fsm/validation/` keeps `validation/` as the rule-family package it is, per
ENH-2774's split.

### Classification rule

Do **not** reproduce MR-11's fixed key allowlist — that is the narrowness this
epic faults it for. Invert it:

- `${captured.*}` → **always untrusted, class B.** No exceptions; a capture is
  either LLM output or command output, never operator-fixed.
- `${prev.*}` → **always untrusted, class B.** `prev` carries the previous
  state's `output` / `stderr` / `exit_code`, so `${prev.output}` is the same
  LLM-or-command text a `captured` reference holds — it simply reaches the
  action without being named. Live example outside any Python body:
  `rlhf-svg-evaluate.yaml:517`, `PREV_OUTPUT="${prev.output}"` — model output
  inside a bash **double-quoted** assignment, where a `"` breaks tokenizing and
  `$(...)` command-substitutes. Corpus usage as of 2026-08-27: 7 `${prev.output}`,
  3 `${prev.exit_code}`, 2 `${prev.state}`, 1 `${prev.timeout_kind}`.
  `exit_code` / `state` / `timeout_kind` are runner-constructed and are **class
  C**; only `output` and `stderr` are untrusted.
- `${context.<key>}` → **untrusted by default, class A**, except an enumerated
  trusted set of runner-constructed keys. That set is closed as of 2026-08-27:
  `run_dir` (`executor.py:903, 979`), `promoted_artifact`
  (`persistence.py:1229`), and any underscore-prefixed bookkeeping key
  (`_tamper_guard`, `_prepatch_check`). A trusted key inside a Python body is
  **class C**.
- `${loop.*}` → runner-constructed, trusted, not reported.
- Consequence, and the point of the inversion: a newly-introduced `${context.*}`
  key is **untrusted until someone adds it to the trusted list** — the safe
  default direction.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/interp_sweep.py` — **new**. The scanner and
  classifier.
- `scripts/tests/data/loop_interpolation_baseline.json` — **new**. The ratcheting
  baseline, seeded from the sweep's first run over `main`.
- `scripts/tests/test_builtin_loops.py` — the equality test, in the same shape as
  the existing `test_completeness_guard` (`:18666-18688`).
- `docs/reference/API.md` — a module entry for `interp_sweep`, per repo
  convention.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/fsm/validation/shell_safety.py` — ENH-3342 imports the
  classifier from here. Not modified by this issue.

### Similar Patterns

- `scripts/little_loops/fsm/fence.py:156-164` + `test_completeness_guard`
  (`test_builtin_loops.py:18666-18688`) — the discovered-set-equals-checked-in-set
  ratchet shape to copy.
- `scripts/little_loops/fsm/validation/shell_safety.py:169-188` — the
  line-oriented heredoc tracking to extend (and fix; see below).

### Tests

- The baseline-equality test itself.
- Unit tests for the scanner against synthetic action strings, covering each
  requirement in Implementation Steps — especially the two host shapes, the
  column-0 terminator, and the per-site (not per-file) assertion.

### Documentation

- `docs/reference/API.md` — new module entry.

### Configuration

- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **Recursive-walk convention for a text/grammar sweep (this issue's shape) vs. a schema-validation walk**: two distinct patterns coexist in this codebase, and this issue's scanner matches the first. (1) Raw-YAML text sweeps use `LOOPS_DIR.rglob("*.yaml")` with dot-prefixed-path-segment exclusion, then `yaml.safe_load` scoped to `states`/`fragments` and walked without going through the `FSMLoop` schema — evidence: `scripts/tests/test_builtin_loop_interpolation.py:37-80` (`_builtin_loop_files`, `_iter_strings`), which already recurses into both `lib/` and `oracles/` as this issue's Implementation Step 1 requires. (2) Schema-typed structural walks instead filter with `is_runnable_loop(p)` and call `load_and_validate(path, raise_on_error=False)` to get validated `FSMLoop` objects — evidence: `doctor.py:540-562`, `validation/reachability.py:121-125`. Since this sweep scans action-string *text* for interpolation tokens rather than validating loop *structure*, pattern (1) is the established convention to follow, not (2).
- **No existing `python3 -c "..."` host-shape boundary tracking anywhere in the codebase** — confirmed via unfiltered repo-wide grep (36 hits for the literal string `python3 -c`, all either loop-YAML action bodies or `fence.py`'s docstring deferring this exact class to "BUG-3331/BUG-3339" without implementing it). `shell_safety.py`'s heredoc-only tracking is the sole "host shape" logic that exists, and it has no `-c "` awareness at all. This scanner's `-c "` boundary tracking has no precedent to reuse or diverge from — it is new work in this codebase.
- **No `@dataclass(frozen=True)` with a custom `__eq__`/`__hash__` excluding one field exists anywhere in the codebase** (repo-wide grep for `__eq__`/`__hash__` under `scripts/`, zero matches). The closest structural relative, `issues/cli_claims.py:33-40`'s `CliFlagClaim`, is a plain frozen dataclass placed in a `set` using dataclass-generated equality over *all* fields, no exclusion. The issue's proposed `InterpSite` dataclass excluding `line` from equality (for baseline-anchoring purposes) would be a new pattern in this codebase, not an established one — implement it deliberately (e.g. `line: int = field(compare=False)`), there is nothing to copy.
- **`docs/reference/API.md` convention is narrower than this issue's Documentation section assumes**: sibling validation rules (MR-1 through MR-14, including MR-11) are documented as bullets inside the single shared `### little_loops.fsm.validation` → `#### validate_fsm` entry's "Checks performed" list (`docs/reference/API.md:6279-6323`), not as their own per-submodule headings — `shell_safety.py` itself has no dedicated heading. More directly relevant: `fence.py` — the module this issue's own Design Decisions section names as the ratchet-pattern precedent — has **no API.md entry at all**; it's documented instead in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:641-672` and is absent from `docs/ARCHITECTURE.md`'s `fsm/` directory tree (`:239-258`) even though `shell_safety.py` is listed there. Whether `interp_sweep.py` gets its own API.md heading, a bullet under an existing entry, or (matching its closest precedent, `fence.py`) no API.md entry at all, is a genuinely open documentation-placement question this issue's own "per repo convention" claim does not resolve — there isn't a single settled convention to follow here.

## Scope Boundaries

**In scope:** the scanner, the classifier, the checked-in baseline, and the
equality test. Seeding the baseline from `main` and recording its counts.

**Out of scope:** converting any site (BUG-3339/3340/3341); changing MR-11 to use
the classifier (ENH-3342); class-C sites beyond recording them in the baseline.

## Program Design

### Signatures

Proposed; adjust names freely, but keep the classifier importable by ENH-3342.

- `classify_site(namespace: str, key: str) -> str` — returns `"A"`, `"B"`, or
  `"C"` per the classification rule above. **This is the function ENH-3342
  imports.**
- `scan_action(action: str, *, state: str, file: str) -> list[InterpSite]` —
  scans one action string, tracking both host shapes, returning one `InterpSite`
  per interpolation inside a Python body.
- `scan_corpus(root: Path) -> list[InterpSite]` — globs `loops/**/*.yaml`
  recursively, walks **both top-level shapes**: every entry under `states:`
  *and* every entry under `fragments:`, returning all sites sorted
  deterministically. `lib/` files have **no `states:` key at all** — they are
  top-level `fragments:` (`lib/common.yaml:14`, `lib/harness.yaml:1`,
  `lib/cli.yaml:21`, `lib/benchmark.yaml:14`) and contain live python3 bodies
  with interpolations (`lib/composer.yaml:97`, `lib/policy-router.yaml:81,135`,
  `lib/rubric-router.yaml:74,105,122`). A states-only walk globs those files
  and yields nothing — a false clean for exactly the `lib/` coverage
  Implementation Step 1 mandates. For a fragment site, the fragment name
  fills the `state` anchor field. (`_iter_strings` in
  `scripts/tests/test_builtin_loop_interpolation.py:37-80` — this issue's
  named walk precedent — already walks both keys.)
- `@dataclass(frozen=True) class InterpSite` — `file`, `state`, `var`, `cls`,
  `host_shape`, `misapplied_remedy`, `line`, `count`. `__eq__`/`__hash__` over
  the four anchor fields only — `line`, `host_shape`, `misapplied_remedy`, and
  `count` are `field(compare=False)` (see baseline anchoring above).
  `misapplied_remedy` is `True` for a `:shell`-suffixed site found inside a
  Python body.

### Decision Rules

Per interpolation token found inside a Python body:

| Condition | Verdict |
|---|---|
| namespace is `loop` | clean |
| namespace is `captured` | class B |
| namespace is `prev`, key is `output` / `stderr` | class B |
| namespace is `prev`, otherwise | class C |
| namespace is `context`, key in the trusted set | class C |
| namespace is `context`, otherwise | class A |

**`:shell` does not clear a site inside a Python body.** An earlier draft of this
table had "carries a `:shell` suffix anywhere in its chain → clean" as its first
row. That is wrong, and it is the one error that could certify a broken
conversion as green. `:shell` is `shlex.quote()`, which is safe **only at a bash
token position**. Inside a quoted heredoc bash performs no processing at all, so
the quoted form is handed straight to the Python parser:

```
shlex.quote("don't")  ->  '\'don\'"\'"\'t\''
goal = ''don'"'"'t''  ->  SyntaxError: unterminated string literal
```

So a site written as `goal = '${context.goal:shell}'` **inside** the heredoc is
still broken, and must still be reported. The rule:

- `:shell` at a bash token position (the `LL_ARG_X=${context.x:shell}` binding on
  the `python3` invocation line) — outside a Python body, therefore never scanned.
- `:shell` **inside** a Python body — reported with its normal class (A or B) and
  a `misapplied_remedy: true` flag on the `InterpSite`, so the failure message can
  say "`:shell` used inside a Python body; hoist it to a `LL_ARG_` binding"
  rather than the generic text. This is a distinct and more actionable failure
  than a raw site, and it is the exact mistake a hurried BUG-3340 conversion
  makes.

**Scope note — the sweep reports Python-body sites only.** An untrusted value in
a plain **bash** position (`PREV_OUTPUT="${prev.output}"`,
`rlhf-svg-evaluate.yaml:517`) is a real defect of the same family but is MR-11's
territory, not this baseline's; ENH-3342's widening is what must catch it.
`classify_site()` still returns the right class for it — the position filter, not
the classifier, is what excludes it here.

"Inside a Python body" is determined by host shape:
- **heredoc** — between a `<<'MARKER'` / `<<"MARKER"` opener recognized
  **anywhere on a line** and a line that is **exactly** `MARKER` at column 0.
  The column-0 constraint applies to the **terminator only** — a heredoc
  opener is a redirection and sits mid-line in every corpus occurrence
  (`python3 << 'PYEOF'` after env-var bindings at `loop-router.yaml:514`,
  after a pipe and indented inside an `if` block at `rn-implement.yaml:102`,
  after `cat > file <<'EOF'` at `brainstorm.yaml:162`). An opener-side
  column-0 requirement would scope ~0 real heredocs and certify a false
  clean. **Unquoted heredocs** (`<<EOF`, no quotes on the marker): zero in
  the corpus today, but treat the body the same as a quoted one — FSM
  interpolation runs before bash, so marker quoting changes bash expansion,
  not whether the interpolated text lands in the Python parser.
- **`-c` string** — between `python3 -c "` and the next unescaped `"`, **and
  equally** between `python3 -c '` and the closing `'`. The single-quoted
  shape is live in the corpus (`rn-refine.yaml:920,928`,
  `rn-implement.yaml:102`, `workflow-generator.yaml:75,253`); none of those
  bodies contain an interpolation today, but single quotes protect nothing
  here — FSM interpolation happens before bash ever tokenizes — and a
  scanner that doesn't recognize the shape both misses future sites and
  mis-scopes the remainder of the action string.

Under ENH-3337's S1 there is **no `:default=` / `?` exemption**: every class-A/B
site converts, and a surviving raw one is a failure.

### Call Path

`scripts/tests/test_builtin_loops.py` → `scan_corpus(loops_root)` → per file,
per entry under `states:` **and** `fragments:`, `scan_action(entry.action)` →
`classify_site()` per token → set compared against
`scripts/tests/data/loop_interpolation_baseline.json` (new).

The scanner reads the same `state.action` field that
`_find_unsafe_context_interpolations(fsm)`
(`scripts/little_loops/fsm/validation/shell_safety.py:148`) walks, and models the
substitution that `interpolate(template, ctx)`
(`scripts/little_loops/fsm/interpolation.py:209`) performs before
`bash -c <action>` (`scripts/little_loops/fsm/runners.py:297`). Loops are parsed
into `FSMLoop` via the same schema those consume.

No runtime path. This is a static analysis over checked-in YAML; it never
executes a loop.

## Implementation Steps

1. **Glob recursively** (`loops/**/*.yaml`). `lib/` holds fragments composed into
   runnable loops and `oracles/` loops are themselves runnable — both are in
   scope. A non-recursive glob certifies a **false clean**; that is exactly how
   the original survey missed 28 sites across 8 files. **Walk `fragments:` as
   well as `states:`** — `lib/` files have no `states:` key, so a states-only
   walk visits them and finds nothing (see `scan_corpus` in Program Design).
2. **Handle both host shapes** — a heredoc body delimited by its marker, and a
   `python3 -c` body delimited by its closing quote (**double- and
   single-quoted**; the `-c '` shape is live at `rn-refine.yaml:920,928` and
   `workflow-generator.yaml:75,253`). A line-oriented scanner that only tracks
   heredoc markers silently mis-scopes every `-c` block.
3. **Track heredoc terminators at column 0**, not `line.strip() == marker` —
   the **terminator only**; the opener is a mid-line redirection and must be
   recognized anywhere on a line (see Decision Rules). Bash matches a `<<`
   terminator only at column 0 (`<<-` relaxes it for **tabs**
   only, which this repo's space-indented YAML block scalars cannot supply).
   MR-11's `:173` check is looser than bash and mis-scopes any block following an
   indented marker-equal line — do not inherit that bug.
4. **Assert per interpolation site, not per file.**
   `mechanize-skills.yaml:283-286` is the counterexample: one converted
   `SKILL_FILE` binding on one line, a raw `${captured.run_dir.output}`
   interpolation on the next, inside the same heredoc.
5. Skip `action_type` values other than `shell` / `None` — `runners.py` only
   shells out for those, and a `prompt` action's text is prose, not a live
   invocation. `harness-optimize.yaml:160-165` is the live example of a naive
   grep's false positive.
6. Recognize the `:shell` suffix **anywhere in the chain** (ENH-3337's shared
   helper, not `endswith`) — but do **not** treat it as clearing a Python-body
   site. Flag it `misapplied_remedy` and report it with its normal class, per
   Decision Rules.
7. Assert the epic's naming conventions where they apply: the `LL_ARG_` prefix on
   bindings this work introduces, and the `<state>-<capture>.txt` filename rule
   on Option B writes.
8. Seed `loop_interpolation_baseline.json` from the first run over `main`, sorted
   deterministically. **Record the resulting class-A/B/C counts in EPIC-3336** —
   they supersede the survey table.
9. The failure message names file, state, line, var, and class, and says which
   direction failed (new site vs. stale entry). This message is read once per
   conversion commit across the whole epic; make it good.

## Acceptance Criteria

1. The sweep globs `loops/**/*.yaml` recursively, handles both host shapes
   (heredoc with mid-line opener + column-0 terminator; `-c` with both `"` and
   `'` quoting), and classifies per site — each with a unit test against a
   synthetic action string, including one whose heredoc opener follows an
   env-var-binding prefix mid-line.
1b. The sweep walks `fragments:` as well as `states:`; at least one
   `lib/` fragment site (e.g. from `lib/policy-router.yaml:81` or
   `lib/rubric-router.yaml:74`) appears in the seeded baseline, proving the
   fragments walk.
2. `scripts/tests/data/loop_interpolation_baseline.json` is checked in, seeded
   from `main`, and anchored on `(file, state, var, class)` — not on line number.
3. The equality test fails in **both** directions: a new unbaselined site, and a
   baseline entry that no longer scans.
4. The test is **green on `main`** at the commit that introduces it and at every
   subsequent commit of EPIC-3336. `python -m pytest scripts/tests/` exits 0.
5. `classify_site()` is importable and is the single implementation of the
   classification rule — ENH-3342 consumes it rather than duplicating it.
6. `harness-optimize.yaml:160-165` does **not** appear in the baseline (its
   enclosing state is `action_type: prompt`).
7. `mechanize-skills.yaml:283-286` appears as **one** site, not zero — proving
   the per-site assertion.
8. The seeded class-A/B/C counts are recorded in EPIC-3336, superseding the
   survey table's provisional numbers.
9. A `:shell`-suffixed interpolation **inside a Python body** is reported (not
   cleared) with `misapplied_remedy: true`, with a unit test whose synthetic
   action contains `goal = '${context.goal:shell}'` inside a quoted heredoc. A
   `:shell` binding at a bash token position outside any Python body is not
   reported.
10. `classify_site("prev", "output")` returns `"B"` and
    `classify_site("prev", "exit_code")` returns `"C"`, each with a unit test.

## Impact

- **Priority**: P2 — inherited from EPIC-3336. It gates the three conversion
  issues: without it they are unverifiable.
- **Effort**: Medium — the scanner is the whole cost. Two host shapes, column-0
  terminator semantics, and per-site granularity are each a place a naive
  implementation goes quietly wrong, and two prior scans of this corpus already
  did.
- **Risk**: Low to the running system (static analysis, no runtime path). The
  real risk is a **scanner that under-reports**, certifying a false clean — which
  is why ACs 1, 6, and 7 pin specific known-tricky sites.
- **Breaking Change**: No.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-27_

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 81/100 → HIGH CONFIDENCE

### Gaps to Address
- `blocked_by: ENH-3337` is unresolved (status: open). ENH-3338's own scope note
  says it must seed its baseline *after* ENH-3337 lands, so this issue is not
  implementable yet regardless of its own readiness — the sweep would baseline
  a pre-fix `general-task.yaml:895-902` site.

## Status

**Open** | Created: 2026-08-27 | Priority: P2

## Session Log
- `/ll:confidence-check` - 2026-08-28T03:13:07 - `e52b5f8b-4479-4377-bf0a-15b1b4dcbd9a.jsonl`
- `/ll:confidence-check` - 2026-08-28T03:03:44 - `486b558c-b1c6-4706-9fa1-9c30566c1e36.jsonl`
- `/ll:wire-issue` - 2026-08-28T02:57:43 - `13d6dd54-6fe5-483d-8ac7-01629c54d02f.jsonl`
- `/ll:refine-issue` - 2026-08-28T02:39:00 - `b0fc8e25-b423-43c9-a6e7-49a921fc64b8.jsonl`
- `/ll:format-issue` - 2026-08-28T02:28:48 - `2ce7a90a-6aac-441b-a6ef-bdf7013fe147.jsonl`
- `/ll:scope-epic` - 2026-08-27T17:51:45 - `c766dcf0-a664-4805-9c8a-6eba323145c8.jsonl`
