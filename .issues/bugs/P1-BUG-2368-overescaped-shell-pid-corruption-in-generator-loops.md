---
id: BUG-2368
type: BUG
title: Over-escaped shell `$$` PID-corrupts run_dir in 3 generator loops
priority: P1
status: done
captured_at: '2026-06-28T06:26:46Z'
completed_at: '2026-06-28T06:26:46Z'
discovered_date: 2026-06-28
discovered_by: audit-loop-run
labels:
- fsm
- harness
- loops
- shell-escaping
- interactive-component-generator
- html-website-generator
- svg-image-generator
relates_to:
- ENH-2366
- ENH-2367
- ENH-2365
decision_needed: false
confidence_score: 100
---

# BUG-2368: Over-escaped shell `$$` PID-corrupts run_dir in 3 generator loops

## Summary

Three generator-family loops over-escaped bash in their `action_type: shell` states,
writing `$$(` and `$$VAR` where single `$` was required. The FSM interpolation engine
only rewrites the brace form `$${...}` → `${...}`; bare `$(...)` and `$VAR` are passed
to `bash -c` untouched. The doubled `$$` is therefore **not an escape** — bash expands
the leading `$$` to the **process ID**, so `init`'s `echo "$$(pwd)/$$DIR"` captured
`<pid>(pwd)/<pid>DIR` instead of an absolute path, silently corrupting every downstream
`${captured.run_dir.output}` reference.

This was surfaced by an `audit-loop-run` audit of `interactive-component-generator`
run `2026-06-28T054140`, which observed the corrupted capture `66563(pwd)/66563DIR`
but **misdiagnosed** it as an "interpolation sentinel" caused by *under*-escaping, and
recommended *adding* escaping. Empirical testing inverted that conclusion (see below).

## Root cause (verified empirically)

Confirmed end-to-end against `DefaultActionRunner` + `interpolate()`:

- `interpolate()` (`scripts/little_loops/fsm/interpolation.py:27-28, 202-270`) only
  matches `${...}` (`VARIABLE_PATTERN`) and `$${` (`ESCAPED_PATTERN`). It emits **no
  numeric sentinel** and leaves bare `$(...)`/`$VAR` untouched.
- The runner does `cmd = ["bash", "-c", action]` (`scripts/little_loops/fsm/runners.py:166`),
  reached via `_run_action` → `interpolate` then dispatch
  (`scripts/little_loops/fsm/executor.py:1244`), with **no `$$`→`$` unescape** anywhere.
- Therefore:

  ```
  $$(pwd)/$$DIR  ->  20391(pwd)/20391DIR   # 20391 = PID  (audit saw 66563, also a PID)
  $(pwd)/$DIR    ->  /abs/correct/path      # the correct form
  ```

`66563` in the audit was a PID, not a sentinel; the defect was over-escaping, not
under-escaping.

## Fix (this session)

### 1. Corrected the over-escape in all 3 loops

`$$(` → `$(`, `$$VAR` → `$VAR` in shell actions; the legitimate `$${VAR}` /
`$${VAR:-default}` brace escapes (which DO collide with `${ns.path}`) were preserved.

- `scripts/little_loops/loops/interactive-component-generator.yaml` — 46 occurrences
- `scripts/little_loops/loops/html-website-generator.yaml` — 5 (run_dir abs-path setup)
- `scripts/little_loops/loops/svg-image-generator.yaml` — 5 (run_dir abs-path setup)

Verified with the real `DefaultActionRunner`: the fixed `init` now captures
`/…/scripts/.loops/runs/<id>` — absolute, no PID prefix.

### 2. Shift-left gate: new `ll-loop validate` rule MR-9

- `scripts/little_loops/fsm/validation.py` — `_OVERESCAPED_SHELL_RE`
  (`\$\$(?=\(|[A-Za-z_])`) + `_validate_overescaped_shell()` (ERROR), wired into
  `validate_fsm`. Scans shell actions only; exempts the legit `$${` brace escape and a
  standalone PID `$$`.
- `scripts/little_loops/fsm/schema.py` — `shell_pid_ok` suppression flag on `FSMLoop`
  (dataclass field, `from_dict`, `to_dict`) + added to `KNOWN_TOP_LEVEL_KEYS`.
- `scripts/tests/test_fsm_validation.py` — `TestOverescapedShell` (10 tests): fires on
  `$$(`/`$$VAR`, ignores `$(pwd)`/`$DIR`, ignores legit `$${VAR:-0}`, ignores standalone
  PID `tmp.$$`, ignores prompt actions, `shell_pid_ok` suppresses, wired into
  `validate_fsm`.

### 3. Documentation / memory

- `.claude/CLAUDE.md` "Loop Authoring" — added the MR-9 rule paragraph.
- Corrected the `reference_fsm_bash_brace_escape` mental model: brace `${VAR}` → escape
  `$$`; paren/bare `$(...)`/`$VAR` → stay single `$`.

## Verification

- `python -m pytest scripts/tests/test_fsm_validation.py` — 213 passed (incl. 10 new).
- `ll-loop validate` clean on all 3 loops; sweep found no other loop with the pattern.
- `ruff check` + `mypy` clean on changed Python.
- Full `pytest scripts/tests/` — run as final gate.

## Follow-ups (filed separately)

- **ENH-2366** — residual loop-local audit findings (diagnose root-cause access;
  empty-vs-drained queue). Notes that audit proposal #2 ("verdict laundering") was
  assessed and is **not** a defect (`smoke_component` records missing artifacts as
  `SMOKE_FAIL`).
- **ENH-2367** — harden `audit-loop-run`/`loop-specialist` so a PID artifact is not
  mislabeled an "interpolation sentinel" and the fix direction is not inverted.
- **ENH-2365** — emit `summary.json` on terminal `done` (audit proposal #5, generic).
- Latent, out of scope: inside `node -e "…"` shell heredocs in
  `smoke_component`/`verify_final`, JS `page.$('…')` uses a single `$(` exposed to shell
  command substitution — the **inverse** of MR-9; noted in ENH-2366.

## Notes

The original audit artifact was relocated to
`.loops/diagnostics/audit-interactive-component-generator-2026-06-28.md` with a
maintainer correction header noting the misdiagnosis.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-28T06:29:52 - `846e532c-b018-45c9-8c76-e4f1186d3d5c.jsonl`
