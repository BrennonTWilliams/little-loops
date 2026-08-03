---
id: ENH-3021
title: ll-config get cannot distinguish an unknown config path from an unset one
type: ENH
status: done
priority: P3
discovered_date: 2026-08-03
discovered_by: epic-review
completed_at: '2026-08-03T17:01:35Z'
parent: EPIC-3008
depends_on:
- BUG-3012
testable: true
labels:
- config
- cli
- ux
milestone: epic-3008
confidence_score: 96
outcome_confidence: 91
score_complexity: 21
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 24
---

# ENH-3021: `ll-config get` cannot distinguish an unknown config path from an unset one

## Summary

`ll-config get <dot.path>` prints nothing and exits `0` for three very
different situations: the key is valid but unset, the key is valid and set to
`null`, and the key **does not exist in the config schema at all** (typo, or a
section `to_dict()` forgot to emit). A caller cannot tell them apart. This
silence is the reason BUG-3012's 11-section omission survived undetected —
every affected lookup looked exactly like "not configured."

## Current Behavior

`main_config` (`scripts/little_loops/cli/config.py:48-70`):

```python
value = BRConfig(Path.cwd()).resolve_variable(args.key)   # :63
...
if value is not None:
    print(value)
return 0                                                   # :70 — always
```

`resolve_variable()` (`config/core.py:963-983`) returns `None` for a missing
path, a `None` value, and an unknown root alike. The `--help` epilog
(`cli/config.py:32-34`) states the contract explicitly: *"0 - always
(never-raise, config-or-default contract; unknown keys print nothing)"*.

Demonstration in this repo:

```
$ ll-config get project.name              # little-loops       exit 0
$ ll-config get project.nonexistent_key   # (nothing)          exit 0
$ ll-config get totally.made.up.path      # (nothing)          exit 0
$ ll-config get context_monitor.enabled   # (nothing)          exit 0   ← BUG-3012, indistinguishable from the two above
```

## Expected Behavior

A path whose **root section is not a known config section** is a different
class of event from a valid-but-unset key, and should say so on stderr — while
keeping stdout and the exit code exactly as they are today.

## Scope Boundaries

In scope: a stderr diagnostic in `ll-config get` when the dot-path's root
segment is not a known top-level config section, plus tests.

Out of scope, deliberately:

- **Changing the exit code.** It stays `0`. The documented never-raise contract
  exists because shell callers do `VAL=$(ll-config get x.y)` in
  `set -e`/pipefail contexts; making unknown keys exit non-zero would break
  those call sites, and the value of this change is diagnostic, not control-flow.
- **Warning on a valid-root-but-unset leaf.** `project.nonexistent_key` stays
  silent — leaf-level validation would require a full JSON-Schema walk, which
  the codebase deliberately does not do at config-load time (see EPIC-3008's
  "Context: why these gaps can exist silently").
- **Touching `resolve_variable()` itself.** It has a second caller
  (`skill_expander.py:64`) with different needs; keep the change in the CLI.

## Suggested Fix Direction

In `main_config` (`cli/config.py:62-70`), when `value is None`, check whether
`args.key.split(".")[0]` is a **known root** (see next section for how that set
is derived — it is *not* just `to_dict()`). If it is not, print a single line to
**stderr**:

```
Warning: 'totally' is not a known config section (ll-config get totally.made.up.path)
```

Then return `0` as before. Reuse the `BRConfig` instance already constructed at
`:63` rather than building a second one — but see "Existing try/except" below;
that reuse is not as simple as it looks.

Update the `--help` epilog (`cli/config.py:32-34`) so the documented contract
matches: still `0` always, but unknown *sections* now warn on stderr.

## Deriving the known-root set: `to_dict()` keys ∪ schema properties

The obvious implementation — treat `BRConfig.to_dict()`'s keys as the known-root
set — **false-warns on real config keys**, because `to_dict()` is deliberately
not a complete inventory of the config file:

- `install_source` is written into `.ll/ll-config.json` by `ll-init`
  (`init/tui.py:591-592`) and is set in this repo's own config, but BUG-3012
  explicitly excludes it from `to_dict()` as a provenance stamp rather than
  user-tunable config. `ll-config get install_source` would warn *"not a known
  config section"* — false.
- `$schema` has the same shape: a real top-level key in every generated config,
  excluded from `to_dict()`.
- `skill_budget` (added to the schema by ENH-3014) is a third instance during
  any window where that issue has landed and its `to_dict()` entry has not.

**Derive the known-root set as the union of `to_dict()`'s top-level keys and
`config-schema.json`'s top-level `properties` keys.** The schema is the honest
inventory of "is this a real config section"; `to_dict()` is the inventory of
"is this resolvable". A root in the schema but not in `to_dict()` is a
BUG-3012-class defect, not a user typo, and warning about it would blame the
user for a tool bug.

Read the schema via the same accessor `ll-init` uses (`schema_default()`'s
loader in `little_loops/init/`) rather than re-implementing a path lookup — the
schema ships as package data and is not resolvable relative to `cwd`.

### Existing try/except: the single-instance AC is not free

`cli/config.py:62-66` currently reads:

```python
try:
    value = BRConfig(Path.cwd()).resolve_variable(args.key)
except Exception:
    value = None
```

The instance is constructed *inside* the `try` and never bound to a name, so
"reuse the instance" requires hoisting the construction out of the expression.
And if `BRConfig(...)` itself raises (unreadable or malformed
`.ll/ll-config.json`), there is no instance to call `to_dict()` on — the
warning path must not turn that into an `UnboundLocalError`/`NameError`. Bind
the instance to `None` up front and skip the section check when it is `None`;
the schema half of the union is still available in that case, but a config that
failed to load is not evidence of a user typo, so emit nothing.

### Relationship to BUG-3012

This issue is the detector; **BUG-3012 is the defect it would have caught.**

`depends_on: [BUG-3012]` is retained, but note that the union-based known-root
set above already removes the ordering hazard: `orchestration` is a
`config-schema.json` property today, so it is a known root regardless of whether
BUG-3012 has landed, and no misleading *"'orchestration' is not a known config
section"* warning can be emitted. (An earlier draft of this issue used
`to_dict()` alone, which is where that hazard — and the `depends_on` edge —
came from.)

The edge is kept anyway because it costs nothing and keeps the epic's dependency
graph honest about which issue is the fix and which is the detector. It is no
longer load-bearing for correctness; if scheduling pressure ever makes it
inconvenient, it can be dropped without breaking this issue's ACs.

## Program Design

### Signatures

- `main_config() -> int` — existing, `scripts/little_loops/cli/config.py:48`
- `BRConfig.to_dict(self) -> dict` — existing, `config/core.py:648-961`
- `BRConfig.resolve_variable(self, var_path: str) -> str | None` — existing,
  `config/core.py:963-983`

### Call Path

`main_config` -> `BRConfig(Path.cwd())` (single instance) ->
`resolve_variable(key)` -> on `None`, test `key.split(".")[0]` against
`to_dict()` keys -> stderr warning if absent -> `return 0` unchanged.

## Acceptance Criteria

- [x] `ll-config get totally.made.up.path` prints one `Warning:` line to stderr,
      prints nothing to stdout, and exits `0`.
- [x] `ll-config get project.nonexistent_key` prints **nothing** on either
      stream and exits `0` (valid root, unset leaf — unchanged behavior).
- [x] `ll-config get project.name` prints the value to stdout with no stderr
      output and exits `0`.
- [x] Every section emitted by `to_dict()` is accepted as a known root — asserted
      by iterating `to_dict()` keys rather than a hardcoded list, so the check
      can't drift from BUG-3012's fix.
- [x] Every top-level property in `config-schema.json` is likewise accepted as a
      known root, asserted by iterating the schema rather than a hardcoded list.
- [x] `ll-config get install_source` and `ll-config get $schema` emit **no**
      warning (real config keys deliberately absent from `to_dict()`), while
      still printing nothing to stdout and exiting `0`.
- [x] A malformed or unreadable `.ll/ll-config.json` (so `BRConfig(...)` itself
      raises) exits `0`, prints nothing to stdout, emits no unknown-section
      warning, and produces no traceback — the existing `except Exception`
      contract at `cli/config.py:64-66` is preserved, not narrowed.
- [x] stdout stays byte-identical to today's output in all three cases above
      (shell callers capture stdout).
- [x] Exactly one `BRConfig` is constructed per invocation.
- [x] The `--help` epilog (`cli/config.py:32-34`) describes the new stderr
      behavior.
- [x] Tests added to `scripts/tests/test_config_cli.py`;
      `python -m pytest scripts/tests/` exits 0.

## Status

**Done** | Created: 2026-08-03 | Priority: P3

## Resolution

Implemented the stderr diagnostic in `main_config()` (`cli/config.py`): the
`BRConfig` instance is now bound to a name (`cfg`) before the resolve call so
it can be reused for the section check, and a new `_warn_if_unknown_section()`
helper warns on stderr when a `None` result's root segment is absent from the
union of `cfg.to_dict()` keys and `config-schema.json`'s top-level
`properties` keys. When `BRConfig(...)` itself raises, `cfg` stays `None` and
the check is skipped entirely (no warning), preserving the never-raise
contract. Added 9 new tests to `test_config_cli.py` covering every AC; full
suite passes (4 pre-existing, unrelated failures in `test_logo.py` /
`test_des_audit.py` / `test_init_e2e.py` confirmed present on `main` before
this change).

## Impact

- **Priority**: P3 — no functional break, but it is the missing feedback loop
  that let an 11-section config gap (BUG-3012) go unnoticed indefinitely. Cheap
  insurance against the next one.
- **Effort**: Small — a few lines in one CLI entry point, plus tests.
- **Risk**: Low — stdout and exit code are unchanged by construction; only
  stderr gains output.
- **Breaking Change**: No.


## Session Log
- `/ll:manage-issue` - 2026-08-03T17:00:49 - `d67ac782-7394-4b87-b7f3-bc9abfa2b904.jsonl`
- `/ll:ready-issue` - 2026-08-03T16:52:22 - `22a7b21a-c980-4b51-b963-92c853114928.jsonl`
- `/ll:confidence-check` - 2026-08-03T15:10:03 - `d8659c88-4c05-448f-aed7-88d399d39874.jsonl`
