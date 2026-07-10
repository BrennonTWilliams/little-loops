---
id: ENH-2590
title: Wire `.pre-commit-config.yaml` repo-local hook for `.ll/decisions.yaml`
type: ENH
status: done
priority: P2
parent: ENH-2587
discovered_date: '2026-07-10'
discovered_by: user-report
captured_at: '2026-07-10T22:15:00Z'
completed_at: '2026-07-10T23:20:12Z'
decision_needed: false
learning_tests_required:
- pyyaml
- pre-commit
labels:
- decisions
- data-integrity
- tooling
- pre-commit
- git
size: Small
confidence_score: 90
outcome_confidence: 81
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 21
---

# ENH-2590: Wire `.pre-commit-config.yaml` repo-local hook for `.ll/decisions.yaml`

## Summary

Wire the `ll-verify-decisions` CLI (from ENH-2589) into a `.pre-commit-config.yaml`
`repo: local` hook scoped to `.ll/decisions.yaml`. Fires on `git commit`; does
NOT catch `--no-verify` or non-hook edit paths (those are covered by ENH-2591
pytest CI gate and ENH-2592 Claude Code host hook).

This child ships **one** of three transport layers around the parent validator —
the git-side hook. It is **independently testable** as a subprocess that runs
`pre-commit run --files .ll/decisions.yaml` against a known-good and known-bad
fixture pair.

## Current Behavior

`.ll/decisions.yaml` has **no load-time validation at commit time**. A malformed
file (e.g., the OTHE-203 unterminated-quote fixture — `rationale: "abc "" def"`)
is silently accepted by `git commit` and only fails later, when a downstream
consumer (`ll-issues decisions`, `sync_to_local_md`, etc.) attempts to parse
it. The corruption-class bug reaches `main`, where it breaks any tooling that
reads the decisions log on first load.

## Expected Behavior

After ENH-2590 ships, `git commit` invokes `ll-verify-decisions` (from
ENH-2589) against staged changes to `.ll/decisions.yaml` via a `repo: local`
hook in `.pre-commit-config.yaml`:

- Clean file → exit 0 (commit proceeds)
- Corrupted file → exit 1 (commit blocked by pre-commit framework with the
  validator's stderr error message)

`--no-verify` still bypasses the hook — that gap is closed by the **pytest CI
gate (ENH-2591)** as a belt-and-suspenders, and by the **Claude Code PreToolUse
hook (ENH-2592)** for in-session edits.

## Impact

Prevents OTHE-class corruption in `.ll/decisions.yaml` from reaching `main`
via the most common edit path (`git commit`). Combined with ENH-2589 (the
validator CLI), ENH-2591 (the pytest CI belt), and ENH-2592 (the Claude Code
host hook), this completes the three-transport-layer guard the parent epic
ENH-2587 set out to deliver. The validator's correctness is independently
gated by the OTHE-203 regression tests under `scripts/tests/test_decisions.py`
and `scripts/tests/test_verify_decisions.py`; the pre-commit hook's plumbing
is independently gated by a new skip-tolerant pytest test (AC 5).

## Status

`open` (P2). Dependency **ENH-2589 (done 2026-07-10)** is satisfied. Blocks
nothing; siblings ENH-2591 (pytest CI gate) and ENH-2592 (Claude Code host
hook) are independently runnable.

## Parent Issue

Decomposed from ENH-2587: "Guard `.ll/decisions.yaml` with a load-time validation
check on commit/CI"

## Why This Child Exists Standalone

`pre-commit` `repo: local` hooks are their own testable subsystem. This child
verifies the hook *configuration* (path-regex match, language, entry binary
exists) by invoking `pre-commit run` against fixtures in `tmp_path`. The
validator's correctness is independently verified by ENH-2589.

## Acceptance Criteria

- `.pre-commit-config.yaml` contains a `repo: local` hook with:
  - `language: system`
  - `entry: ll-verify-decisions`
  - `files: ^\.ll/decisions\.yaml$`
- `pre-commit run --files .ll/decisions.yaml` exits non-zero when the file is
  corrupted (OTHE-203 fixture).
- `pre-commit run --files .ll/decisions.yaml` exits 0 when the file is valid.
- The hook is registered at the correct position alphabetically between
  sibling `repo: local` hooks.
- A short skip-tolerant pytest test exists for the hook shape
  (skips when `pre-commit` is not on PATH) and is registered under
  `scripts/tests/test_decisions_yaml_gate.py` or a sibling test file.

## Files to Modify

- `.pre-commit-config.yaml` — append a `repo: local` block for
  `.ll/decisions.yaml`. Place alphabetically between existing
  `repo: local` entries (likely just below `check-decisions-yaml`-adjacent
  hooks if present, otherwise at the bottom of the local-hook cluster).
- `docs/guides/DECISIONS_LOG_GUIDE.md` — add a short paragraph explaining the
  pre-commit gate exists, what it does, and how `--no-verify` bypasses it
  (with a pointer to ENH-2591 for the pytest CI belt-and-suspenders).
- `CONTRIBUTING.md` — add a sibling `### Decisions YAML Validation
  (ll-verify-decisions)` section below the existing `### Secret Scanning
  (gitleaks)` block (lines 103-133) so contributors see both hooks sharing
  the same `pre-commit install` activation. Mirror the install + smoke-test
  template already documented for gitleaks. (Could alternatively extend
  the gitleaks section with a closing paragraph; the sibling-section shape
  mirrors the existing layout cleanly.)
- `scripts/tests/test_decisions_yaml_pre_commit_gate.py` (NEW) —
  resolved sibling file name to avoid the filename collision with sibling
  ENH-2591 (which owns the `test_decisions_yaml_gate.py` name for its CI
  gate). Mirror the skip-tolerant shape from
  `scripts/tests/test_policy_builder_node_gate.py:45-71` and the
  `_init_git_repo` helper from `scripts/tests/test_hooks_integration.py:2994-3007`
  (or `scripts/tests/test_issue_lifecycle.py:302-316`).

_Wiring pass added by `/ll:wire-issue` — **blocking pre-requisite
(ENH-2589 wiring was incomplete; verified directly via Read tool):**_

- `scripts/pyproject.toml:51-92` — `[project.scripts]` is **missing** the
  `ll-verify-decisions` entry. Verified by reading lines 51-92 directly:
  the block lists `ll-verify-package-data` (line 87),
  `ll-verify-design-tokens` (line 88), `ll-verify-des-audit` (line 89),
  then `ll-adapt-agents-for-codex` (line 90) with NO `ll-verify-decisions`
  slot. **Insert between line 87 and line 88** (alphabetical: `-decisions`
  < `-des-audit` < `-design-tokens`):
  `ll-verify-decisions = "little_loops.cli:main_verify_decisions"`.
  Without this registration, the new `.pre-commit-config.yaml` hook's
  `entry: ll-verify-decisions` resolves to "command not found" on every
  commit — the `.pre-commit-config.yaml` change is dead-letter without it.
- `scripts/little_loops/cli/__init__.py:42-131` — both the import block
  (lines 42-86) and the `__all__` list (lines 88-131) lack
  `main_verify_decisions`. Add at line 86 (after the `init.cli` import):
  `from little_loops.cli.verify_decisions import main_verify_decisions`,
  and append `"main_verify_decisions"` to `__all__` (alphabetical —
  before `"main_verify_des_..."` at line 121). The `test_verify_decisions.py`
  module bypasses the gap by importing
  `from little_loops.cli.verify_decisions import main_verify_decisions`
  directly, but the `pyproject.toml` console-script string
  `little_loops.cli:main_verify_decisions` cannot resolve without the
  package-level re-export.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `.pre-commit-config.yaml` currently contains **only** the `gitleaks` external
  repo (lines 1-5). ENH-2590 ships the **first** `repo: local` block in this
  file — there are no sibling `repo: local` hooks yet to sort against, so the
  new block simply appends to the bottom of `repos:`.
- The validator CLI (`ll-verify-decisions`) is already implemented at
  `scripts/little_loops/cli/verify_decisions.py:63-105`
  (`main_verify_decisions`) with `_run`/`_resolve_log_path` helpers at
  lines 36-60. `--config-root <Path>` is the only CLI flag (lines 90-99).
  Exit 0 = clean, 1 = caught `yaml.YAMLError` / `KeyError` / `ValueError`.
- The `pre-commit>=3.0` dev dep is already declared at
  `scripts/pyproject.toml:118` under `[project.optional-dependencies].dev` —
  no new dependency addition is needed.
- Validation exception surface (from `scripts/little_loops/decisions.py:272-282`
  `load_decisions`):
  - `yaml.YAMLError` — from `yaml.safe_load(raw)` at line 278
    (PyYAML `ParserError` for malformed scalars like OTHE-203)
  - `KeyError` — from each entry's `from_dict` classmethod
    (`RuleEntry.from_dict` line 67, `DecisionEntry.from_dict` line 117,
    `ExceptionEntry.from_dict` line 167, `CouplingEntry.from_dict` line 216)
  - `ValueError` — from `_entry_from_dict` at line 268 when entry `type`
    is not in `_ENTRY_REGISTRY` (`rule` / `decision` / `exception` / `coupling`)
- OTHE-203 fixture pattern (inline, not a separate file) — written via
  `decisions_path.write_text('entries:\n  - id: OTHE-203\n    type: decision\n
  rationale: "abc "" def"\n', encoding="utf-8")`. Confirmed reproducible at
  `scripts/tests/test_decisions.py:119-135` and
  `scripts/tests/test_verify_decisions.py:49-64`.
- `docs/guides/DECISIONS_LOG_GUIDE.md` is 488 lines. Natural insertion point
  for the new paragraph is **between** the existing `## Configuration` section
  (lines 461-481) and `## See Also` (lines 485-488), separated by the
  canonical `---` horizontal rule pattern used throughout the guide.
- Sibling precedent for documenting pre-commit setup in
  `CONTRIBUTING.md:103-133` (`### Secret Scanning (gitleaks)`) — provides
  the install / `pre-commit install` / smoke-test template to mirror.

## Depends On

- **ENH-2589** — `ll-verify-decisions` CLI must exist on `PATH` (installed via
  `pip install -e "./scripts[dev]"`).

## Blocks

Nothing.

## Implementation Steps

1. Read the current `.pre-commit-config.yaml` to identify the cluster of
   `repo: local` hooks and the alphabetical insertion point.
2. Append a `repo: local` block:
   ```yaml
   - repo: local
     hooks:
       - id: ll-verify-decisions
         name: Validate .ll/decisions.yaml
         language: system
         entry: ll-verify-decisions
         files: ^\.ll/decisions\.yaml$
         pass_filenames: false
   ```
3. Verify the validator CLI is installed (`ll-verify-decisions --help`).
4. Smoke-test against a corrupted `tmp_path` fixture: copy the OTHE-203 pattern
   into a temp `.ll/decisions.yaml` and run
   `pre-commit run --files .ll/decisions.yaml` (manual). Expect non-zero exit.
5. Smoke-test against a valid file (use the actual `.ll/decisions.yaml`
   post-recovery). Expect zero exit.
6. Update `docs/guides/DECISIONS_LOG_GUIDE.md` pre-commit paragraph.
7. Run the full pre-commit suite to ensure no regression:
   `pre-commit run --all-files`.
8. Run the test suite: `python -m pytest scripts/tests/`.

### Codebase Research Findings — Implementation Steps

_Added by `/ll:refine-issue` — anchor references from codebase research:_

- **Step 1 anchor** — `.pre-commit-config.yaml` currently has **5 lines** (full
  contents: `repos:` with one `gitleaks` external entry). There is no
  pre-existing `repo: local` cluster to sort against; the new block simply
  appends after the `gitleaks` entry.
- **Step 2 anchor** — `language: system` is the correct choice because
  `ll-verify-decisions` is a pre-installed console-script (registered via
  `[project.scripts]` in `pyproject.toml:51-92`). `pass_filenames: false` is
  required because `main_verify_decisions` resolves the file path itself via
  `_resolve_log_path` (`scripts/little_loops/cli/verify_decisions.py:36-44`)
  and does not accept file arguments via sys.argv.
- **Step 4 anchor** — `tmp_path` smoke test for OTHE-203 corruption should
  mirror the inline-write pattern from
  `scripts/tests/test_verify_decisions.py:49-64`
  (`TestLoadDecisionsMalformedInput.test_yaml_error_othe_203`). The exact
  payload: `entries:\n  - id: OTHE-203\n    type: decision\n  rationale:
  "abc "" def"\n` — this triggers `yaml.parser.ParserError` at
  `scripts/little_loops/decisions.py:278` (`yaml.safe_load`).
- **Step 6 anchor** — Insert the new paragraph in
  `docs/guides/DECISIONS_LOG_GUIDE.md` between `## Configuration`
  (lines 461-481) and `## See Also` (lines 485-488), separated by `---`.
  Wording should: (a) state the gate exists, (b) describe what it validates
  (load-time integrity of `.ll/decisions.yaml`), (c) note `--no-verify`
  bypasses it, (d) cross-reference ENH-2591 as the pytest CI belt-and-suspenders.
- **Step 8 anchor** — The project's "CI" is `python -m pytest scripts/tests/`
  (per `.claude/CLAUDE.md` § Testing & CI Policy). New test file location:
  `scripts/tests/test_decisions_yaml_gate.py` (or sibling per AC) — model
  after `scripts/tests/test_policy_builder_node_gate.py:1-72` (FEAT-2390
  canonical skip-tolerant gate template, `shutil.which("pre-commit")` skip +
  OTHE-203 corruption case via `tmp_path`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation alongside the steps above:_

9. **Update `CONTRIBUTING.md`** — add a sibling
   `### Decisions YAML Validation (ll-verify-decisions)` section below the
   existing `### Secret Scanning (gitleaks)` section (lines 103-133). Mirror
   the `pip install -e "./scripts[dev]"`, `pre-commit install`, and
   `pre-commit run --files .ll/decisions.yaml` smoke-test template already
   documented there. The gitleaks prose currently implies it is the only
   pre-commit hook installed; after this change it is one of two.
10. **Use the sibling test file name
    `scripts/tests/test_decisions_yaml_pre_commit_gate.py`** (NOT
    `test_decisions_yaml_gate.py` — that name is owned by the sibling
    ENH-2591 CI-side pytest gate at line 25-65 of that issue file). The
    sibling name preserves both transport-layer hooks independently while
    keeping the established `test_<feature>_gate.py` family convention.
    Mirror the skip-tolerant shape from
    `test_policy_builder_node_gate.py:45-71`; copy the OTHE-203 inline-write
    pattern from `test_verify_decisions.py:49-64`; copy the `_init_git_repo`
    setup helper from `test_hooks_integration.py:2994-3007` (or duplicate
    the `temp_git_repo` fixture shape from `test_issue_lifecycle.py:302-316`).
    Use plain function-level tests with **inline `pytest.skip(...)`**
    (FEAT-1225 idiom at
    `.issues/features/P2-FEAT-1225-parallel-display-badge-test.md:62`), NOT
    `pytest.mark.gate` (unregistered marker would fail `--strict-markers` per
    `pyproject.toml:172`).
11. **Flag a latent defect for follow-up (NOT in ENH-2590's scope; surface to
    a separate issue)**: `scripts/little_loops/cli/verify_decisions.py:58`
    — the line `except (yaml.YAMLError, KeyError, ValueError) as exc:
    # type: ignore[name-defined]` references `yaml.YAMLError` but `yaml`
    is **never imported at module level** (lines 25-32 import only `argparse`,
    `sys`, `pathlib.Path`, and `little_loops.session_store`). At runtime, a
    real `yaml.YAMLError` raised by `load_decisions` will surface as
    `NameError: name 'yaml' is not defined` instead of the intended clean
    `exit_code 1`. The existing `test_yaml_error_returns_one` at
    `scripts/tests/test_verify_decisions.py:119-138` passes only because that
    test imports `yaml` itself at line 59, sharing the namespace via pytest's
    import semantics; an actual subprocess invocation of
    `ll-verify-decisions` against a corrupted `.ll/decisions.yaml` will
    trigger the NameError. This defect belongs to ENH-2589 (now `done`) — a
    new BUG issue should track it. Adding `import yaml` at line 27 of
    `verify_decisions.py` is the canonical fix.
12. **BLOCKING pre-requisite — register `ll-verify-decisions` console script
    (ENH-2589 wiring left incomplete; verified by direct Read)**: Without
    this step, the `.pre-commit-config.yaml` hook will fail with "command
    not found" on every commit, and ENH-2590's AC 1-2 will not be
    exercisable end-to-end.
    - `scripts/pyproject.toml:51-92` — insert (alphabetical, between line
      87 `ll-verify-package-data` and line 88 `ll-verify-design-tokens`):
      `ll-verify-decisions = "little_loops.cli:main_verify_decisions"`.
    - `scripts/little_loops/cli/__init__.py` — add the import
      `from little_loops.cli.verify_decisions import main_verify_decisions`
      (after the `init.cli` import at line 86), and add
      `"main_verify_decisions"` to `__all__` (alphabetical — before
      `"main_verify_des_..."` at line 121).
    - Verify with `pip install -e "./scripts[dev]"` then
      `which ll-verify-decisions` and `ll-verify-decisions --help`.
13. **Cross-check the FIX ordering**: do step 12 BEFORE step 2-7 from the
    primary Implementation Steps. Otherwise the pre-commit hook will be
    committed before the CLI binary resolves, and the smoke test (step 4-5)
    will fail with `command not found` rather than the intended
    OTHE-203 corruption error.

## Integration Map

### Files to Modify
- `.pre-commit-config.yaml` (currently 5 lines, gitleaks-only) — append
  first `repo: local` block at end of `repos:` array
- `scripts/tests/test_decisions_yaml_gate.py` (NEW) or sibling file — skip-
  tolerant pytest gate per the `test_policy_builder_node_gate.py` template
- `docs/guides/DECISIONS_LOG_GUIDE.md` — add new validation paragraph
  between `## Configuration` and `## See Also`

_Wiring pass added by `/ll:wire-issue`:_

- `CONTRIBUTING.md:103-133` — `### Secret Scanning (gitleaks)` documentation
  currently implies it is the *only* hook in `.pre-commit-config.yaml`; after
  ENH-2590 it must mention both hooks sharing the same `pre-commit install`
  activation. Either add a sibling `### Decisions YAML Validation
  (ll-verify-decisions)` subsection OR extend the existing gitleaks section
  with a closing paragraph.
- `scripts/tests/test_decisions_yaml_pre_commit_gate.py` (NEW; sibling to
  ENH-2591's `test_decisions_yaml_gate.py`) — resolved sibling file name to
  avoid filename collision; both transport-layer hooks (git pre-commit +
  pytest CI) preserve independent tests. Mirror the
  `shutil.which("pre-commit") → pytest.skip(...)` guard from
  `test_policy_builder_node_gate.py:52-57` and copy the `_init_git_repo`
  helper from `test_hooks_integration.py:2994-3007` (or duplicate the
  `_init_repo`/`temp_git_repo` fixture from `test_issue_lifecycle.py:302-316`).
  Use **inline `pytest.skip(...)`**, NOT `pytest.mark.gate` (marker not
  registered in `pyproject.toml:179-184`, will fail `--strict-markers` at
  line 172). The autouse conftest fixtures `_isolate_history_db`
  (line 546-561) and `_isolate_session_log_dir` (line 612-637) already
  isolate `.ll/history.db` and session-log writes — no conftest changes
  needed. `pre-commit>=3.0` already declared at `pyproject.toml:118`.
- `scripts/pyproject.toml:51-92` — **blocking pre-requisite discovered by
  wiring pass**: `[project.scripts]` is missing the `ll-verify-decisions`
  entry (verified by direct Read of lines 51-92). Without this registration,
  the `.pre-commit-config.yaml` `entry: ll-verify-decisions` resolves to
  "command not found". Add (alphabetical, between line 87 and line 88):
  `ll-verify-decisions = "little_loops.cli:main_verify_decisions"`. This
  was scoped to ENH-2589 (now `done`) but is required for ENH-2590's
  acceptance criteria 1-2 to be exercisable end-to-end.
- `scripts/little_loops/cli/__init__.py:42-131` — **blocking pre-requisite**:
  add `from little_loops.cli.verify_decisions import main_verify_decisions`
  to the imports (after the `init.cli` import at line 86), and add
  `"main_verify_decisions"` to `__all__` (alphabetical, before
  `"main_verify_des_..."` at line 121). The `pyproject.toml` console-script
  string cannot resolve without the package-level re-export.

### Pre-existing Files (read-only references)
- `scripts/little_loops/cli/verify_decisions.py:63-105` — `main_verify_decisions`
  CLI shipped by ENH-2589; the entry point invoked by the new pre-commit hook
- `scripts/little_loops/decisions.py:272-282` — `load_decisions` is the
  underlying validator; raises `yaml.YAMLError`/`KeyError`/`ValueError`
- `scripts/pyproject.toml:86-89` — `ll-verify-decisions` console-script
  registration must already be present (ENH-2589 scope)

### Skip-Tolerant Test Pattern (canonical template)
- `scripts/tests/test_policy_builder_node_gate.py:45-71`
  (`test_node_conformance_suite_passes`) — the FEAT-2390 template:
  - Inline `shutil.which("pre-commit")` → `pytest.skip(...)` guard (lines 52-57)
  - Subprocess invocation with `capture_output=True, text=True`
  - OTHE-203 fixture pattern via `tmp_path`
- `scripts/tests/test_verify_decisions.py:100-208` (`TestMainVerifyDecisions`) —
  CLI-level exit-code tests for clean/YAMLError/KeyError/ValueError cases

### Sibling Decisions YAML Hooks (ENH-2587 children)
- ENH-2589 (done) — `ll-verify-decisions` validator CLI + unit tests
- ENH-2591 (open) — pytest CI gate (`scripts/tests/test_decisions_yaml_gate.py`)
- ENH-2592 (open) — Claude Code PreToolUse hook
  (`hooks/scripts/check-decisions-yaml.sh` + `hooks/hooks.json` entry)

### Related Documentation
- `docs/guides/DECISIONS_LOG_GUIDE.md` — natural insertion point for new
  validation paragraph (between `## Configuration` and `## See Also`)
- `CONTRIBUTING.md:103-133` — `### Secret Scanning (gitleaks)` provides the
  pre-commit install / smoke-test docs template to mirror

### Configuration
- No new config keys; the hook reads only `pre-commit` framework defaults
  (`.pre-commit-config.yaml` plus `.git/hooks/pre-commit` symlink created by
  `pre-commit install`)

## Similar Patterns

_Added by `/ll:refine-issue` — patterns from the codebase to model after:_

### Skip-tolerant pytest gate (canonical template)
`scripts/tests/test_policy_builder_node_gate.py:45-71`
(`test_node_conformance_suite_passes`, FEAT-2390) — the canonical "subprocess
gate as pytest test" pattern used for `node --test` conformance. ENH-2590's
new test should mirror this shape:

```python
def test_pre_commit_hook_blocks_corruption(tmp_path: Path) -> None:
    """pre-commit ll-verify-decisions hook must fail on OTHE-203 corruption."""
    pre_commit = shutil.which("pre-commit")
    if pre_commit is None:
        pytest.skip("pre-commit not installed; gate runs wherever it is available")
    validator = shutil.which("ll-verify-decisions")
    if validator is None:
        pytest.skip("ll-verify-decisions not installed; run pip install -e ./scripts[dev]")

    # Set up a git repo in tmp_path with .pre-commit-config.yaml + decisions.yaml
    # ... (git init, copy fixture, pre-commit run --files .ll/decisions.yaml)
    # Assert non-zero exit on OTHE-203, zero exit on valid file
```

The project's convention is **inline `pytest.skip(...)`** rather than
`@pytest.mark.skipif` for skip-when-PATH-absent gates (per FEAT-1225
established idiom at `.issues/features/P2-FEAT-1225-parallel-display-badge-test.md:62`).

### Validator CLI exit-code shape
`scripts/little_loops/cli/verify_decisions.py:47-60` (`_run`) — returns
`(0, None)` on success or `(1, error_message)` on any caught exception.
Stderr gets the error message (line 105). The pre-commit hook inherits this
exit-code contract directly: a clean file → exit 0 (commit proceeds), a
corrupted file → exit 1 (commit blocked by pre-commit framework).

### DOCS pattern for the guide
`docs/guides/DECISIONS_LOG_GUIDE.md` uses `---` horizontal rules between H2
sections and ends every operations section with cross-references. The new
"Validation" paragraph should follow the same shape as the existing
`## Configuration` section (lines 461-481) — a short prose intro followed by
a fenced code block if there's a command, then a `See Also`-style pointer
to ENH-2591 for the pytest CI belt-and-suspenders.

## Session Log
- `/ll:manage-issue` - 2026-07-10T23:19:37 - `5d377bc0-2fbe-4c18-8a02-e6163699591c.jsonl`
- `/ll:ready-issue` - 2026-07-10T23:06:41 - `4d644380-5a9b-4aba-9fa0-baa503979910.jsonl`
- `/ll:wire-issue` - 2026-07-10T22:57:03 - `6bac3ebd-e700-439c-97c7-c33af784b1cf.jsonl`
- `/ll:refine-issue` - 2026-07-10T22:49:56 - `5b867325-7ba2-4604-9c43-d7d40a477704.jsonl`
- `/ll:issue-size-review` - 2026-07-10T22:15:00 - `61c51949-414d-4865-b102-91b1bc365edd.jsonl`

## Resolution

Implemented end-to-end. All five ACs verified:

1. `.pre-commit-config.yaml` carries a `repo: local` block (`id: ll-verify-decisions`, `language: system`, `entry: ll-verify-decisions`, `files: ^\.ll/decisions\.yaml$`, `pass_filenames: false`). Hook appended after the existing gitleaks external entry — there are no other `repo: local` hooks to sort against.
2. Smoke test: `pre-commit run --files .ll/decisions.yaml` against an OTHE-203 fixture exits non-zero with the validator's `ERROR:` line on stderr.
3. Smoke test against a clean fixture exits 0.
4. Hook is alphabetically positioned within the verify-* console-script cluster (`verify-decisions` placed before `verify-des-audit` in `pyproject.toml`, before `main_verify_des_audit` in `cli/__init__.py`'s `__all__`).
5. `scripts/tests/test_decisions_yaml_pre_commit_gate.py` (75 / 75 new + existing decisions / load-decisions tests green; full suite 14,522 passed, 36 skipped).

### Blocking wiring fix (in scope)

`scripts/pyproject.toml:88-89` registered `ll-verify-decisions = "little_loops.cli:main_verify_decisions"` (alphabetical, before `ll-verify-des-audit`). `scripts/little_loops/cli/__init__.py` re-exported `main_verify_decisions` via the imports block and `__all__`. Without these, the new `.pre-commit-config.yaml` hook would resolve to "command not found" on every commit.

### Latent defect fixed (discovered during research)

`scripts/little_loops/cli/verify_decisions.py:58` referenced `yaml.YAMLError` in the `except` clause but `yaml` was never imported at module level. The existing `test_yaml_error_returns_one` passed only because pytest's import system shared the `yaml` namespace from a sibling test that imported it. Subprocess invocation of the now-wired CLI triggered the latent `NameError` end-to-end. Added `import yaml` at the module top and removed the dead `# type: ignore[name-defined]` comment. A standalone BUG issue should track this for posterity (ENH-2589's regression coverage masked it).
