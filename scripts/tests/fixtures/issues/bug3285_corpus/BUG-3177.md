---
id: BUG-3177
type: BUG
title: 'll-mcp serves zero prompts on a non-editable install: skills/ is not package
  data and _find_plugin_root falls back to the site-packages parent'
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T03:25:30Z'
completed_at: '2026-08-15T05:55:44Z'
parent: EPIC-3127
labels:
- mcp
- multi-host
relates_to:
- BUG-3178
- BUG-3179
blocked_by:
- BUG-3179
testable: true
decision_needed: false
learning_tests_required:
- hatchling
confidence_score: 96
outcome_confidence: 61
score_complexity: 19
score_test_coverage: 15
score_ambiguity: 15
score_change_surface: 12
missing_artifacts: true
---

# BUG-3177: ll-mcp serves zero prompts on a non-editable install: skills/ is not package data and _find_plugin_root falls back to the site-packages parent

## Summary

`ll-mcp`'s prompts-from-skills surface — the payoff EPIC-3127 calls "the biggest
strategic" one, skills invocable from any MCP host with zero per-host adaptation —
resolves to an empty index on a `pip install little-loops` deployment, silently.

`build_server()` builds the prompt index from `_find_plugin_root() / "skills"`
(`scripts/little_loops/mcp_server/server.py:99`). `_find_plugin_root()`
(`scripts/little_loops/skill_expander.py:25`) reads `CLAUDE_PLUGIN_ROOT` if set,
otherwise falls back to `Path(__file__).resolve().parent.parent.parent`. In this
editable checkout that fallback lands on the repo root, where `skills/` exists —
which is why the surface works here and in every `local-editable` project on this
machine. In a wheel install it lands on the site-packages parent, which has no
`skills/` directory: `scripts/pyproject.toml:177` packages only
`little_loops/**` and `LICENSE`, and `skills/` lives at the repo root, outside
the package.

`build_prompt_index()` returns `{}` when the directory is absent
(`scripts/little_loops/mcp_server/prompts.py:64-65`) with no warning and no log
line, so `prompts/list` answers with an empty list and the host has no way to
tell an empty catalog from a misresolved root.

The affected configuration is exactly the one the EPIC targets. Claude Code sets
`CLAUDE_PLUGIN_ROOT` when it loads the plugin, so the Claude Code path is
covered by accident. A third-party MCP host — Codex, or anything else spawning
`ll-mcp` from a venv — sets no such variable and gets zero prompts.


## Steps to Reproduce

1. Build and install the wheel into a clean venv, so `little_loops` lives in
   `site-packages` rather than an editable path:
   `python -m build scripts/ && pip install dist/little_loops-*.whl[mcp]`
2. From a little-loops project directory, with `CLAUDE_PLUGIN_ROOT` unset (the
   state for any host that is not Claude Code), start the server: `ll-mcp`
3. Issue `prompts/list`.
4. Observe: `{"prompts": []}`. No warning, no stderr line, exit status normal.

## Current Behavior

`prompts/list` returns an empty list. The server reports success and advertises
the prompts capability, so a host cannot distinguish "this project has no
skills" from "the server resolved its skills root to a directory that does not
exist."

## Expected Behavior

`ll-mcp` serves the skill catalog as MCP prompts on every supported install
source (`pypi`, `local-editable`, `global-claude-code`, `project-claude-code`),
not only where a repo checkout happens to sit two directories above the package.
Where the catalog genuinely cannot be located, the server says so on stderr
rather than answering with a silent empty list.

## Root Cause

- **File**: `scripts/little_loops/skill_expander.py`
- **Anchor**: `in function _find_plugin_root()`
- **Cause**: Two independent facts compose into the failure. (1) The fallback
  `Path(__file__).resolve().parent.parent.parent` encodes the *source-checkout*
  layout `<repo>/scripts/little_loops/skill_expander.py`; under a wheel install
  the same three hops land on the directory above `site-packages`, which has no
  `skills/`. (2) `skills/` is not shipped in the distribution at all —
  `scripts/pyproject.toml:177` sets `include = ["little_loops/**", "LICENSE"]`
  and `skills/` lives at the repo root — so no path resolution can find it in a
  wheel install; the data is simply absent.

  The silence is a third, separable defect:
  `scripts/little_loops/mcp_server/prompts.py:64-65` returns `{}` for a missing
  directory, which is correct for "no skills configured" but indistinguishable
  from "root misresolved."

## Location

- **File**: `scripts/little_loops/mcp_server/server.py`
- **Line(s)**: 99 (at scan commit: `fe176022`)
- **Anchor**: `in function build_server()`
- **Code**:
```python
prompt_index = build_prompt_index(_find_plugin_root() / "skills")
```

## Environment

Reproduces on any `install_source: pypi` install, and on `local-editable`
installs whose checkout layout differs from this repo's. Does **not** reproduce
in this repo or in the `local-editable` projects on this machine, because
`CLAUDE_PLUGIN_ROOT` is set by Claude Code and the fallback would work anyway.

## Frequency

Deterministic for the affected configuration.

## Motivation

EPIC-3127 names prompts-from-skills "the biggest strategic payoff" of `ll-mcp`:
skills become invocable from any MCP host with zero per-host adaptation, making
`ll-adapt-skills-for-codex` largely obsolete. That payoff is currently
unrealized anywhere except a source checkout. Together with BUG-3178 (Codex
registration emits no launchable server definition) this means the
host-agnostic serving claim has no verified end-to-end path off Claude Code.

The silence is what makes this P2 rather than P3: a host operator sees a
working server that answers every read tool correctly and simply has no
prompts, with nothing pointing at the cause.

## Proposed Solution

> **Read the Revised Decision (2026-08-15) under Decision Rationale before implementing.**
> The three points below are the original framing. Two claims in them have since been
> disproven: the packaging move is **not** mechanical (point 1), and the shared-resolver
> rework is **out of scope** (point 2, and the ENH-3171 coordination note). Option A′ is
> the selected approach.

Two changes, both needed; the third is optional but cheap.

1. **Ship the skills.** Either add `skills/` to the wheel as package data under
   `little_loops/` (matching the FEAT-2274 precedent that moved
   `hooks/prompts/` and `hooks/adapters/codex/` inside the package), or
   establish that MCP prompts come from the *project's* skills rather than the
   plugin's. Prefer the former: `prompts.py`'s contract is the plugin catalog,
   and the packaging move is mechanical and already has precedent.
2. **Make the root explicit.** Give the skills root the same override treatment
   ENH-3171 specifies for the project root — an `LL_MCP_SKILLS_ROOT` (or a
   resolution order that consults the installed package location first) so the
   `parents[2]` heuristic is not the only path.
3. **Break the silence.** When the resolved skills directory does not exist,
   emit one stderr line naming the path tried. `ll-mcp` is spawned by a host, so
   stderr is the host's server log — the right channel for this.

Coordinate with ENH-3171: both are "the server resolves a root by guessing and
answers truthfully about nothing when it guesses wrong." A single resolution
helper covering project root and skills root is likely the better shape than
two independent fixes.

> **Revised 2026-08-15**: the shared-helper coordination is deferred to the split-out
> resolver issue (see Implementation Steps → Scope note), not attempted here. ENH-3171 is
> still open and its scope (`tools.py::_project_root()`, `tasks.py::_loops_dir()`,
> `server.py`'s `BRConfig` line) does not cover the skills-root site at `server.py:99`, so
> there is nothing to converge on yet. Building a shared helper now would mean designing it
> against one real caller and one hypothetical one.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

Research surfaced a fact this issue's point 1 does not account for: FEAT-2274 (status: done, the
precedent this issue cites) explicitly decided to keep `skills/`, `commands/`, `agents/`, and
`hooks/hooks.json` **out** of the wheel as "host-plugin glue not read by package code" (the `BUG-938`
stance, FEAT-2274 lines 109-114). Point 1's "Prefer the former [ship skills/]... matching the FEAT-2274
precedent" is not accurate as stated — FEAT-2274 shipped `templates/`, `assets/`, and two `hooks/`
files precisely *because* package code reads them, and drew the line at `skills/` for the opposite
reason. This issue's premise (`ll-mcp`'s own code now reads `skills/`) is a legitimate reason to
reverse that boundary, but it is a reversal of a recorded decision, not an extension of one — the two
resolutions below make that fork explicit.

**Option A**: Ship a subset of `skills/` (the `SKILL.md`-bearing tree `ll-mcp` reads) as package data
under `little_loops/skills/`, via `git mv` per the FEAT-2274/BUG-885 mechanism (physical relocation
under `scripts/little_loops/`, zero `pyproject.toml` change needed beyond the existing
`include = ["little_loops/**", "LICENSE"]`), registered in `PACKAGE_DATA_ASSETS`
(`scripts/little_loops/package_data.py:28-48`).

> **Superseded 2026-08-15 — see Option A′ below and the Revised Decision section.** Option A was
> selected on the premise that relocating `skills/` is mechanical. Verification showed it is not:
> it breaks Claude Code plugin loading and touches 42 in-package path references. Option A′ gets
> the same outcome without the relocation.

_(Original selection rationale, retained for history:)_ Option A — reuses the FEAT-2274 packaging
mechanism (physical relocation + flat `PACKAGE_DATA_ASSETS` entries + existing `little_loops/**`
wildcard) and scores highest on risk and testability despite reopening the FEAT-2274/BUG-938
boundary decision; Option B depends on unlanded ENH-3171 scope that does not actually cover this
call site and diverges from EPIC-3127's "fixed catalog invocable from any host" semantics.

**Option A′ (SELECTED)**: Keep `skills/` physically at the repo root — no `git mv` — and add a
hatchling `force-include` mapping so the wheel gets an in-package copy at
`little_loops/skills/`:

```toml
[tool.hatch.build.targets.wheel.force-include]
"../skills" = "little_loops/skills"

[tool.hatch.build.targets.sdist.force-include]
"../skills" = "little_loops/skills"
```

Then teach only the MCP skills-root lookup to prefer the in-package copy when it exists, falling
back to the repo-root layout for editable installs.

**The sdist mapping is not optional.** PyPI releases publish an sdist alongside the wheel,
and a pip install from sdist builds the wheel *from the sdist's contents* — where
`../skills` does not exist, so hatchling's force-include silently skips the missing source
(its default behavior) and produces a skills-less wheel with no build error. Wheel-only
force-include fixes this bug for wheel installs while leaving sdist-based installs with
the identical silent failure. With the sdist mapping, `skills/` lands at
`little_loops/skills` *inside the sdist*, where the wheel build's existing
`little_loops/**` include picks it up. (The 2026-08-15 proof below tested the wheel target
only.)

**Proven 2026-08-15** against a minimal reproduction project: `force-include` *does* accept a
source path escaping the packaging root via `../` (unlike the `readme` field — see BUG-3179), and
the built wheel contained both the demo skill's `SKILL.md` **and** its companion
`reference.md`, under the mapped in-package destination.
So companion files ride along at zero extra cost, and no `PACKAGE_DATA_ASSETS` registration is
needed for wheel inclusion.

**Option B**: Keep `skills/` out of the wheel — preserving the FEAT-2274/BUG-938 boundary as-is — and
have `build_server()` resolve the prompt index from the *project's* `skills/` directory instead of the
plugin's bundled catalog, reusing the project-root resolution ENH-3171 is already adding. This changes
what `prompts/list` serves (a project's own skills, not a fixed plugin catalog), which may or may not
match what EPIC-3127 means by a host-agnostic prompts-from-skills surface.

**Recommended**: Option A — it is what this issue already leans toward and matches the mechanical
precedent, but since it reverses a decision FEAT-2274 recorded on purpose, treat it as a boundary
change to flag explicitly (e.g. in the PR description or a note back to `BUG-938`/FEAT-2274), not as
a routine extension of an existing pattern.

### Revised Decision (2026-08-15) — Option A′ supersedes Option A

The scoring below selected Option A on the strength of "physical relocation … zero
`pyproject.toml` change needed," treating the move as mechanical. Direct verification
contradicts that premise on two counts:

1. **It breaks the Claude Code plugin.** `.claude-plugin/plugin.json` declares
   `"skills": ["./skills"]` — a plugin-root-relative path. `git mv skills/
   scripts/little_loops/skills/` makes the plugin load zero skills unless `plugin.json`
   is repointed. The Decision Rationale never accounts for this.
2. **The blast radius is 42 references, not 15.** `grep -rn '"skills"' scripts/little_loops
   --include='*.py'` returns 42 hits. The issue's caller table enumerates
   `_find_plugin_root()`'s 15 callers, but plenty of code reaches `skills/` without going
   through that resolver — `tool_catalog.py:152`, `doc_counts.py` (5 sites: `:30,162,355,402,460`),
   `issue_history/evolution.py:190`, `issue_history/quality.py:448`, `cli/artifact.py:34`,
   `init/core.py:18`, `skill_expander.py:44`. Every one of them would need auditing.

Option A′ avoids both entirely: `skills/` never moves, so `plugin.json` is untouched and all
42 references keep resolving. The only code change is at the MCP skills-root lookup, which is
the single site this bug is actually about. This converts the change from "reverse a recorded
architectural boundary and split a shared resolver" into "add three lines to `pyproject.toml`
and add one preferred-path check."

Note that A′ also **does not reverse** the FEAT-2274/BUG-938 boundary in the repo layout —
`skills/` remains host-plugin glue at the repo root. It only adds a build-time copy into the
wheel for package code that now genuinely reads it. That is a narrower, more defensible change
than what Option A required, and the "flag the reversal explicitly" caveat below softens
accordingly (still worth a PR-description note, since the wheel *contents* do change).

One convention caveat: FEAT-2274's research recorded that no
`hatch_build.py`/`BuildHookInterface`/`[tool.hatch.build.hooks.*]` exists anywhere in the repo.
`force-include` is build-*target* configuration, not a build hook plugin, so A′ introduces no
new hook module — but it is the first `force-include` use in this repo and should be commented
in `pyproject.toml` accordingly.

---

### Decision Rationale (original, for Option A vs B — superseded above)

**Selected: Option A** — ship the `SKILL.md`-bearing tree as package data under
`little_loops/skills/`.

Codebase-evidence agents scored each option across consistency, simplicity, testability, and
risk (0–3 each, 12 max), using the FEAT-2274 packaging precedent and ENH-3171's actual scope as
grounding:

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — ship `skills/` as package data | 2 | 1 | 2 | 1 | 6/12 |
| B — resolve project's own `skills/` | 1 | 1 | 1 | 0 | 3/12 |

**Key evidence for A**: `pyproject.toml`'s `include = ["little_loops/**", "LICENSE"]` already
covers any file physically relocated under `scripts/little_loops/skills/` with zero packaging
config change; `scripts/little_loops/hooks/prompts/` and `hooks/adapters/codex/` are real,
already-shipped precedents of exactly this `git mv`-under-package mechanism (FEAT-2274);
`ll-verify-package-data`'s manifest check is additive to extend. Complicating factors: this
reverses FEAT-2274/BUG-938's deliberate choice to keep `skills/` out of the wheel, and
`_find_plugin_root()` is shared by 15 callers — some resolving `commands/`/`agents/` from the same
root — so relocating only `skills/` forces a resolver split, not a pure packaging move; the
existing `TestFindPluginRoot::test_falls_back_to_package_parent` asserts the exact 3-parent
formula and must be rewritten.

**Key evidence against B**: BUG-3177's own text frames Option B as "reusing the project-root
resolution ENH-3171 is already adding," but ENH-3171 (status: open, unimplemented) explicitly
scopes to `tools.py::_project_root()`, `tasks.py::_loops_dir()`, and `server.py`'s `BRConfig`
line — not the skills-root site at `server.py:99` — so B depends on unlanded work that does not
yet cover this call site. `find_project_root()` is the codebase's real project-root pattern but is
not currently used anywhere in `mcp_server/`. Serving a project's own skills would also serve a
different catalog than EPIC-3127's "fixed catalog invocable from any host" framing, and would
require reworking all ~6 tests in `test_mcp_server.py`'s "Prompts-from-skills (FEAT-3137)" section
that use `_use_plugin_root()`.

Both agents flag the same open follow-up: Option A's packaging fix alone does not resolve
`_find_plugin_root()`'s shared resolution order (needed for non-`skills/` callers under a wheel
install) — that remains BUG-3177 point 2 / coordination with ENH-3171, not settled by this
decision.

## Integration Map

### Files to Modify

_Revised 2026-08-15 for Option A′ — see Revised Decision:_
- `scripts/pyproject.toml` — add `[tool.hatch.build.targets.wheel.force-include]` **and**
  `[tool.hatch.build.targets.sdist.force-include]`, each with
  `"../skills" = "little_loops/skills"`, plus an explanatory comment (first `force-include`
  use in this repo). The sdist mapping is required so a wheel built *from the sdist* (the
  pip-from-PyPI source-install path) still contains `skills/` — see Revised Decision
- ~~`scripts/little_loops/skill_expander.py` — `_find_plugin_root()` resolution order~~ —
  **no longer modified**; the shared resolver is untouched under A′ (see Implementation
  Steps → Scope note)
- `scripts/little_loops/mcp_server/server.py` — skills-root resolution at line 99; this is
  now the *only* code file this bug changes besides `prompts.py`
- ~~`.claude-plugin/plugin.json`~~ — untouched under A′; would have required repointing
  `"skills": ["./skills"]` under the superseded Option A
- `scripts/little_loops/mcp_server/prompts.py` — warn on missing directory; also
  extend `build_prompt_index()`'s discovery beyond `rglob("SKILL.md")` — see
  the companion-file gap under Dependent Files below

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/package_data.py` — `PACKAGE_DATA_ASSETS` (lines 28-48)
  is a **flat tuple of individual file paths**, not a directory glob; Option A
  requires registering each of the 69 `skills/**/SKILL.md` files (and, if
  companion files ship too, the ~31 non-`SKILL.md` companions — see below)
  individually, or extending `check_asset_accessible()`/`list_missing_assets()`
  to accept a glob pattern. This is a real implementation decision the issue
  currently elides by saying "registered in `PACKAGE_DATA_ASSETS`" as if it
  were mechanical. [Agent 1 finding]
- `scripts/little_loops/cli/verify_package_data.py` — `_ALLOWLIST` (lines
  34-39) exempts `skill_expander.py` **by filename**, not by matching its
  current 3-parent-traversal formula specifically. If the resolution order is
  reworked toward a single `.parent` in-package pattern (matching
  `issue_template.py`'s `get_bundled_templates_dir()`, see Tests below), this
  allowlist entry's rationale changes but its filename-keyed exclusion still
  applies — confirmed the two allowlist tests
  (`test_verify_package_data.py::test_allowlisted_files_excluded`,
  `::test_allowlist_entries_cover_known_resolvers`) will **not** break, so
  this is a review-for-staleness item, not a required code change. [Agent 1 +
  Agent 3 finding]
- `docs/ARCHITECTURE.md` — the tree listing's `# Package data:` annotation
  convention (`assets/`, `templates/`, `hooks/prompts/...`,
  `hooks/adapters/codex/...` around lines 322-351) marks what ships in the
  wheel; `skills/` currently sits outside that block as a plain repo-root
  entry (~line 112) and needs to move into it if relocated. [Agent 2 finding]
- `docs/reference/API.md` — `## little_loops.skill_expander` section (~line
  10537) states the *current* resolution order in prose ("Reads
  `CLAUDE_PLUGIN_ROOT` env var first; falls back to the directory three
  levels above `skill_expander.py`") and must be rewritten to match whatever
  new order lands. [Agent 2 finding]
- `docs/reference/CLI.md` — the `ll-mcp` section (~lines 4267-4432) documents
  exactly one env var today (`LL_MCP_TRANSPORT`) and does **not** mention
  `CLAUDE_PLUGIN_ROOT` at all; if `LL_MCP_SKILLS_ROOT` is added, the
  codebase's own convention is to document it here, not only in
  `MCP_SERVER_GUIDE.md` as this issue's Documentation subsection currently
  states alone. [Agent 2 finding]

### Dependent Files (Callers/Importers)
- Every other caller of `_find_plugin_root()` — changing its resolution order
  affects skill expansion generally, not just MCP. Enumerate with
  `grep -rn "_find_plugin_root" scripts/` before touching it.

_Wiring pass added by `/ll:wire-issue`:_
- **Companion-file gap (new defect class, not currently in scope anywhere in
  this issue)**: `build_prompt_index()` (`prompts.py:68`) discovers prompts
  via `skills_dir.rglob("SKILL.md")` only. 31 skills ship non-`SKILL.md`
  companion files (`templates.md`, `reference.md`, etc. — e.g. this very
  `wire-issue` skill links to `behavior-parity.md`,
  `static-coupling-layer.md`). `adapters/core.py`'s
  `_iter_skill_companions()`/`_sync_skill_companions()` (lines 280-351,
  BUG-3163/BUG-3164) already treats a companion-less mirror as a defect
  ("dangles every [reference]") for other host-adapter emitters — the same
  failure mode is unaddressed here. Even after Option A ships `SKILL.md`
  files as package data, `prompts/get` on a skill with companions will return
  a body with dangling local-file links in a non-editable install unless
  companions are shipped and served too. [Agent 1 + Agent 2 finding]
- `cli/verify_host_map.py::_host_compat_md_path()` (line 46) resolves
  `docs/reference/HOST_COMPATIBILITY.md` via `_find_plugin_root()`; that doc
  is not in `PACKAGE_DATA_ASSETS` and is not shipped by either FEAT-2274 or
  this issue's proposed fix — this caller's premise is **already false today
  in a wheel install**, independent of BUG-3177. A resolution-order rework
  must not silently mask this (e.g. by always resolving to *some* existing
  directory) while leaving the actual target file still absent. [Agent 2
  finding]
- `cli/verify_cli_allowlist.py::_areas_md_path()` (line 43) resolves
  `skills/configure/areas.md` — a companion file, not a `SKILL.md` itself. If
  Option A ships only the `SKILL.md`-bearing subset, this becomes a second
  silent-miss site alongside the one BUG-3177 targets. [Agent 2 finding]
- `cli/adapt.py`, `cli/help.py`, `cli/queue.py`, `cli/harness.py`,
  `cli/action.py`, `cli/adapt_skills_for_codex.py`,
  `cli/adapt_agents_for_codex.py` — all also resolve `commands/`/`agents/`,
  which stay out-of-wheel per FEAT-2274's explicit boundary. A resolution
  change that generically "prefers the installed package location" (rather
  than a skills-specific override) would relocate these callers' failure mode
  into `site-packages/little_loops/`, which still has no `commands/`/`agents/`
  — same silent-degradation class, not fixed by a generic rework. This is the
  concrete version of what this issue's own Decision Rationale already flags
  as "forces a resolver split, not a pure packaging move." [Agent 2 finding]

### Similar Patterns
- FEAT-2274 moved `hooks/prompts/optimize-prompt-hook.md` and
  `hooks/adapters/codex/hooks.json` into the package for exactly this reason;
  follow that pattern.
- `ll-verify-package-data` already exists to assert package data ships; extend
  it rather than writing a new gate.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_template.py`'s `get_bundled_templates_dir()` /
  `_default_templates_dir()` (lines 19-36) is the closest existing precedent
  for the resolution-order fix itself: a single `Path(__file__).resolve().parent`
  in-package lookup that works identically in editable and non-editable
  installs, with `CLAUDE_PLUGIN_ROOT` consulted first and validated
  (`.is_dir()`) before being trusted — unlike `_find_plugin_root()`'s
  unconditional trust today. Its tests
  (`test_issue_template.py::test_load_default`, `::test_falls_back_to_file_relative`,
  `::test_uses_claude_plugin_root_when_set`,
  `::test_falls_back_to_bundled_when_env_var_has_no_templates`) are all
  in-process, no venv/build required — model both the implementation and its
  tests on this rather than only on the FEAT-2274 packaging precedent.
  [Agent 3 finding]

### Tests
- `scripts/tests/test_feat_3137_mcp_prompts.py` (or wherever the prompts-surface
  tests live) — add a case that builds the index with `CLAUDE_PLUGIN_ROOT`
  unset and the package resolved outside a checkout.
- A packaging test asserting `skills/**/SKILL.md` is present in the built
  distribution.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wheel_smoke.py::TestWheelSmoke` — read in full: it has
  **no existing assertion, positive or negative, about `skills/`** anywhere
  (nothing to flip, a pure gap). No test in this file exercises `ll-mcp`'s
  server surface at all today — every existing method checks isolated
  `importlib.resources` file paths, not `build_server()`/`prompts/list`. Two
  new methods are needed: a package-data-accessible check for a
  `skills/<name>/SKILL.md` path (model on
  `test_codex_adapter_hooks_json_accessible`, lines 142-154) and a real
  `prompts/list`-returns-full-catalog acceptance test inside the installed
  venv (model on the `_run()` snippet pattern, lines 77-86) — this is
  Implementation Step 1's acceptance test; it does not exist anywhere today.
  [Agent 3 finding]
- `scripts/tests/test_mcp_server.py` — `_use_plugin_root()` (lines 474-476)
  only ever **sets** `CLAUDE_PLUGIN_ROOT`, never unsets it; all 5 existing
  prompt tests (lines 483, 506, 522, 543, 562) go through the env-var-present
  branch only and never exercise `_find_plugin_root()`'s fallback path. None
  of them will break from a fallback rework, but none of them cover it
  either — add a new test with `monkeypatch.delenv("CLAUDE_PLUGIN_ROOT")`
  exercising `build_server()`/`list_prompts()` in-process. Also: no test file
  imports `little_loops.mcp_server.prompts` directly — `build_prompt_index()`
  has no direct unit test; add one for the nonexistent-`skills_dir` /
  stderr-warning branch (no existing `capsys` precedent for a
  missing-directory warning specifically — closest general shape is
  `test_verify_host_map.py::test_dirty_state_returns_one_with_error`'s
  `capsys.readouterr().err` substring-assertion idiom, a CLI-return-path
  case, not a directory-warning case). [Agent 3 finding]
- `scripts/tests/test_verify_package_data.py::test_allowlisted_files_excluded`,
  `::test_allowlist_entries_cover_known_resolvers` — confirmed these will
  **not** break under a resolution-formula rework (the allowlist excludes
  `skill_expander.py` by filename, not by matching the specific 3-parent
  formula) — verified-safe, not a gap, but worth noting so it isn't
  re-litigated during implementation. [Agent 3 finding]

### Documentation
- `docs/guides/MCP_SERVER_GUIDE.md` — how the skills root is resolved
- `docs/reference/CLI.md` — `ll-mcp` entry, if a new env var lands

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/MCP_SERVER_GUIDE.md` is more tightly coupled than the generic
  listing above suggests: its "Resources and Prompts in Practice" section and
  its Troubleshooting table (`prompts/list is empty` row) both state the
  exact defect as *intentional, documented behavior* — e.g. "A pip-only
  install with no plugin checkout therefore lists zero prompts; set
  `CLAUDE_PLUGIN_ROOT`... if you want them." These need rewriting, not just
  updating. [Agent 2 finding]
- `docs/ARCHITECTURE.md` — tree listing (~line 112) and `# Package data:`
  annotation convention (~lines 322-351); see Files to Modify. [Agent 2
  finding]
- `docs/reference/API.md` — `## little_loops.skill_expander` section (~line
  10537) states the current resolution order in prose; see Files to Modify.
  [Agent 2 finding]
- `.issues/bugs/P2-BUG-938-plugin-assets-missing-from-pip-wheel.md` (closed
  invalid) — the actual recorded decision this issue reverses. The issue's
  Codebase Research Findings currently cite only FEAT-2274 by name; BUG-938
  is the original boundary ruling FEAT-2274 later reaffirmed, and is worth
  citing directly (e.g. in the PR description) alongside FEAT-2274 per this
  issue's own recommendation to "flag \[the reversal\] explicitly." [Agent 1
  finding]

### Configuration
- Possible new env var `LL_MCP_SKILLS_ROOT`; no `.ll/ll-config.json` change
  expected (the server must work before it can read project config).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

### Full Enumeration of `_find_plugin_root()` Callers (15 total, from code-graph `callers-of`)

Each caller degrades under the same wheel-install fallback, but not all touch `skills/` —
a resolution-order fix affects all of them, but the packaging fix (shipping `skills/`) only
directly restores the callers marked `skills/`:

| Caller | Anchor | Resolves against |
|---|---|---|
| `main_adapt` | `cli/adapt.py:92` | `skills/`, `commands/`, `agents/` |
| `main_generate_skill_descriptions` | `cli/generate_skill_descriptions.py:189` | `skills/` only |
| `_areas_md_path` | `cli/verify_cli_allowlist.py:43` | `skills/configure/areas.md` (single file) |
| `main_help` | `cli/help.py:277` | `commands/`, `skills/` |
| `_classify_action` | `cli/queue.py:181` | `skills/{name}/SKILL.md` then `commands/{name}.md` via `_resolve_content_path` |
| `TestCatalogDriftGate::test_collect_entries_covers_real_plugin_root` | `scripts/tests/test_help.py:147` | `commands/`; already fallback-tolerant (`pytest.skip` if dir absent, line 149-150) |
| `TestFindPluginRoot::test_uses_env_var_when_set` | `scripts/tests/test_skill_expander.py:41-43` | env var branch only, unaffected by fallback changes |
| `TestFindPluginRoot::test_falls_back_to_package_parent` | `scripts/tests/test_skill_expander.py:45-53` | asserts equality against the exact 3-parent formula, not against "a directory containing skills/" — **must be rewritten**, not just re-validated, if the fallback algorithm changes |
| `_host_compat_md_path` | `cli/verify_host_map.py:55` | `docs/reference/HOST_COMPATIBILITY.md` (single doc file) |
| `_resolve_skill_target_path` | `cli/harness.py:116` | `skills/`/`commands/` via `_resolve_content_path` |
| `build_server` | `mcp_server/server.py:99` | `skills/` only — the BUG-3177 site |
| `expand_skill` | `skill_expander.py:145` | `skills/`/`commands/` via `_resolve_content_path` |
| `main_adapt_agents_for_codex` | `cli/adapt_agents_for_codex.py:108` | `agents/` only |
| `_load_skills` | `cli/action.py:205` | delegates to `collect_entries(plugin_root)` (`commands/`, `skills/`) |
| `main_adapt_skills_for_codex` | `cli/adapt_skills_for_codex.py:98` | `skills/`, `commands/` |

All non-test callers already degrade explicitly (an `ERROR:`/`Warning:` stderr line or a skip) except
`build_prompt_index()` (`mcp_server/prompts.py:64-65`), which is the only silent one — this is the gap
BUG-3177's point 3 ("Break the silence") targets specifically.

### `ll-verify-package-data` extension mechanics
`scripts/little_loops/cli/verify_package_data.py` runs two independent gates: (1) an escape lint
(`run_escape_lint`, lines 99-143) that already allowlists `skill_expander.py`'s 3-parent traversal
(`_ALLOWLIST`, lines 34-39, comment: `_find_plugin_root() — same pattern as shared resolver`); (2) a
manifest check (`run_manifest_check`) that delegates to `package_data.list_missing_assets()`, driven
by the static `PACKAGE_DATA_ASSETS` tuple list (`scripts/little_loops/package_data.py:28-48`) resolved
via `importlib.resources.files("little_loops")` — which can only reach paths inside the `little_loops`
package, so any asset added to this manifest must first physically live under `scripts/little_loops/`.
Companion test: `scripts/tests/test_package_data_manifest.py` (parametrized over every `PACKAGE_DATA_ASSETS` entry).

### stderr warning precedent for point 3
`scripts/little_loops/cli/adapt_skills_for_codex.py:103` already emits
`print(f"ERROR: skills directory not found: {skills_dir}", file=sys.stderr)` for exactly this
scenario (missing skills dir) — the closest existing idiom to model the new warning on. No shared
logging helper exists for this; every call site in the codebase does `print(..., file=sys.stderr)` inline.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

### Types
N/A — no new data shape; the change is a resolution/packaging fix, not a schema change.

### Signatures
- `_find_plugin_root() -> Path` — `scripts/little_loops/skill_expander.py:25-35`. Env-var branch (`CLAUDE_PLUGIN_ROOT`) trusts the value unconditionally if set, no existence check; fallback is `Path(__file__).resolve().parent.parent.parent`, recomputed on every call (no caching/memoization).
- `build_prompt_index(skills_dir: Path) -> dict[str, _PromptEntry]` — `scripts/little_loops/mcp_server/prompts.py:54-83`. Returns `{}` for both a missing directory (`skills_dir.is_dir()` false, lines 64-65) and an existing-but-empty one (the `rglob("SKILL.md")` loop at line 68 simply never iterates) — same silent end state via two different code paths.
- 15 call sites share `_find_plugin_root()`'s fallback and are each independently affected by any resolution-order change (see Integration Map → Dependent Files for the full enumeration and what each resolves against).

### Call Path
`build_server()` (`mcp_server/server.py:99`) -> `_find_plugin_root()` (`skill_expander.py:25`) -> `build_prompt_index()` (`mcp_server/prompts.py:54`) -> closed over by `make_list_prompts_handler`/`make_get_prompt_handler` (`prompts.py:86-158`), built once at server-construction time, never re-enumerated per request.

### Decision Rules
This issue's Proposed Solution introduces new resolution logic (a possible `LL_MCP_SKILLS_ROOT`
env var, or a resolution order that consults the installed package location first) and a new
stderr-warning gate ("resolved skills directory does not exist"). An implementer adding an env var
should follow the established `os.environ.get("LL_<SUBSYSTEM>_<NAME>")`-first, `Path`-fallback
shape already used by `_find_plugin_root()` itself and by `init/cli.py:_plugin_root()` (both trust
the env var unconditionally once set — no existence check), which differs from
`issue_template.py:_default_templates_dir()` (lines 24-36), which validates the env-derived path's
subdirectory exists before trusting it.

**DECIDED 2026-08-15 — use the validate-first shape (`issue_template.py`).** The issue previously
said the implementer "must choose one, not invent a third" and then declined to choose; that choice
is now made, so it does not get relitigated mid-implementation. Rationale: unconditional trust of
`CLAUDE_PLUGIN_ROOT` is *the same silent-misresolution failure class this bug exists to fix* — a
stale or wrong env var yields a confidently-empty prompt list with no diagnostic. Validating
`.is_dir()` before trusting, then falling back, costs one line and makes the new stderr warning
(point 3) actually reachable in the env-var-set case rather than only in the fallback case. Apply
this at the skills-root lookup A′ introduces; do **not** retrofit `_find_plugin_root()`'s shared
behavior here (see the scope note under Implementation Steps).

The concrete resolution order for the skills root:
1. `LL_MCP_SKILLS_ROOT` if set **and** `.is_dir()`
2. `CLAUDE_PLUGIN_ROOT / "skills"` if set **and** `.is_dir()`
3. the in-package wheel copy A′ ships, resolved as
   `importlib.resources.files("little_loops") / "skills"` (matching how
   `package_data.py` resolves assets) if `.is_dir()`. **Not** `Path(__file__).parent /
   "skills"` — the lookup lives in `mcp_server/server.py`, where `__file__`'s parent is
   `little_loops/mcp_server/`, one level too deep; a literal file-relative implementation
   resolves the wrong directory, silently passes in this checkout via fallback 4, and
   fails in a wheel — the exact failure mode this bug is about
4. repo-root fallback (current `_find_plugin_root() / "skills"`) — editable checkouts
5. none of the above → serve an empty index **and** emit the stderr warning naming every path tried

## Implementation Steps

**Prerequisite: BUG-3179 must land first.** `python -m build --wheel scripts/` fails on
main today (`ValueError: Readme path must be within the project directory: ../README.md`),
reconfirmed 2026-08-15. Step 1 below — and the whole `TestWheelSmoke` class it extends —
cannot run until that is fixed. Tracked as `blocked_by: BUG-3179`.

1. Reproduce in a clean venv against a built wheel — this is the acceptance
   test and does not exist today.
2. Ship `skills/` into the wheel via Option A′'s `force-include` — both the wheel target
   **and** the sdist target (see Revised Decision: without the sdist mapping, a wheel
   built from the sdist silently lacks `skills/`), no file relocation, `plugin.json`
   untouched. Add one sentinel/glob entry to `ll-verify-package-data` for gate coverage —
   not 69 entries. In step 5's verification, additionally build from the sdist
   (`python -m build --sdist`, then build/install the wheel from the unpacked sdist) and
   confirm `skills/` is present — the wheel-direct acceptance test alone cannot catch a
   missing sdist mapping.
3. Add the skills-root resolution order specified under Program Design → Decision Rules,
   local to the MCP call site (`mcp_server/server.py:99`).
4. Add the stderr warning for a missing skills directory, naming every path tried.
5. Verify: wheel install, `CLAUDE_PLUGIN_ROOT` unset, `prompts/list` returns the
   full catalog.

### Scope note (2026-08-15): the shared-resolver rework is split out

The original step 3 was "rework `_find_plugin_root()` resolution order, checking every
caller." **That is now out of scope for this bug** and should be spun into its own issue,
coordinated with ENH-3171. Reasons:

- Under Option A′, fixing this bug does not require touching `_find_plugin_root()` at all —
  the skills-root lookup is local to the MCP site.
- The issue already concedes a generic rework does **not** fix the `commands/`/`agents/`
  callers (`cli/adapt.py`, `cli/help.py`, `cli/queue.py`, `cli/harness.py`, `cli/action.py`,
  `cli/adapt_agents_for_codex.py`, `cli/adapt_skills_for_codex.py`), since those directories
  stay out-of-wheel per FEAT-2274 — it would relocate their failure mode into
  `site-packages/little_loops/`, not resolve it.
- Two callers (`cli/verify_host_map.py::_host_compat_md_path()`,
  `cli/verify_cli_allowlist.py::_areas_md_path()`) already resolve targets absent from the
  wheel *today*, independent of this bug. They belong to the split-out issue, where they can
  be fixed rather than incidentally masked.
- This is what drives `outcome_confidence: 61`, below the configured `outcome_threshold` of
  65. Removing it leaves BUG-3177 as: ship skills → local skills-root resolution → stderr
  warning, all three verifiable by the acceptance test in step 5.

Keep `TestFindPluginRoot::test_falls_back_to_package_parent`
(`scripts/tests/test_skill_expander.py:45-53`) **unchanged** under this scope — the wiring
pass flagged it as "must be rewritten," but that only applies if the shared fallback formula
changes, which A′ no longer does.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- ~~Decide the `PACKAGE_DATA_ASSETS` registration mechanism before enumerating
  entries~~ — **RESOLVED 2026-08-15, this obstacle does not exist.**
  `.ll/learning-tests/hatchling.md` records "PACKAGE_DATA_ASSETS registration is
  required for a file to be included in the built wheel: **fail**", and the Option A′
  force-include proof reconfirms it. Registration governs only the `ll-verify-package-data`
  manifest gate's *coverage*, not what ships. So there is nothing to hand-enumerate:
  register one sentinel entry (or extend `check_asset_accessible()` to accept a glob) for
  gate coverage and move on. The "69 entries impractical to enumerate" framing treated a
  dissolved problem as a gating decision.
- ~~Decide whether companion files ship alongside `SKILL.md`~~ — **RESOLVED
  2026-08-15: yes, ship them; cost is zero.** Both the existing hatchling learning test
  and the Option A′ force-include proof show non-`SKILL.md` companions under the same
  tree are picked up by the same mechanism with no separate registration. Since there is
  no cost, there is no tradeoff to defer: shipping them avoids the dangling-local-link
  regression on `prompts/get` for the 31 skills with companions (e.g. `wire-issue` →
  `behavior-parity.md`). Do not ship this as a "known limitation."
- Re-verify `cli/verify_host_map.py::_host_compat_md_path()` and
  `cli/verify_cli_allowlist.py::_areas_md_path()` against whatever new
  fallback order lands — both already resolve targets absent from the wheel
  today, independent of this fix, and must not be silently "fixed" into a
  different silent failure.
- Add the `TestWheelSmoke` acceptance test (package-data-accessible check +
  real `prompts/list`-inside-installed-venv check) — this is what
  Implementation Step 1 requires and it does not exist today.
- Add an in-process `test_mcp_server.py` case with
  `monkeypatch.delenv("CLAUDE_PLUGIN_ROOT")` covering the fallback path — the
  5 existing prompt tests never exercise it.
- Update `docs/guides/MCP_SERVER_GUIDE.md`, `docs/ARCHITECTURE.md`, and
  `docs/reference/API.md` — each currently documents the pre-fix behavior as
  intentional/current, not just silent about the fix.

## Impact

- **Priority**: P2 — silently disables the EPIC's headline capability on the
  exact deployment the EPIC targets, with no diagnostic.
- **Effort**: ~~Medium~~ → **Small-Medium under Option A′** (revised 2026-08-15). Three
  lines of packaging config, one resolution helper at a single call site, one stderr
  warning, plus tests. The shared-resolver rework that made this Medium is split out.
- **Risk**: ~~Medium — changing a shared root resolver~~ → **Low under Option A′**. No
  shared resolver changes, no file relocation, `plugin.json` untouched, all 42 in-package
  `skills/` references keep resolving. The residual risk is packaging-only: the wheel gains
  content, and `force-include` is a first-use-in-repo mechanism (proven, but new here).
- **Breaking Change**: No.
- **Blocked by**: BUG-3179 — the wheel cannot be built on main, so the acceptance test
  cannot run.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Confidence Check Notes

_Added by `/ll:confidence-check` — 2026-08-14:_

**Readiness Score: 96/100 → PROCEED** | **Outcome Confidence: 61/100** (below the
configured `outcome_threshold` of 65)

### Outcome Risk Factors

- **New, live blocker discovered while proving the `hatchling` learning test
  target**: `python -m build --wheel scripts/` currently **fails on main**,
  independent of this issue. `scripts/pyproject.toml`'s `readme = "../README.md"`
  is rejected by hatchling 1.31.0 (the version PEP 517's isolated build environment
  resolves from the unpinned `requires = ["hatchling"]`): `ValueError: Readme path
  must be within the project directory: ../README.md`. Reproduced directly and via
  `PYTEST_INTEGRATION=1 python -m pytest scripts/tests/test_wheel_smoke.py` (already
  fails at the wheel-build fixture step, before any BUG-3177 code exists). This
  blocks Implementation Step 1 ("Reproduce in a clean venv against a built wheel —
  this is the acceptance test and does not exist today") and the whole
  `TestWheelSmoke` class outright — not just the new methods this issue proposes
  adding to it. Recommend filing/fixing this as its own prerequisite bug (e.g. pin
  `hatchling` or fix the readme path) before or alongside BUG-3177's Step 1, or the
  acceptance test cannot run at all.
- **Verified good news, same experiment**: with the readme issue worked around,
  files physically relocated under `scripts/little_loops/skills/**/` — including
  non-`SKILL.md` companion files — are picked up by the existing
  `include = ["little_loops/**", "LICENSE"]` glob automatically, with zero
  `pyproject.toml` change and no `PACKAGE_DATA_ASSETS` registration required for
  wheel inclusion itself. This confirms Option A's central packaging claim. Proof
  recorded at `.ll/learning-tests/hatchling.md` (target: `hatchling`,
  `ll-learning-tests check "hatchling"`).
- **Unresolved design choice flagged in the issue's own Program Design → Decision
  Rules**: the codebase has two disagreeing precedents for trusting an env-var
  override (`_find_plugin_root()`/`init/cli.py:_plugin_root()` trust unconditionally
  vs. `issue_template.py:_default_templates_dir()` which validates first) — the
  issue explicitly says the implementer "must choose one, not invent a third" but
  does not itself choose. Resolve before or during implementation.
- **Deferred-or-not decision left open**: whether non-`SKILL.md` companion files
  ship alongside `SKILL.md` (31 skills affected) is explicitly unresolved in the
  Wiring Phase — leaving it deferred without flagging produces a silent
  dangling-link regression on `prompts/get` for those skills.
- **Change surface**: `_find_plugin_root()` has 15 enumerated callers, several
  resolving `commands/`/`agents/` (which stay out-of-wheel per FEAT-2274) rather
  than `skills/` — a generic resolution-order fix risks relocating those callers'
  failure mode into `site-packages/little_loops/` rather than fixing it. The issue
  already tracks this as a required "resolver split," not a pure packaging move.

## Resolution

- **Action**: fix
- **Completed**: 2026-08-15
- **Status**: Completed

### Changes Made
- `scripts/pyproject.toml`: add `[tool.hatch.build.targets.wheel.hooks.custom]` /
  `[tool.hatch.build.targets.sdist.hooks.custom]` (Option A′, revised to a build hook —
  see Deviations below)
- `scripts/hatch_build.py` (new): conditional force-include of `skills/` into
  `little_loops/skills/`, only when `../skills` exists relative to the build root
- `scripts/little_loops/mcp_server/server.py`: `_resolve_skills_root()` — the
  `LL_MCP_SKILLS_ROOT` → `CLAUDE_PLUGIN_ROOT/skills` → in-package wheel copy →
  checkout fallback resolution order from Program Design → Decision Rules, each
  candidate validated with `.is_dir()`, with a stderr warning naming every path
  tried when none resolve; `build_server()` now calls this instead of
  `_find_plugin_root() / "skills"` directly
- `scripts/little_loops/package_data.py`: comment explaining why `skills/` is
  **not** added to `PACKAGE_DATA_ASSETS` (it is not physically present in an
  editable install — see Deviations)
- `scripts/tests/test_mcp_server.py`: 5 new tests for `_resolve_skills_root()`
  (override precedence, fallthrough, env-unset fallback, stderr warning) and one
  `build_server()`/`list_prompts()` integration test over the full fallback chain
- `scripts/tests/test_wheel_smoke.py`: `[mcp]` extra added to the installed-venv
  fixture; 3 new acceptance tests — package-data-accessible check for
  `skills/manage-issue/SKILL.md`, a real `prompts/list`-returns-full-catalog
  check inside the installed venv, and a wheel-built-from-sdist check (this last
  one caught the force-include-vs-build-hook deviation below)
- `docs/guides/MCP_SERVER_GUIDE.md`, `docs/reference/CLI.md`, `docs/ARCHITECTURE.md`:
  updated to describe the new resolution order, `LL_MCP_SKILLS_ROOT`, and the
  stderr warning; replaced the "prompts/list is empty" troubleshooting row's
  stale "no plugin checkout" framing

### Deviations
- **2026-08-15**: Program Design specified static
  `[tool.hatch.build.targets.{wheel,sdist}.force-include]` tables (`"../skills" =
  "little_loops/skills"`). Implemented instead as a custom `hatch_build.py` build
  hook that adds the same mapping *only when `../skills` exists*. Reason: direct
  verification showed hatchling's static force-include raises
  `FileNotFoundError: Forced include not found` — not the "silently skips" behavior
  the issue's research assumed — whenever the source path is absent. A wheel built
  *from the unpacked sdist* (the scenario the sdist mapping exists to cover) has no
  `../skills` relative to that build root, since the sdist already copied the
  content in-place at `little_loops/skills/`; a static mapping there hard-fails the
  build instead of falling through to the plain `include = ["little_loops/**"]`
  glob that already covers the in-place copy. The conditional hook produces the
  same shipped artifact for both build roots without that failure. Caught by the
  new `test_sdist_force_include_ships_skills` test, which reproduced the failure
  before the hook was added.
- **2026-08-15**: `skills/manage-issue/SKILL.md` was **not** added to
  `PACKAGE_DATA_ASSETS` as the Integration Map's wiring pass suggested. That
  manifest's completeness check (`list_missing_assets()`) asserts every entry is
  importlib-accessible in a *dev/editable* install, which `skills/` genuinely is
  not under Option A′ (it stays physically at the repo root; only the built wheel
  gets a copy). Registering it broke `test_package_data_manifest.py` in every
  editable checkout. Coverage for "did the wheel actually ship skills/" instead
  lives in the wheel-smoke integration tests, which build a real wheel rather than
  asserting against the editable source tree.
- Shared-resolver rework (`_find_plugin_root()`'s formula, its 15 other callers)
  remained out of scope per the issue's own Scope note — not touched.

### Verification Results
- Tests: PASS (`python -m pytest scripts/tests/` — 19296 passed, 46 skipped,
  0 failed; `PYTEST_INTEGRATION=1 python -m pytest scripts/tests/test_wheel_smoke.py`
  — 10/10 passed, including the new acceptance tests)
- Lint: PASS (`ruff check scripts/`)
- Format: PASS (`ruff format --check`)
- Types: PASS (`python -m mypy scripts/little_loops/` — no issues, 339 files)

## Status

**Open** | Created: 2026-08-15 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-15T05:54:36 - `d74d13f8-3dde-4769-b5ec-ae03310339a8.jsonl`
- `/ll:ready-issue` - 2026-08-15T05:06:20 - `53fca6d8-a7d5-4e43-85c6-ba7660175076.jsonl`
- `/ll:confidence-check` - 2026-08-15T03:54:19 - `49e15b7f-91ee-43ed-876b-a654ebdcd023.jsonl`
- `/ll:wire-issue` - 2026-08-15T03:47:54 - `b9fd5a8c-f315-4b0d-81b2-99082dc1958e.jsonl`
- `/ll:decide-issue` - 2026-08-15T03:36:50 - `2a5e59d9-4425-4f9d-8ab0-866c509b36cd.jsonl`
- `/ll:refine-issue` - 2026-08-15T03:32:03 - `d730c0cc-e383-42c2-b3ab-672713d72ffb.jsonl`
- `/ll:capture-issue` - 2026-08-15T03:27:53 - `d730c0cc-e383-42c2-b3ab-672713d72ffb.jsonl`
