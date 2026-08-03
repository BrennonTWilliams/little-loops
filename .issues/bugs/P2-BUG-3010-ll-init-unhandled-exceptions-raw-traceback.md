---
id: BUG-3010
title: ll-init has no top-level exception handling; errors surface as raw tracebacks
type: BUG
status: open
priority: P2
discovered_date: 2026-08-02
discovered_by: multi-agent-audit
parent: EPIC-3008
testable: true
labels:
- ll-init
- ux
- error-handling
milestone: epic-3008
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3010: `ll-init` has no top-level exception handling; errors surface as raw tracebacks

## Summary

`main_init` (`scripts/little_loops/init/cli.py:722`) documents a clean 0/1/2
exit-code contract in its own `--help` epilog (`cli.py:751-754`), but there is
no top-level `try/except` around the command body. `cli_event_context`
(`scripts/little_loops/session_store/writers.py:473-503`) explicitly lets
errors raised by the wrapped body propagate — so any unexpected failure
surfaces as a raw Python traceback instead of the documented clean error path.

## Current Behavior

- `main_init` wraps its body in `cli_event_context(...)` (`cli.py:728`) purely
  for analytics/session tracking; that wrapper does not catch or reformat
  exceptions.
- Concrete repro: `detect_project_type_all` (`init/detect.py:144-169`) raises a
  bare `FileNotFoundError` when the bundled templates dir is missing or
  corrupted (e.g. a broken/partial install). Nothing in `cli.py` catches this —
  it propagates as an unformatted traceback to the terminal, even though the
  `--help` epilog documents "template missing" as covered by exit code `1`
  (`cli.py:753`).
- Other plausible failure modes with the same gap: permission errors writing
  `.ll/`, disk-full during `write_config`/`writers.py` calls, corrupted
  `.ll/ll-config.json` JSON on the headless merge path.

## Steps to Reproduce

1. Corrupt or remove the bundled templates directory so
   `detect_project_type_all` (`init/detect.py:144-169`) raises
   `FileNotFoundError` (e.g. simulate a broken/partial install).
2. Run `ll-init --yes` in a scratch project directory.
3. Observe a raw Python traceback printed to the terminal instead of a clean
   `Error: ...` message with exit code `1`, despite `main_init`'s own
   `--help` epilog documenting "template missing" as a clean exit-code-1 case.

## Expected Behavior

Predictable failures (missing templates, permission errors, disk errors,
corrupted existing config) should print a short `Error: <message>` to stderr
and exit with the documented code, not a Python traceback.

## Suggested Fix Direction

Wrap the dispatch logic in `main_init` (`cli.py:856-926`, i.e. from
`project_root = ...` through the final `return run_tui(...)`) in a `try/except`
that prints a one-line `Error: ...` to stderr and returns exit code `1` —
matching the pattern already used for the `apply --config` JSON-parse error
(`cli.py:665-669`) and the `--enable`/`--disable` validation error
(`cli.py:885-896`).

### Decision: what to catch (resolved — not an implementer open question)

Catch exactly **`(OSError, json.JSONDecodeError)`**. Everything else propagates
as a traceback.

- `FileNotFoundError` and `PermissionError` are both `OSError` subclasses —
  listing them separately (as an earlier draft of this issue did) is redundant.
  `OSError` alone covers the missing-templates, permission-denied, and disk-full
  cases in Current Behavior.
- `json.JSONDecodeError` covers a corrupted `.ll/ll-config.json` on the headless
  merge path. (It subclasses `ValueError`, not `OSError`, so it must be listed.)
- Genuinely unexpected exceptions (`AttributeError`, `KeyError`, `TypeError` —
  i.e. programming bugs) **deliberately keep their traceback**, because a
  traceback is the useful artifact in a bug report. Do **not** add an
  `except Exception` catch-all.
- `SystemExit` (raised by `argparse` on a usage error) is not caught by either
  clause and must continue to exit `2`. Assert this — a broadened catch here
  would silently reclassify every usage error as exit `1`.

## Program Design

### Signatures

- `main_init(argv: list[str] | None = None) -> int` — existing, `scripts/little_loops/init/cli.py:722`

### Call Path

`main_init` -> inside the existing `cli_event_context(...)` block
(`cli.py:728`, which by design does not catch or reformat exceptions) -> wraps
its dispatch block (`cli.py:856-926`) in
`try: ... except (OSError, json.JSONDecodeError) as exc:
print(f"Error: {exc}", file=sys.stderr); return 1` -> matches the pattern
already used for `apply --config` JSON errors (`cli.py:665-669`).

Note the wrapped range must start at or before
`templates_dir = get_bundled_templates_dir()` (`cli.py:860`) so a broken/partial
install is caught, and must extend past the `apply` subcommand dispatch
(`cli.py:875`) and the `run_tui` tail call (`cli.py:920-926`).

## Acceptance Criteria

- [ ] A simulated missing/corrupt bundled templates dir makes `ll-init --yes`
      print a single `Error: ...` line to stderr and exit `1` — no traceback.
- [ ] A corrupted `.ll/ll-config.json` on the headless merge path exits `1` with
      one `Error:` line.
- [ ] A read-only `.ll/` (PermissionError) exits `1` with one `Error:` line.
- [ ] An unknown `--enable` value still exits `2` (argparse/validation path
      unchanged by the new wrapper).
- [ ] A deliberately injected `AttributeError` still raises with a full
      traceback (asserts no catch-all was added).
- [ ] The `apply` subcommand and the `run_tui` tail call are both inside the
      wrapped range.
- [ ] New tests live in `scripts/tests/test_init_core.py` (`TestMainInit`);
      `python -m pytest scripts/tests/` exits 0.

## Status

**Open** | Created: 2026-08-02 | Priority: P2

## Impact

- **Priority**: P2 — user-facing crash instead of documented clean failure;
  contradicts the tool's own `--help` text.
- **Effort**: Small — one wrapping `try/except` plus a couple of new tests in
  `scripts/tests/test_init_core.py` (`TestMainInit`).
- **Risk**: Low.
- **Breaking Change**: No.


## Session Log
- `/ll:confidence-check` - 2026-08-03T14:56:07 - `8315e9f9-979b-46c8-8d38-ae829695a554.jsonl`
