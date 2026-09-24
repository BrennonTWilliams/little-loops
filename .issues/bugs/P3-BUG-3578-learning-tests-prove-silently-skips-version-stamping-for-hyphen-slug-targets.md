---
id: BUG-3578
type: BUG
title: learning-tests prove silently skips version stamping for hyphen-slug targets
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T20:00:30Z'
completed_at: '2026-09-24T20:04:21Z'
---

# BUG-3578: learning-tests prove silently skips version stamping for hyphen-slug targets

## Summary

`ll-learning-tests prove` silently skips stamping `proven_package`/`proven_version` when the record's target is a hyphenated slug (e.g. `jinja2-byte-exact-round-trip`). The record stays on age-only staleness, `prove` exits 0 with no diagnostic, and the `/ll:explore-api` skill tells agents that `prove` is how the fields get filled, so they are sent to a no-op.

## Current Behavior

`resolve_target_version` in `little_loops.learning_tests.gate` reduces the target to its first whitespace-delimited token. `jinja2-byte-exact-round-trip` has no spaces, so it looks up a distribution literally named `jinja2-byte-exact-round-trip`, gets `PackageNotFoundError`, and returns `None`. `_stamp_proven_version` in `little_loops.cli.learning_tests` then returns without writing, and `cmd_prove` prints the record and exits 0.

## Expected Behavior

- A slug target whose leading hyphen segment(s) name an installed distribution (`jinja2-…` → `jinja2`) resolves to that distribution and gets stamped.
- When `prove` cannot stamp a version, it says so on stderr.
- `skills/explore-api/SKILL.md` describes stamping as conditional on the target's leading token resolving to an installed distribution.

## Motivation

`/ll:explore-api` told agents that `prove` is how version fields get filled, so an agent asked to fix a missing version ran `prove`, which silently did nothing. The record then stayed on age-only staleness and could not detect a jinja2 upgrade.

## Proposed Solution

1. In `resolve_target_version`, after the whole-token lookup misses, try progressively shorter hyphen prefixes (longest first) and return the first installed distribution; apply the stdlib guard to each candidate.
2. In `cmd_prove`, print a stderr note when the record has no `proven_version` after stamping.
3. Update `skills/explore-api/SKILL.md` to state stamping is conditional.

## Integration Map

### Files to Modify
- `scripts/little_loops/learning_tests/gate.py` — `resolve_target_version`
- `scripts/little_loops/cli/learning_tests.py` — `cmd_prove`
- `skills/explore-api/SKILL.md` (+ `ll-adapt` mirrors for gemini / kimi-code / qwen)

### Dependent Files (Callers/Importers)
- `cmd_backfill_versions` and `is_record_stale` / `describe_staleness` also call `resolve_target_version`, and pick up the fallback automatically.

### Tests
- `scripts/tests/test_learning_tests_version_staleness.py`

## Implementation Steps

1. Add failing tests: slug prefix fallback, full hyphenated distribution name wins, stdlib prefix guard, `prove` stamps a slug target, `prove` notes a skipped stamp.
2. Implement the resolver fallback and the `prove` stderr note.
3. Update the skill text and regenerate host mirrors.

## Impact

- **Scope**: 1 of 100 records in the source repo (`jinja2-byte-exact-round-trip` → `jinja2 3.1.6`); any consumer using slug-style targets is affected.
- **Severity**: version-drift staleness silently disabled for affected records.

## Steps to Reproduce

1. `python -c "from little_loops.learning_tests.gate import resolve_target_version as r; print(r('jinja2-byte-exact-round-trip'))"` → `None`
2. Same call with `'jinja2 byte exact'` → `('jinja2', '3.1.6')`
3. `ll-learning-tests prove "jinja2-byte-exact-round-trip"` → exits 0; record has no `proven_*` keys.

## Root Cause

- **File**: `scripts/little_loops/learning_tests/gate.py`
- **Anchor**: `resolve_target_version`
- **Cause**: first-token reduction splits on whitespace only; no fallback for hyphen-joined slugs. `_stamp_proven_version` (`scripts/little_loops/cli/learning_tests.py`) swallows the `None` silently, and `skills/explore-api/SKILL.md` states the fields are stamped unconditionally.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Additional Finding: silently truncated claims

Stamping the jinja2 record re-serialized its YAML and exposed a separate defect. Two claims had been written as unquoted YAML containing ` #`, which YAML reads as a comment start, so they had always parsed truncated (e.g. `an inline [[# ...`). That is also why a later agent summary misreported them as reworded claims. The `/ll:explore-api` record template never mentioned quoting. Fixed by restoring the two claims as single-quoted scalars and adding a quoting rule to the skill. No other record in the registry has this pattern.

## Resolution

- `resolve_target_version` falls back to the longest installed hyphen prefix, and the stdlib guard applies to every candidate.
- `ll-learning-tests prove` prints a stderr note when no version was stamped.
- `skills/explore-api/SKILL.md` documents conditional stamping and claim quoting; host mirrors regenerated.
- `.ll/learning-tests/jinja2-byte-exact-round-trip.md` is stamped `jinja2 3.1.6` and its two truncated claims are restored. Only this record was stamped. `backfill-versions` would also stamp 10 unrelated records; that was deliberately left for a separate decision.

## Labels

`learning-tests`, `bug`

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-24T20:00:36 - `774b8428-d1d9-4202-80c4-08500a1aa065.jsonl`
