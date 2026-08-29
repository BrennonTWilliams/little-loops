---
id: ENH-3342
type: ENH
title: Widen MR-11 lint and document the safe loop-interpolation idiom
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T17:51:35Z'
parent: EPIC-3336
blocked_by:
- ENH-3337
- ENH-3338
- BUG-3339
- BUG-3340
- BUG-3341
- ENH-3347
confidence_score: 75
verify_verdict: PROPOSAL_UNSOUND
outcome_confidence: 45
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 0
reconcile_attempted: true
---

# ENH-3342: Widen MR-11 lint and document the safe loop-interpolation idiom

## Summary

> **Priority raised P3 → P2 (2026-08-27).** This carries EPIC-3336's AC 7 and is
> the only child that prevents the class from returning. Everything else in the
> epic is a one-time cleanup; without this, the next loop author reintroduces the
> bug and nothing catches it.


Extend MR-11 (`scripts/little_loops/fsm/validation/shell_safety.py`) so it
covers what EPIC-3336 actually fixed: drop the fixed seven-key allowlist, add the
`captured` namespace, distinguish "inside a quoted heredoc" (bash-safe) from
"inside a Python literal within one" (not safe), and tighten the heredoc
terminator to column 0. Then document the two safe idioms in
`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`.

MR-11 consumes ENH-3338's `classify_site()` rather than reimplementing the
classification rule.

Also adds the per-site `# ll-lint: mr11-ok(<var>) <reason>` marker — the narrow
escape hatch that lets the widening's residual findings be recorded in place
instead of trading away the corpus's zero-warning property. Without it, the
widening either forces every pre-existing finding to be converted inside this
issue or leaves ambient warnings that destroy MR-11's value as a regression
signal.

## Current Behavior

`_find_unsafe_context_interpolations` / `_validate_unsafe_context_interpolation`
(`shell_safety.py:148-227`) is narrower than the class EPIC-3336 fixed, in four
specific ways:

1. **Fixed key allowlist.** `_UNSAFE_CONTEXT_INTERP_RE` (`:33-35`) matches only
   `input|goal|description|task|prompt|query|topic`. Every class-A key outside
   that set is invisible.
2. **No `captured` or `prev` namespace.** The regex is `\$\{context\.…` with no
   alternation — **class B, the sharper class, is entirely outside MR-11's
   reach.** BUG-3341 can convert all 67 sites and MR-11 will not notice if one is
   missed. `${prev.output}` is equally invisible, and unlike the class-B sites
   this epic converts, it also occurs in plain **bash** positions that no other
   guard covers: `rlhf-svg-evaluate.yaml:517`, `PREV_OUTPUT="${prev.output}"` —
   model output inside a double-quoted assignment, where a `"` breaks tokenizing
   and `$(...)` command-substitutes. ENH-3338's baseline deliberately does not
   cover bash-position sites, so **this rule is the only thing that can catch
   them.**
3. **A quoted heredoc is unconditionally safe** (`:152-154`, `:178-180`). True
   from bash's perspective; false once the body is re-parsed as Python. This is
   the exact inversion EPIC-3336 exists to fix, and MR-11 currently encodes the
   wrong half of it.
4. **Heredoc terminator is looser than bash.** `:173` closes on
   `stripped == heredoc_marker`, so an *indented* line equal to the marker ends
   the tracked block — where bash requires column 0 (`<<-` relaxes it for **tabs**
   only). Any block after such a line is scoped wrong.

Additionally, `:183`'s `token.endswith(":shell}")` recognizes only a trailing
`:shell`; ENH-3337 fixes that ahead of this issue, and this issue must not
reintroduce it.

MR-11 emits `ValidationSeverity.WARNING` and is suppressible per-loop via
`unsafe_context_interpolation_ok` (`:206-212`). **No loop in the corpus sets that
flag** — the corpus is MR-11-clean, which is what makes any new warning a
regression signal rather than ambient noise.

Documentation: nothing describes the `-c "` vs. heredoc host shapes, the
`LL_ARG_` env-var idiom, or the heredoc-to-file idiom.
`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` holds the MR rule table and is where
they belong.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Stale line citations — this section describes the pre-ENH-3337 file, not the current one.** ENH-3337 landed in commit `4ca5cbb91` (2026-08-27 22:35), before this issue's own prior `/ll:refine-issue` session (2026-08-29T16:03:29), but the citations above were never updated. Current locations (verified against the tree): `_UNSAFE_CONTEXT_INTERP_RE` is `:34-36`; `_find_unsafe_context_interpolations` spans `:149-198`; `_validate_unsafe_context_interpolation` spans `:201-237`; the heredoc terminator check (`stripped == heredoc_marker`) is at `:175`, not `:173`. Most importantly, item 4's `:183` no longer contains `token.endswith(":shell}")` anywhere — ENH-3337 replaced that exact check with `parse_interpolation_suffixes(raw)` returning a `shell_quote` boolean, unconditionally cleared by `if shell_quote: continue` (current `:190-193`). The quoted snippet `token.endswith(":shell}")` does not exist in the current tree. The remedy AC 5b needs (making `:shell` position-aware, not merely suffix-chain-aware) must be made to that `if shell_quote: continue` block at `:193`, not to any `token.endswith(...)` call.

## Expected Behavior

MR-11 flags any untrusted interpolation reaching a Python literal, regardless of
key, namespace, or host shape — and does **not** flag a correctly converted site.
`ll-loop validate` therefore fails a future author who reintroduces the pattern,
which is the whole point of running this issue last.

The guide documents both idioms with a copy-pasteable block, so the answer to
"how do I get a goal into my Python heredoc?" is written down rather than
inferred from the corpus.

## Motivation

EPIC-3336's other six children are a one-time cleanup of 145 sites. This is the
ratchet. ENH-3338's baseline catches a **new** site in the built-in corpus, but
MR-11 is what a loop author sees when they run `ll-loop validate` on their own
loop — including loops in consuming projects, which no baseline covers.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/validation/shell_safety.py`
  - `:34-36` — `_UNSAFE_CONTEXT_INTERP_RE`: drop the key allowlist, add the
    `captured` and `prev` namespaces, or replace the regex entirely with a call
    into ENH-3338's scanner
  - `:190-193` — `if shell_quote: continue`: this must become position-aware,
    not merely suffix-chain-aware. ENH-3337 already relocated the `:shell`
    check to here, replacing the old `token.endswith(":shell}")` test with
    `parse_interpolation_suffixes(raw)` → `shell_quote`; this issue fixes
    *whether* recognizing it clears the site (it does not, inside a Python
    body)
  - `:41` — `_QUOTED_HEREDOC_START_RE` and the terminator check at `:175`:
    column-0 semantics
  - `:149-198` — `_find_unsafe_context_interpolations`: the Python-literal
    position distinction and the `-c "` host shape
  - `:201-237` — the validator's message text (see below), plus the marker's
    own well-formedness check, which emits `ValidationSeverity.ERROR` (not
    WARNING) for a malformed or reasonless marker
  - **new** — marker parsing: grammar, per-variable matching, placement
    (trailing or preceding-line), and the `${`-rejection guard. Note the
    existing scanner `continue`s on any line whose `stripped.startswith("#")`
    (`:170-171`) and skips heredoc interiors wholesale (`:166-169`); both paths
    change under this issue, so marker lines must be read *before* those skips
    rather than falling through them
- `scripts/little_loops/fsm/interp_sweep.py` (new), created by ENH-3338 — **not
  modified here**; imported. `classify_site()` is the single implementation of
  the classification rule.
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the two idioms, in or beside
  §The Design Rules where the MR table lives.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation/__init__.py:118-126,184-217` — imports
  and re-exports `_UNSAFE_CONTEXT_INTERP_RE`, `_QUOTED_HEREDOC_START_RE`, and
  `_find_unsafe_context_interpolations` by literal name (both in its `from
  shell_safety import (...)` block and its `__all__` list). Confirmed via
  `ll-code importers-of` + grep: these are the exact symbols step 1's regex
  removal/replacement targets. If any of the three is removed or renamed
  while delegating to `interp_sweep.scan_action()`/`classify_site()`, this
  file's import block and `__all__` must be updated in the same change or the
  package fails to import (`ImportError`) — this supersedes the existing
  Dependent Files bullet below, which characterizes the risk as "no change
  expected unless the rule is split." It is not about splitting the rule; it
  is about `__init__.py` importing constants by name that this issue may
  remove.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/fsm/validation/__init__.py` — imports and re-exports
  `_UNSAFE_CONTEXT_INTERP_RE`, `_QUOTED_HEREDOC_START_RE`, and
  `_find_unsafe_context_interpolations` by literal name, both in its
  `from shell_safety import (...)` block and its `__all__` list. If any of the
  three is removed or renamed while delegating to
  `interp_sweep.scan_action()`/`classify_site()`, this file's import block and
  `__all__` must be updated in the same change or the package fails to import
  (`ImportError`) — not contingent on "splitting the rule."
- Every loop in `scripts/little_loops/loops/**` is subject to the widened
  rule. This is not the whole blast radius: `validate_fsm()` also runs over
  inline FSM YAML fixtures embedded directly in test files outside that
  glob — `test_builtin_loops.py`, `test_create_loop.py`,
  `test_enh2892_subloop_failure_dispatch.py`, `test_fsm_executor.py`,
  `test_fsm_fragments.py`, `test_interp_sweep.py`, `test_ll_loop_commands.py`,
  `test_rn_implement.py`, `test_rn_remediate.py`, and
  `test_verify_issue_loop.py`. Any such fixture using a non-allowlisted
  context key (or `captured`/`prev` namespace) in a shell action begins
  emitting a new MR-11 WARNING post-widening and needs the same triage
  (convert or mark) as corpus loops (see Implementation Steps step 7).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation/structural_rules.py:68-71,1165` — the
  actual call site of `_validate_unsafe_context_interpolation(fsm)` (confirmed
  via `ll-code callers-of`), invoked from `validate_fsm()` (`:983`) alongside
  `_validate_bash_default_interpolation` and `_validate_overescaped_shell`,
  which it also imports from `shell_safety.py`. This corrects/completes the §
  Call Path description above — the dispatcher is `structural_rules.py`'s
  `validate_fsm()`, not `validation/__init__.py` (which only re-exports).
  Signature is unchanged per § Program Design, so no edit is expected here,
  but this is the file to check first if `ll-loop validate` stops calling
  MR-11 after the refactor.
- `scripts/tests/test_fsm_validation_shell_safety.py:14-19` — imports
  `_validate_unsafe_context_interpolation` and friends from
  `little_loops.fsm.validation` (the `__init__.py` re-export), not directly
  from `shell_safety.py` — a second, test-side consumer of the re-export risk
  noted above.
- `scripts/tests/test_interp_sweep.py` — ENH-3338's own unit suite for
  `classify_site()` / `scan_action()` (confirmed via `ll-code importers-of`),
  already covering the column-0 heredoc-terminator distinction
  (`TestScanActionHeredoc::test_heredoc_terminator_must_be_column_zero`) and
  Python-body classification that this issue's delegation consumes. Not
  currently listed anywhere in this issue; keep green — it is the existing
  coverage for behavior step 1 delegates to, not new coverage to write.

### Tests

- `scripts/tests/test_fsm_validation_shell_safety.py` — the MR-11 unit suite.
  Existing fixtures to preserve: `test_mr11_does_not_fire_inside_quoted_heredoc`
  (`:267-273`, marker-agnostic — uses `LL_EOF`) and the `:shell` non-firing case
  (`:276`). **`test_mr11_does_not_fire_inside_quoted_heredoc` asserts the exact
  behavior item 3 above says is wrong** — it must be revised, not merely kept
  green. Record the revision explicitly; a silently rewritten assertion is how
  this rule got narrow in the first place. Also needs new cases, one per
  acceptance criterion, distinct from the marker tests below: a
  `${context.<key>}` outside the old seven-key allowlist inside a Python
  literal (AC 1); `${captured.*}` inside a Python literal (AC 2);
  `${prev.output}`/`${prev.stderr}` flagged and `${prev.exit_code}` clean at a
  bash-token position (AC 2b); a quoted-heredoc-as-Python-body case flagged
  vs. quoted-heredoc-as-non-Python-body clean (AC 3); an indented
  marker-equal line not closing the tracked heredoc block (AC 4); and
  `:shell` flagged inside a Python body but clean at a bash-token position,
  with the Python-body message naming the `LL_ARG_` hoist remedy (AC 5b).
- `scripts/tests/test_builtin_loops.py` — ENH-3338's baseline test stays green;
  plus the marker-count ratchet assertion (AC 8c), which belongs here beside the
  other corpus-wide guards rather than in the MR-11 unit suite.
- `scripts/tests/test_fsm_validation_shell_safety.py` — the marker unit tests
  (AC 8b): per-variable exemption, both placements, each malformed form → ERROR,
  `${`-bearing marker → ERROR, ordinary comment → not a marker.
- `ll-loop validate` across the whole corpus must be clean **after** the widening.

### Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — required.
- `.claude/CLAUDE.md` §Loop Authoring references the guide's rule table; check
  whether the widened rule needs a line there.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:872` — describes MR-11 with the exact old seven-key
  allowlist (`${context.input|goal|description|task|prompt|query|topic}`) and
  states "single-quoted string, quoted heredoc `<<'EOF'`, or the `:shell`
  suffix" are unconditionally safe positions. Both claims are contradicted by
  the widened § Decision Rules table (quoted-heredoc-as-Python-body and
  `:shell`-inside-a-Python-body are now flagged, not clean). Needs revision in
  the same change.
- `docs/reference/API.md:6416` — the near-identical duplicate of the CLI.md
  passage above; same stale allowlist and same "always-safe" claim, needs the
  same fix. Also `:6309` ("a distinct hazard from the bash-position risk MR-11
  ... checks") describes MR-11 and `interp_sweep` as covering disjoint
  hazards; after this issue MR-11 delegates to `interp_sweep` for the
  Python-body hazard too, so this line is worth a wording pass (lower
  priority than `:6416`). `:6322` already names this issue by ID
  ("ENH-3342 imports it to widen MR-11") and needs no change.
- `skills/review-loop/reference.md:50` — a third near-duplicate copy of the
  same stale allowlist + "quoted heredoc is safe" text, in a rule-summary
  table row. Needs the same correction as the two docs above.
- `docs/guides/LOOPS_REFERENCE.md:1831` — checked, no correction needed: it
  describes `flux-image-generator`'s prompt as read from a *file* inside the
  heredoc (the safe heredoc-to-file idiom this issue documents), not a raw
  `${context.*}` interpolation into the heredoc body.

### Configuration

- N/A — `unsafe_context_interpolation_ok` already exists and is not extended.
  The marker is deliberately **not** config: it lives in the loop YAML beside the
  site it exempts, where a reviewer reading that action sees it. A config-file
  allowlist would put the exemption somewhere nobody reading the code will look.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **No existing precedent for a per-site inline suppression marker.** Every
  existing suppression mechanism in the FSM validation family is a loop-level
  boolean flag on `FSMLoop` (`schema.py:1428-1472`, e.g.
  `unsafe_context_interpolation_ok`, `tamper_guard_ok`, `terminal_action_ok`).
  No rule in `scripts/little_loops/fsm/validation/*.py` parses an inline
  per-site comment marker today; `policy_rules.py:131`'s `startswith("#")` is
  an ordinary comment-skip, not marker parsing. The `# ll-lint:
  mr11-ok(<var>) <reason>` grammar this issue specifies is new mechanism in
  this codebase, not an established idiom to match.
- **Two existing, differently-shaped precedents for tracking "known/accepted
  residual findings" both live in the test suite, not inline in loop YAML —
  and they disagree with each other on directionality:**
  - `test_builtin_loops.py:16399-16429`'s ratcheted-category ALLOWLIST: a
    hardcoded `set[(loop, category, path)]` tuple literal in the test file.
    `test_deterministic_warning_categories_do_not_regrow` checks one
    direction (new unallowlisted findings fail); a companion
    `test_allowlist_entries_are_not_stale` checks the other (a stale entry
    that no longer produces its warning must be removed).
  - ENH-3338's baseline (`test_builtin_loops.py:19183-19226`,
    `scripts/tests/data/loop_interpolation_baseline.json`): a checked-in
    JSON file of per-site entries, asserted via exact-set equality
    (`discovered == expected`) in a single test — new sites fail as
    "unbaselined", removed/converted sites fail as "stale", both directions
    from one assertion.
  Both precedents centralize the accepted-finding registry in the test
  suite as a structured, per-entry set (not a bare count) and both are
  bidirectional. This doesn't contradict this issue's own rejection of
  extending the ENH-3338 baseline for MR-11 (correct — MR-11 never reads
  it), but it means AC 8c's "checked-in marker count asserted by a test" is
  a weaker shape than either sibling precedent: a bare integer identifies
  how many markers exist, not which sites carry them or whether any one of
  them has gone out of date. The `grep -rn` enumeration AC 8c already
  requires gets closer to the sibling patterns' per-entry structure than a
  count alone would — worth weighing before deciding how far to match them.
- **ERROR severity in this rule family fires in exactly two existing shapes,
  never from unparseable free-text.** Across every current `ERROR` emission
  (`_base.py:34`'s dataclass default, `shell_safety.py:90,143`,
  `meta_rules.py:106`, `evaluator_rules.py:318`, `structural_rules.py:908`,
  `reachability.py:95,511,542`), the trigger is either (a) an unresolvable
  static reference (e.g. the static `loop:` ref check), or (b) a value
  outside a fixed enum/grammar (`tamper_guard:`, `prepatch_check:` must be
  one of a closed set of literal strings). No existing rule emits `ERROR`
  for malformed free-text comment syntax. The proposed malformed-marker
  `ERROR` would be this family's first ERROR triggered by unparseable
  ad-hoc grammar rather than reference-resolution or enum-membership
  failure — the closest shape to imitate is the enum-membership check
  (tamper_guard/prepatch_check), not the reference-resolution check.
- **The Design Rules table's row format is fixed and MR-11's own row is the
  template to preserve.** `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`'s table
  (`:92` for the current MR-11 row) is 5 columns: Rule | What it requires |
  Why | Severity | Suppress with. Worked examples that don't fit a cell are
  added as prose/code blocks in a `###`-level subsection immediately after
  the table, not crammed into a cell — see MR-1's own "Canonical MR-1
  example" subsection (`:118-127`) for the existing shape. The two idiom
  code blocks this issue adds should follow that same after-the-table
  subsection convention rather than inventing a new placement.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Correction to the "no per-site marker precedent" finding above: the `policy_rules.py:131` citation is misplaced.** `policy_rules.py` lives at `scripts/little_loops/fsm/policy_rules.py` — outside the `scripts/little_loops/fsm/validation/*.py` glob that finding is scoped to — and implements an unrelated policy-router/decision-table predicate-rule parser (`lhs -> rhs` routing rules), not any FSM validation rule. Line 131's `if not line or line.startswith("#"): continue` is real, but it is not evidence about conventions inside the FSM-validation rule family; the underlying claim (no existing per-site marker mechanism in `fsm/validation/*.py`) still holds, just not on this citation.
- **Correction to the "Design Rules table format" finding above: `:92` is the table header row, not MR-11's row.** `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:92` is `| Rule | What it requires | Why | Severity | Suppress with |`. The current MR-11 row is at `:104`.
- **Correction to the `mechanize-skills.yaml:283-286` marker-rationale example: it is stale.** BUG-3341 (status: done) already converted the second reference at these lines. Current `mechanize-skills.yaml:283` reads `SKILL_FILE="${captured.current_skill.output}" python3 << 'PYEOF'` (bash-token position, already converted) and `:286` reads `${context.run_dir}` — `run_dir` is a trusted key per this issue's own Decision Rules table, not a raw "unsafe sibling". The file no longer exhibits the unconverted-raw-sibling failure shape at these lines; it is historical precedent from before BUG-3341 landed, not a live example. The design principle it illustrates (a bare line-level marker would exempt every site on the line) stands independent of this specific example being live.
- **Correction to the "ERROR severity fires in exactly two shapes" finding above: two of its own cited examples don't fit either named bucket.** `meta_rules.py:106` (MR-1) fires because the loop declares no non-LLM evaluator at all, and `structural_rules.py:908` fires because a template-capable loop has no `artifact_output` block — both verified at those lines. Neither is "an unresolvable static reference" nor "a value outside a fixed enum/grammar"; they are a third shape (a required field/capability is absent). This weakens, but does not defeat, the conclusion that the enum-membership check (tamper_guard/prepatch_check) is the closest existing shape for the marker's malformed-syntax ERROR to imitate — a missing-required-declaration shape is at least as close a fit.
- **`scripts/tests/test_builtin_loops.py:16311-16330` (`TestValidatorWarningBudget.CATEGORY_PATTERNS["unsafe-context-interp"]`) hardcodes the substring `"interpolates user-controlled context raw into a shell body"`** as the sole classifier mapping MR-11's live WARNING message to the pre-existing corpus-wide regression ratchet (`test_deterministic_warning_categories_do_not_regrow` / `test_allowlist_entries_are_not_stale`, `:16394` onward). Verified via grep: this is the only other consumer of that exact substring in the repo. Step 6/message-update step's planned message rewrite must preserve this substring (or the classifier's pattern must be updated in the same change) — if the rewritten message drops it, `_classify()` silently returns `None` for every MR-11 warning and this ratchet stops tracking MR-11 with no test failure to signal it.
- **The blast radius of "every loop in `scripts/little_loops/loops/**`" is incomplete.** `validate_fsm()` also runs over inline FSM YAML fixtures embedded directly in test files outside that glob. Confirmed via grep for `action_type: shell` fixtures containing `${context.*}`: `scripts/tests/test_builtin_loops.py`, `test_create_loop.py`, `test_enh2892_subloop_failure_dispatch.py`, `test_fsm_executor.py`, `test_fsm_fragments.py`, `test_interp_sweep.py`, `test_ll_loop_commands.py`, `test_rn_implement.py`, `test_rn_remediate.py`, `test_verify_issue_loop.py`. Any such fixture using a non-allowlisted context key (or `captured`/`prev` namespace) in a shell action begins emitting a new MR-11 WARNING post-widening; the step-6 triage plan (marker or convert) is scoped to `scripts/little_loops/loops/**` and does not name a triage path for test fixtures.
- **`scripts/tests/test_flux_image_generator.py:187-206` (`test_no_raw_user_input_in_shell_actions`, docstring-labeled "MR-11") independently hand-duplicates the exact fixed seven-key list** (`${context.input}`, `${context.description}`, `${context.prompt}`, `${context.query}`, `${context.task}`, `${context.goal}`, `${context.topic}`) this issue drops from `_UNSAFE_CONTEXT_INTERP_RE`, checked as raw substring absence against `WRAPPER`/`ORACLE`. It won't break post-widening, but it stays a narrower, hand-maintained duplicate of exactly the mechanism this issue's Motivation says should be the single ratchet.

## Scope Boundaries

**In scope:** MR-11's matcher width, namespace coverage, Python-literal position
awareness, and column-0 terminator; the validator's message text; the
`# ll-lint: mr11-ok(<var>)` marker (grammar, parsing, well-formedness ERROR, and
the marker-count ratchet); the guide's idiom documentation; triage of findings
the widening surfaces.

**Out of scope:** the suffix grammar (ENH-3337); the sweep and its baseline
(ENH-3338); converting the 145 epic sites (BUG-3339/3340/3341); raising MR-11's
*finding* severity to `ERROR` (the marker's well-formedness check is a separate,
new ERROR and does not change MR-11's finding severity — see § Severity);
extending the marker to other MR rules; removing or deprecating the loop-level
`unsafe_context_interpolation_ok` flag.

## Program Design

### Signatures

- `_find_unsafe_context_interpolations(fsm: FSMLoop) -> list[tuple[str, str]]`
  (`shell_safety.py:148`) — same signature; body delegates to
  `interp_sweep.scan_action()` / `classify_site()`.
- `_validate_unsafe_context_interpolation(fsm: FSMLoop) -> list[ValidationError]`
  (`shell_safety.py:191`) — same signature; message text updated.
- `classify_site(namespace: str, key: str) -> str` (ENH-3338,
  `scripts/little_loops/fsm/interp_sweep.py`) — **imported, not reimplemented.**
- `_parse_mr11_marker(line: str) -> MarkerParse | None`
  (`shell_safety.py`, new) — returns the exempted `<namespace>.<key>` and the
  reason for a well-formed marker, a malformed-marker sentinel carrying the
  defect for the ERROR path, or `None` for an ordinary comment. Proposed name;
  keep it private to `shell_safety.py` — the marker is MR-11's, not a
  cross-rule mechanism.

### Decision Rules

The rule MR-11 enforces after widening:

| Position of an untrusted interpolation | Verdict |
|---|---|
| bash token position, not single-quoted, carries `:shell` | clean (unchanged) |
| bash token position, not single-quoted, no `:shell` | flag (unchanged) |
| inside a quoted heredoc that is **not** a Python body | clean (unchanged) |
| inside a quoted heredoc that **is** a Python body, in a string literal | **flag (new)** |
| inside a quoted heredoc that **is** a Python body, carrying `:shell` | **flag (new)** — see below |
| inside a `python3 -c "…"` body | **flag (new)** |
| trusted key (`run_dir`, `promoted_artifact`, `_`-prefixed), `prev.exit_code`/`state`/`timeout_kind`, or `${loop.*}` | clean |
| carries a well-formed `# ll-lint: mr11-ok(<this var>) <reason>` marker | clean, and counted against the marker ratchet |
| carries a malformed / reasonless / `${`-bearing marker | **ERROR** (louder than the warning it tried to silence) |

Untrusted-ness comes from `classify_site()`: `captured.*` always,
`prev.output`/`prev.stderr` always, `context.*` minus the enumerated trusted set.
**Not** a fixed untrusted-key allowlist.

**`:shell` is position-dependent, and an earlier draft of this table got it
wrong.** It read "carries `:shell` anywhere in its suffix chain → clean,"
unqualified. `:shell` is `shlex.quote()`, which is safe only at a **bash token
position**; inside a quoted heredoc bash does nothing, so the quoted form is
handed straight to the Python parser:

```
shlex.quote("don't")  ->  '\'don\'"\'"\'t\''
goal = ''don'"'"'t''  ->  SyntaxError: unterminated string literal
```

Clearing on `:shell` unconditionally would make MR-11 certify the single most
likely bad BUG-3340 conversion as clean. The lint must flag it, and its message
should name the specific remedy — hoist the `:shell` out to a `LL_ARG_X=` binding
on the `python3` invocation line — rather than the generic text.

### Severity

Keep `WARNING` **for findings**. Raising to `ERROR` would hard-fail
`ll-loop validate` on consuming projects' pre-existing loops at upgrade time,
which is a migration this epic did not scope. Reconsider in a follow-up once the
idiom is documented and has shipped for a release. Record this as a decision.

**The marker's well-formedness check is `ERROR`, and that is deliberate and not
in tension with the above.** A consuming project that never writes a marker never
sees it, so it adds no upgrade-time hard failure — the only way to trip it is to
write a marker and write it wrong. Making it a WARNING would mean a malformed
marker both fails to suppress *and* fails to announce itself clearly, which is
the worst of both.

### Expected finding surface

The widening will surface **pre-existing findings in files EPIC-3336 does not
otherwise touch** — that is the point of dropping the allowlist, and it is why
this issue runs last. **Neither `unsafe_context_interpolation_ok` nor a
re-narrowed regex is an acceptable response.** Budget for this triage; it is not
a rubber stamp.

#### Triage — resolved 2026-08-27

An earlier draft offered "add it to ENH-3338's baseline as class-C/accepted with
a reason" as an outcome. **That does not work, and it made the ACs
self-contradictory.** ENH-3338's baseline is a *test data file* consumed by
`test_builtin_loops.py`; MR-11 never reads it, and had no per-site suppression —
only the loop-level `unsafe_context_interpolation_ok` flag this issue forbids. So
a baselined finding still emitted a WARNING, and the old AC 5 ("`ll-loop validate`
clean across the entire corpus") could not hold alongside the old AC 8.

**Resolution: this issue adds a per-site inline marker** (see the next section),
so corpus-wide cleanliness stays a real, continuously-enforced property rather
than being traded away. Triage per finding is then:

- **Convert it** — the default, and always preferred.
- **Mark it** with an inline `# ll-lint: mr11-ok(<var>) <reason>` naming a
  tracking issue, when conversion is genuinely out of this epic's reach.
- **Never** `unsafe_context_interpolation_ok`, and never a re-narrowed pattern.

The deferral option (carry residual warnings until a follow-up lands) was
considered and rejected: EPIC-3336's Motivation leans on the corpus being
MR-11-clean so that *any* warning is a regression signal, and a window of
ambient warnings destroys exactly that property for the duration.

### The `# ll-lint: mr11-ok(...)` marker — in scope for this issue

A narrow, per-site, reason-bearing escape hatch. Grammar:

```
# ll-lint: mr11-ok(<namespace>.<key>) <reason, must reference an issue ID>
```

Design constraints, each one a lesson from how MR-11 got narrow in the first
place:

1. **It names the variable it exempts.** A bare line-level marker would exempt
   *every* site on that line — the `mechanize-skills.yaml:283-286` failure shape
   (one converted binding, a raw sibling on the next line) is precisely what a
   line-level exemption would hide. The parenthesized `<namespace>.<key>` is
   mandatory.
2. **A reason is mandatory and must cite an issue ID.** A marker with no reason,
   no parenthesized variable, or a malformed one is itself a validation
   **ERROR** — not a silently-ignored comment. A lazy blanket marker must fail
   louder than the warning it was trying to silence.
3. **Placement: trailing on the site's own line, or alone on the line
   immediately above it.** The two-line form is required for a
   `python3 -c "…"` one-liner, where a trailing `#` would comment out the rest
   of the Python body; there the marker goes on a preceding *shell* comment
   line. Inside a heredoc Python body both forms are ordinary Python comments.
4. **The marker must not quote the token it exempts.** The FSM interpolates the
   whole action string, comments included
   (`reference_fsm_action_interpolated_before_bash`), so writing
   `# ll-lint: mr11-ok(context.goal) — see ${context.goal}` makes the comment its
   own live interpolation site. The grammar's `<namespace>.<key>` is bare text
   with no `${`, which is what keeps it inert; reject a marker containing `${`.
5. **Markers are counted.** A test asserts the total marker count in the corpus
   against a checked-in integer, so adding one is a deliberate, reviewed act
   rather than a quiet edit. Removing one needs no ceremony — the count only
   ratchets down.

The loop-level `unsafe_context_interpolation_ok` flag is **not** removed or
deprecated here (that is a migration this epic did not scope), but no loop in the
corpus sets it and none may start.

### Call Path

`ll-loop validate` → `validation/__init__.py` rule dispatch →
`_validate_unsafe_context_interpolation(fsm)` →
`_find_unsafe_context_interpolations(fsm)` → `interp_sweep.scan_action()` →
`classify_site()` → `ValidationError(WARNING)` per finding.

No runtime path — validation only.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Stale signature-anchor citations.** `_find_unsafe_context_interpolations` is at `:149` (not `:148`); `_validate_unsafe_context_interpolation` is at `:201` (not `:191`) — both shifted by the same ENH-3337 offset noted under Current Behavior/Integration Map above.
- **`scan_action()` cannot supply AC 2b's bash-token-position finding, and the Signatures/Summary framing of "delegates to scan_action()" is inconsistent with the Decision Rules table.** `interp_sweep.scan_action()`'s own docstring (`interp_sweep.py:128-134`) states it reports only sites inside an embedded Python body (heredoc-is-python or a `python3 -c "…"` string) and states verbatim: "Tokens outside any Python body (plain bash position, including a `:shell` binding on a `python3` invocation line) are not reported here — that position is MR-11's territory (ENH-3342), not this baseline's." AC 2b requires MR-11 to keep flagging a bash-token-position site (`PREV_OUTPUT="${prev.output}"`, `rlhf-svg-evaluate.yaml:517` — confirmed a plain double-quoted bash assignment, no heredoc or `-c` body around it, and confirmed absent from `scripts/tests/data/loop_interpolation_baseline.json`, since ENH-3338's own scanner never records bash-position sites). Full delegation to `scan_action()` as the Signatures entry states cannot produce this finding. The constraint this issue must satisfy: MR-11 needs **two independent scan paths** sharing the same classification primitive — (1) the existing bash-token-position line scan (today's `_UNSAFE_CONTEXT_INTERP_RE.finditer` loop), re-targeted from the fixed 7-key regex to extract `namespace.key` for **any** namespace and classify it via `interp_sweep.classify_site(namespace, key)`, keeping the existing single-quote / `:shell`-position rules unchanged at that position; and (2) delegation to `interp_sweep.scan_action()` for the Python-literal-position half (AC 1, 2, 3, 5b's Python-body case). The Summary's weaker claim ("MR-11 consumes `classify_site()` rather than reimplementing the classification rule") is the accurate one; the Signatures entry's stronger "body delegates to `interp_sweep.scan_action()`" over-claims full delegation and should be read as "delegates to `scan_action()` for the Python-body half only."
- **Adapter gap between `scan_action()`'s shape and `_find_unsafe_context_interpolations`'s current contract.** `scan_action(action, *, state, file)` (`interp_sweep.py:128`) takes a mandatory keyword-only `file: str` and returns `list[InterpSite]` (`var`/`cls`/`host_shape`/`line`/`count` fields), not `(state_name, token)` tuples. `FSMLoop` (`schema.py`) has no source-file-path field to supply as `file`. `InterpSite.var` is the bare `namespace.key_path` with no suffix chain, whereas the current `token` returned by `_find_unsafe_context_interpolations` is the full `${context.<raw>}` text including suffixes, which `_validate_unsafe_context_interpolation`'s message builder interpolates directly into the WARNING text. Reconciling these two shapes (what `file` value to pass for the Python-body half; how to reconstruct a message-worthy token from an `InterpSite` for that half) is required before "same signature" in the Signatures entry above is achievable.
- **The Decision Rules table's two bash-token-position rows are not actually "(unchanged)".** Today, bash-token-position scanning uses `_UNSAFE_CONTEXT_INTERP_RE`, which matches only `context.*` with the old fixed 7-key list — so `${prev.output}` and `${captured.*}` at a bash-token position are invisible today (per Current Behavior item 2 and AC 2b). Post-widening, bash-token-position untrusted-ness must also come from `classify_site()` across all namespaces (same source as the Python-literal-position rows), not a namespace-restricted regex. The `:shell`-clears-it / not-single-quoted mechanics at that position are unchanged, but the namespace scope feeding into "is this token untrusted" is not — the table's "(unchanged)" label describes only the flag/clean mechanics, not the namespace coverage, and should not be read as "bash-position scanning needs no code change."

## Implementation Steps

1. Replace the bash-token-position scan's fixed seven-key regex match with a
   namespace-generic lookup through `classify_site()` (covering `context.*`
   beyond the old allowlist plus the `captured` and `prev` namespaces),
   keeping the existing single-quote / `:shell`-position clearing rules
   unchanged at that position. Add a second, independent scan path that
   delegates to `interp_sweep.scan_action()` for the Python-literal-position
   half (a quoted heredoc that is a Python body, or a `python3 -c "…"` body).
   Both paths share `classify_site()` as the single untrusted-key classifier.
   `scan_action()` alone cannot produce AC 2b's bash-token-position finding —
   its docstring scopes it to Python-body sites only — so the bash-token-
   position scan must stay independent, not be replaced by delegation. Keep
   MR-11's per-state / `action_type` / suppression-flag scaffolding.
2. Add the Python-literal-position distinction and the `-c "` host shape to
   the `scan_action()`-delegated path.
3. Tighten the heredoc terminator to column 0.
4. Revise `test_mr11_does_not_fire_inside_quoted_heredoc` to assert the
   corrected semantics, and record why the old assertion was wrong. Add new
   unit test cases for AC 1, 2, 2b, 3, 4, and 5b — each needs its own case (a
   non-allowlisted `context.*` key, `captured.*`, `prev.output`/`prev.stderr`
   vs. `prev.exit_code`, the two heredoc-body cases, the column-0 terminator
   case, and the `:shell`-inside-a-Python-body vs.
   `:shell`-at-bash-token-position cases) — distinct from the
   marker-constraint tests in step 5.
5. Implement the `# ll-lint: mr11-ok(<var>) <reason>` marker: grammar, per-
   variable matching, both placements, the `${`-rejection guard, the
   malformed-marker ERROR, and the checked-in marker-count ratchet. Do this
   **before** the corpus-triage step (step 7 below) — triaging without the
   mechanism is what forced the earlier draft's contradiction.
6. Update the validator's message to name both remedies concretely — the
   `LL_ARG_X=${context.x:shell}` + `os.environ` idiom and the
   `LL_RAW_9F3C1A7E_EOF` heredoc-to-file idiom — and link the guide section.
   Sequenced before the corpus-triage step so triage surfaces findings against
   the final message text.
7. Run `ll-loop validate` across the corpus; triage every newly surfaced
   finding — convert it, or mark it with a reason citing a tracking issue.
   This includes findings from the inline FSM YAML test fixtures outside
   `scripts/little_loops/loops/**` (see Integration Map § Dependent Files),
   not only built-in loops. Do not set `unsafe_context_interpolation_ok`, do
   not re-narrow the pattern, and do not baseline (MR-11 does not read
   ENH-3338's baseline).
8. Document both idioms in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` with the
   canonical copy-pasteable blocks, including the column-0 hoisting rule and the
   `<state>-<capture>.txt` naming rule.
9. Record the WARNING-vs-ERROR severity decision.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/fsm/validation/__init__.py` — keep its
  `from shell_safety import (...)` block and `__all__` list in sync with
  whatever `_UNSAFE_CONTEXT_INTERP_RE` / `_QUOTED_HEREDOC_START_RE` /
  `_find_unsafe_context_interpolations` become; a removed or renamed symbol
  that is still imported here breaks the package at import time.
- Update `docs/reference/CLI.md:872` and `docs/reference/API.md:6416` — both
  state the old seven-key allowlist and "quoted heredoc / `:shell` is always
  safe" as fact; revise to match the widened § Decision Rules table.
- Update `skills/review-loop/reference.md:50` — same stale MR-11 summary row,
  same fix.
- Verify `scripts/tests/test_interp_sweep.py` stays green — it is the
  existing unit coverage for the `classify_site()`/`scan_action()` behavior
  step 1 delegates to; no new test file is needed there, only confirmation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **No listed step directs writing the new unit tests Acceptance Criteria 1, 2, 2b, 3, 4, and 5b each require.** Step 4 only revises one pre-existing fixture (`test_mr11_does_not_fire_inside_quoted_heredoc`); Step 5 (marker implementation) covers AC 8b's per-constraint tests but not these six. Constraint: `scripts/tests/test_fsm_validation_shell_safety.py` needs new cases covering — a `${context.<key>}` outside the old 7-key allowlist inside a Python literal (AC 1); `${captured.*}` inside a Python literal (AC 2); `${prev.output}`/`${prev.stderr}` flagged and `${prev.exit_code}` clean, each at a bash-token position (AC 2b); a quoted-heredoc-as-Python-body case flagged vs. quoted-heredoc-as-non-Python-body clean (AC 3); an indented marker-equal line not closing the tracked heredoc block (AC 4); and `:shell` flagged inside a Python body but clean at a bash-token position, with the Python-body message naming the `LL_ARG_` hoist remedy (AC 5b). These are additive test cases the acceptance criteria require, distinct from the AC 8b marker-constraint tests already named in Step 5.
- **The two-scan-path constraint from § Program Design's Codebase Research Findings above (independent bash-token-position scan via `classify_site()`, separate from `scan_action()` delegation for the Python-body half) is not expressed anywhere in these steps.** Step 1 as written ("replace MR-11's regex-based detection with a call into ENH-3338's scanner") reads as a single full substitution; literally executed, it satisfies AC 1/2/3/5b (the Python-body cases `scan_action()` covers) but cannot produce AC 2b's bash-token-position finding, since `scan_action()`'s own docstring excludes that position by design. The bash-token-position half needs its own widened scan (namespace-generic `classify_site()` lookup replacing the old fixed-key regex match), kept alongside — not replaced by — the `scan_action()` delegation.

## Acceptance Criteria

1. MR-11 flags an untrusted `${context.<any-key>}` — not only the seven
   allowlisted ones — inside a Python literal, with a unit test using a key
   outside the old allowlist.
2. MR-11 flags an untrusted `${captured.*}` inside a Python literal, with a unit
   test. Class B is no longer invisible to the lint.
2b. MR-11 flags `${prev.output}` / `${prev.stderr}` in an unsafe position and
   does **not** flag `${prev.exit_code}`, with a unit test for each. The live
   bash-position site `rlhf-svg-evaluate.yaml:517`
   (`PREV_OUTPUT="${prev.output}"`) is flagged and triaged per Expected finding
   surface — ENH-3338's baseline does not cover bash-position sites, so this rule
   is the only guard for it.
3. MR-11 distinguishes a quoted heredoc that is a Python body from one that is
   not, and flags only the former — with a unit test for each side.
4. MR-11 closes a heredoc only on a column-0 terminator; an indented
   marker-equal line does not end the tracked block, with a unit test.
5. MR-11 does not fire on any correctly converted site — verified by
   `ll-loop validate` running clean across the **entire corpus** after
   BUG-3339 / 3340 / 3341 have landed, with **no** loop setting
   `unsafe_context_interpolation_ok`. Residual pre-existing findings are
   converted or marked (AC 8); the corpus's zero-warning property is preserved
   continuously, not restored later.
5b. MR-11 flags a `:shell`-suffixed interpolation inside a Python body and does
   **not** flag one at a bash token position, with a unit test for each. Its
   message for the former names the hoist-to-`LL_ARG_` remedy specifically.
6. `classify_site()` is imported from `interp_sweep`, not duplicated in
   `shell_safety.py`.
7. `test_mr11_does_not_fire_inside_quoted_heredoc` is revised, and the reason the
   original assertion was wrong is recorded in the test or this issue.
8. Every finding surfaced by the widening is triaged — converted in this issue,
   or exempted with a well-formed `# ll-lint: mr11-ok(<var>) <reason>` marker
   citing a tracking issue. None is suppressed via
   `unsafe_context_interpolation_ok` or by re-narrowing the pattern. Baselining
   is **not** an accepted outcome — MR-11 does not read ENH-3338's baseline.
8b. The marker is implemented per § The `# ll-lint: mr11-ok(...)` marker, with a
   unit test for each constraint: it exempts only the named variable (a sibling
   site on the same line still fires); a marker with no reason, no parenthesized
   variable, or a `${` in it is an **ERROR**; both placements work, including the
   preceding-line form for a `python3 -c "…"` one-liner; and an ordinary comment
   is not mistaken for a marker.
8c. The corpus's marker count is checked in and asserted by a test. Every marker
   present at close carries a reason naming a tracking issue —
   `grep -rn "ll-lint: mr11-ok" scripts/little_loops/loops/` enumerates them, and
   the enumeration is recorded in this issue so the residual set is visible
   rather than diffuse.
9. `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` documents both idioms with
   copy-pasteable blocks, the column-0 hoist rule, the `<state>-<capture>.txt`
   naming rule, and the marker's grammar and placement rules — including that it
   is a last resort and must not quote the token it exempts.
10. The WARNING-vs-ERROR severity decision is recorded with its rationale.
11. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 (raised from P3) — the only child that stops the class from
  returning, and the only one whose effect reaches loops in consuming projects.
- **Effort**: Medium–Large — raised when the marker was scoped in (2026-08-27).
  Three parts now: the lint widening (contained), the marker mechanism (new
  parsing, a new ERROR path, and a count ratchet — small but genuinely new lint
  surface), and step 6's triage of newly-surfaced pre-existing findings, which is
  open-ended by design. The marker is what keeps that triage from being
  unbounded: a finding beyond this epic's reach costs one reviewed line, not a
  conversion.
- **Risk**: Low to runtime (validation only). Two process risks. First, an
  implementer under time pressure re-narrows the pattern or sets the loop-level
  flag to make `ll-loop validate` green — AC 8 exists to make that visible.
  Second, and new: **the marker becomes the path of least resistance** and the
  triage turns into a marking exercise. The count ratchet (AC 8c) and the
  mandatory issue-citing reason are the countermeasures; if the residual marker
  count comes out large, that is a signal to convert more, not to accept it.
- **Breaking Change**: No. MR-11 findings stay at `WARNING`, so consuming
  projects see new warnings, not failures. The marker's well-formedness check is
  an `ERROR`, but it is unreachable for any project that does not write a marker.

## Status

**Open** | Created: 2026-08-27 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue shares
`scripts/tests/test_builtin_loops.py` with [ENH-3347]. ENH-3347 adds the four
behavioral injection/quote-breaking test cases; this issue adds the
marker-count ratchet assertion (AC 8c) and keeps ENH-3338's baseline test
green. The existing `blocked_by`/`blocks` edge (ENH-3347 blocks this issue)
already sequences the edits — land in that order.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-29_

**Readiness Score**: 75/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 45/100 → LOW

_Supersedes the 85/71 scores from the prior `/ll:confidence-check` pass
(2026-08-29T16:27:18), which ran **before** the subsequent `/ll:refine-issue`
(16:34:32) and `/ll:verify-issues` (16:43:36) passes surfaced the Program
Design adapter-gap finding and the `verify_verdict: PROPOSAL_UNSOUND` verdict
below — this run incorporates both._

### Concerns
- `verify_verdict: PROPOSAL_UNSOUND` is currently persisted on this issue (no
  accompanying body findings — `/ll:verify-issues --check` mode writes only
  the frontmatter verdict). Per its definition, this means the Proposed
  Solution, implemented as written, contradicts the code it names. The most
  plausible source, from this issue's own text, is the Program Design
  "Adapter gap" finding below.
- **Program Design's own Codebase Research Findings admit the Signatures
  entry over-claims.** `_find_unsafe_context_interpolations` is stated to
  have the "same signature; body delegates to `interp_sweep.scan_action()`",
  but the findings immediately below it say this "over-claims full
  delegation" — `scan_action()`'s own docstring excludes bash-token-position
  findings (needed for AC 2b) by design, so two independent scan paths are
  actually required, sharing `classify_site()`. Beyond that, the shape
  mismatch itself is unresolved: `scan_action()` requires a keyword-only
  `file: str` that `FSMLoop` has no field to supply, and `InterpSite.var` is
  a bare `namespace.key_path` with no suffix chain, while the current
  WARNING message interpolates the full raw token including suffixes. The
  finding says reconciling these "is required before 'same signature' ... is
  achievable" but does not itself propose the adapter — this is a concrete,
  unresolved implementation-shape question, not a citation staleness issue.
- Eight `⚠ Superseded` markers remain unresolved in the Integration Map and
  Implementation Steps (confirmed via `ll-issues format-check --format json`
  → `superseded_marker_count: 8`), including two consecutive steps both
  numbered "6" with cross-referencing annotations about which should run
  first — the issue itself calls out that `/ll:reconcile-issue` is needed to
  renumber them. An implementer would need to resolve this ordering before
  starting Step 5/6.
- The `# ll-lint: mr11-ok(<var>) <reason>` marker is genuinely new mechanism —
  codebase research found no existing precedent for a per-site inline
  suppression marker anywhere in the FSM validation family (every other
  suppression is a loop-level boolean flag). The design is well justified and
  modeled on the nearest analogous shape (enum-membership ERROR checks), but
  it is new parsing + a new ERROR path + a count ratchet, not a pure widening
  of existing logic.
- Step 6's triage of newly-surfaced findings across the loop corpus is
  explicitly open-ended by design (per § Impact: "open-ended by design"), and
  a later Codebase Research Finding confirms the blast radius is even wider
  than originally scoped — `validate_fsm()` also runs over inline FSM YAML
  fixtures in ~10 test files outside `scripts/little_loops/loops/**`
  (`test_builtin_loops.py`, `test_create_loop.py`, `test_fsm_executor.py`,
  etc.), for which no triage path is named. The number of sites requiring
  conversion vs. marking cannot be bounded until the widened rule actually
  runs.

### Outcome Risk Factors
- **Change surface is an unenumerated, per-site-judgment sweep, not a
  uniform mechanical substitution** — the Triage section requires deciding
  "convert it" vs. "mark it" per finding, so this does not qualify as
  Pattern B's enumerated mechanical fanout despite touching an enumerated
  set of doc files. The core surface (every loop in the corpus, plus the
  newly-identified ~10 test-fixture files) is open-ended by the issue's own
  admission — broad, unbounded enumeration across many sites, each requiring
  individual judgment.
- Ambiguity: the unresolved Program Design adapter-gap (see Concerns) is a
  concrete open engineering decision — what value to pass as `scan_action`'s
  `file` argument, and how to reconstruct a message-worthy token from
  `InterpSite`'s bare `namespace.key_path` — left to the implementer with no
  stated resolution.

## Session Log
- `/ll:reconcile-issue` - 2026-08-29T16:58:40 - `48e9d546-94fd-4111-9bec-ae917ba67439.jsonl`
- `/ll:confidence-check` - 2026-08-29T16:51:34 - `58d393ce-925a-4f28-b052-80c8ddfba7fe.jsonl`
- `/ll:verify-issues` - 2026-08-29T16:43:36 - `2b9cf0aa-17fa-4c56-a0c2-6a6f4f822dae.jsonl`
- `/ll:refine-issue` - 2026-08-29T16:34:32 - `2b9cf0aa-17fa-4c56-a0c2-6a6f4f822dae.jsonl`
- `/ll:confidence-check` - 2026-08-29T16:27:18 - `2b9cf0aa-17fa-4c56-a0c2-6a6f4f822dae.jsonl`
- `/ll:wire-issue` - 2026-08-29T16:12:58 - `d066a1db-8c85-4efb-8d7e-f8a88f18b677.jsonl`
- `/ll:refine-issue` - 2026-08-29T16:03:29 - `c54a423f-c560-4b02-ba94-5edb4f845eaa.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-28T02:22:57 - `bd65b096-20a2-4a7e-b430-c4b13ac5b81d.jsonl`
- `/ll:scope-epic` - 2026-08-27T17:51:45 - `c766dcf0-a664-4805-9c8a-6eba323145c8.jsonl`
