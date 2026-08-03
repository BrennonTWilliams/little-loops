---
id: BUG-3025
title: Logo banner tests assert a wordmark the redesign removed - one fails, two pass vacuously
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
2. **Add a regression guard** so the vacuous-assertion failure mode cannot recur:
   a test asserting the chosen marker is non-empty and present in
   `get_logo("full")`. Without this, fix option 1 is still silently breakable if
   the asset is ever emptied.

Whichever marker is chosen, apply it to **all three** assertions (359, 371, 385)
— fixing only the red one leaves the two vacuous negatives in place, which is
the larger half of this bug.

## Integration Map

### Files to Modify
- `scripts/tests/integration/test_init_e2e.py` — class `TestInitLogoBanner`,
  assertions at lines 359, 371, 385.

### Dependent Files (Callers/Importers)
- None. Test-only change; no production behavior is at fault. The logo asset and
  `logo.py` are correct as-is — the redesign was intentional
  (`d8b3a17d`), only the tests lagged.

### Tests
- `scripts/tests/test_logo.py` — existing logo unit tests; checked and contains
  **no** `"little loops"` substring assertions, so it is unaffected. Worth
  confirming whether the marker guard from fix option 2 belongs here rather than
  in the integration file.

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
- [ ] The two negative assertions fail if the banner is made unconditional —
      verify by temporarily removing the `isatty()` guard, per Steps to
      Reproduce step 3. This is the criterion that distinguishes a real fix from
      re-silencing.
- [ ] The chosen marker is derived from or pinned against `get_logo("full")`, so
      a future art redesign cannot silently invalidate the assertions.
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
