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
blocked_by: [ENH-3337, ENH-3338, BUG-3339, BUG-3340, BUG-3341, ENH-3347]
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
  - `:33-35` — `_UNSAFE_CONTEXT_INTERP_RE`: drop the key allowlist, add the
    `captured` and `prev` namespaces, or replace the regex entirely with a call
    into ENH-3338's scanner
  - `:183` — `token.endswith(":shell}")`: this must become position-aware, not
    merely suffix-chain-aware. ENH-3337 fixes *where* the suffix is recognized;
    this issue fixes *whether recognizing it clears the site* (it does not,
    inside a Python body)
  - `:41` — `_QUOTED_HEREDOC_START_RE` and the terminator check at `:173`:
    column-0 semantics
  - `:148-188` — `_find_unsafe_context_interpolations`: the Python-literal
    position distinction and the `-c "` host shape
  - `:191-227` — the validator's message text (see below), plus the marker's
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

### Dependent Files (Callers/Importers)

- `scripts/little_loops/fsm/validation/__init__.py` — rule registration; no
  change expected unless the rule is split.
- Every loop in `scripts/little_loops/loops/**` is subject to the widened rule.

### Tests

- `scripts/tests/test_fsm_validation_shell_safety.py` — the MR-11 unit suite.
  Existing fixtures to preserve: `test_mr11_does_not_fire_inside_quoted_heredoc`
  (`:267-273`, marker-agnostic — uses `LL_EOF`) and the `:shell` non-firing case
  (`:276`). **`test_mr11_does_not_fire_inside_quoted_heredoc` asserts the exact
  behavior item 3 above says is wrong** — it must be revised, not merely kept
  green. Record the revision explicitly; a silently rewritten assertion is how
  this rule got narrow in the first place.
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

### Configuration

- N/A — `unsafe_context_interpolation_ok` already exists and is not extended.
  The marker is deliberately **not** config: it lives in the loop YAML beside the
  site it exempts, where a reviewer reading that action sees it. A config-file
  allowlist would put the exemption somewhere nobody reading the code will look.

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

## Implementation Steps

1. Replace MR-11's regex-based detection with a call into ENH-3338's scanner,
   keeping MR-11's per-state / `action_type` / suppression-flag scaffolding.
2. Add the Python-literal-position distinction and the `-c "` host shape.
3. Tighten the heredoc terminator to column 0.
4. Revise `test_mr11_does_not_fire_inside_quoted_heredoc` to assert the corrected
   semantics, and record why the old assertion was wrong.
5. Implement the `# ll-lint: mr11-ok(<var>) <reason>` marker: grammar, per-
   variable matching, both placements, the `${`-rejection guard, the
   malformed-marker ERROR, and the checked-in marker-count ratchet. Do this
   **before** step 6 — triaging without the mechanism is what forced the earlier
   draft's contradiction.
6. Run `ll-loop validate` across the corpus; triage every newly surfaced finding
   — convert it, or mark it with a reason citing a tracking issue. Do not set
   `unsafe_context_interpolation_ok`, do not re-narrow the pattern, and do not
   baseline (MR-11 does not read ENH-3338's baseline).
6. Update the validator's message to name both remedies concretely — the
   `LL_ARG_X=${context.x:shell}` + `os.environ` idiom and the
   `LL_RAW_9F3C1A7E_EOF` heredoc-to-file idiom — and link the guide section.
7. Document both idioms in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` with the
   canonical copy-pasteable blocks, including the column-0 hoisting rule and the
   `<state>-<capture>.txt` naming rule.
8. Record the WARNING-vs-ERROR severity decision.

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

## Session Log
- `/ll:scope-epic` - 2026-08-27T17:51:45 - `c766dcf0-a664-4805-9c8a-6eba323145c8.jsonl`
