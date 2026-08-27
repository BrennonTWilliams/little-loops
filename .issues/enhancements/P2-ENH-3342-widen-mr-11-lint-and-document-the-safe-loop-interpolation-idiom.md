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
blocked_by: [ENH-3337, ENH-3338, BUG-3339, BUG-3340, BUG-3341]
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

## Current Behavior

`_find_unsafe_context_interpolations` / `_validate_unsafe_context_interpolation`
(`shell_safety.py:148-227`) is narrower than the class EPIC-3336 fixed, in four
specific ways:

1. **Fixed key allowlist.** `_UNSAFE_CONTEXT_INTERP_RE` (`:33-35`) matches only
   `input|goal|description|task|prompt|query|topic`. Every class-A key outside
   that set is invisible.
2. **No `captured` namespace.** The regex is `\$\{context\.…` with no alternation
   — **class B, the sharper class, is entirely outside MR-11's reach.** BUG-3341
   can convert all 67 sites and MR-11 will not notice if one is missed.
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
    `captured` namespace, or replace the regex entirely with a call into
    ENH-3338's scanner
  - `:41` — `_QUOTED_HEREDOC_START_RE` and the terminator check at `:173`:
    column-0 semantics
  - `:148-188` — `_find_unsafe_context_interpolations`: the Python-literal
    position distinction and the `-c "` host shape
  - `:191-227` — the validator's message text (see below)
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
- `scripts/tests/test_builtin_loops.py` — ENH-3338's baseline test stays green.
- `ll-loop validate` across the whole corpus must be clean **after** the widening.

### Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — required.
- `.claude/CLAUDE.md` §Loop Authoring references the guide's rule table; check
  whether the widened rule needs a line there.

### Configuration

- N/A — `unsafe_context_interpolation_ok` already exists and is not extended.

## Scope Boundaries

**In scope:** MR-11's matcher width, namespace coverage, Python-literal position
awareness, and column-0 terminator; the validator's message text; the guide's
idiom documentation; triage of findings the widening surfaces.

**Out of scope:** the suffix grammar (ENH-3337); the sweep and its baseline
(ENH-3338); converting the 145 epic sites (BUG-3339/3340/3341); raising MR-11 to
`ERROR` severity; other MR rules.

## Program Design

### Signatures

- `_find_unsafe_context_interpolations(fsm: FSMLoop) -> list[tuple[str, str]]`
  (`shell_safety.py:148`) — same signature; body delegates to
  `interp_sweep.scan_action()` / `classify_site()`.
- `_validate_unsafe_context_interpolation(fsm: FSMLoop) -> list[ValidationError]`
  (`shell_safety.py:191`) — same signature; message text updated.
- `classify_site(namespace: str, key: str) -> str` (ENH-3338,
  `scripts/little_loops/fsm/interp_sweep.py`) — **imported, not reimplemented.**

### Decision Rules

The rule MR-11 enforces after widening:

| Position of an untrusted interpolation | Verdict |
|---|---|
| bash token position, not single-quoted, no `:shell` | flag (unchanged) |
| inside a quoted heredoc that is **not** a Python body | clean (unchanged) |
| inside a quoted heredoc that **is** a Python body, in a string literal | **flag (new)** |
| inside a `python3 -c "…"` body | **flag (new)** |
| carries `:shell` anywhere in its suffix chain | clean |
| trusted key (`run_dir`, `promoted_artifact`, `_`-prefixed) or `${loop.*}` | clean |

Untrusted-ness comes from `classify_site()`: `captured.*` always, `context.*`
minus the enumerated trusted set. **Not** a fixed untrusted-key allowlist.

### Severity

Keep `WARNING`. Raising to `ERROR` would hard-fail `ll-loop validate` on
consuming projects' pre-existing loops at upgrade time, which is a migration this
epic did not scope. Reconsider in a follow-up once the idiom is documented and
has shipped for a release. Record this as a decision.

### Expected finding surface

The widening will surface **pre-existing findings in files EPIC-3336 does not
otherwise touch** — that is the point of dropping the allowlist, and it is why
this issue runs last. Two outcomes are acceptable per finding: convert it, or
add it to ENH-3338's baseline as class-C/accepted with a reason. **Neither
`unsafe_context_interpolation_ok` nor a re-narrowed regex is an acceptable
response.** Budget for this triage; it is not a rubber stamp.

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
5. Run `ll-loop validate` across the corpus; triage every newly surfaced finding
   (convert, or baseline with a reason). Do not suppress.
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
3. MR-11 distinguishes a quoted heredoc that is a Python body from one that is
   not, and flags only the former — with a unit test for each side.
4. MR-11 closes a heredoc only on a column-0 terminator; an indented
   marker-equal line does not end the tracked block, with a unit test.
5. MR-11 does not fire on any correctly converted site — verified by
   `ll-loop validate` running clean across the entire corpus after BUG-3339 /
   3340 / 3341 have landed, with **no** loop setting
   `unsafe_context_interpolation_ok`.
6. `classify_site()` is imported from `interp_sweep`, not duplicated in
   `shell_safety.py`.
7. `test_mr11_does_not_fire_inside_quoted_heredoc` is revised, and the reason the
   original assertion was wrong is recorded in the test or this issue.
8. Every finding surfaced by the widening is triaged — converted or baselined
   with a reason. None is suppressed via the flag or by re-narrowing the pattern.
9. `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` documents both idioms with
   copy-pasteable blocks, the column-0 hoist rule, and the `<state>-<capture>.txt`
   naming rule.
10. The WARNING-vs-ERROR severity decision is recorded with its rationale.
11. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 (raised from P3) — the only child that stops the class from
  returning, and the only one whose effect reaches loops in consuming projects.
- **Effort**: Medium — the lint change is contained, but step 5's triage of
  newly-surfaced pre-existing findings is open-ended by design.
- **Risk**: Low to runtime (validation only). The risk is process: an implementer
  under time pressure re-narrows the pattern or sets the suppression flag to make
  `ll-loop validate` green, which silently undoes the epic. AC 8 exists to make
  that visible.
- **Breaking Change**: No at `WARNING` severity — consuming projects see new
  warnings, not failures. It would be at `ERROR`, which is why the severity stays
  as-is.

## Status

**Open** | Created: 2026-08-27 | Priority: P2

## Session Log
- `/ll:scope-epic` - 2026-08-27T17:51:45 - `c766dcf0-a664-4805-9c8a-6eba323145c8.jsonl`
