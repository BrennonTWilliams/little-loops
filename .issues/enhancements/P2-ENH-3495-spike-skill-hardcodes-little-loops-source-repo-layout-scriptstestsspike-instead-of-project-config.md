---
id: ENH-3495
type: ENH
title: spike skill hardcodes little-loops source-repo layout (scripts/tests/spike)
  instead of project config
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-17'
captured_at: '2026-09-17T00:15:03Z'
completed_at: '2026-09-17T03:47:59Z'
decision_needed: false
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 25
---

# ENH-3495: spike skill hardcodes little-loops source-repo layout (scripts/tests/spike) instead of project config

## Summary

`/ll:spike` hardcodes the little-loops source-repo layout. Its `allowed-tools` frontmatter grants `Write(scripts/tests/spike/**)` / `Edit(scripts/tests/spike/**)`, its plan template and SKILL.md body place every spike package under `scripts/tests/spike/<slug>/`, and the promotion step targets `scripts/little_loops/spike/<slug>/`. Neither path exists in a consuming project, so in any project other than little-loops itself the skill writes into a directory the user never asked for, and its `allowed-tools` pre-approval never matches (interactive runs prompt on every spike write; automation runs under `--dangerously-skip-permissions` are unaffected).

## Context

Found 2026-09-16 during the docs-audience sweep (CONTRIBUTING.md § Documentation Audience). `docs/reference/COMMANDS.md` carries an `ll-audience-ok` suppression on the `/ll:spike` entry that should be removed when this lands. The skills-audience gate in `scripts/tests/test_docs_audience_gate.py` exempts `skills/spike/` by this issue ID; remove that exemption too.

## Current Behavior

- `skills/spike/SKILL.md` frontmatter: `Write(scripts/tests/spike/**)`, `Edit(scripts/tests/spike/**)`.
- SKILL.md body (Implementation, Spike location, Promotion, `--check` mode) and `skills/spike/plan-template.md` all name `scripts/tests/spike/<slug>/` and `scripts/little_loops/spike/<slug>/` literally.
- The regression-suite command `python -m pytest scripts/tests/<named-regression-suite>.py` assumes the source-repo test dir.

## Expected Behavior

Spike location derives from the consuming project's config: `project.test_dir` (or `tests/` when unset) joined with `spike/<slug>/`. Promotion is described as folding the proven code into its real home (the production module under `project.src_dir` and its test under `project.test_dir`) in a separate PR — there is no canonical promotion directory (see Review Findings). `allowed-tools` must still pre-approve writes only under the spike directory; since the frontmatter glob is static, either widen it to a config-independent shape (e.g. `Write(**/spike/**)`) or document that consuming projects override it via `.claude/settings` — decided below (Option A). The skill must run unchanged in a project whose layout is `src/` + `tests/`.

**Permission semantics (corrected 2026-09-17):** Claude Code's skill `allowed-tools` is a *pre-approval* list, not a fence. A write outside the granted globs prompts the user in interactive mode and is simply allowed under `--dangerously-skip-permissions` / `ll-auto`. Spike isolation is therefore enforced by convention plus the plan's mandatory regression-guard test, and the skill's prose must say so rather than claiming `allowed-tools` makes production files read-only.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

Expected Behavior leaves the `allowed-tools` static-glob resolution as an open decision ("decide during refinement"). Codebase research found no existing precedent for either branch in this repo — `skills/spike/SKILL.md` is the only skill whose `allowed-tools` targets a `scripts/tests/...`-shaped subpath at all, and no skill or command anywhere uses a widened prefix-free glob (`Write(**/foo/**)`); a project-local Claude Code settings override is not a checked-in file in this repo today. Both alternatives are genuinely novel here, not applications of an existing pattern.

**Option A**: Widen `allowed-tools` to a config-independent glob shape — `Write(**/spike/**)` / `Edit(**/spike/**)` — so the grant matches a `spike/<slug>/` directory regardless of where `project.test_dir` resolves in a given consuming project, with no per-project setup required.

> **Selected:** Option A — scores 10/12 vs. Option B's 4/12; satisfies AC3 out-of-the-box for any consuming-project layout with no new mechanism, and the `**/x/**` glob token is already idiomatic in this codebase (scan/exclude patterns) even though this is its first use in an `allowed-tools` grant.

**Recommended**: Option A — it satisfies Acceptance Criterion 3 ("`allowed-tools` still restricts writes to the spike directory in a `src/` + `tests/` project") for any consuming-project layout without requiring the user to configure anything first, whereas Option B pushes a manual setup burden onto every consuming project and has no existing mechanism in this repo to model it on.

**Option B**: Keep a project-specific static glob and document that consuming projects whose resolved `project.test_dir` differs from what ships by default must override the grant themselves via a project-local Claude Code settings override (not currently a checked-in file in this repo), since Claude Code's `allowed-tools` frontmatter cannot itself be dynamically parameterized by a config value resolved at skill-run time.

### Decision Rationale

**Selected:** Option A — widen `allowed-tools` to `Write(**/spike/**)` / `Edit(**/spike/**)`.

**Reasoning:** Option A satisfies AC3 for any consuming-project layout with zero per-project setup, reusing a glob token (`**/x/**`) already idiomatic in this codebase's scan/exclude configs even though this is its first appearance in a permission grant. Option B does not actually resolve the issue's core defect — it keeps a hardcoded, project-specific literal and requires every consuming project with a non-default `test_dir` to manually edit an uncommitted `.claude/settings*.json` before the skill works, which contradicts this codebase's documented zero-config design goal (`terminal_adapter.py`, ENH-2317, FEAT-1931) and has no existing precedent to model — no skill or command doc in this repo instructs users to hand-edit permissions for a skill to function.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 2/3 | 0/3 |
| Simplicity | 3/3 | 2/3 |
| Testability | 3/3 | 1/3 |
| Risk | 2/3 | 1/3 |
| **Total** | **10/12** | **4/12** |

**Key evidence:**
- No skill or command in this repo uses a prefix-free `Write(**/foo/**)`/`Edit(**/foo/**)` grant today, but the `**/x/**` shape itself is an established convention for scan/exclude patterns (`scripts/little_loops/config/features.py:346`, `config-schema.json:69,826`, every `templates/*.json` project type, `.ll/ll-config.json:20-24`). Claude Code's Read/Edit permission rules follow the gitignore spec, where a leading `**/` matches at any depth including the root; the skill's existing `Write(.ll/spikes/**)` grant is the local proof that cwd-relative `**` patterns are honored. (An earlier citation to `docs/claude-code/memory.md:201-206` was wrong — that table is the CLAUDE.md `paths:` frontmatter glob syntax, not permission rules; see Review Findings #10.)
- The collision risk noted for Option A — `**/spike/**` could in principle match an unrelated top-level `spike/` directory a consuming-project user creates, or a `node_modules/spike/**` path — is real but narrow (bounded to directories literally named `spike`) and has no existing precedent either confirming or ruling it out, since no prior `allowed-tools` grant has used this shape. Because `allowed-tools` only pre-approves (it never blocks; see Expected Behavior), the over-grant is low-stakes: it saves a prompt on a path the model should not be writing to anyway, and the regression-guard test remains the real isolation check.
- No committed `.claude/settings*.json` file exists anywhere in this repo (`.gitignore:59` keeps it out of version control), and the only "hand-edit settings.json" precedent in little-loops' own docs (`README.md:90`) is a narrowly-scoped plugin-install fallback, not a skill-functionality permission-scoping mechanism — undermining Option B's premise that consuming projects have an established, documented path to do this.
- Every other instance of permission entries entering `.claude/settings*.json` in this codebase is automation-written by `ll-init`/`ll-adapt` (`docs/guides/GETTING_STARTED.md:84,103`, `docs/reference/CLI.md:52`, FEAT-749, ENH-1846, BUG-2042), never doc-instructed manual user action — Option B would be the first case of the latter.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

Confirmed literal-path and convention findings from `codebase-locator`, `codebase-analyzer`, and `codebase-pattern-finder`, grouped below.

### Files to Modify
- `skills/spike/SKILL.md` — `allowed-tools` `Write(scripts/tests/spike/**)`/`Edit(scripts/tests/spike/**)` (lines 10, 12) plus the body references to `scripts/tests/spike/`/`scripts/little_loops/spike/` need to resolve from `project.test_dir`. **Do not trust the line-number inventory** — the authoritative list is the audience gate's own scan, which reports 17 hits in `SKILL.md` (lines 10, 12, 137, 138, 156, 161, 172, 174, 175, 185×2, 186×2, 213, 215, 253, 254×2 — note lines 141/146/149 cited earlier are `.ll/spikes/` references, not literals) and 10 in `plan-template.md` (lines 39, 44, 46, 49, 76×2, 77×2, 89×2). The `source-tree-tool-cmd` marker (`pytest scripts…`) fires on 185/186/254 in addition to `source-tree-test-path`; the same `"$SPIKE_DIR"` substitution clears both. Iterate until the scan returns empty:
  ```python
  from test_docs_audience_gate import scan_audience, HARNESS_MARKERS
  scan_audience(Path("skills/spike/SKILL.md").read_text(), HARNESS_MARKERS)  # must be []
  ```
- `skills/spike/plan-template.md` — 10 marker hits (see above).
- `skills/spike/SKILL.md` `allowed-tools` — add `Bash(ll-config:*)` (the new `ll-config get` calls are otherwise ungranted and every interactive run prompts at the first path-resolution step; no skill grants it today, including `go-no-go`, which has the same latent gap) and `Bash(mkdir:*)` (the existing Phase 3 `mkdir -p .ll/spikes/` is ungranted today — pre-existing gap, close it in the same edit).
- `scripts/tests/test_docs_audience_gate.py` — remove the `HARNESS_EXEMPT` entry at line 38 and update `test_exempt_prefix_excluded` (lines 189-192), which currently hard-asserts `skills/spike/` files are excluded from the audience scan; that assertion inverts once the exemption is removed.
- `docs/reference/COMMANDS.md` — remove the `ll-audience-ok` suppression comment at line 378.

_Wiring pass added by `/ll:wire-issue`:_
- `.ll/ll-config.json` — add `"test_dir": "scripts/tests/"` alongside the existing `"src_dir": "scripts/"` entry. Without this, `ll-config get project.test_dir` in this repo resolves to the schema default `"tests"` (not `scripts/tests/`, where spikes actually live and where `project.test_cmd` already points), silently relocating this repo's own future spikes the moment the dynamic resolution lands.
- `skills/spike/SKILL.md` — two literal sites outside the original 12-line inventory, both untouched by the `SPIKE_DIR`/`PROMOTE_DIR` substitution in Program Design: (1) lines 137-138 cite `scripts/little_loops/cli/loop/run.py` and `scripts/little_loops/fsm/executor.py` in Call Path prose — once the `skills/spike` audience-gate exemption below is removed, these trip the `source-tree-module-path` HARNESS_MARKER and must become dotted-module form (`little_loops.cli.loop.run`, `little_loops.fsm.executor`), the gate's own stated convention; (2) line 186's regression-suite command (`python -m pytest scripts/tests/<named-regression-suite>.py -v`) is the literal the issue's own Current Behavior section calls out but the Program Design Call Path never assigns a resolution to — it needs the same `${TEST_DIR%/}`-based substitution as `SPIKE_DIR`, not a `SRC_DIR`-based one.
- `skills/spike/plan-template.md` — line 77 carries the identical uncovered regression-suite literal as `SKILL.md:186`.

### Dependent Files (Callers/Importers)
- `.gemini/skills/spike/SKILL.md`, `.gemini/skills/spike/plan-template.md`, `.kimi-code/skills/spike/SKILL.md`, `.kimi-code/skills/spike/plan-template.md`, `.qwen/skills/spike/SKILL.md`, `.qwen/skills/spike/plan-template.md` — host-adapter mirrors of `skills/spike/`, synced via `ll-adapt --host <name> --apply`; carry the identical hardcoded literals today and will drift out of sync with the fixed source unless re-synced after this lands.
- `scripts/tests/test_spike_skill.py::test_spike_code_confined_to_tests_dir` — asserts `"scripts/tests/spike/" in _plan_text()` via raw substring match; this is the test currently pinning the hardcoded literal this issue changes and needs updating alongside the fix.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/spike-gate.yaml:51,63` — comments cite exact `SKILL.md:190,199` / `SKILL.md:221-234` line numbers for the write-back phase; these will drift once `SKILL.md`'s body is edited and should be re-pointed after this issue lands.

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md:379` — the `/ll:spike` entry's "Flow" prose sentence itself (not just the `ll-audience-ok` suppression comment on line 378) states the literal `scripts/tests/spike/`/`scripts/little_loops/` paths three times. Deleting only the line-378 comment without rewriting line 379 to describe the config-derived resolution will make `test_user_docs_are_end_user_facing` fail on this line the moment the suppression is gone.

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_spike_skill.py::test_promotion_path_documented` (lines 83-85) — asserts `"scripts/little_loops/spike/" in _plan_text()`; a second test pinning the exact literal this issue removes, alongside `test_spike_code_confined_to_tests_dir` above. Rewrite it to assert the new Promotion wording (fold into the production module + its test, separate PR) rather than any path, since there is no promotion directory (see Review Findings).
- `scripts/tests/test_spike_skill.py` — new test needed asserting the widened `Write(**/spike/**)`/`Edit(**/spike/**)` grants are present in `SKILL_FILE`, mirroring the existing `test_allowed_tools_grants_ll_spikes_write` pattern (`skills/spike/SKILL.md` line ~130 equivalent).
- `scripts/tests/test_docs_audience_gate.py` — new regression-guard test recommended, mirroring `test_general_task_and_rl_coding_agent_are_not_exempt` in `test_bug3269_test_cmd_resolution_gate.py`: assert `"skills/spike" not in HARNESS_EXEMPT` so the exemption cannot silently reappear once this issue closes.

### Conventions in Force
- This codebase resolves config values inside a markdown skill's bash body via the `ll-config get <key>` CLI (wrapping `BRConfig.resolve_variable()`), not by hand-parsing `.ll/ll-config.json` — established by ENH-2678, whose stated rationale is "config is read only in Python, never in markdown skills." The only existing call site is `skills/go-no-go/SKILL.md:154` (`PENALTY=$(ll-config get history.go_no_go.correction_penalty)`).
- The `{{config.project.src_dir}}`/`{{config.project.test_dir}}` template-token syntax used elsewhere in `commands/*.md` and some `skills/*/SKILL.md` prose is not usable here: it only expands under `ll-auto`'s `skill_expander.py` pre-expansion pass (frontmatter is stripped before expansion runs, and interactive/slash-command invocation never triggers it at all) — `scripts/little_loops/skill_expander.py:126-165`, `docs/reference/CLI.md:598`, `docs/reference/API.md:5170`.
- No skill or command in this codebase uses a widened, config-independent `allowed-tools` glob shape (e.g. `Write(**/spike/**)`) — confirmed absent by a repo-wide search. `skills/spike/SKILL.md` is the only skill whose `allowed-tools` targets a `scripts/tests/...`-shaped subpath at all; there is no existing precedent for either resolution named in Expected Behavior.
- No hardcode-detection gate covers `skills/` or `commands/` for `scripts/tests`/`scripts/little_loops` literals — `test_builtin_loop_hardcode_gate.py` is scoped only to `scripts/little_loops/loops/**/*.yaml` (its `BUILTIN_LOOPS_DIR` constant). A regression here would not be caught by any existing automated check.

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `skills/spike/SKILL.md` | Hardcoded `scripts/tests/spike/<slug>/` and `scripts/little_loops/spike/<slug>/` literals for spike location and promotion target | CHANGED | Replaced by `<test_dir>/spike/<slug>/` resolved via `ll-config get project.test_dir`; the promotion-directory literal is dropped entirely (see Review Findings #2), not replaced 1:1. |
| `docs/reference/COMMANDS.md` | `ll-audience-ok` suppression comment on the `/ll:spike` entry (line 378) plus its "Flow" prose naming the literal `scripts/tests/spike/`/`scripts/little_loops/` paths (line 379) | DROPPED | The suppression is removed once the underlying literals it exempts are gone; the Flow prose is rewritten to describe config-derived resolution rather than deleted outright. |
| `scripts/little_loops/cli/loop/run.py` | Cited by its filesystem path in `SKILL.md`'s Call Path prose (lines 137-138) | CHANGED | Rewritten to dotted-module form `little_loops.cli.loop.run`, since the filesystem-path literal trips the audience gate's `source-tree-module-path` marker once the `skills/spike/` exemption is removed. |
| `scripts/little_loops/fsm/executor.py` | Cited by its filesystem path in `SKILL.md`'s Call Path prose (lines 137-138) | CHANGED | Rewritten to dotted-module form `little_loops.fsm.executor`, same rationale as `cli/loop/run.py` above. |
| `scripts/tests/test_docs_audience_gate.py` | `HARNESS_EXEMPT` entry excluding `skills/spike/` from the audience scan (line 38), and the `test_exempt_prefix_excluded` assertion that depends on it (lines 189-192) | DROPPED | Exemption entry removed and the dependent assertion inverted, now that `skills/spike/` must pass the same audience scan as every other skill. |

## Program Design

### Types

- `SPIKE_DIR: str` (bash var, `<test_dir>/spike/<slug>`)
- ~~`PROMOTE_DIR: str` (bash var, `<src_dir>/spike/<slug>`)~~ — **dropped** (see Review Findings: no promotion directory exists or has ever existed; promotion prose names `project.src_dir`/`project.test_dir` descriptively, no variable needed)

### Signatures

- `BRConfig.resolve_variable(self, var_path: str) -> str | None` — existing,
  `scripts/little_loops/config/core.py:1108`; backs the `ll-config get
  project.test_dir` / `ll-config get project.src_dir` CLI already exercised
  from bash elsewhere (`scripts/little_loops/cli/config.py`)
- `BRConfig.get_src_path(self) -> Path` — existing,
  `scripts/little_loops/config/core.py:606`

### Call Path

`skills/spike/SKILL.md` new "Phase 0: Resolve layout" block (before Phase 3;
single resolution point, see Wiring second pass) -> `ll-config get
project.test_dir` -> `BRConfig.resolve_variable("project.test_dir")` ->
`: "${TEST_DIR:=tests}"` -> `SPIKE_DIR="${TEST_DIR%/}/spike/<slug>"` (replaces
the literal `scripts/tests/spike/<slug>/`); Phase 3 (Plan), Phase 4
(Implement), Phase 5 (Verify), and Check Mode reference `$SPIKE_DIR` without
re-resolving. Phase 6 (Promotion) becomes prose only:
"promote the proven code into its production module under `project.src_dir`
and its test under `project.test_dir`, in a separate PR" — no `ll-config get
project.src_dir` call and no `PROMOTE_DIR` (superseded; see Review Findings).
`skills/spike/plan-template.md` follows the same substitution for its
`Critical files` and `Implementation` sections and the same prose rewrite for
`Promotion`. Note: this
repo's own `.ll/ll-config.json` does not set `project.test_dir`, so it
currently resolves to the schema default `"tests"`, not the actual
`scripts/tests/` root — implementation should confirm whether that also
needs setting here, or whether the skill falls back to a
`pytest.ini`/`pyproject.toml` probe when `project.test_dir` is absent.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

`BRConfig.resolve_variable("project.test_dir")` never returns `None` for this key: `ProjectConfig.from_dict()` (`scripts/little_loops/config/core.py:239-240`) defaults `test_dir` to `"tests"` and `src_dir` to `"src/"` when absent from `.ll/ll-config.json`, and `to_dict()` (`core.py:763-766`) always materializes both keys before `resolve_variable`'s dict-walk runs. This resolves the open question in the Call Path note above: no `pytest.ini`/`pyproject.toml` probe fallback is needed — the method's contract guarantees a non-empty string.

> ⚠ Superseded — one gap remains: `ll-config get` (`main_config()`, `scripts/little_loops/cli/config.py:54-87`) never raises and exits 0 even when `BRConfig(Path.cwd())` construction itself fails — that path prints nothing on stdout *or* stderr. A naive `TEST_DIR=$(ll-config get project.test_dir); SPIKE_DIR="${TEST_DIR%/}/spike/<slug>"` would then silently resolve to `/spike/<slug>` (filesystem-root-anchored) rather than erroring. Implementation must guard the capture — e.g. `: "${TEST_DIR:=tests}"` — before building `SPIKE_DIR`/`PROMOTE_DIR`. _(Added by `/ll:wire-issue`.)_

This repo's own `.ll/ll-config.json` sets `project.src_dir: "scripts/"` but does not set `project.test_dir`, so `ll-config get project.test_dir` resolves to the schema default `"tests"` here today — not `scripts/tests/`, where spike packages actually live and where this repo's own `project.test_cmd` (`python -m pytest scripts/tests/`) points. Implementing the fix as a literal `project.test_dir` + `spike/<slug>` join, without also adding `"test_dir": "scripts/tests/"` to this repo's own `.ll/ll-config.json` (mirroring the existing explicit `src_dir` entry), would silently relocate this repo's own future spikes to `tests/spike/<slug>/`, diverging from every prior spike under `scripts/tests/spike/` and from `test_spike_code_confined_to_tests_dir`'s current assumption.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `"test_dir": "scripts/tests/"` to `.ll/ll-config.json`'s `project` block.
- Rewrite `skills/spike/SKILL.md:137-138` to cite `little_loops.cli.loop.run` / `little_loops.fsm.executor` (dotted-module form) instead of `scripts/little_loops/...` paths.
- Resolve `skills/spike/SKILL.md:186` and `plan-template.md:77`'s regression-suite command through the same `${TEST_DIR%/}` substitution as `SPIKE_DIR`.
- Guard the `TEST_DIR` bash capture against an empty value (`ll-config get` prints nothing, exit 0, on a `BRConfig` construction failure): `: "${TEST_DIR:=tests}"` before building `SPIKE_DIR`.
- Rewrite `docs/reference/COMMANDS.md:379`'s "Flow" prose to describe config-derived resolution, not just delete the line-378 suppression comment.
- Update `scripts/tests/test_spike_skill.py::test_promotion_path_documented` alongside `test_spike_code_confined_to_tests_dir` (assert wording, not a path).
- Add a new `test_spike_skill.py` case asserting the widened `Write(**/spike/**)`/`Edit(**/spike/**)` grants and the new `Bash(ll-config:*)` grant.
- Add a new `test_docs_audience_gate.py` case asserting `"skills/spike" not in HARNESS_EXEMPT` (non-regression guard).
- Re-point the `SKILL.md:190,199` / `SKILL.md:221-234` line-number citations in `scripts/little_loops/loops/spike-gate.yaml:51,63` after `SKILL.md`'s body shifts.

_Added by review — 2026-09-17:_
- Add `Bash(ll-config:*)` and `Bash(mkdir:*)` to `skills/spike/SKILL.md` `allowed-tools` (see Files to Modify).
- Rewrite the "enforced by `allowed-tools`" / "production files are read-only" prose at `SKILL.md:174-175`, `plan-template.md:46`, and `docs/reference/COMMANDS.md:379` to: `allowed-tools` pre-approves writes only under `<test_dir>/spike/`; isolation is enforced by the plan's mandatory regression-guard test.
- Drop the promotion directory entirely: rewrite `SKILL.md:161,215` and `plan-template.md:86-91` (`## Promotion`) to "promote into the production module under `project.src_dir` and its test under `project.test_dir`, separate PR".
- `scripts/little_loops/init/introspect.py:729-733` — extend the existing `tests/`/`test/` probe to also set `project.test_dir` in the generated config (today it only feeds `focus_dirs`). Without this, a consuming project laid out as `test/` resolves the schema default `tests` and spikes land in a directory that does not exist. Add a unit test for the detection in the init test module. Shape: a sibling `_introspect_test_dir()` returning its own `IntrospectedValue` with provenance, stored as `values["project.test_dir"]` next to `src_dir` at `introspect.py:175` — not a side effect inside `_introspect_focus_dirs`.
- **`ll-init` plumbing beyond `introspect.py` (Review Findings #7).** An introspected `project.test_dir` lands in `choices["test_dir"]` via `_flat_key` (`init/proposal.py:274-276`) and then dies; three more sites must learn the key:
  - `init/core.py:326-337` — `build_config` copies a fixed list of project keys into the config (`src_dir`, `test_cmd`, `lint_cmd`, `format_cmd`, `type_cmd`, `build_cmd`); add `test_dir`.
  - `init/proposal.py:32` (`_PROJECT_FIELDS`), `:34-41` (`_PROJECT_FIELD_LABELS`), and `:287` (existing-config preservation loop) — all omit `test_dir`, so today a re-run of `ll-init` silently drops a hand-set `test_dir`. Add it to all three; the unit test must cover the re-run/preservation case.
  - `init/tui.py:1059` — the TUI `build_config` call passes only `src_dir`; thread `test_dir` through.
- Re-sync the host mirrors after editing `skills/spike/`: `ll-adapt --host gemini --apply`, `ll-adapt --host kimi-code --apply`, `ll-adapt --host qwen --apply`. The mirror gates fail otherwise.
- Run the audience-gate scan (snippet under Files to Modify) on both skill files until it returns `[]` before removing the `HARNESS_EXEMPT` entry.

_Added by review — 2026-09-16 (second pass):_
- Resolve the layout **once**, in a single bash block placed before Phase 3 (e.g. a "Phase 0: Resolve layout" step), and reference `$SPIKE_DIR` from Phase 3, Phase 4, Phase 5, and Check Mode. The Call Path above names Phase 3 and Phase 4 as separate resolution points and omits Check Mode (`SKILL.md:253-254`), which invites drift across three bash blocks. Block shape:
  ```bash
  TEST_DIR=$(ll-config get project.test_dir); : "${TEST_DIR:=tests}"
  SPIKE_DIR="${TEST_DIR%/}/spike/<slug>"
  ```
- Declare the skill **Python/pytest-only** in its `description`/intro and in Scope Boundaries (Review Findings #8). Do **not** route the Verification commands through `project.test_cmd`.
- Keep the existing `Write(.ll/spikes/**)` and `Edit(.issues/**)` grants; AC3 is reworded accordingly (Review Findings #9).
- Fix the glob-validity citation (Review Findings #10): cite the gitignore-spec rule for Read/Edit permission patterns and the existing `Write(.ll/spikes/**)` grant as the local proof, not `docs/claude-code/memory.md`.

## Review Findings

_Added 2026-09-17 by pre-implementation review; each claim verified against the working tree._

1. **`allowed-tools` never blocks.** The Summary's original "blocked by its own permission glob" was wrong: skill `allowed-tools` pre-approves; an unmatched write prompts in interactive mode and is allowed outright in automation. This lowers the stakes of Option A's `**/spike/**` over-grant (it also matches `<src_dir>/spike/**`) to "one skipped prompt", and it means the "read-only, enforced by `allowed-tools`" prose in the skill, template, and `COMMANDS.md` was always overstated. Rewrite it; keep Option A.
2. **The promotion directory is a fiction.** `scripts/little_loops/spike/` has never existed in this repo's git history (`git log --all -- scripts/little_loops/spike` is empty). Every real promotion folded the spike's assertions into the actual module and test file — see the module docstrings of `scripts/tests/test_terminal_adapter.py`, `test_program_design_gate.py`, and `test_session_discovery.py`. The proposed `<src_dir>/spike/<slug>/` substitution would also resolve to `scripts/spike/` here, since `project.src_dir` is `scripts/`, not the package root. Hence `PROMOTE_DIR` is dropped and Promotion becomes prose.
3. **`Bash(ll-config:*)` is ungranted.** The plan's new `ll-config get` call has no pre-approval in the skill's `allowed-tools`; no skill grants it today. Added to Wiring.
4. **`ll-init` never sets `project.test_dir`.** `init/introspect.py:729-733` probes `tests/`/`test/` only for `focus_dirs`; `.ll/ll-config.json` in a consuming project therefore never carries `test_dir`, and the schema default `tests` is silently wrong for `test/` layouts. Small in-scope fix added to Wiring (the probe already exists).
5. **Line-number inventory was partly wrong.** Lines 141/146/149 of `SKILL.md` are `.ll/spikes/` references, not source-repo literals; the gate scan is authoritative (17 + 10 hits). Recorded under Files to Modify.
6. **Confirmed as stated:** `ll-config get` exits 0 and prints nothing on a `BRConfig` failure (`cli/config.py:66-69`), so the `${TEST_DIR:=tests}` guard is required; adding `test_dir: "scripts/tests/"` to this repo's config is safe — the only Python consumer is the leak-detection prefix list in `parallel/worker_pool.py:1505`, where it is benign (the trailing slash is handled by `${TEST_DIR%/}`); `**/` gitignore-style globs are valid in Claude Code permission rules (see #10 for the corrected evidence).

_Second pass — 2026-09-16, verified against HEAD 805014f2a:_

7. **The `ll-init` test_dir wiring was incomplete.** Extending `introspect.py` alone never emits `test_dir` into the generated config: `build_config` (`init/core.py:326-337`) copies a fixed key list, `_PROJECT_FIELDS`/`_PROJECT_FIELD_LABELS`/the existing-config preservation loop (`init/proposal.py:32,34-41,287`) omit it — so today a re-run of `ll-init` silently drops a hand-set `test_dir` — and the TUI path (`init/tui.py:1059`) passes only `src_dir`. All four files are now in Wiring; the unit test must cover the re-run/preservation case.
8. **The pytest/Python toolchain hardcode is untouched and stays that way.** `python -m pytest` in Phase 5, Check Mode, and the plan template's Verification, the `Bash(python -m pytest:*)` grant, and the `__init__.py`/AST-sniff conventions are all Python-specific. The fix removes the *path* axis only. Routing Verification through `project.test_cmd` was considered and rejected: that value usually already embeds a path (this repo: `python -m pytest scripts/tests/`), so appending `$SPIKE_DIR` would run the whole suite. Decision: declare the skill Python/pytest-only explicitly (description + Scope Boundaries) rather than imply it runs unchanged in a project of any language. The audience gate's `source-tree-tool-cmd` marker (`(pytest|ruff …|mypy) scripts\b`) does not fire on `python -m pytest "$SPIKE_DIR"`, so no gate change is needed.
9. **AC3 was literally false as written.** "Pre-approves writes only under the spike directory" ignored the `Write(.ll/spikes/**)` and `Edit(.issues/**)` grants that must remain (plan doc and issue write-back). AC3 is reworded to enumerate the permitted grant set.
10. **Wrong evidence citation for the `**/` glob claim.** Key evidence and #6 cited `docs/claude-code/memory.md:201-206`, which is the CLAUDE.md `paths:` frontmatter glob table, not permission-rule syntax; the repo mirrors no permissions page under `docs/claude-code/`. The claim itself holds: Claude Code's Read/Edit permission rules follow the gitignore spec, where a leading `**/` matches at any depth including the root, and the skill's existing `Write(.ll/spikes/**)` grant is the local proof that cwd-relative `**` patterns work. Cite those instead.
11. **Confirmed benign, no action:** the gemini/kimi-code/qwen adapters pass `allowed-tools` through verbatim (`adapters/codex.py:140-143`; `.gemini/skills/spike/SKILL.md` carries the identical block), so `**/spike/**` mirrors cleanly via `ll-adapt --apply`.

## Scope Boundaries

- **In scope**: deriving the spike directory from `project.test_dir` in
  `skills/spike/SKILL.md` and `skills/spike/plan-template.md`, and rewriting
  Promotion as prose that names `project.src_dir`/`project.test_dir`; widening
  the `allowed-tools` glob (Option A) and adding the `Bash(ll-config:*)` /
  `Bash(mkdir:*)` grants; correcting the "read-only, enforced by
  `allowed-tools`" prose; teaching `ll-init` introspection to set
  `project.test_dir`; removing the `skills/spike/` exemption in
  `test_docs_audience_gate.py` and the `ll-audience-ok` suppression in
  `docs/reference/COMMANDS.md`; re-syncing the gemini/kimi-code/qwen mirrors;
  plumbing `test_dir` through `init/core.py`, `init/proposal.py`, and
  `init/tui.py` so the introspected value actually reaches the generated
  config and survives an `ll-init` re-run; stating explicitly in the skill
  that it is Python/pytest-only.
- **Out of scope**: making the skill toolchain-agnostic — `python -m pytest`,
  the `Bash(python -m pytest:*)` grant, `__init__.py` packages, and the
  AST-sniff regression guard remain Python-specific by decision (Review
  Findings #8); resolving Verification commands via `project.test_cmd`;
  changing the spike plan's required section shape
  (`plan-template.md`'s Context/Approach/Acceptance Criteria structure);
  changes to `/ll:explore-api` (the external-API analogue); migrating any
  spike artifacts already committed under `scripts/tests/spike/` in this
  repo.

## Impact

- **Priority**: P2 - functional-correctness/portability bug (not a crash):
  `/ll:spike` is unusable as shipped in any consuming project whose layout
  isn't `scripts/`, so it blocks a whole skill outside the source repo.
- **Effort**: Small-to-Medium - text/template substitution in two files
  (`SKILL.md`, `plan-template.md`), removing two doc-audience exemptions,
  a small `test_dir` detection in `init/introspect.py` plumbed through
  `init/core.py`, `init/proposal.py`, and `init/tui.py` with unit tests,
  and a mirror re-sync; reuses the existing `ll-config get` CLI pattern
  (`skills/go-no-go/SKILL.md:154`), no new mechanism needed.
- **Risk**: Low - the spike directory stays isolated under
  `<test_dir>/spike/<slug>/` either way; the only behavior change is which
  literal path is written to, verified by re-running the skill in both the
  `scripts/`-layout source repo and a `src/`+`tests/` fixture project.
- **Breaking Change**: No - existing spike artifacts already committed under
  `scripts/tests/spike/` are untouched; only future `/ll:spike` invocations
  resolve their path dynamically.

## Acceptance Criteria

- [ ] `skills/spike/SKILL.md` and `plan-template.md` contain no `scripts/tests` or `scripts/little_loops` literals (the `HARNESS_MARKERS` scan returns `[]` for both files).
- [ ] Spike dir resolves from `project.test_dir` (guarded default `tests`) as `<test_dir>/spike/<slug>/`; Promotion prose names `project.src_dir`/`project.test_dir` and no promotion directory.
- [ ] `allowed-tools` carries no `Write`/`Edit` grant outside `**/spike/**`, `.ll/spikes/**`, and `.issues/**` (so in a `src/` + `tests/` project spike code is pre-approved only under `tests/spike/`), and grants `Bash(ll-config:*)` and `Bash(mkdir:*)`; the skill, template, and `COMMANDS.md` no longer claim `allowed-tools` makes production files read-only.
- [ ] The layout is resolved in one bash block before Phase 3 (`TEST_DIR` guarded to `tests`, `SPIKE_DIR` derived) and Phases 3–5 and Check Mode all reference `$SPIKE_DIR` rather than re-resolving.
- [ ] The skill's description/intro and `COMMANDS.md` entry state it is Python/pytest-only.
- [ ] `ll-init` introspection sets `project.test_dir` from a detected `tests/` or `test/` directory, the value is emitted by `build_config` (`init/core.py`) and the TUI path, and an existing `test_dir` survives an `ll-init` re-run (`init/proposal.py`) — each covered by a unit test.
- [ ] The `skills/spike/` exemption in `test_docs_audience_gate.py` and the `ll-audience-ok` line in `docs/reference/COMMANDS.md` are removed, with a non-regression guard on `HARNESS_EXEMPT`.
- [ ] `.gemini/`, `.kimi-code/`, and `.qwen/` spike mirrors are re-synced and the mirror gates pass.

## Resolution

- **Action**: improve
- **Completed**: 2026-09-17
- **Status**: Completed

### Changes Made
- `skills/spike/SKILL.md`: added `Bash(ll-config:*)`/`Bash(mkdir:*)` grants, widened `Write`/`Edit` to `**/spike/**`, added a "Phase 0: Resolve Layout" block deriving `$SPIKE_DIR` from `project.test_dir` (guarded to `tests`), rewrote Phase 3/4/5/6/Check Mode to reference `$SPIKE_DIR`/`$TEST_DIR` instead of the literal `scripts/tests/spike/`, dropped the promotion-directory literal in favor of prose naming `project.src_dir`/`project.test_dir`, corrected the "read-only, enforced by `allowed-tools`" overclaim, converted the Call Path file citations to dotted-module form, and declared the skill Python/pytest-only.
- `skills/spike/plan-template.md`: mirrored the same `<test_dir>/spike/<slug>/` substitution and Promotion-as-prose rewrite.
- `docs/reference/COMMANDS.md`: removed the `ll-audience-ok` suppression and rewrote the `/ll:spike` Flow prose to describe config-derived resolution.
- `scripts/tests/test_docs_audience_gate.py`: cleared `HARNESS_EXEMPT`, replaced the exemption assertion with a non-regression guard (`test_spike_skill_is_not_exempt`) plus `test_no_exemptions_registered`.
- `scripts/little_loops/init/introspect.py`: added `_introspect_test_dir()`, wired into `introspect()` as `values["project.test_dir"]`.
- `scripts/little_loops/init/core.py`: `build_config` now emits `project.test_dir` when present in choices.
- `scripts/little_loops/init/proposal.py`: added `test_dir` to `_PROJECT_FIELDS`, `_PROJECT_FIELD_LABELS`, and the existing-config preservation loop.
- `scripts/little_loops/init/tui.py`: added `test_dir` to `WizardAnswers`, seeded it in `_answers_from_proposal`, and threaded it through `_build_final_config` into `build_config`'s choices dict.
- `.ll/ll-config.json`: added `"test_dir": "scripts/tests/"` alongside the existing `src_dir` entry, matching this repo's actual spike location.
- `scripts/little_loops/loops/spike-gate.yaml`: re-pointed the `SKILL.md` line-number citations after the body shifted.
- `scripts/tests/test_spike_skill.py`: updated the two tests pinning the old hardcoded literals; added `TestSpikeSkillLayoutPortability` covering the widened grants, the new `Bash` grants, the absence of any `scripts/tests`/`scripts/little_loops` literal, and the Python/pytest-only declaration.
- `scripts/tests/test_init_introspect.py`, `test_init_core.py`, `test_init_proposal.py`, `test_init_tui.py`: added unit tests for test_dir detection, `build_config` emission, existing-config survival across re-init, and TUI threading.
- `.gemini/`, `.kimi-code/`, `.qwen/` spike mirrors: re-synced via `ll-adapt --host <name> --apply`.

### Verification Results
- Tests: PASS (full suite: 24900 passed, 51 skipped, 1 pre-existing unrelated failure — `test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence` flags an evidence citation in `P2-BUG-3484-*.md`, a file untouched by this issue)
- Lint: PASS
- Types: PASS
- Run: N/A (skill/config change, no server process)
- Integration: PASS (audience-gate scan returns `[]` for both `SKILL.md` and `plan-template.md`; mirrors re-synced; `ll-config get project.test_dir` resolves `scripts/tests/` in this repo)

## Status

**Open** | Created: 2026-09-17 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-09-17T03:47:59 - `6b6d66b2-acbe-43ad-9d98-9a834b171aa5.jsonl`
- `/ll:format-issue` - 2026-09-17T02:07:43 - `48770689-552c-4834-aa6a-4bcbb2a0f9c6.jsonl`
- `/ll:confidence-check` - 2026-09-17T01:41:57 - `43a75e43-d004-403c-835f-a3d1eaae553d.jsonl`
- `/ll:wire-issue` - 2026-09-17T01:12:06 - `86a9c74b-9864-4b0f-956c-f789b6eb77ab.jsonl`
- `/ll:decide-issue` - 2026-09-17T00:55:55 - `8e7ed6a7-45f1-4830-9b8d-ec6405748b84.jsonl`
- `/ll:refine-issue` - 2026-09-17T00:46:42 - `a247e656-a04b-48d2-b369-8647c50460db.jsonl`
- `/ll:format-issue` - 2026-09-17T00:37:18 - `2b860fe0-3e33-4473-a957-2f06e4ff45f0.jsonl`
