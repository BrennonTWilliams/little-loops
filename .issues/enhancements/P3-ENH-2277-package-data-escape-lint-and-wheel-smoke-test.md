---
id: ENH-2277
type: ENH
priority: P3
status: open
captured_at: "2026-06-24T00:00:00Z"
discovered_date: 2026-06-24
discovered_by: capture-issue
parent: EPIC-2257
relates_to: [BUG-2271, BUG-2273, BUG-2275, BUG-2276, FEAT-2274, BUG-885, BUG-938]
labels: [enhancement, packaging, testing, lint, ci, install, host-compat]
---

# ENH-2277: Left-shift gates for the "package-data escapes the wheel" bug class — `__file__`-escape lint + wheel smoke test

## Summary

A recurring defect class keeps shipping: package code under `little_loops/`
reaches **outside** the package (via `Path(__file__)` traversal or a hardcoded
`claude` literal) to read a repo-root asset that the pip wheel does not contain
and non-Claude hosts never deliver — and degrades silently. Known instances:
BUG-885 (`loops/`), BUG-2271 / BUG-2273 (`templates/`), BUG-2275 (`hooks/`),
BUG-2276 (`assets/`). The editable dev install **structurally masks** every one
of them, because `__file__` points into the source tree during development, so
maintainers never reproduce the failure. Add two automated gates so the next
instance is caught at authoring/CI time instead of by an end user.

## Motivation

- **The dev loop hides the bug.** Editable installs (`pip install -e ./scripts`)
  resolve every escaping `__file__` path correctly, so the entire class is
  invisible until a user runs a non-editable install — exactly the dominant
  `pip install little-loops` distribution path.
- **It recurs.** Five issues to date, all the same root cause; without a gate
  there will be a sixth. This mirrors the `ll-loop validate` MR-rules philosophy
  already in the project: encode the failure mode as a check rather than
  rediscovering it per-incident.
- **Cross-host stakes.** Every non-Claude host (Codex / Gemini / oh-my-pi) gets
  the package solely via the wheel and never sets `CLAUDE_PLUGIN_ROOT`; a
  self-sufficient wheel is the only common substrate.

## Current Behavior

- No lint flags an `__file__` traversal in `little_loops/` that resolves outside
  the package root.
- No test builds the wheel and exercises the asset-read paths in a clean,
  non-editable environment with `CLAUDE_PLUGIN_ROOT` unset.
- FEAT-2274 proposes a one-off slice (`unzip -l dist/*.whl | grep templates/`)
  but it is manual, issue-scoped, and covers only `templates/`.

## Expected Behavior

1. A static check fails CI when package code resolves a repo-root asset by
   escaping the package (e.g. `Path(__file__).parent.parent...` that leaves
   `little_loops/`), unless the target is whitelisted as in-package.
2. A wheel smoke test builds the wheel, installs it non-editable into a clean
   venv with `CLAUDE_PLUGIN_ROOT` unset, and exercises the real asset-read
   surfaces (`ll-init --yes`, `load_issue_sections()` / `ll-issues sections`,
   the prompt-optimization hook, the Codex adapter install, `get_logo()`),
   asserting none silently degrade.

## Proposed Solution

### 1. `__file__`-escape lint (`ll-verify-*` family)

Add a verifier (e.g. `ll-verify-package-data`, mirroring `ll-verify-skills` /
`ll-verify-triggers`) that AST-scans `little_loops/` for `Path(__file__)`
expressions whose static parent-walk count exits the package, plus reads of
known repo-root dir names (`templates`, `assets`, `hooks`, `skills`, `commands`,
`agents`, `prompts`). Allowlist legitimately in-package targets (`loops/`). Exit
non-zero on a violation; wire into the existing verify suite. Optionally also
flag hardcoded `"claude"` literals outside `host_runner.py` (the `resolve_host()`
boundary already mandated in CLAUDE.md / BUG-2266).

### 2. Wheel smoke test

Add a test (gated/marked so it runs in CI but is skippable locally) that:
- builds the wheel (`python -m build` / `hatch build`),
- installs it non-editable into a throwaway venv,
- runs the asset-read surfaces above with `CLAUDE_PLUGIN_ROOT` unset,
- asserts each produces its real effect (file written / template rendered /
  logo present), not a silent no-op.

Generalize FEAT-2274's `unzip -l` check into a reusable assertion over the full
package-data manifest rather than a single grep.

## API/Interface

- New CLI: `ll-verify-package-data` — exit 1 on any escaping `__file__` asset
  read; `--list` to print findings; registered alongside the other `ll-verify-*`
  tools.

## Integration Map

### Files to Modify / Add
- `scripts/little_loops/cli/verify_package_data.py` (new) — the lint.
- `scripts/pyproject.toml` — register the `ll-verify-package-data` entry point.
- `scripts/tests/test_wheel_smoke.py` (new) — the build+install+exercise test.
- CI workflow — run the new verifier and smoke test.

### Similar Patterns
- `ll-verify-skills` / `ll-verify-skill-budget` / `ll-verify-triggers` — existing
  `ll-verify-*` gate pattern to mirror.
- `ll-loop validate` MR-rules — precedent for encoding a failure mode as a gate
  (CLAUDE.md "Loop Authoring").

### Tests
- Self-tests for the lint (a fixture module with an escaping `__file__` read must
  trip it; an in-package read must not).
- The wheel smoke test itself.

### Documentation
- `docs/reference/CLI.md` — document `ll-verify-package-data`.
- `CONTRIBUTING.md` — note the wheel smoke test and why editable installs mask
  this class.

## Implementation Steps

1. Build the AST lint + allowlist; add self-tests.
2. Register the entry point; wire into the verify suite / CI.
3. Add the wheel smoke test (mark it `slow`/CI-gated).
4. Backfill: run the lint, confirm it flags the already-known instances
   (BUG-2275 / BUG-2276) until they're fixed; confirm clean once they are.

## Scope Boundaries

- Fixing the individual instances (owned by BUG-2271 / BUG-2273 / BUG-2275 /
  BUG-2276 / FEAT-2274). This issue adds the *gates*, not the fixes.
- Changing the packaging mechanism itself (owned by FEAT-2274).

## Impact

- **Priority**: P3 — prevention, not a live break; high leverage (stops the
  recurrence of a 5-instance class).
- **Effort**: Medium — one AST lint + one CI smoke test + wiring.
- **Risk**: Low — additive tooling.
- **Breaking Change**: No.

## Related

- FEAT-2274 — packaging fix; this generalizes its one-off `unzip -l` check.
- BUG-2271 / BUG-2273 / BUG-2275 / BUG-2276 — the instances this would have
  caught.
- BUG-885 / BUG-938 — earlier instances of the same class.
- CLAUDE.md "Loop Authoring" MR-rules — the encode-the-failure-mode precedent.

## Labels

`enhancement`, `packaging`, `testing`, `lint`, `ci`, `install`, `host-compat`

## Status

**Open** | Created: 2026-06-24 | Priority: P3
