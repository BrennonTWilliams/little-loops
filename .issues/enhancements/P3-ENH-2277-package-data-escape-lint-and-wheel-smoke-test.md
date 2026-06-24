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

# ENH-2277: Left-shift gates for the "package-data escapes the wheel" bug class — manifest-completeness check (primary) + `__file__`-escape lint + wheel smoke test

## Summary

A recurring defect class keeps shipping: package code under `little_loops/`
reaches **outside** the package (via `Path(__file__)` traversal or a hardcoded
`claude` literal) to read a repo-root asset that the pip wheel does not contain
and non-Claude hosts never deliver — and degrades silently. Known instances:
BUG-885 (`loops/`), BUG-2271 / BUG-2273 (`templates/`), BUG-2275 (`hooks/`),
BUG-2276 (`assets/`). The editable dev install **structurally masks** every one
of them, because `__file__` points into the source tree during development, so
maintainers never reproduce the failure. Add automated gates so the next
instance is caught at authoring/CI time instead of by an end user.

### The defect is semantic, not syntactic — gate accordingly

The true defect is *"an asset the code reads at runtime did not ship in the
wheel."* That is a **semantic** property (code-reads vs. what-shipped), not the
**syntactic** `Path(__file__)` traversal that happens to express it today. An
`__file__`-escape lint catches the syntactic symptom, but it has a fatal blind
spot: the remediation for every instance above is to route the read through a
shared resolver (env-var → in-package). Once a callsite is "well-behaved" and
calls the resolver, the lint sees nothing — yet a **new asset that the resolver
loads but that nobody added to the wheel manifest sails straight through, green,
and ships broken.** The lint would give a false sense of security exactly after
the codebase adopts the recommended pattern.

Therefore the **primary** gate is a **manifest-completeness check** keyed on the
defect itself: enumerate every asset the package reads and assert each resolves
inside the built wheel. The `__file__`-escape lint is demoted to a **regression
backstop** (one-time sweep of today's syntactic instances + prevent their
reintroduction); the wheel smoke test is the **runtime backstop** for surfaces
the manifest enumeration misses. Only the manifest check stays meaningful after
everyone routes through the resolver.

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

- Nothing asserts that the assets package code reads are actually present in the
  built wheel.
- No lint flags an `__file__` traversal in `little_loops/` that resolves outside
  the package root.
- No test builds the wheel and exercises the asset-read paths in a clean,
  non-editable environment with `CLAUDE_PLUGIN_ROOT` unset.
- FEAT-2274 proposes a one-off slice (`unzip -l dist/*.whl | grep templates/`)
  but it is manual, issue-scoped, and covers only `templates/`.

## Expected Behavior

1. **(Primary)** A manifest-completeness check fails CI when any asset the
   package reads at runtime is **absent from the built wheel** — keyed on
   code-reads-vs-shipped, so it stays meaningful even after every callsite routes
   through the shared resolver.
2. A static lint fails CI when package code resolves a repo-root asset by
   escaping the package (`Path(__file__).parent...` / `.parents[n]` that leaves
   `little_loops/`), unless the target is allowlisted as in-package — a
   regression backstop for the syntactic symptom.
3. A wheel smoke test builds the wheel, installs it non-editable into a clean
   venv with `CLAUDE_PLUGIN_ROOT` unset, and exercises the real asset-read
   surfaces (`ll-init --yes`, `load_issue_sections()` / `ll-issues sections`,
   the prompt-optimization hook, the Codex adapter install, `get_logo()`),
   asserting none silently degrade — a runtime backstop for surfaces the
   manifest enumeration misses.

## Proposed Solution

### 1. Manifest-completeness check (PRIMARY gate)

Make the package **declare the assets it reads** in one place, then assert at
build/CI time that every declared asset exists inside the built wheel. This
inverts the check: it keys on the defect (read-but-not-shipped), not on the
`__file__` syntax that today expresses it, so it does **not** go blind once
callsites adopt the shared resolver.

Two viable mechanisms (decide in implementation):

- **Resource registry + wheel assertion.** Maintain a single
  `PACKAGE_DATA_ASSETS` manifest (a module-level list, or auto-derived by having
  the shared resolver record each asset key it is asked to resolve). A test
  builds the wheel and asserts every entry is present in the wheel's file list
  (and, ideally, loadable via `importlib.resources.files("little_loops") / ...`
  rather than `__file__` math). New asset, forgotten in packaging → red.
- **`importlib.resources` round-trip in-process.** Have all asset reads go
  through one accessor that uses `importlib.resources`; the completeness test
  enumerates the accessor's known keys and asserts each `.is_file()` against the
  *installed* (non-editable) distribution. This also nudges the codebase off
  `__file__` traversal entirely (the structural cure).

Prefer the mechanism that makes the manifest **hard to forget to update** — e.g.
the resolver itself registering keys, so adding an asset read automatically adds
it to the checked set. Document any deliberately-excluded asset with a reason
(no silent exemptions).

### 2. `__file__`-escape lint (regression backstop)

Add a verifier (e.g. `ll-verify-package-data`, mirroring `ll-verify-skills` /
`ll-verify-triggers`) that AST-scans `little_loops/` for `Path(__file__)`
expressions whose static parent-walk count (`.parent` chains **and** `.parents[n]`
indexing) exits the package, plus reads of known repo-root dir names
(`templates`, `assets`, `hooks`, `skills`, `commands`, `agents`, `prompts`).
Allowlist legitimately in-package targets (`loops/`) and the single shared
resolver. Exit non-zero on a violation; wire into the existing verify suite.
Optionally also flag hardcoded `"claude"` literals outside `host_runner.py`
(the `resolve_host()` boundary already mandated in CLAUDE.md / BUG-2266).

**Known limits (why this is a backstop, not the guarantee):** it sees only the
syntactic pattern, so it is blind to (a) reads routed through the allowlisted
resolver whose asset isn't packaged — covered by gate 1; (b) asset dirs whose
names aren't in its literal list; (c) non-`__file__` escape mechanisms
(cwd-relative, `sys.prefix`, misused `importlib.resources`). Its durable value is
the one-time sweep of today's instances plus preventing their reintroduction.

### 3. Wheel smoke test (runtime backstop)

Add a test (gated/marked so it runs in CI but is skippable locally) that:
- builds the wheel (`python -m build` / `hatch build`),
- installs it non-editable into a throwaway venv,
- runs the asset-read surfaces above with `CLAUDE_PLUGIN_ROOT` unset,
- asserts each produces its real effect (file written / template rendered /
  logo present), not a silent no-op.

Covers conditional/host-specific read paths the static manifest can't enumerate
(e.g. the Codex-only adapter branch). Exercise more than one host where feasible.
Generalize FEAT-2274's `unzip -l` check into a reusable assertion over the full
package-data manifest rather than a single grep.

## API/Interface

- New CLI: `ll-verify-package-data` — runs the manifest-completeness check
  (against the built/installed distribution) **and** the `__file__`-escape lint;
  exit 1 on any unshipped asset or escaping read; `--list` to print findings;
  registered alongside the other `ll-verify-*` tools.

## Integration Map

### Files to Modify / Add
- `scripts/little_loops/package_data.py` (new) — the `PACKAGE_DATA_ASSETS`
  manifest / asset-key registry (or the resolver records keys here).
- `scripts/tests/test_package_data_manifest.py` (new) — the
  manifest-completeness check (every declared asset present in the built/installed
  wheel; loadable via `importlib.resources`).
- `scripts/little_loops/cli/verify_package_data.py` (new) — the `__file__`-escape
  lint + a CLI front-end for the manifest check.
- `scripts/pyproject.toml` — register the `ll-verify-package-data` entry point.
- `scripts/tests/test_wheel_smoke.py` (new) — the build+install+exercise test.
- CI workflow — run the new verifier, manifest check, and smoke test.

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

1. **Primary:** introduce the asset manifest/registry and the
   manifest-completeness test (build wheel → assert every declared asset is
   shipped + loadable via `importlib.resources`). Make the manifest hard to
   forget to update (resolver self-registers keys).
2. Build the `__file__`-escape AST lint (`.parent` chains + `.parents[n]`) +
   allowlist (in-package targets + the shared resolver); add self-tests.
3. Register the `ll-verify-package-data` entry point (manifest check + lint);
   wire into the verify suite / CI.
4. Add the wheel smoke test (mark it `slow`/CI-gated); cover ≥1 non-Claude host
   path (Codex adapter).
5. Backfill: confirm the manifest check + lint flag the already-known instances
   (BUG-2275 / BUG-2276) until they're fixed; confirm clean once they are.

## Scope Boundaries

- Fixing the individual instances (owned by BUG-2271 / BUG-2273 / BUG-2275 /
  BUG-2276 / FEAT-2274). This issue adds the *gates*, not the fixes.
- Changing the packaging mechanism itself (owned by FEAT-2274).

## Impact

- **Priority**: P3 — prevention, not a live break; high leverage (stops the
  recurrence of a 5-instance class). The manifest check is what makes this
  durable — without it, the lint goes blind once the codebase adopts the shared
  resolver, so the cheaper "lint only" version would not actually prevent future
  instances.
- **Effort**: Medium — manifest/registry + completeness test + AST lint + CI
  smoke test + wiring.
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
