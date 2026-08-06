---
id: BUG-3089
type: BUG
title: Release gate's import scan misses function-local and dotted imports, so most
  records can never be flagged
priority: P2
status: open
discovered_date: 2026-08-06
discovered_by: pre-implementation-review
captured_at: '2026-08-06T18:05:00Z'
labels:
- learning-tests
- release
- gates
testable: true
relates_to:
- ENH-3073
- ENH-2214
- ENH-2216
- BUG-3072
---

# BUG-3089: Release gate's import scan misses function-local and dotted imports, so most records can never be flagged

## Summary

`run_release_gate` narrows its stale/refuted record list to packages the project
actually imports, via `r.target in imported_packages` (`release_gate.py:67`). That
intersection is the gate's whole relevance filter — and it silently discards most
records, because `get_imported_packages` cannot see the two import forms this
codebase uses most:

1. **Function-local imports are invisible.** `_PY_IMPORT_RE`
   (`import_scan.py:8`) is `^(?:import|from)\s+(...)` with `re.MULTILINE`. The `^`
   anchor means the import must begin at **column 0**. Every indented import —
   which in this codebase means every deliberate cycle-avoidance import — never
   matches.
2. **Dotted module names can never match.** The regex captures only the
   top-level segment (`[A-Za-z_][A-Za-z0-9_]*`, no `.`), so
   `imported_packages` can never contain `concurrent.futures` or `ruamel.yaml`,
   yet those are the exact strings two live records use as their `target`.
3. **The two consumers normalize differently.** `release_gate.py:67` matches
   `r.target` raw; `cmd_orphans` (`cli/learning_tests.py:157`) matches
   `r.target.split()[0].lower()`. Neither handles the dotted case, and they
   disagree on multi-word and mixed-case targets — so a record can be
   simultaneously "not imported" for the release gate and "imported" for the
   orphan report, or vice versa.

Net effect: **the pre-release audit's relevance filter is mostly a no-op in the
false-negative direction.** A genuinely refuted record for a package imported
function-locally will never appear in the audit, regardless of `release_gate:
block`.

## Current Behavior

`scripts/little_loops/learning_tests/import_scan.py:8`:

```python
_PY_IMPORT_RE = re.compile(r"^(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
```

`scripts/little_loops/learning_tests/release_gate.py:67`:

```python
hits = [r for r in problem_records if r.target in imported_packages]
```

`scripts/little_loops/cli/learning_tests.py:157`:

```python
orphans = [r for r in records if r.target.split()[0].lower() not in imported]
```

### Confirmed live instances (2026-08-06)

| Record `target` | Actually imported at | Seen by scanner? |
|---|---|---|
| `anthropic` | `host_runner.py:1840`, `:1917`, `fsm/executor.py:2469` — all indented | **No** (function-local) |
| `opentelemetry` | `transport.py:359-361` — all indented | **No** (function-local) |
| `concurrent.futures` | `link_checker.py:16`, `parallel/worker_pool.py:17` — column 0 | **No** (dotted; scanner records `concurrent`) |
| `ruamel.yaml` | `cli/loop/_scaffold_core.py:19-20` — column 0 | **No** (dotted; scanner records `ruamel`) |

`ll-learning-tests orphans` reports all four as orphaned records today, which is
the same defect surfacing through the other consumer.

## Steps to Reproduce

1. `ll-learning-tests orphans` — observe `anthropic`, `opentelemetry`,
   `concurrent.futures` listed as orphans despite being imported (see table).
2. Set any of those records to `status: refuted` in `.ll/learning-tests/`.
3. Run the release gate:
   ```
   python -c "from pathlib import Path; from little_loops.learning_tests.release_gate import run_release_gate; raise SystemExit(run_release_gate(Path.cwd()))"
   ```
4. The refuted record does **not** appear in the audit table and the gate returns
   0, even with `release_gate: "block"`. Expected: the record is flagged.

## Expected Behavior

A record whose target is genuinely imported by the project is subject to the
audit, regardless of whether the import sits at module scope or inside a
function, and regardless of whether the target names a dotted submodule. The
release gate and `cmd_orphans` agree on what "imported" means.

## Root Cause

`get_imported_packages` was written (ENH-2214/ENH-2216) as a cheap regex scan and
its `^`-anchored, dot-free pattern encodes two assumptions that do not hold in
this codebase: that imports live at column 0, and that record targets name
top-level packages. Neither consumer normalizes consistently against it, and
nothing tests the intersection with a realistic import layout.

## Proposed Solution

**Parse, don't regex.** Replace the regex with an `ast`-based scan:
`ast.parse` each file and walk `ast.Import` / `ast.ImportFrom` nodes, which finds
imports at any nesting depth and gives the full dotted module name for free. Fall
back to skipping files that fail to parse (the current `errors="ignore"` read
already tolerates junk). This is stdlib-only, so it adds no dependency.

Emit **both** the full dotted name and every dotted prefix into the returned set
(`concurrent.futures` → `{"concurrent", "concurrent.futures"}`), so a record
targeted at either granularity matches.

**Unify the two consumers** on one normalization helper — e.g.
`normalize_target(target: str) -> str` applying `.split()[0].lower()` — called by
both `release_gate.py:67` and `cli/learning_tests.py:157`, with the imported set
lowercased at construction. Today's divergence is itself a latent bug even after
the scan is fixed.

### Considered and rejected

**Widening the regex** to allow leading whitespace and dots. Rejected: it still
mis-fires inside strings, comments, and docstrings — which an `ast` walk is
immune to by construction — and the codebase has many `import`-mentioning
docstrings. The regex's cheapness is not worth defending; this runs once per
release, not per keystroke.

**Normalizing only in the consumers** and leaving the scan alone. Rejected: it
cannot recover a function-local import, which is the larger of the two misses.

## Scope Boundaries

**In scope**: `get_imported_packages`'s scan mechanism, the shared normalization
helper, and updating both consumers to use it.

**Out of scope**:

- Non-Python targets (`bun-types`, `@types/bun`, `claude-code`, `git`, `jq`,
  `kimi`, `oh-my-pi`). A Python import scan legitimately cannot see these, and
  they will remain permanent "orphans" under any fix here. Whether the registry
  should support non-Python targets is a separate design question — file it if it
  matters.
- Changing the staleness predicate (ENH-3073's Option B follow-up).
- Changing `release_gate` from `warn` to `block` for this project.

## Acceptance Criteria

1. `get_imported_packages` finds imports at any indentation level, verified by a
   test with a function-local `import x` inside a nested function.
2. `get_imported_packages` returns full dotted names **and** their prefixes:
   scanning `from concurrent.futures import X` yields both `concurrent` and
   `concurrent.futures`.
3. Imports appearing only inside string literals, comments, or docstrings are
   **not** reported — the regression the `ast` switch buys and the regex could not.
4. A file that fails to parse is skipped without raising, and the scan continues.
5. One shared normalization helper is used by both `release_gate.py:67` and
   `cli/learning_tests.py:157`; the two no longer normalize differently. A test
   asserts a record target that one consumer considers imported is considered
   imported by the other.
6. Regression test for the four live instances: with this repo's real record
   targets, `anthropic`, `opentelemetry`, `concurrent.futures`, and `ruamel.yaml`
   are all reported as imported.
7. `ll-learning-tests orphans` no longer lists those four; the non-Python targets
   in Scope Boundaries still appear (that behavior is unchanged and correct).
8. A refuted record for a function-locally-imported package appears in the audit
   table and, under `release_gate: "block"`, causes exit 1.
9. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 — this silently defeats a shipped gate. Unlike ENH-3073's
  noise problem (a warning that never clears), this is the opposite and more
  dangerous failure: a record that *should* fire never does, so `release_gate:
  block` provides materially less protection than it appears to. It is also a
  precondition for ENH-3073 being worth anything — making remediation reachable
  does not help for rows that never print.
- **Effort**: Small — one function rewritten to `ast`, one shared helper, two
  call-site updates, and tests.
- **Risk**: Low-Medium. The fix makes the gate flag **more** records, so a
  project sitting at `release_gate: block` could newly block on a record that was
  previously invisible. That is the gate working as intended, but call it out in
  the changelog — it will look like a regression to anyone who had silently
  benefited from the false negatives.
- **Breaking Change**: No (behavioral only; no API or wire-format change).

## Program Design

**Invariant.** A record whose target names a module the project imports is subject to the
audit — independent of that import's indentation, dotted depth, or the target string's case
and spacing.

### Types

No new types. `get_imported_packages` keeps its `set[str]` return; the set's *contents*
widen to include dotted names and their prefixes.

### Signatures

Unchanged public surface:

```python
def get_imported_packages(source_dirs: list[Path]) -> set[str]:
```

New shared helper, to be placed alongside it so both consumers can import it without
either depending on the other:

```python
def normalize_target(target: str) -> str:   # .split()[0].lower()
```

Consumers become `normalize_target(r.target) in imported_packages` at
`release_gate.py:67` and `normalize_target(r.target) not in imported` at
`cli/learning_tests.py:157`, with the scan lowercasing at construction so both sides of
the comparison share one convention.

### Call Path

`commands/manage-release.md` → `run_release_gate` (`release_gate.py:36`) →
`get_imported_packages` (`import_scan.py:11`) → per-file `ast.parse` → walk
`ast.Import` / `ast.ImportFrom` → emit dotted name + prefixes → intersect with
`normalize_target(r.target)` at `release_gate.py:67`.

Independently: `ll-learning-tests orphans` → `cmd_orphans`
(`cli/learning_tests.py:~150`) → the same `get_imported_packages` and the same
`normalize_target`.

### Decision Rules

- **`ast` over regex** — the miss is structural (indentation, dots), and an `ast` walk
  additionally excludes imports named inside strings/comments/docstrings, which the regex
  cannot. Stdlib-only, so no new dependency; runs once per release, so parse cost is
  irrelevant.
- **Prefix expansion, not exact-match-only** — `from concurrent.futures import X` emits
  `{"concurrent", "concurrent.futures"}` so records targeted at either granularity match.
  Emitting only the dotted name would break `anthropic`-style top-level targets; emitting
  only the prefix reproduces today's bug for `concurrent.futures`.
- **Unparseable files are skipped, not fatal** — matches the existing
  `errors="ignore"` read posture; a syntax error in one file must not blank the whole scan.
- **Non-Python targets stay unmatched** — see Scope Boundaries. This is correct behavior,
  not a residual defect, and AC 7 pins it so a later "fix" does not paper over it.

## Integration Map

### Files to Modify

- `scripts/little_loops/learning_tests/import_scan.py` — `_PY_IMPORT_RE` (`:8`)
  and `get_imported_packages` (`:11-31`); the scan rewrite.
- `scripts/little_loops/learning_tests/release_gate.py:67` — raw `in` match.
- `scripts/little_loops/cli/learning_tests.py:157` — divergent normalization.

### Dependent Files (Callers/Importers)

- Any other caller of `get_imported_packages` — grep before editing; ENH-2214 and
  ENH-2216 both introduced consumers.

### Tests

- `scripts/tests/test_release_gate.py` — the `block`-mode exit-1 case for a
  function-locally-imported refuted record (AC 8).
- `scripts/tests/test_cli_learning_tests.py` — `cmd_orphans` behavior (AC 7).
- A test module for `import_scan` itself if none exists — AC 1-4 are pure unit
  tests of the scan and belong there rather than in the gate's tests.

### Documentation

- `docs/guides/LEARNING_TESTS_GUIDE.md` — the `## Release Gate` section describes
  the relevance filter; state that the scan is AST-based and matches dotted names.

## Related Issues

- ENH-3073 — surfaced this as an "adjacent defect noticed during review, not fixed
  here"; that note is now this issue. ENH-3073's value depends on this landing.
- ENH-2214 / ENH-2216 — introduced the gate and the import scan.
- BUG-3072 — failing assertions invisible under `proven` status; a different
  false-negative on the same audit.

## Status

**Open** | Created: 2026-08-06 | Priority: P2
