---
id: BUG-3230
type: BUG
title: 'll-loop validate -j: the load-error path ignores --json and writes the reason
  to stderr with an empty stdout, so a programmatic caller gets a rejection with no
  reason'
priority: P2
status: done
discovered_by: little-loops-hermes-audit
discovered_date: '2026-08-16'
completed_at: '2026-08-17T05:01:16Z'
labels:
- loops
- cli-json
testable: true
confidence_score: 100
outcome_confidence: 89
score_complexity: 23
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 22
---

# BUG-3230: ll-loop validate -j: the load-error path ignores --json and writes the reason to stderr with an empty stdout

## Summary

`cmd_validate` (`scripts/little_loops/cli/loop/config_cmds.py:12`) honours `--json` on exactly two of its four exits. The `as_json` branch (lines 29-45) emits `{"loop", "valid", "violations"}`, and the `FileNotFoundError` handler (lines 58-71) emits the same shape. But the `ValueError` handler (lines 73-75) ignores `as_json` entirely and calls `logger.error(...)`, and a YAML parse error is not caught at all — it escapes as an unhandled traceback.

Both of those paths exit non-zero with an **empty stdout** and the only account of the failure on stderr. A caller running `ll-loop validate -j <file>` and parsing stdout receives nothing, so it can report that validation failed but never why.

## Current Behavior

Probed live. A loop file missing a required field:

```console
$ printf 'name: probe\nstates:\n  a:\n    prompt: x\n' > bad.yaml
$ ll-loop validate -j bad.yaml; echo "exit=$?"
exit=1
--stdout--
(empty)
--stderr--
[20:03:24] bad.yaml is invalid: FSM file missing required fields: initial
```

Malformed YAML is worse — nothing catches it:

```console
$ printf 'this is: [not, valid\n  yaml at all\n' > malformed.yaml
$ ll-loop validate -j malformed.yaml; echo "exit=$?"
exit=1
--stdout--
(empty)
--stderr--
Traceback (most recent call last):
  ...
  File ".../fsm/validation/structural_rules.py", line 1598, in load_and_validate
    data: dict[str, Any] = yaml.safe_load(f)
  ...
yaml.parser.ParserError: while parsing a flow sequence
  in "malformed.yaml", line 1, column 10
expected ',' or ']', but got '<stream end>'
```

A file that *loads* behaves correctly and is the contrast case — the channel exists and is well-populated:

```console
$ ll-loop validate -j violations.yaml; echo "exit=$?"
exit=1
{
  "loop": "violations.yaml",
  "valid": false,
  "violations": [
    {"severity": "error", "path": "states", "message": "No terminal state defined. ..."},
    {"severity": "error", "path": "states.a", "message": "State has no transition defined. ..."}
  ]
}
```

So `violations` is reachable only once the file has parsed and its required fields are present — precisely the cases where the caller least needs help. The two failures a generated or hand-edited draft is most likely to hit are the two that report nothing.

## Expected Behavior

Two requirements, one of which is not `--json`-specific.

**1. The unhandled traceback must go away on both paths.** A `yaml.YAMLError`
escaping to the top level is a defect for the *human* caller too — plain
`ll-loop validate malformed.yaml` (no `-j`) tracebacks identically, because
nothing catches it anywhere in `cmd_validate`. The fix must produce a clean
`logger.error(...)` line there, not only a JSON document under `-j`.

**2. `--json` should produce a parseable JSON document on stdout on every exit
path**, as the `as_json` and `FileNotFoundError` branches already do. A load
failure should be reported as a violation, e.g.:

```json
{
  "loop": "bad.yaml",
  "valid": false,
  "violations": [
    {"severity": "error", "path": "<root>", "message": "FSM file missing required fields: initial"}
  ]
}
```

A YAML parse error should be caught rather than escaping as a traceback, and reported in the same shape.

## Steps to Reproduce

1. `printf 'name: probe\nstates:\n  a:\n    prompt: x\n' > bad.yaml`
2. `ll-loop validate -j bad.yaml` — exit 1, empty stdout, reason on stderr only.
3. `printf 'this is: [not, valid\n  yaml at all\n' > malformed.yaml`
4. `ll-loop validate -j malformed.yaml` — exit 1, empty stdout, unhandled `yaml.parser.ParserError` traceback on stderr.
5. Contrast with a file that loads but has violations — stdout carries the full `violations` array, stderr is empty.

## Proposed Solution

In `cmd_validate`, make the `except ValueError` handler (line 73) mirror the `except FileNotFoundError` handler directly above it (lines 58-71), which already branches on `as_json` and emits the standard shape with a single `<root>` violation. Add `yaml.YAMLError` to the caught exceptions so a parse error takes the same path instead of escaping.

The fix is small and local; the two correct handlers in the same function are the template.

### One handler repair covers both branches

Worth stating explicitly, because the Summary can read as though the `as_json`
branch is independently safe: it is not, and that is convenient. The `as_json`
branch calls `load_and_validate(path, raise_on_error=False, ...)` **inside the
same `try`** (line 32). `raise_on_error=False` suppresses *violation*-driven
raising, not load failures — a missing required field or a `yaml.safe_load`
parse error still propagates out of that call. So both the `as_json` and the
human branch funnel their load failures into the same two `except` clauses at
the bottom of the function. Repairing those clauses fixes every path at once;
no separate handling is needed inside the `as_json` branch.

### Implementation trap: handler ordering is load-bearing if `OSError` is added

`yaml.YAMLError` is the correct parent to catch — `ParserError` and
`ScannerError` both derive from it.

Recommend also catching `OSError`, since an existing-but-unreadable file
(permissions) or non-UTF-8 content tracebacks today for the same reason
`YAMLError` does. **If you add it, `except FileNotFoundError` must stay above
it**: `FileNotFoundError` is an `OSError` subclass, so an `except OSError`
placed first would swallow the missing-file case and change its message. The
existing ordering happens to be correct; adding `OSError` makes that ordering
something the code depends on rather than something incidental. Add a comment
saying so.

#### The larger `OSError` trap: the `try` wraps the whole success path

Ordering is the *small* hazard. The bigger one is scope: the `try` opens at
`config_cmds.py:25` and does not close until after every success-path emission —
`print_json` in the `as_json` branch (`:35`) and the six `print()` calls in the
human branch (`:49-56`) are all inside it. `BrokenPipeError` is an `OSError`
subclass, so `ll-loop validate -j big.yaml | head` would print the document,
break the pipe, and then fall into the new handler and emit a **second** JSON
document asserting the loop is invalid — with the pipe error as the violation
message. A `SIGPIPE` in a shell pipeline is a normal, common event, not a
validation outcome.

Two acceptable fixes; pick one and say which:

- **(a)** Narrow the `try` so it wraps only `resolve_loop_path()` and the two
  `load_and_validate()` calls, leaving the emissions outside it. Structurally
  correct — the handlers are about *loading*, and should never see an output
  error. Recommended.
- **(b)** Keep the wide `try` and re-raise the pipe case first:
  `except BrokenPipeError: raise` immediately above the widened clause.
  Cheaper, but leaves a second ordering dependency in a handler stack that now
  has two.

This does not apply to `ValueError` or `yaml.YAMLError`, which the success-path
emissions cannot raise — it is `OSError` specifically that makes the `try`'s
width load-bearing.

### Scope

Deliberately confined to `cmd_validate`. Other `ll-loop` subcommands may share
the "consults `--json` on some exits but not all" pattern, but auditing them is
a separate sweep and should not gate this fix.

## Impact

- **Priority**: P2 — `-j` exists for programmatic callers, and on the two most common authoring failures it returns nothing parseable. A caller that generates a loop draft and validates it gets a rejection it cannot act on or explain. The unhandled traceback is also a rough edge for a supported flag combination.
- **Effort**: Small — one handler brought in line with its neighbour, plus catching `yaml.YAMLError`.
- **Risk**: Low — adds output to paths that currently emit nothing on stdout; the exit code is unchanged. Human-readable (non-`-j`) output is untouched.
- **Breaking Change**: No — a caller parsing stdout today gets an empty string on these paths, which cannot already be relied upon.

## Root Cause

`as_json` is consulted at three of the function's four exits but not the fourth. The `ValueError` handler predates or was simply missed by the `--json` work: `logger.error(f"{loop_name} is invalid: {e}")` at line 74 is unconditional. `yaml.YAMLError` was never in the caught set at all, so `load_and_validate`'s `yaml.safe_load` (`fsm/validation/structural_rules.py:1598`) can raise straight through `cmd_validate` to the top level.

The two are different classes of oversight and only the first is `--json`-specific: the `ValueError` gap is an incomplete flag rollout, while the missing `yaml.YAMLError` catch is an unhandled-exception bug that predates `--json` entirely and affects the human path identically.

## Integration Map

| Site | Role |
| --- | --- |
| `scripts/little_loops/cli/loop/config_cmds.py:12` `cmd_validate` | The defect; all four exit paths. |
| `config_cmds.py:29-45` | `as_json` success/violations branch — correct; the shape template. |
| `config_cmds.py:58-71` | `FileNotFoundError` handler — correct; the handler template. Must remain above any `OSError` clause. |
| `config_cmds.py:73-75` | `ValueError` handler — ignores `as_json`. |
| `scripts/little_loops/fsm/validation/structural_rules.py:1598` `load_and_validate` | Raises the `yaml.safe_load` error that currently escapes. |
| `scripts/little_loops/cli/output.py:227` `print_json` | Emitter used by both correct branches. |

## Program Design

### Signatures
- `cmd_validate(loop_name: str, args: argparse.Namespace, loops_dir: Path, logger: Logger) -> int` — signature unchanged; only its exception-handling tail changes, so no caller is affected; see `scripts/little_loops/cli/loop/config_cmds.py:12`.
- `load_and_validate(path, raise_on_error: bool = True, orchestration_request_path=...) -> tuple[FSM, list[Violation] | list[str]]` — unchanged; note that `raise_on_error=False` suppresses *violation*-driven raising only, so load failures still propagate to the caller's handlers; see `scripts/little_loops/fsm/validation/structural_rules.py:1598`.
- `print_json(data: Any) -> None` — unchanged emitter, `json.dumps(data, indent=2)` to stdout; see `scripts/little_loops/cli/output.py:227`.

### Types
No new types. The failure payload reuses the shape the two correct branches already emit: `{"loop": str, "valid": bool, "violations": list[{"severity": str, "path": str, "message": str}]}`. A load failure is expressed as exactly one violation with `severity: "error"` and `path: "<root>"` — the sentinel the `FileNotFoundError` handler already uses for file-level (as opposed to node-level) problems, so no consumer needs to learn a new discriminator.

### Call Path
`ll-loop validate -j bad.yaml` → `cmd_validate` → `resolve_loop_path()` → `as_json` is truthy so the branch at `:29` runs → `load_and_validate(path, raise_on_error=False, ...)` at `:32` → `yaml.safe_load` (`structural_rules.py:1598`) raises `ParserError`, or the required-field check raises `ValueError` → the exception unwinds out of the `as_json` branch (it is *inside* the same `try`) → `except FileNotFoundError` does not match → `except ValueError` matches only for the required-field case and calls `logger.error` unconditionally, ignoring `as_json`; for `ParserError` nothing matches and the exception escapes `cmd_validate` entirely. Either way stdout is empty and the process exits non-zero. After the fix both land in the widened handler, which branches on `as_json` and emits the standard shape before returning 1.

### Decision Rules
One rule, applied at a single point: on any load failure, emit the standard violation document when `as_json` is set and a `logger.error` line otherwise — never both, never neither. Exit code stays `1` for every failure path regardless of rendering, so no caller's success/failure test changes. Handler *ordering* encodes a second rule that becomes load-bearing once `OSError` is caught: `FileNotFoundError` is an `OSError` subclass, so its clause must precede the widened one or the missing-file message is silently absorbed.

## Implementation Steps

1. Add `import yaml` to `config_cmds.py` (not currently imported).
2. Narrow the `try` (opened at `:25`) so it covers `resolve_loop_path()` and the
   two `load_and_validate()` calls only, leaving `print_json` and the human
   `print()` block outside it — option (a) above. If keeping the wide `try`
   instead, add `except BrokenPipeError: raise` above the widened clause.
3. Widen the final handler to `except (ValueError, yaml.YAMLError, OSError) as e`,
   placed **below** the existing `except FileNotFoundError`, with a comment
   noting the ordering dependency.
4. Give that handler the same `if as_json:` / `else:` shape as the
   `FileNotFoundError` handler: `print_json({"loop", "valid": False,
   "violations": [{"severity": "error", "path": "<root>", "message": str(e)}]})`
   or `logger.error(...)`.
5. Keep the `return 1` exit code unchanged on all failure paths.

## Acceptance Criteria

- [ ] `ll-loop validate -j` on a file missing a required field
      (`initial`) exits 1 and writes a JSON document to **stdout** carrying the
      reason in `violations[0].message`.
- [ ] `ll-loop validate -j` on malformed YAML exits 1, writes the same shape to
      stdout, and produces **no traceback**.
- [ ] `ll-loop validate` (no `-j`) on malformed YAML exits 1 with a clean
      `logger.error` line and **no traceback**.
- [ ] `ll-loop validate -j` on a **missing** file still reports the
      file-not-found message (regression guard for the `OSError` ordering trap).
- [ ] Every `-j` exit path — valid, violations, missing file, load error, parse
      error — produces stdout that `json.loads` accepts. Assert this as a loop
      over the five cases rather than five independent assertions, so a future
      sixth exit path is caught by the same test.
- [ ] Human-readable (non-`-j`) output for the *valid* and *violations* cases is
      unchanged.
- [ ] A `BrokenPipeError` raised by the success-path emission does **not** produce
      a second, contradictory failure document. Assert on a **valid** loop with
      stdout patched to raise `BrokenPipeError` on write: exactly one emission is
      attempted and the widened handler does not claim the loop is invalid.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Found while auditing `little-loops-hermes`, whose `ll_create_loop` tool shells out to `ll-loop validate -j` to gate a generated draft before writing it. Hermes has worked around the symptom by carrying stderr back to the caller when stdout is empty, but the fix belongs here: any consumer of `-j` has the same blind spot.

## Status

**Open** | Created: 2026-08-16 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-17T05:00:53 - `66a7a1fa-2c81-4a0b-ab18-8cc637065ccf.jsonl`
- `/ll:ready-issue` - 2026-08-17T04:53:55 - `9e5dd851-5232-45a7-9885-384e8b5eb139.jsonl`
- `/ll:confidence-check` - 2026-08-17T04:01:20 - `03558def-29ef-40d7-87ba-66fe5fe13be8.jsonl`
