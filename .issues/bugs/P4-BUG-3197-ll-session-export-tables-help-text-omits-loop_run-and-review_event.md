---
id: BUG-3197
type: BUG
title: ll-session export --tables help text omits loop_run and review_event
priority: P4
status: open
testable: true
discovered_by: ll-issues-create
relates_to: [BUG-3187]
discovered_date: '2026-08-15'
captured_at: '2026-08-15T19:45:10Z'
---

# BUG-3197: ll-session export --tables help text omits loop_run and review_event

## Summary

The `--tables` help text in `main_session()` lists 17 choices, omitting `loop_run` and `review_event` — both of which are valid keys in `_EXPORT_TABLE_MAP`. A user reading `ll-session export --help` cannot discover two exportable tables that the command accepts.

## Current Behavior

`--tables` help text (`main_session()` in `scripts/little_loops/cli/session.py`)
enumerates 17 values. `_EXPORT_TABLE_MAP` in
`scripts/little_loops/session_store/queries.py` holds **19** keys. The two
missing from the help text are `loop_run` (ENH-2463) and `review_event`
(ENH-2512).

Both are accepted at runtime — this is a help-text gap, not a rejected argument.
`ll-session export --tables loop_run` works today; nothing tells the user it
exists.

Compounding it: `loop_run` is also absent from `_EXPORT_DEFAULT_TABLES`, so it is
one of only two tables (with `message_event`) that a default `ll-session export`
does **not** emit. `message_event` has a documented opt-in (`--include-messages`);
`loop_run` has neither an opt-in flag nor a mention in the help text, so the only
way to discover it is to read `queries.py`.

## Expected Behavior

The `--tables` help text lists all 19 `_EXPORT_TABLE_MAP` keys, and notes that
the default set excludes `message_event` **and** `loop_run`.

Better: derive the help string from `_EXPORT_TABLE_MAP` rather than restating it,
so the two cannot diverge again. That is what let this drift in the first place —
two hand-maintained lists of the same set.

## Acceptance Criteria

- [ ] `ll-session export --help` lists all 19 keys in `_EXPORT_TABLE_MAP`.
- [ ] The help text states that the default set omits both `message_event` and `loop_run`.
- [ ] The list is derived from `_EXPORT_TABLE_MAP`, not hand-written — adding a key to the map updates `--help` with no second edit.
- [ ] A test asserts the help text's advertised set equals `set(_EXPORT_TABLE_MAP)`.

## Motivation

Found during the BUG-3187 doc fix. `docs/guides/HISTORY_SESSION_GUIDE.md` now
documents all 19 values, so the guide is currently *more* accurate than
`--help` — which inverts the rule in `.claude/CLAUDE.md` that `<cmd> --help` is
authoritative over prose. Either the help text catches up or the doc is the
authority, and the former is correct.

## Program Design

Single call site, in `_build_parser()` (`scripts/little_loops/cli/session.py`) —
the `export_parser.add_argument("--tables", ...)` block, whose `help=` is a
hand-written string literal listing 17 names.

Replace the literal with a derived one:

`_export_tables_help() -> str` — build the `--tables` help text from
`_EXPORT_TABLE_MAP` and `_EXPORT_DEFAULT_TABLES`, so the advertised choice set
and the accepted choice set are the same object. Lives beside the map in
`scripts/little_loops/session_store/queries.py` rather than in the CLI module,
since the map is the thing it must not diverge from.

Both names are already importable from `little_loops.session_store.queries`;
`main_session()` imports from that module today, so no new dependency edge is
introduced.

Note `--tables` uses `nargs="+"` with no `choices=`, so argparse never validated
these names — that is why the drift was invisible at runtime. Adding `choices=`
is **out of scope**: it would turn a today-accepted-but-undocumented value into a
hard argparse error for anyone scripting against it. Fix the help text only.

### Call Path

`ll-session export --help` -> `main_session()` -> `_build_parser()`
(`scripts/little_loops/cli/session.py`) -> `export_parser.add_argument("--tables", help=<literal>)`
-> **argparse renders the stale literal** (the failing step) -> user's terminal.

The accepted set travels a separate path that never meets the one above:
`main_session()` -> `export_history()` -> `_EXPORT_TABLE_MAP`
(`scripts/little_loops/session_store/queries.py`). The fix joins them by having
the help string derive from the map.

## Steps to Reproduce

1. `ll-session export --help`
2. Read the `--tables` choice list — 17 names.
3. `python -c "from little_loops.session_store.queries import _EXPORT_TABLE_MAP; print(len(_EXPORT_TABLE_MAP))"` — 19.
4. `ll-session export --tables loop_run` — succeeds, despite `loop_run` never appearing in `--help`.

## Impact

- **Priority**: P4 — no functional defect; both values work when passed. Discoverability only.
- **Effort**: Small — one help string, ideally derived; one test.
- **Risk**: Low — help-text and test change; no behavior change.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-08-15 | Priority: P4
