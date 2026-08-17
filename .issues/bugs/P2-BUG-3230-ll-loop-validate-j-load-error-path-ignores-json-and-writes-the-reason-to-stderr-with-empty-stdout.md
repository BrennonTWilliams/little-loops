---
id: BUG-3230
type: BUG
title: 'll-loop validate -j: the load-error path ignores --json and writes the reason
  to stderr with an empty stdout, so a programmatic caller gets a rejection with no
  reason'
priority: P2
status: open
discovered_by: little-loops-hermes-audit
discovered_date: '2026-08-16'
labels:
- loops
- cli-json
testable: true
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

`--json` should produce a parseable JSON document on stdout on **every** exit path, as the `as_json` and `FileNotFoundError` branches already do. A load failure should be reported as a violation, e.g.:

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

## Impact

- **Priority**: P2 — `-j` exists for programmatic callers, and on the two most common authoring failures it returns nothing parseable. A caller that generates a loop draft and validates it gets a rejection it cannot act on or explain. The unhandled traceback is also a rough edge for a supported flag combination.
- **Effort**: Small — one handler brought in line with its neighbour, plus catching `yaml.YAMLError`.
- **Risk**: Low — adds output to paths that currently emit nothing on stdout; the exit code is unchanged. Human-readable (non-`-j`) output is untouched.
- **Breaking Change**: No — a caller parsing stdout today gets an empty string on these paths, which cannot already be relied upon.

## Root Cause

`as_json` is consulted at three of the function's four exits but not the fourth. The `ValueError` handler predates or was simply missed by the `--json` work: `logger.error(f"{loop_name} is invalid: {e}")` at line 74 is unconditional. `yaml.YAMLError` was never in the caught set at all, so `load_and_validate`'s `yaml.safe_load` (`fsm/validation/structural_rules.py:1598`) can raise straight through `cmd_validate` to the top level.

## Notes

Found while auditing `little-loops-hermes`, whose `ll_create_loop` tool shells out to `ll-loop validate -j` to gate a generated draft before writing it. Hermes has worked around the symptom by carrying stderr back to the caller when stdout is empty, but the fix belongs here: any consumer of `-j` has the same blind spot.

## Status

**Open** | Created: 2026-08-16 | Priority: P2
