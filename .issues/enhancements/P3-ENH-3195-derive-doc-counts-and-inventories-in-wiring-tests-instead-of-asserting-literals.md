---
id: ENH-3195
type: ENH
title: Derive doc counts and inventories in wiring tests instead of asserting string
  literals
priority: P3
status: open
testable: true
discovered_by: manual-review
discovered_date: '2026-08-15'
captured_at: '2026-08-15T00:00:00Z'
relates_to: [BUG-3186, BUG-3188, BUG-3189, BUG-3190, BUG-3191]
---

# ENH-3195: Derive doc counts and inventories in wiring tests instead of asserting string literals

## Summary

The doc-drift class that produced BUG-3186 through BUG-3191 has no gate. The existing
wiring tests assert **string literals** against docs, so every count they cover drifts,
fails, and gets commented out rather than corrected. Replace the literal assertions for
countable/enumerable facts with **derived** assertions that compute the truth from the
filesystem and compare it to what the doc claims.

## Current Behavior

`scripts/tests/test_wiring_guides_and_meta.py` is a parametrized table of
`(doc_path, expected_string, issue_id)` tuples checked by `test_string_present_in_doc`.
When a count changes, the entry is deleted rather than repaired. From the file itself:

```python
# REMOVED (stale/false-positive, count drifted 68->42 via ll-verify-docs --fix
# during FEAT-2354): ("README.md", "68 skills", "FEAT-1287"),
# REMOVED (stale/false-positive, count drifted 39->42 via ll-verify-docs --fix
# during FEAT-2354): ("docs/ARCHITECTURE.md", "39 composable skills", "FEAT-1447"),
```

Three such entries are commented out. The skill count is now 69 and is asserted nowhere;
`test_wiring_cli_registry.py` has the same shape for CLI entry points (individual
`("docs/reference/CLI.md", "ll-doctor", ...)` rows, added by hand per issue).

The consequence is visible across the current audit batch:

- **BUG-3190** fixes skill counts and a command count. Those counts were fixed before.
- **BUG-3189** fixes a hook count ("Five hooks run before a tool executes") and a
  registered-hook omission (`check-private-refs.sh`, `hooks/hooks.json:80`).
- **BUG-3186** fixes five CLI entry points and subcommands missing from `CLI.md` —
  discoverable by diffing installed console-scripts against `CLI.md` sections.
- **BUG-3191** fixes a "28 slash command templates" vs. 29 mismatch inside a single file
  that states 29 correctly ten lines earlier.

Every one of these is mechanically derivable and none is currently checked.

## Expected Behavior

Add derived assertions to the existing local pytest suite (per the project's no-hosted-CI
policy — this suite *is* CI). Each computes ground truth and asserts the doc agrees:

1. **Skill count** — `len(glob("skills/*/SKILL.md"))` (69) vs. every documented skill
   count in `README.md`, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md`.
2. **Command count** — `len(glob("commands/*.md"))` (29) vs. documented counts, including
   the two independent claims in `docs/ARCHITECTURE.md:24` and `:64` that currently
   disagree with each other.
3. **CLI entry-point coverage** — console-scripts declared in `scripts/pyproject.toml` vs.
   `### ll-*` sections in `docs/reference/CLI.md`. Fails on any entry point with no
   section. Would have caught `ll-compact-session`.
4. **Hook coverage** — handler entries in `hooks/hooks.json` vs. hooks named in
   `docs/guides/BUILTIN_HOOKS_GUIDE.md`. Fails on any registered hook the guide omits.
   Would have caught `check-private-refs.sh` and both `record-hook-event.sh` shims.

Assert the derived number against a regex capture in the doc (e.g. `(\d+) skills`) so the
failure message reads "doc says 42, filesystem has 69" — actionable without investigation.

### Deliberately out of scope: host-tier coverage

An earlier draft included a fifth check asserting `_HOST_RUNNER_REGISTRY` /
`_KNOWN_HOSTS` / the `install_*_adapter` set against the canonical host-tier table that
BUG-3186 introduces. **Dropped, and reassigned to BUG-3186 itself.**

The other four checks bind to shapes that already exist in the tree — a numeric callout,
`###` sections in `CLI.md`, script basenames in `hooks.json`. The host-tier check would
bind to an artifact that does not exist yet, at a location BUG-3186 only *suggests*
(`docs/reference/HOST_COMPATIBILITY.md`) and in a format it does not specify. An assertion
whose anchor is still undecided is brittle by construction, and brittle assertions in this
suite have a documented history of being commented out rather than repaired — the very
failure mode this ENH exists to end. Adding one here would undercut the premise.

Whoever implements BUG-3186 will know exactly where the table lives and what shape it
takes; adding the assertion in that change is both cheaper and more durable than
specifying it here in advance. This also keeps ENH-3195 free of a hard `blocked_by` edge
on a doc issue.

## Implementation Notes

- Extend `test_wiring_guides_and_meta.py` and `test_wiring_cli_registry.py` rather than
  adding new files; both already carry the fixtures and `project_root` plumbing.
- Keep the existing literal-string table for genuinely non-derivable facts (prose
  concepts, symbol names like `LLHookEvent`). This ENH replaces only the countable and
  enumerable rows.
- Where a doc deliberately truncates a list (BUG-3190 proposes exactly this for the
  skills subtree), assert the *count callout*, not the enumeration — a truncated tree
  with a `...` should not fail.
- Allow an explicit opt-out marker for intentionally-approximate prose ("about 70
  skills") so the gate does not force false precision.

## Acceptance Criteria

- [ ] Skill-count, command-count, CLI-entry-point, and hook-coverage assertions exist and derive ground truth from the filesystem/package metadata, not from a hardcoded expected number.
- [ ] Each assertion's failure message names both the documented value and the derived value.
- [ ] The three commented-out `# REMOVED (stale/false-positive, count drifted ...)` entries are deleted and superseded by derived checks.
- [ ] Re-introducing any BUG-3186/3189/3190 defect (removing a `CLI.md` section, adding an unregistered-in-docs hook, letting a skill count drift) fails `python -m pytest scripts/tests/`.
- [ ] The suite still passes on a clean tree; no new third-party dependency.

## Motivation

Six issues in the current batch are doc rot, and at least three are re-fixes of counts
that were fixed before. Fixing them again without a gate schedules a seventh audit. The
per-item cost of these checks is a few lines each; the cost of not having them is a
recurring multi-issue audit sweep.

## Impact

- **Priority**: P3 — no user-facing defect, but it is the only item in this batch that stops the class rather than one instance.
- **Effort**: Small-Medium — ~4 focused tests in two existing files, plus deleting the stale table rows.
- **Risk**: Low. Main risk is over-strictness causing false failures on deliberately approximate prose; mitigated by the opt-out marker and by asserting count callouts rather than enumerations.
- **Breaking Change**: No.

## Sequencing

Land **after** BUG-3186/3189/3190 so the derived assertions go green on first run.
Landing it first would red the suite until each doc fix merges.

## Status

**Open** | Created: 2026-08-15 | Priority: P3
