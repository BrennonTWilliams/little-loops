---
id: BUG-3201
type: BUG
title: symbol_claims index misses SQL CREATE TABLE names and import-bound aliases,
  producing false stale_symbol_ref
priority: P3
status: done
discovered_by: ll-issues-create
testable: true
discovered_date: '2026-08-15'
captured_at: '2026-08-15T20:05:20Z'
completed_at: '2026-08-15T20:54:42Z'
---

# BUG-3201: symbol_claims index misses SQL CREATE TABLE names and import-bound aliases, producing false stale_symbol_ref

## Summary

`_extract_symbols` (`scripts/little_loops/issues/symbol_claims.py:203`) — the function
that answers "does this symbol resolve in this file?" for `format-check`'s
`stale_symbol_ref` / `mislocated_symbol_ref` gates — recognizes only def/class def-sites
(`_SYMBOL_DEF_PATTERNS`) and assignment-style module constants (`_MODULE_CONSTANT_RE`).

Two classes of legitimately-citable name are invisible to it:

1. **SQL object names** declared as `CREATE TABLE …` inside triple-quoted migration
   strings — 40 table + 64 index names repo-wide, concentrated in
   `scripts/little_loops/session_store/schema.py` and `scripts/little_loops/queue_store.py`.
2. **Names bound by `import`** — 10,684 bindings across 782 tracked `.py` files, 129 of
   them `as`-aliased.

Neither gap fires on the current backlog (the 6 live hits are genuine future-state
citations), so this is latent: it fires on the next issue that legitimately cites a
table name or an aliased import.

## Current Behavior

Repro against the live repo, driving `extract_symbol_claims` → `symbol_exists_in_file`
→ `symbol_resolves_elsewhere`:

```
GAP (elsewhere=False)  tool_events            session_store/schema.py       <- SQL table
GAP (elsewhere=False)  summary_nodes          session_store/schema.py       <- SQL table
GAP (elsewhere=False)  _core_process_agents   cli/adapt_agents_for_codex.py <- import alias
GAP (elsewhere=False)  _fpr                   cli/adapt.py                  <- import alias
GAP (elsewhere=False)  dt_time                cli/logs.py                   <- import alias
OK                     extract_symbol_claims  issues/symbol_claims.py       (control)
```

The two sub-classes differ in severity:

- **`import x as y` / `from m import x as y`** — the alias name is defined nowhere in the
  repo, so `symbol_resolves_elsewhere` is False and the consumer
  (`scripts/little_loops/issue_parser.py:785-791`) emits a hard `stale_symbol_ref`.
- **plain `from m import x`** — `x` resolves in `m`, so the reverse index finds it there
  and the claim degrades to `mislocated_symbol_ref` instead. Still a false positive, and
  one with a confidently wrong explanation attached ("symbol exists elsewhere in the
  repo; this is a mis-attribution"). Example: `resolve_ref_path`, imported and used in
  `scripts/little_loops/issues/symbol_claims.py`, is a true claim about that file.

The alias sites cluster in *function-local* imports (`scripts/little_loops/cli/doctor.py:638`,
`scripts/little_loops/cli/deps.py:269`), so a module-header-only scan would not fix this.

## Steps to Reproduce

```python
from pathlib import Path
from little_loops.text_utils import build_ref_index
from little_loops.issues.symbol_claims import (
    extract_symbol_claims, build_symbol_index,
    symbol_exists_in_file, symbol_resolves_elsewhere,
)

ri = build_ref_index(Path("."))
si = build_symbol_index(Path("."))
body = """
The `tool_events` table in `scripts/little_loops/session_store/schema.py` needs a column.
And `scripts/little_loops/cli/adapt_agents_for_codex.py:_core_process_agents` is the entry point.
The `_fpr` helper in `scripts/little_loops/cli/adapt.py` resolves the plugin root.
"""
for c in extract_symbol_claims(body, ri):
    print(symbol_exists_in_file(si, c.file, c.symbol), c.symbol, c.file)
```

Every line prints `False` except the control. Placing the same prose under a `## Summary`
or `## Current Behavior` heading of a real issue reproduces it end-to-end through
`ll-issues format-check`.

## Program Design

All changes are additive patterns inside `_extract_symbols`. `SymbolIndex`, the reverse
index build, and the consumer at `issue_parser.py:774-791` keep their shape. No new
subprocess is introduced — the single `git ls-files` at `symbol_claims.py:239` is
untouched.

### SQL object names — index into both the per-file and reverse index

New `_SQL_OBJECT_DEF_RE` beside `_MODULE_CONSTANT_RE`: anchored
`^[ \t]*CREATE …(TABLE|INDEX|VIEW)…<name>`, case-insensitive, tolerating `IF NOT EXISTS`
and the `UNIQUE` / `VIRTUAL` / `TEMPORARY` modifiers. Same shape as the existing precedent
at `scripts/little_loops/cli/verify_kinds.py:26`, widened past `TABLE`.

Ungated by language: `CREATE TABLE` means the same thing in a Go heredoc, and no pattern
in `scripts/little_loops/issues/anchors.py:15-55` can match a line starting with `CREATE`.

`.sql` is deliberately **not** added to `_SUPPORTED_SYMBOL_EXTENSIONS`. Today a `.sql`
citation returns `None` (fail open); adding it would make it answer `False` for every
column, trigger and constraint name the patterns do not cover — a new false-positive class.

SQL names do belong in the reverse index: they are repo-unique, so citing `tool_events`
against the wrong file correctly yields `mislocated_symbol_ref` pointing at the schema.

### Import bindings — per-file index only, `.py` only

New `_IMPORT_LINE_RE` / `_IMPORT_BINDING_RE` / `_TRAILING_COMMENT_RE` plus an
`_import_bindings(clause)` helper. An `import_paren_depth` counter threads through the
existing `for line in lines` loop, consulted *before* `_SYMBOL_DEF_PATTERNS` so a
continuation line like `    field,` is read as a binding rather than mistaken for a
def-site, and clamped with `max(0, …)` so a stray `)` cannot permanently disable
continuation handling.

Three constraints, each established by measurement:

- **Line regex, not `ast.parse`.** `ast.parse` over every tracked `.py` measured **2.25s**,
  roughly an order of magnitude more than the regex plus a continuation counter at
  **0.22s**, against a whole-index build under a second. Recall is **10,678 / 10,684**.
- **Strip trailing comments before counting parens.** All 6 misses were
  `scripts/little_loops/cli/loop/info.py:37-45`, where
  `ACRONYMS,  # noqa: F401  (re-exported for tests/lint)` carries a `)` inside the comment
  that closed the continuation early.
- **Gate on `path.suffix == ".py"`.** `import java.util.List;` would index `java` into
  every Java file; Go's `import (` block would open a continuation with nothing findable
  inside; TS/JS place names before `from`, inverted from Python.

Accepted imprecision, to be documented in-code: 33 import-shaped lines inside docstrings
are indexed as bindings. The direction is fail-open (extra names produce fewer gaps).

### Exclude imports from the reverse index

`_build_reverse_index` (`symbol_claims.py:254`) passes `include_imports=False`;
`SymbolIndex.symbols_in` (`:285`) keeps the default. These are already separate reads, so
there is no cache to keep coherent and no extra I/O.

This is the load-bearing decision. Without it, `json` / `Path` / `re` / `field` each map to
hundreds of files, and every genuinely stale claim naming a common token flips to
`mislocated_symbol_ref` — whose printed rationale ("symbol exists elsewhere in the repo;
this is a mis-attribution", `scripts/little_loops/cli/issues/format_check.py:179-183`) would
then be false. With the exclusion, both false-positive classes die and no new noise appears.

Residual accepted loss: an issue attributing `_find_plugin_root` to `cli/adapt.py` (which
only re-exports it) is no longer flagged. That is the weakest member of the mislocated
class, and is unflaggable without import-vs-def provenance the index does not carry.

### Rejected alternatives

- **A third gap class `imported_symbol_ref`** — needs a new `FormatGaps` field
  (`issue_parser.py:301`), a `to_dict` key, a `has_gaps` clause, a printer and two help
  strings, in order to re-emit a finding that is not a defect.
- **"Index imports for the stale determination but not the mislocated one"** — incoherent:
  `issue_parser.py:785` gates on `symbol_exists_in_file(...) is False` *before* ever
  reaching `symbol_resolves_elsewhere`.
- **Adding `.sql` to `_SUPPORTED_SYMBOL_EXTENSIONS`** — see above; flips `.sql` from
  fail-open to checked.

## Expected Behavior

A backticked symbol attributed to a file resolves when that name genuinely resolves in
the file — including a SQL table/index/view name declared in an embedded migration string,
and any name bound by an import statement in a `.py` file. The five GAP rows in the repro
above all become `OK`; the control stays `OK`; the 6 pre-existing genuine hits on the
backlog are unchanged.

## Impact

- **Priority**: P3
- **Effort**: S
- **Risk**: Low — additive to the per-file index, which can only turn a gap into a
  non-gap; the reverse index gains only repo-unique SQL names.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] A `CREATE TABLE` / `CREATE INDEX` / `CREATE VIEW` name declared inside a
      triple-quoted string in a `.py` file resolves via `symbol_exists_in_file`.
- [ ] SQL object names enter the reverse index, so a table name claimed against the wrong
      file yields `mislocated_symbol_ref`, not `stale_symbol_ref`.
- [ ] `.sql` files still return `None` from `symbol_exists_in_file` (fail open); `.sql` is
      not added to `_SUPPORTED_SYMBOL_EXTENSIONS`.
- [ ] A name bound by `import x as y`, `from m import x as y`, or plain `from m import x`
      resolves in the importing `.py` file, including function-local and parenthesized
      multi-line imports.
- [ ] A parenthesized import whose first line carries a trailing comment containing `)`
      does not close the continuation early (regression test for the 6 measured misses).
- [ ] Import-bound names are excluded from the reverse index: a name only ever imported,
      claimed against an unrelated file, yields `stale_symbol_ref` and not
      `mislocated_symbol_ref`.
- [ ] The import scan is gated to `.py`: `.java`, `.go` and `.ts` import lines index
      nothing, and a `.go` `import (…)` block does not suppress indexing of a following
      `func`.
- [ ] `check_format_gaps` still spawns no subprocess, and `format-check` still makes
      exactly two `git ls-files` calls per invocation.
- [ ] `python -m pytest scripts/tests/` exits 0.
- [ ] `ll-issues format-check --all` reports the same 6 pre-existing symbol hits, none added.

## Related Key Documentation

- `scripts/little_loops/issues/symbol_claims.py` — extractor and resolver (FEAT-3048,
  BUG-3063)
- `scripts/little_loops/issue_parser.py:774-791` — the consumer that splits
  `stale_symbol_ref` from `mislocated_symbol_ref`
- `scripts/little_loops/cli/verify_kinds.py:26` — precedent `CREATE TABLE` regex
- `docs/reference/CLI.md` — `ll-issues format-check` gap-class list

## Status

**Open** | Created: 2026-08-15 | Priority: P3
