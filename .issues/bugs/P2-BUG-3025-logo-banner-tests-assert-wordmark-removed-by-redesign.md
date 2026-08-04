---
id: BUG-3025
title: Logo banner tests assert a wordmark the redesign removed - one fails, two pass
  vacuously
type: BUG
status: open
priority: P2
discovered_date: 2026-08-03
discovered_by: user-report
testable: true
labels:
- tests
- logo
- init
- vacuous-assertion
confidence_score: 100
outcome_confidence: 92
score_complexity: 24
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 23
---

# BUG-3025: Logo banner tests assert a wordmark the redesign removed — one fails, two pass vacuously

## Summary

All three tests in `TestInitLogoBanner`
(`scripts/tests/integration/test_init_e2e.py`) assert on the literal substring
`"little loops"` in `ll-init` stdout. Commit `d8b3a17d`
("improve(assets): redesign ll-cli logo") removed the only line of the **full**
logo variant that contained that literal, without updating the tests.

The visible symptom is one red test. The more serious defect is silent: the two
**negative** assertions in the same class now pass unconditionally, so the
invariant they exist to protect — *the banner must never pollute
machine-readable output* — is no longer tested at all.

## Current Behavior

`scripts/little_loops/init/cli.py:310` and `init/tui.py:150` both call
`print_logo()` with no argument. `logo.py:11,20` defaults `variant="full"`,
which loads `scripts/little_loops/assets/ll-cli-logo.txt`.

Before `d8b3a17d`, that file ended with a two-line wordmark block:

```
                l i t t l e   l o o p s
            big things run in little loops
```

The tagline `big things run in little loops` is what every assertion was
actually matching. The redesign deleted the tagline and kept only the
letter-spaced wordmark:

```
            l i t t l e   l o o p s
          ɢʀᴏᴡ ꜱᴏᴍᴇᴛʜɪɴɢ ʙᴇᴀᴜᴛɪꜰᴜʟ
```

`l i t t l e   l o o p s` does not contain the substring `little loops`.
Confirmed empirically:

```
$ python -c "from little_loops.logo import get_logo; \
    print('full:', 'little loops' in (get_logo('full') or '')); \
    print('small:', 'little loops' in (get_logo('small') or ''))"
full: False
small: True
```

The **small** variant (`ll-cli-logo-small.txt`) still contains the literal — but
no `ll-init` code path requests it, so it is irrelevant to these three tests.

Resulting state of the class:

| Line | Assertion | Status | Why |
|------|-----------|--------|-----|
| 359 | `"little loops" in out` | **FAILS** | substring no longer emitted |
| 371 | `"little loops" not in out` | passes **vacuously** | substring can never appear |
| 385 | `"little loops" not in stdout` | passes **vacuously** | substring can never appear |

Line 385 is the `--plan` case — the assertion guarding the documented promise at
`init/cli.py:306-308` that "the machine-readable `--plan`/apply paths [...] never
call this, so their JSON output stays clean." A regression that leaked the banner
into `--plan` JSON would now ship green.

## Steps to Reproduce

1. `python -m pytest "scripts/tests/integration/test_init_e2e.py::TestInitLogoBanner" -q`
2. `test_yes_run_prints_logo_banner_on_tty` fails with
   `AssertionError: logo banner missing from --yes stdout on a TTY`.
3. To see the vacuous pair: make `print_logo()` unconditional (drop the
   `sys.stdout.isatty()` guard at `init/cli.py:309`) and re-run — the two
   negative tests still pass despite the banner now leaking.

## Expected Behavior

- The positive test passes against the current logo asset.
- The two negative tests **fail** when the banner leaks into non-TTY or `--plan`
  output — i.e. they assert on something the banner actually emits.
- The assertions do not silently decay the next time the logo art is redesigned.

## Root Cause

The tests couple to *decorative asset content* rather than to a stable marker.
Any wordmark restyling — letter-spacing, a tagline edit, a font swap — silently
invalidates them, and because two of the three are negative assertions, the
decay is invisible.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

- **Confirmed via codebase-analyzer**: `get_logo(variant="full")` (`scripts/little_loops/logo.py:11`) returns `Path(__file__).parent / "assets" / "ll-cli-logo.txt"` read verbatim via `read_text()` (no exception handling beyond an `exists()` guard). `print_logo()` (`logo.py:27`) uses `if logo := get_logo(variant):` — a falsy (`None` or empty-string) result is a **silent no-op** (documented in its own docstring), which matters for the regression-guard test proposed in Suggested Fix Direction: an accidentally-emptied asset would make `print_logo()` silently stop printing rather than error, and a marker derived from `get_logo("full")` in that case would be an empty string that trivially "matches" nothing — worth asserting non-empty explicitly, as already proposed.
- The asset's actual line structure (`scripts/little_loops/assets/ll-cli-logo.txt`): line 1 is empty, lines 2-18 are box-drawing/ornament glyphs (`˚`, `∘`, `╭`, `╮`, `╫`, `●`, `╌`, etc.) with no plain-text words, line 20 is the letter-spaced wordmark `l i t t l e   l o o p s`, line 21 is the small-caps tagline replacement `ɢʀᴏᴡ ꜱᴏᴍᴇᴛʜɪɴɢ ʙᴇᴀᴜᴛɪꜰᴜʟ`.
- Marker candidate check: `get_logo("full").strip().splitlines()[0]` resolves to the box-drawing ornament line (`˚   ∘   ˚`, from source line 2 after `.strip()` removes the leading empty line and indentation) — not the wordmark text. This line is part of the ornamental shape rather than the wordmark that has already changed once (tagline → letter-spaced wordmark) in `d8b3a17d`, so it is structurally more stable than asserting against wordmark prose, though still asset-content-derived rather than a hand-picked stable glyph.

## Suggested Fix Direction

Pick a banner marker that is stable under art redesign. Options, in preference
order:

1. **Assert on a structural constant of the banner** rather than its prose —
   e.g. a distinctive box-drawing glyph the art is built from (`╫`, `◑`), or the
   first line of `get_logo("full")` itself. Strongest option: assert against
   `get_logo("full")` directly, so the test tracks the asset by construction and
   cannot drift:
   ```python
   from little_loops.logo import get_logo
   marker = (get_logo("full") or "").strip().splitlines()[0]
   assert marker in out
   ```
2. **Add a regression guard** so the vacuous-assertion failure mode cannot recur.
   Note the vacuity is **directional**, which determines where the guard is
   needed: if the asset is ever emptied, `marker` becomes `""`, and
   - `assert marker in out` (line 359, positive) passes **vacuously** —
     `"" in out` is always `True`;
   - `assert marker not in out` (lines 371, 385, negative) **fails loudly** —
     `"" not in out` is always `False`.

   So the non-empty guard protects the *positive* assertion only. Put it at unit
   level in `scripts/tests/test_logo.py` (cheap, no `ll-init` run):
   ```python
   def test_full_logo_marker_is_non_empty() -> None:
       marker = (get_logo("full") or "").strip().splitlines()[0]
       assert marker, "logo asset empty — banner assertions would pass vacuously"
   ```
3. **Add a detector-sanity test** so "these assertions are live" stays true
   rather than being verified once by hand. Capture `print_logo()` directly and
   assert the marker *is* found — this proves the same marker the negative
   assertions use can actually detect a banner:
   ```python
   def test_logo_marker_detects_a_printed_banner(capsys) -> None:
       print_logo()
       assert _LOGO_MARKER in capsys.readouterr().out
   ```
   This belongs in the integration file next to the assertions it protects.

Whichever marker is chosen, define it **once** as a module-level constant in
`test_init_e2e.py` and apply it to **all three** assertions (359, 371, 385) —
fixing only the red one leaves the two vacuous negatives in place, which is the
larger half of this bug.

## Integration Map

### Files to Modify
- `scripts/tests/integration/test_init_e2e.py` — class `TestInitLogoBanner`,
  assertions at lines 359, 371, 385; plus a shared marker constant and the
  detector-sanity test.
- `scripts/tests/test_logo.py` — add the non-empty marker guard.

### Dependent Files (Callers/Importers)
- None. Test-only change; no production behavior is at fault. The logo asset and
  `logo.py` are correct as-is — the redesign was intentional
  (`d8b3a17d`), only the tests lagged.

### Tests
- `scripts/tests/test_logo.py` — existing logo unit tests; checked and contains
  **no** `"little loops"` substring assertions, so it is unaffected. **Decided:**
  the non-empty marker guard (fix option 2) goes here — it is a property of the
  asset, needs no `ll-init` run, and stays cheap. The detector-sanity test (fix
  option 3) goes in `test_init_e2e.py`, beside the assertions it protects.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

- `scripts/tests/test_ll_loop_execution.py:352` (`test_quiet_mode_suppresses_logo`) — a fourth `assert "little loops" not in captured.out`, outside this issue's stated scope of `test_init_e2e.py`. **It is _not_ the same defect, and the marker fix must not be applied to it.** `ll-loop` has no logo code path at all: `print_logo` is called only from `init/cli.py:310` and `init/tui.py:150`, and commit `88db2cd0` ("refactor(cli): remove logo printing from CLI commands") removed it from the loop CLI. The test guards a feature that no longer exists, so it passes unconditionally for a different reason — and would keep passing unconditionally under a marker-based rewrite, since nothing is printed with or without `--quiet`. Correct disposition is to **delete it** (or repoint it at whatever `--quiet` actually suppresses today), tracked as a separate follow-up, not folded into this fix.
- Two established stdout-capture idioms coexist in `test_init_e2e.py`, applied by destination: `capsys.readouterr()` for the two `TestInitLogoBanner` assertions at lines 359/371 (direct-print paths), and `io.StringIO()` + `contextlib.redirect_stdout` for the `--plan` case at line 385 (`TestInitHeadlessIntrospection` uses the same idiom at lines 271-284, 311-337), since `--plan` output must stay parseable as pure JSON via `json.loads(...)`. No shared helper wraps either idiom — both are used inline. A fix should preserve this existing dual convention rather than introducing a new capture helper.
- No file in `scripts/tests/` currently derives a stdout-assertion marker from `get_logo(...)` output (the technique this issue proposes is novel to this codebase, not an existing convention being followed). The closest existing pattern (`scripts/tests/test_logo.py:30`, `scripts/tests/test_wheel_smoke.py:88-100`) only checks non-None/non-empty on `get_logo()`, not a specific derived marker.

## Program Design

### Signatures

No production signature changes — test-only fix. Existing API used by the fix:

```python
# scripts/little_loops/logo.py:11 — unchanged
def get_logo(variant: str = "full") -> str | None: ...

# scripts/little_loops/logo.py:27 — unchanged
def print_logo(variant: str = "full") -> None: ...
```

### Call Path

`_run_init(["--yes", ...])` -> `init/cli.py:309` `sys.stdout.isatty()` guard
-> `init/cli.py:310` `print_logo()` (variant defaults to `"full"`)
-> `logo.py:20` resolves `assets/ll-cli-logo.txt`
-> stdout, captured by `capsys` in the test
-> assertion compares against a marker derived from `get_logo("full")` rather
   than a hardcoded prose substring.

The `--plan` path never enters this chain (`init/cli.py:306-308`), which is
precisely the invariant the line-385 assertion must be restored to enforce.

## Acceptance Criteria

- [ ] `test_yes_run_prints_logo_banner_on_tty` passes against the current asset.
- [ ] A **detector-sanity test** asserts the chosen marker is found in captured
      `print_logo()` output. This is the automated form of "the negative
      assertions can actually fail", and is the criterion that distinguishes a
      real fix from re-silencing. (One-time manual confirmation via Steps to
      Reproduce step 3 is fine as a sanity check, but must not be the only
      evidence — a manual check is exactly the decay mode this bug is about.)
- [ ] A unit-level guard in `scripts/tests/test_logo.py` asserts the marker is
      non-empty, covering the one direction where an emptied asset would make an
      assertion pass vacuously (the positive test).
- [ ] The chosen marker is derived from or pinned against `get_logo("full")`, so
      a future art redesign cannot silently invalidate the assertions, and is
      defined once as a single constant shared by all three assertions.
- [ ] `test_ll_loop_execution.py:352` is left untouched by this fix; its separate
      disposition is filed as a follow-up (see Integration Map).
- [ ] `python -m pytest scripts/tests/integration/test_init_e2e.py` exits 0.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Status

**Open** | Created: 2026-08-03 | Priority: P2

## Impact

- **Priority**: P2 — the red test is trivial, but two silently-dead assertions
  on a machine-readable-output invariant is a live regression-detection hole.
  `--plan` JSON purity is a contract other tooling parses; a leak would ship
  green.
- **Effort**: Small — one test class, three assertions, plus a marker guard.
- **Risk**: Low — test-only; no production code changes.
- **Breaking Change**: No.

## Notes

Surfaced while verifying BUG-3024 (`resolve_epic` / `all_known_ids`): the full
suite showed exactly one failure, which was confirmed pre-existing by re-running
it with that fix stashed. Filed separately because it shares no code with
BUG-3024.

Note that BUG-3009's Resolution section attributes four then-current failures to
"an uncommitted `ll-cli-logo.txt` change." That asset is now committed and clean
(`git status` on `scripts/little_loops/assets/` is empty); the residue is this
single test-side drift, not an uncommitted working-tree change.


## Session Log
- `/ll:confidence-check` - 2026-08-04T02:14:56 - `bf431c8e-9360-452f-ad2d-3353ebec0f47.jsonl`
- `/ll:confidence-check` - 2026-08-03T22:06:28 - `0625a809-cbc4-471f-aa6c-852d08e8ee2e.jsonl`
- `/ll:wire-issue` - 2026-08-03T22:04:24 - `0a2cd27e-890b-4a2c-8139-d2e883aa3480.jsonl`
- `/ll:refine-issue` - 2026-08-03T21:57:57 - `f61be32c-6886-4f60-a42c-ae9e57f0ca2c.jsonl`
