---
id: ENH-2277
type: ENH
priority: P3
status: open
captured_at: "2026-06-24T00:00:00Z"
discovered_date: 2026-06-24
discovered_by: capture-issue
parent: EPIC-2279
relates_to: [BUG-2271, BUG-2273, BUG-2275, BUG-2276, FEAT-2274, BUG-885, BUG-938]
labels: [enhancement, packaging, testing, lint, ci, install, host-compat]
decision_needed: false
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

> **Selected:** `importlib.resources` round-trip in-process — resolver self-registers keys so the manifest updates automatically; also nudges the codebase toward `importlib.resources` (the structural cure for `__file__` traversal).

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

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-24.

**Decision 1 — Manifest-completeness mechanism**

**Selected**: `importlib.resources` round-trip in-process (Mechanism B)

**Reasoning**: The issue text explicitly prefers the approach that makes the manifest hard to forget to update — the resolver self-registers keys so any new asset read is automatically added to the checked set. This also nudges the codebase away from `__file__` traversal toward `importlib.resources`, which is the structural cure. The explicit registry (Mechanism A) requires manual updates, creating a gap where a forgotten entry produces a false-green result.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Resource registry + wheel assertion | 2/3 | 2/3 | 3/3 | 1/3 | 8/12 |
| `importlib.resources` round-trip | 2/3 | 2/3 | 3/3 | 3/3 | 10/12 |

**Key evidence**:
- Resource registry: explicit list risks silent green when maintainer forgets to add an entry after adding a new asset read (risk 1/3)
- `importlib.resources` round-trip: resolver self-registration eliminates the update gap; `importlib.metadata` is already used in `install_check.py`, making the `importlib` namespace familiar; zero `importlib.resources` usage today means this is a clean introduction at a single entry point

---

**Decision 2 — Lint implementation**

**Selected**: Regex

**Reasoning**: The `.parent` chain pattern on `Path(__file__)` is syntactically regular and well-suited to regex detection, consistent with the established `import_scan.py:_PY_IMPORT_RE` / `get_imported_packages()` pattern. The lint's role is a regression backstop for the syntactic symptom — semantic coverage (reads vs. what's shipped) is the manifest check's job. Regex is simpler, consistent, and sufficient for that narrower scope. AST would be more precise for chain-depth counting but introduces `ast.NodeVisitor` with no existing codebase precedent.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Regex | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| AST | 1/3 | 2/3 | 3/3 | 3/3 | 9/12 |

**Key evidence**:
- Regex: `_PY_IMPORT_RE` in `learning_tests/import_scan.py` is the established scanning pattern; no `ast.parse`/`ast.NodeVisitor` exists anywhere in the codebase (AST = 1/3 consistency); regex is "likely sufficient for the backstop role" per the embedded codebase research
- AST: more precise chain-depth counting, but overkill for the backstop role; would require introducing an entirely new scanning idiom to the codebase

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

### Dependent Files (Callers/Importers)
- N/A — all integration targets are new files; no existing code imports them yet. The `ll-verify-package-data` entry point is invoked directly by the verify suite / CI rather than imported.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Additional files to modify (not in original list):**
- `scripts/little_loops/cli/__init__.py` — must add `from little_loops.cli.verify_package_data import main_verify_package_data` and include it in `__all__`; this is required because all `[project.scripts]` entry points resolve through `little_loops.cli:<function>` (established pattern: `main_verify_triggers`, `main_verify_skills`, etc. all re-exported here)
- `scripts/little_loops/skill_expander.py` — has `_find_plugin_root()` using 3× `.parent` traversal (env-var-first with `CLAUDE_PLUGIN_ROOT`); the lint must handle this — either flag it as a remaining escape to fix, or allowlist it alongside `init/cli._plugin_root()`

**Build backend is hatchling (not setuptools):**
- Config lives in `[tool.hatch.build.targets.wheel]` in `scripts/pyproject.toml`: `packages = ["little_loops"]` and `include = ["little_loops/**", "LICENSE"]`
- No `MANIFEST.in`, no `[tool.setuptools.package-data]`
- For bundling repo-root assets into the wheel (FEAT-2274 scope), the correct mechanism is hatchling's `shared-data` or `artifacts` config, not setuptools `package-data`

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

### Configuration
- `scripts/pyproject.toml` — already listed under Files to Modify (new `ll-verify-package-data` entry point registration).

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


## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Complete `__file__` Escape Site Inventory

All sites where `little_loops/` code reaches outside the package via `Path(__file__)` traversal:

| File | Anchor | Traversal | Target asset | Env-var guard? | Lint verdict |
|---|---|---|---|---|---|
| `scripts/little_loops/logo.py` | `get_logo()` | 3× `.parent` + `/ "assets" / "ll-cli-logo.txt"` | `assets/ll-cli-logo.txt` | **No** | **FLAG** — bare escape, no fallback |
| `scripts/little_loops/hooks/user_prompt_submit.py` | `_PROMPT_FILE` (module-level const) | `.parents[3]` + `/ "hooks" / "prompts" / ...` | `hooks/prompts/optimize-prompt-hook.md` | **No** | **FLAG** — bare escape, evaluated at import time |
| `scripts/little_loops/issue_template.py` | `_default_templates_dir()` | 3× `.parent` + `/ "templates"` | `templates/` | Yes (`CLAUDE_PLUGIN_ROOT`) | **FLAG** — escapes without env var on non-editable |
| `scripts/little_loops/skill_expander.py` | `_find_plugin_root()` | 3× `.parent` | repo root | Yes (`CLAUDE_PLUGIN_ROOT`) | **FLAG or allowlist** — same pattern as shared resolver |
| `scripts/little_loops/init/cli.py` | `_plugin_root()` | 4× `.parent` | repo root | Yes (`CLAUDE_PLUGIN_ROOT`) | **Allowlist** — this IS the shared resolver; all others should route through it |
| `scripts/little_loops/init/detect.py` | `_find_templates_dir()` | 4× `.parent` + `/ "templates"` | `templates/` | Yes (`CLAUDE_PLUGIN_ROOT`) | **FLAG** — duplicate of the resolver; should call `_plugin_root()` |
| `scripts/little_loops/cli/loop/_helpers.py` | `get_builtin_loops_dir()` | 3× `.parent` | `scripts/little_loops/loops/` | No | **OK** — resolves inside the package; must be on allowlist |
| `scripts/little_loops/fsm/fragments.py` | `_BUILTIN_LOOPS_DIR` (module-level) | 2× `.parent` | `scripts/little_loops/loops/` | No | **OK** — resolves inside the package; must be on allowlist |

**Allowlist design:** The lint's pass/fail criterion is whether the resolved path exits `scripts/little_loops/`. `_helpers.py` and `fragments.py` stay inside — they are structurally OK and must be on the allowlist to avoid false positives. `init/cli._plugin_root()` is the canonical shared resolver and can also be allowlisted; all other escaping sites are lint targets.

### `__file__` Escape Pattern Details

- `logo.py:get_logo()` uses `logo_path.exists()` as a guard — silently returns `None` if absent; `print_logo()` is a no-op on `None`. No `CLAUDE_PLUGIN_ROOT` check at all.
- `hooks/user_prompt_submit._PROMPT_FILE` is a **module-level constant** set at import time. The `handle()` function checks `_PROMPT_FILE.is_file()` but the path is baked in when the module loads — particularly brittle.
- `skill_expander._find_plugin_root()` was not mentioned in the original issue but follows the same `CLAUDE_PLUGIN_ROOT`-first pattern as `init/cli._plugin_root()`; it reaches `skills/` and `commands/` at repo root.

### Manifest Completeness Check — API

`importlib.metadata` is already used in `scripts/little_loops/init/install_check.py:detect_installation()` and `init/validate._check_little_loops_version()`. The established test-patching pattern lives in `scripts/tests/test_init_install.py`.

For the completeness check, use `importlib.metadata.Distribution("little-loops").files()` — returns a list of `PackagePath` objects covering all files in the installed distribution. Assert each declared asset appears in this list.

For the in-process read path, `importlib.resources.files("little_loops")` provides a traversable interface to package-bundled data. **Zero usage of `importlib.resources` exists today** — the implementation will introduce it for the first time.

### Lint Implementation — AST vs. Regex

No `ast.parse` / `ast.walk` / `ast.NodeVisitor` usage exists in the codebase. Two options:

- **Regex** (consistent with `scripts/little_loops/learning_tests/import_scan.py:_PY_IMPORT_RE` and `get_imported_packages()` — the established scanning pattern). Simpler, but can miss dynamic constructions.

> **Selected:** Regex — matches the established `import_scan.py` scanning pattern; syntactically regular `.parent` chains are sufficient to detect without AST; appropriate for the backstop role (semantic coverage is the manifest check's job, not the lint's).

- **AST** (more accurate for counting `.parent` chains; new to the codebase). `ast.NodeVisitor` walking `ast.Attribute` nodes can precisely detect `Path(__file__).parent.parent...` chains and count depth.

Given the pattern is syntactically regular (`.parent` chains on `Path(__file__)`), regex is likely sufficient for the backstop role. AST is more future-proof if the lint needs to count chain depth exactly.

### CLI Structure — Model After `verify_triggers.py`

The closest model for `cli/verify_package_data.py` is `scripts/little_loops/cli/verify_triggers.py:main_verify_triggers()`:

```python
def main_verify_package_data() -> int:
    with cli_event_context(DEFAULT_DB_PATH, "ll-verify-package-data", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-verify-package-data",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="Exit codes:\n  0 - all assets shipped\n  1 - missing assets or escaping reads",
        )
        parser.add_argument("-C", "--directory", type=Path, default=None, ...)
        parser.add_argument("--list", action="store_true", ...)
        parser.add_argument("--json", action="store_true", ...)
        args = parser.parse_args()
        ...
        return 0  # or 1
```

### Wheel Smoke Test — Marks and Guard Pattern

Use `@pytest.mark.slow` + `@pytest.mark.integration` + an `PYTEST_INTEGRATION=1` env guard, matching `scripts/tests/test_rn_build.py:TestE2E`:

```python
@pytest.mark.slow
@pytest.mark.integration
class TestWheelSmoke:
    def test_asset_reads_non_editable(self) -> None:
        if not os.environ.get("PYTEST_INTEGRATION"):
            pytest.skip("Set PYTEST_INTEGRATION=1 to run wheel smoke tests")
        # build wheel → install non-editable venv → exercise asset-read surfaces
```

Both marks are already declared in `[tool.pytest.ini_options]` in `scripts/pyproject.toml` — no new registration needed.

For subprocess invocations in the smoke test, follow the pattern in `test_rn_build.py`: `subprocess.run([...], capture_output=True, text=True, timeout=N)` without `check=True`; assert manually on `returncode`.

## Session Log
- `/ll:decide-issue` - 2026-06-25T04:21:22 - `31eb1bb9-53b5-4aad-998f-729f66e478aa.jsonl`
- `/ll:refine-issue` - 2026-06-25T04:17:08 - `a21d9f22-89f7-43e3-9e2d-36a72e4d4b27.jsonl`
- `/ll:format-issue` - 2026-06-25T04:09:14 - `18bb767c-bb64-42b8-87dd-2614b8c50967.jsonl`
