---
id: BUG-3197
type: BUG
title: ll-session export table list drifted across four hand-maintained restatements;
  loop_run missing from defaults
priority: P3
status: done
testable: true
discovered_by: ll-issues-create
relates_to:
- BUG-3187
- ENH-2463
- ENH-2512
discovered_date: '2026-08-15'
captured_at: '2026-08-15T19:45:10Z'
completed_at: '2026-08-15T20:34:59Z'
---

# BUG-3197: ll-session export table list drifted across four hand-maintained restatements; loop_run missing from defaults

## Summary

The set of exportable tables is restated by hand in **four** places, and three of
them have drifted from `_EXPORT_TABLE_MAP` — the one list that actually governs
what `ll-session export` accepts. The `--tables` help text lists 17 of 19 keys;
`export_history()`'s own docstring lists 15. Separately, `loop_run` is missing
from `_EXPORT_DEFAULT_TABLES`, which the git history shows is an oversight in
ENH-2463 rather than a design choice.

## Current Behavior

`_EXPORT_TABLE_MAP` (`scripts/little_loops/session_store/queries.py:89-109`)
holds **19** keys and is the sole authority on what `--tables` accepts. Four
other lists restate it:

| Location | Count | Missing |
|---|---|---|
| `_EXPORT_TABLE_MAP` (`queries.py:89-109`) | **19** | — (authority) |
| `--tables` help literal (`cli/session.py:252-258`) | 17 | `loop_run`, `review_event` |
| `export_history()` docstring (`queries.py:148-152`) | 15 | `loop_run`, `session_lifecycle_event`, `context_pressure_event`, `review_event` |
| `docs/reference/CLI.md:3415` | 17 | `loop_run`, `review_event` |
| `docs/guides/HISTORY_SESSION_GUIDE.md:273` | 19 | — (correct as of BUG-3187) |

All 19 are accepted at runtime — this is a documentation gap, not a rejected
argument. `ll-session export --tables loop_run` works today; only the guide says
so.

The `export_history()` docstring carries a second, separate error: it states
*"Defaults to all non-message tables"* (`queries.py:147`), which is false —
`loop_run` is also excluded from `_EXPORT_DEFAULT_TABLES`.

### `loop_run`'s absence from the defaults is a bug, not a design choice

Established by git archaeology, since the original issue treated it as settled
context:

- ENH-2463's commit (`842059a6`) added `loop_run` to `_EXPORT_TABLE_MAP` and
  **never touched** `_EXPORT_DEFAULT_TABLES` (it appears in the diff only as
  context). The commit message enumerates the registrations it made:
  `VALID_KINDS`/`_KIND_TABLE`/`_EXPORT_TABLE_MAP`. The defaults list is absent.
- ENH-2512's commit (`31bf1b05`), the same-shape enhancement that added
  `review_event`, states: *"Register review/review_events in `VALID_KINDS`,
  `_KIND_TABLE`, `_EXPORT_TABLE_MAP`, `_EXPORT_DEFAULT_TABLES`."* Four lists,
  not three.
- **Size is not the rationale**: `loop_runs` holds ~1 K rows against `sessions`
  at ~12 K, which is already default-on. `message_event`'s exclusion is
  justified by ~28 K rows; nothing comparable applies.
- **Content sensitivity is not the rationale**: `loop_runs` (`branch`,
  `head_sha`, `diagnostics_path`) is the same shape as `orchestration_runs`
  (`branch`, `head_sha`, `pr_url`), which is default-on.
- **No consumer breaks**: nothing in-repo reads the export JSONL, and records
  are `type`-tagged precisely so new types are additive.

## Expected Behavior

1. `loop_run` joins `_EXPORT_DEFAULT_TABLES`, making `message_event` the *only*
   non-default table — which is what the docstring already claims and what
   `--include-messages` already implies.
2. The `--tables` help text advertises all 19 keys and names the excluded
   default(s), both **derived** from `_EXPORT_TABLE_MAP` / `_EXPORT_DEFAULT_TABLES`
   rather than restated, so they cannot diverge again.
3. `export_history()`'s docstring stops enumerating the set and points at the
   map instead — a docstring cannot be derived, so the fix is to not duplicate.
4. `docs/reference/CLI.md:3415` matches, since it is the CLI reference and
   `.claude/CLAUDE.md` makes `--help` authoritative over prose.

## Acceptance Criteria

**Defaults fix**

- [x] `loop_run` is present in `_EXPORT_DEFAULT_TABLES`.
- [x] A default `ll-session export` (no `--tables`) emits `loop_run` records when the table is non-empty.
- [x] A test asserts `set(_EXPORT_TABLE_MAP) - set(_EXPORT_DEFAULT_TABLES) == {"message_event"}` — pinning the invariant that messages are the sole opt-in, so the next table added to the map cannot silently repeat ENH-2463's omission.

**Derived help text**

- [x] `export_tables_help()` is defined in `session_store/queries.py` beside the two lists it reads, and is public (no leading underscore) since the CLI imports it across a package boundary.
- [x] Its returned string's advertised key set equals `set(_EXPORT_TABLE_MAP)` — adding a key to the map updates `--help` with no second edit.
- [x] The excluded-by-default names in that string are derived as `sorted(set(_EXPORT_TABLE_MAP) - set(_EXPORT_DEFAULT_TABLES))`, **not** hand-written — otherwise a literal set sits one line below a derived one, reproducing this exact bug class.
- [x] `export_parser`'s `--tables` action uses that function's return value as its `help=`.

**Tests**

- [x] A unit test on `export_tables_help()` asserts set equality against `_EXPORT_TABLE_MAP`, parsing the returned string directly.
- [x] A separate test asserts the `--tables` action's `help` attribute on the parser built by `_build_parser()` **is** `export_tables_help()`'s output. Do not scrape argparse-rendered `--help` output — terminal-width line wrapping makes that assertion brittle.

**Companion prose**

- [x] `export_history()`'s docstring no longer enumerates the valid values (it points at `_EXPORT_TABLE_MAP` instead) and its "Defaults to all non-message tables" claim is now true.
- [x] `docs/reference/CLI.md:3415` lists all 19 values and the corrected default-exclusion note.
- [x] `docs/guides/HISTORY_SESSION_GUIDE.md:273` is updated for the defaults change (it currently states, correctly for today, that the default set excludes `message_event` **and** `loop_run`).

## Motivation

Found during the BUG-3187 doc fix. `docs/guides/HISTORY_SESSION_GUIDE.md` now
documents all 19 values, so the guide is currently *more* accurate than
`--help` — which inverts the rule in `.claude/CLAUDE.md` that `<cmd> --help` is
authoritative over prose. Either the help text catches up or the doc is the
authority, and the former is correct.

The deeper motivation is the count: four hand-maintained restatements of one
set, three already drifted, each drifting independently. Deriving the help text
retires two of them (help literal, and the docstring by deletion) and makes the
map the single thing to edit.

## Program Design

Two changes in `scripts/little_loops/session_store/queries.py`, one in
`scripts/little_loops/cli/session.py`, plus prose.

**1. Add `loop_run` to `_EXPORT_DEFAULT_TABLES`** (`queries.py:111-129`) — a
one-line insertion, placed after `orchestration_run` to mirror the map's
ordering. See the archaeology under Current Behavior for why this is a
correction rather than a policy change.

**2. `export_tables_help() -> str`** — build the `--tables` help text from
`_EXPORT_TABLE_MAP` and `_EXPORT_DEFAULT_TABLES` so the advertised choice set
and the accepted choice set derive from the same objects. Lives beside the two
lists in `queries.py` rather than in the CLI module, since they are what it must
not diverge from — and putting it in the CLI would mean importing two private
module-level names across a package boundary.

Name it **without** a leading underscore. The CLI imports it from another
package, so `_`-prefixing would advertise the opposite of its actual
visibility; the two lists it reads stay private.

**3. The `--tables` help literal** (`cli/session.py:252-258`) — replace the
hand-written string with `help=export_tables_help()`. `main_session()` already
imports from `little_loops.session_store` (`cli/session.py:55`), so no new
dependency edge is introduced.

**4. Prose** — `export_history()`'s docstring (`queries.py:147-152`) drops its
enumeration in favor of a pointer to `_EXPORT_TABLE_MAP` (a docstring cannot be
derived, so the fix is deletion, not restatement); `docs/reference/CLI.md:3415`
and `docs/guides/HISTORY_SESSION_GUIDE.md:273` are brought current.

### Out of scope

`--tables` uses `nargs="+"` with no `choices=`, so argparse never validated
these names — that is why the drift was invisible at runtime. Adding `choices=`
is **out of scope**: it would turn a today-accepted-but-undocumented value into a
hard argparse error for anyone scripting against it.

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
5. `ll-session export | python -c "import sys,json; print({json.loads(l)['type'] for l in sys.stdin})"` — no `loop_run` records, despite the docstring claiming the default is "all non-message tables".

## Impact

- **Priority**: P3 — the help-text half is discoverability only, but the defaults half is a real (if small) data-completeness gap: a default export silently omitted a populated table. Raised from P4 on that basis.
- **Effort**: Small — one list entry, one derived help function, two prose fixes, three tests.
- **Risk**: Low. The defaults change alters default export *output* (one additional record type), but no in-repo consumer reads the JSONL and records are `type`-tagged so unknown types are ignorable by construction.
- **Breaking Change**: No. Additive to a `type`-tagged stream; no accepted argument becomes invalid.

## Status

**Open** | Created: 2026-08-15 | Priority: P3
