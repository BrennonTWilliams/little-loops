---
id: ENH-2235
title: Fix Release Gate section in LEARNING_TESTS_GUIDE.md
type: ENH
priority: P3
status: open
---

## Problem

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

## Implementation Plan

Rewrite the "Release Gate" section to accurately describe:

1. **Trigger condition**: "When `learning_tests.enabled` is `true`" (correct) — but clarify the gate checks all learning-test registry records whose targets match imported packages in `scan_dirs`, not sprint `learning_tests_required` fields.
2. **Gate behavior table**: Change the framing from "blocks tagging if..." to explain `release_gate: "warn"` (default, continues) vs `release_gate: "block"` (aborts).
3. **Remove** the `--skip-learning-gate` bypass line (flag doesn't exist on `ll-manage-release`). Add that for emergency releases, set `release_gate: "warn"` temporarily.
4. **Update example output** to match the actual tabular format from `release_gate.py`.

## References

- `scripts/little_loops/learning_tests/release_gate.py` — actual gate implementation
- `commands/manage-release.md:280–298` — correct description of the gate integration
- `scripts/little_loops/cli_args.py:214` — where `--skip-learning-gate` actually lives (`ll-parallel`)
- `scripts/little_loops/config/features.py:398` — `release_gate: str = "warn"` default
