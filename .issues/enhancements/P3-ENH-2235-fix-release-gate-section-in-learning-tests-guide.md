---
id: ENH-2235
title: Fix Release Gate section in LEARNING_TESTS_GUIDE.md
type: ENH
priority: P3
status: done
testable: false
completed_at: 2026-06-20 03:58:01+00:00
---

## Summary

The "Release Gate" section (lines 370–392) of `docs/guides/LEARNING_TESTS_GUIDE.md` contains three compounding inaccuracies against the actual implementation: incorrect trigger conditions (sprint issues vs imported packages), incorrect default behavior (block vs warn by default), and a non-existent bypass flag (`--skip-learning-gate` on `ll-manage-release`). The example output format is also wrong.

## Current Behavior

The "Release Gate" section (lines 370–392) of `docs/guides/LEARNING_TESTS_GUIDE.md` contains three compounding inaccuracies against the actual implementation (`scripts/little_loops/learning_tests/release_gate.py`, `commands/manage-release.md:280–298`).

### Inaccuracy 1: What the gate checks

**Guide says:** "blocks tagging if any issue in the current sprint (or in the set of recently completed issues) declares `learning_tests_required` targets that are stale or refuted."

**Reality:** The gate scans **actively-imported packages** from `learning_tests.scan_dirs` source files via `get_imported_packages()`, then cross-references those packages against all registry records with status `"refuted"` or a date older than `stale_after_days`. It does not look at sprint issues or `learning_tests_required` fields at all.

### Inaccuracy 2: Default behavior is warn, not block

**Guide says:** With `learning_tests.enabled: true`, `ll-manage-release` "blocks tagging".

**Reality:** `enabled: true` only activates the audit step. The blocking vs. warning behavior is controlled by `learning_tests.release_gate`:
- `"warn"` (default) — prints a warning table but continues the release
- `"block"` — aborts with exit 1

The manage-release command docs (`commands/manage-release.md:296–298`) describe this correctly; the guide does not.

### Inaccuracy 3: `--skip-learning-gate` is not a `ll-manage-release` flag

**Guide says:** "The gate can be bypassed for emergency releases with `ll-manage-release --skip-learning-gate`."

**Reality:** `--skip-learning-gate` is a flag for `ll-parallel` (per-worktree proof-first gate, `scripts/little_loops/cli_args.py:214`). `ll-manage-release` has no equivalent bypass flag. For emergency releases, set `release_gate: "warn"` in config instead.

### Also: example output format is wrong

The guide's example output uses a `[ll-manage-release] Learning-test gate: BLOCK` prefix with indented bullet lines. The actual format is a tabular table (Package / Status / Record Date / Days Since Proven), followed by either a block or warn message.

## Expected Behavior

The "Release Gate" section in `docs/guides/LEARNING_TESTS_GUIDE.md` accurately describes:

1. **Trigger**: Gate checks imported packages from `learning_tests.scan_dirs` source files (via `get_imported_packages()`), not sprint `learning_tests_required` fields
2. **Default behavior**: `release_gate: "warn"` (default) prints a warning table and continues; `release_gate: "block"` aborts with exit 1
3. **Emergency bypass**: Set `release_gate: "warn"` in config temporarily — no `--skip-learning-gate` CLI flag exists on `ll-manage-release`
4. **Example output**: Tabular format with columns: Package / Status / Record Date / Days Since Proven

## Proposed Solution

Rewrite the "Release Gate" section to accurately describe:

1. **Trigger condition**: "When `learning_tests.enabled` is `true`" (correct) — but clarify the gate checks all learning-test registry records whose targets match imported packages in `scan_dirs`, not sprint `learning_tests_required` fields.
2. **Gate behavior table**: Change the framing from "blocks tagging if..." to explain `release_gate: "warn"` (default, continues) vs `release_gate: "block"` (aborts).
3. **Remove** the `--skip-learning-gate` bypass line (flag doesn't exist on `ll-manage-release`). Add that for emergency releases, set `release_gate: "warn"` temporarily.
4. **Update example output** to match the actual tabular format from `release_gate.py`.

## Scope Boundaries

- **In scope**: Rewriting the "Release Gate" section of `docs/guides/LEARNING_TESTS_GUIDE.md` to fix 3 documented inaccuracies and the incorrect example output format
- **Out of scope**: Changes to implementation code (`release_gate.py`), other sections of the learning tests guide, other guide files

## Impact

- **Priority**: P3 — Documentation accuracy issue; misleads users about gate behavior but doesn't break functionality
- **Effort**: Small — Targeted rewrite of a single guide section (~30 lines)
- **Risk**: Low — Documentation-only change with no code impact
- **Breaking Change**: No

## Labels

`documentation`, `learning-tests`, `captured`

## References

- `scripts/little_loops/learning_tests/release_gate.py` — actual gate implementation
- `commands/manage-release.md:280–298` — correct description of the gate integration
- `scripts/little_loops/cli_args.py:214` — where `--skip-learning-gate` actually lives (`ll-parallel`)
- `scripts/little_loops/config/features.py:398` — `release_gate: str = "warn"` default

## Status

**Open** | Created: 2026-06-19 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-06-20T03:56:40 - `d445de64-7691-4c6d-a1c8-94f4fe2bdb10.jsonl`
- `/ll:format-issue` - 2026-06-20T03:51:07 - `af33a2f7-b8a5-40ce-9634-e1101e03615b.jsonl`
