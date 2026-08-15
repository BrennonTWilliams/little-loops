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
depends_on: [BUG-3186, BUG-3189, BUG-3190]
---

# ENH-3195: Derive doc counts and inventories in wiring tests instead of asserting string literals

## Summary

The doc-drift class that produced BUG-3186 through BUG-3191 has no *blocking* gate. The
existing wiring tests assert **string literals** against docs, so every count they cover
drifts, fails, and gets commented out rather than corrected. Meanwhile a derived checker
already exists (`ll-verify-docs` / `little_loops.doc_counts`) but is wired only to
advisory surfaces. Promote the derived check to a blocking pytest gate, fix the two
defects that make it miss real drift today, and extend it to the enumerable inventories
(CLI entry points, hooks) it does not cover.

## Prior art: `ll-verify-docs` already does half of this

`scripts/little_loops/doc_counts.py` already derives counts from the filesystem for
`commands`/`agents`/`skills`/`loops` and compares them against `README.md`,
`CONTRIBUTING.md`, and `docs/ARCHITECTURE.md` (`DOC_FILES`, `COUNT_TARGETS`,
`verify_documentation`, `fix_counts`). It is exposed as `ll-verify-docs`, consumed by
`ll-doctor`, and run advisorily by the SessionStart `drift-check.sh` hook.

That changes the shape of this ENH. Items 1–2 below are **not** new assertions to write
from scratch — they are "make the existing derived check blocking, and repair it."
Writing an independent glob in `test_wiring_*.py` would create a second, competing
definition of ground truth, which is the failure mode described in the next section.

### Blocker: the two ground truths disagree today

On the current tree, `ll-verify-docs` fails:

```
✗ Found 4 mismatch(es):
  skills: documented=69, actual=40   README.md:183
  skills: documented=69, actual=40   CONTRIBUTING.md:177
  skills: documented=69, actual=40   docs/ARCHITECTURE.md:26
  skills: documented=69, actual=40   docs/ARCHITECTURE.md:112
```

`doc_counts` counts `skills/*/SKILL.md` (69) and then subtracts the 29 bridge skills
(`BRIDGE_MARKER`) → **40**. The docs say **69**, set that way by commit 9ac827b9.

Two consequences that must be resolved *before* any gate lands:

1. Wiring the existing checker into pytest as-is turns the suite red immediately.
2. The next `ll-verify-docs --fix` rewrites 69 → 40, reddening any derived assertion
   that picked 69. **This oscillation is the `68→42` and `39→42` drift the Current
   Behavior section quotes as evidence — it is still live.** The gate and `--fix` must
   share a single ground-truth function, over a single agreed definition of "skill."

### Blocker: the command-count miss is an extractor bug, not a missing test

BUG-3191's `docs/ARCHITECTURE.md:64` — `# 28 slash command templates` — is in a file
`doc_counts` already scans, yet is not flagged. `extract_count_from_line` builds
`rf"(\d+)\s+\w*\s*{category}"` with `category="commands"`; the line reads "command
**templates**" (singular), so it never matches. This is the same class as the
special-case the function already carries for `skills?`. Fixing the extractor makes that
check exist for free — no new test row needed.

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

Add a blocking gate to the existing local pytest suite (per the project's no-hosted-CI
policy — this suite *is* CI), backed by the existing `doc_counts` module so that the gate,
`ll-verify-docs`, `ll-verify-docs --fix`, `ll-doctor`, and `drift-check.sh` all read from
one function.

**Step 0 — reconcile the skill definition (prerequisite for everything else).** Decide
whether the canonical skill count is all 69 `skills/*/SKILL.md` or the 40 non-bridge
skills, then make `doc_counts.COUNT_TARGETS`/`BRIDGE_MARKER` and the four documented
callouts agree. Do not proceed to the gate while `ll-verify-docs` is red on a clean tree.

Then:

1. **Skill count** — derived from the filesystem per the Step-0 definition, vs. every
   documented skill count in `README.md`, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md`.
   Mechanism already exists; this item is Step 0 plus making failure blocking.
2. **Command count** — `len(glob("commands/*.md"))` vs. documented counts, including the
   two independent claims in `docs/ARCHITECTURE.md:24` and `:64` that currently disagree
   with each other. Requires the `extract_count_from_line` fix above so the singular
   "command templates" phrasing at `:64` is matched.
3. **CLI entry-point coverage** — console-scripts declared in `scripts/pyproject.toml`
   (parsed with stdlib `tomllib`, **not** `importlib.metadata.entry_points()`, which
   reflects a possibly-stale editable install) vs. `### ll-*` sections in
   `docs/reference/CLI.md`. Fails on any entry point with no section. Would have caught
   `ll-compact-session`.

   Exclusions must be explicit, or the check demands sections for all 51 scripts: define
   the rule for the non-`ll-` entry point (`mcp-call`) and for entries marked internal in
   `pyproject.toml` (`ll-generate-schemas` carries an `# internal: dev tooling` comment).
   Prefer keying the exclusion off that existing comment convention over a second list.
4. **Hook coverage** — handler entries in `hooks/hooks.json` vs. hooks named in
   `docs/guides/BUILTIN_HOOKS_GUIDE.md`. Fails on any registered hook the guide omits.
   Would have caught `check-private-refs.sh` and both `record-hook-event.sh` shims.

   Join on **script basename**, deduped: `hooks.json` stores full
   `bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/<name>.sh` command strings while
   the guide names hooks in prose, and `record-hook-event.sh` appears under several
   events. Decide explicitly whether the second registry —
   `scripts/little_loops/hooks/adapters/codex/hooks.json` — is in scope; if not, say so in
   the test docstring so the omission is not read as an oversight.

Checks 3–4 are enumeration-coverage, a different mechanism from the numeric callouts in
1–2. Before implementing, grep `ll-verify-cli-allowlist` and `ll-verify-host-map` for
overlap rather than adding a third partial CLI inventory. Expose 3–4 through
`ll-verify-docs` (e.g. a coverage mode) so they are runnable outside pytest like every
other `ll-verify-*` gate.

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

- Put the derivation logic in `little_loops/doc_counts.py` (extending
  `verify_documentation` / adding a coverage sibling); the pytest tests should be thin
  wrappers that call it and assert `all_match`. Anything that globs the filesystem
  directly inside a test file re-creates the competing-ground-truth problem.
- Extend `test_wiring_guides_and_meta.py` and `test_wiring_cli_registry.py` rather than
  adding new files; both already carry the fixtures and `project_root` plumbing.
- `fix_counts` must honor the same definition and the same opt-out marker as the gate,
  or `--fix` will rewrite the very lines the gate exempts.
- Keep the existing literal-string table for genuinely non-derivable facts (prose
  concepts, symbol names like `LLHookEvent`). This ENH replaces only the countable and
  enumerable rows.
- Where a doc deliberately truncates a list (BUG-3190 proposes exactly this for the
  skills subtree), assert the *count callout*, not the enumeration — a truncated tree
  with a `...` should not fail.
- Allow an explicit opt-out marker for intentionally-approximate prose ("about 70
  skills") so the gate does not force false precision. Pin the syntax rather than leaving
  it to the implementer — proposed: an HTML comment `<!-- ll-doc-count: ignore -->` on the
  preceding line, honored by both `verify_documentation` and `fix_counts`.
- `DOC_FILES` is currently three files. Checks 3–4 read `docs/reference/CLI.md` and
  `docs/guides/BUILTIN_HOOKS_GUIDE.md`, which are not in that list; extend it or keep the
  coverage checks on their own file list, but do not silently leave a doc unscanned.

## Program Design

### Types

- `CoverageGap: CountResult` — reuse the existing dataclass rather than adding a parallel one; `category` carries `"cli_entry_points"` / `"hooks"`, `documented`/`actual` carry set sizes, and a new `missing: list[str]` field names the specific entry points or hook basenames the doc omits.
- `missing: list[str] = field(default_factory=list)` — new field on `CountResult` (`doc_counts.py:38-59`), defaulted so every existing construction site in `doctor.py` and `test_cli_docs.py` keeps working.
- `SKILL_COUNT_INCLUDES_BRIDGES: bool` — module constant recording the Step-0 decision next to `BRIDGE_MARKER` (`doc_counts.py:35`), so the definition lives in one greppable place instead of being implied by a subtraction.

### Signatures

- `verify_documentation(base_dir: Path | None = None) -> VerificationResult` — existing entry point (`doc_counts.py:133-195`), unchanged in signature; gains opt-out-marker skipping inside its per-line loop.
- `extract_count_from_line(line: str, category: str) -> int | None` — existing (`doc_counts.py:105-130`); its `commands` branch is widened to match the singular "N slash command templates" phrasing the way the `skills?` branch already does.
- `verify_coverage(base_dir: Path | None = None) -> VerificationResult` — new sibling holding checks 3-4, returning the same result type so `format_result_text` / `format_result_json` / `format_result_markdown` (`doc_counts.py:198-281`) render it with no changes.
- `declared_entry_points(pyproject: Path) -> dict[str, bool]` — new; parses `[project.scripts]` with stdlib `tomllib`, mapping name to "is internal", where internal is derived from the `# internal:` comment convention already used at `scripts/pyproject.toml:102`.
- `documented_cli_sections(cli_md: Path) -> set[str]` — new; captures `### ll-*` headings from `docs/reference/CLI.md`.
- `registered_hook_scripts(hooks_json: Path) -> set[str]` — new; walks the nested `hooks`/`matcher`/`hooks` structure of `hooks/hooks.json` and reduces each `command` string to its script basename, deduped.
- `documented_hook_names(guide: Path) -> set[str]` — new; extracts `*.sh` basenames named anywhere in `docs/guides/BUILTIN_HOOKS_GUIDE.md`.
- `is_count_opted_out(lines: list[str], index: int) -> bool` — new; returns True when the preceding line carries the `<!-- ll-doc-count: ignore -->` marker. Called by both `verify_documentation` and `fix_counts` so the verifier and the rewriter can never disagree.
- `fix_counts(base_dir: Path, result: VerificationResult) -> FixResult` — existing (`doc_counts.py:423-486`); gains the same opt-out guard and skips any `CoverageGap`-shaped mismatch, which is not auto-rewritable.

### Call Path

`main_verify_docs()` (`little_loops.cli`) -> `verify_documentation(base_dir)` -> `count_files()` + `extract_count_from_line()` + `is_count_opted_out()` -> `VerificationResult.add_result()` -> `format_result_text()` ; `main_verify_docs()` -> `verify_coverage(base_dir)` -> `declared_entry_points()` / `documented_cli_sections()` / `registered_hook_scripts()` / `documented_hook_names()` -> set difference -> `CountResult(missing=[...])`. The pytest gate enters at the same two functions from `test_wiring_cli_registry.py` and `test_wiring_guides_and_meta.py`, asserting `result.all_match` and printing `format_result_text(result)` as the failure message. `main_doctor()` and the `drift-check` handler continue to call `verify_documentation()` unchanged, and `main_verify_docs(--fix)` reaches `fix_counts()` on the same result object.

## Scope Boundaries

Explicitly **out of scope**:

- **Host-tier coverage.** Reassigned to BUG-3186 — see "Deliberately out of scope: host-tier coverage" above for the full rationale.
- **Rewriting the remaining literal-string rows.** `DOC_STRINGS_PRESENT` keeps every non-countable row (prose concepts, symbol names like `LLHookEvent`, path fragments). Only the three commented-out count rows are removed.
- **Line-citation drift.** BUG-3188/BUG-3191 include stale `file:line` references in prose. Deriving and asserting those is a different and much larger mechanism; this ENH covers counts and inventories only.
- **The codex adapter hook registry** (`scripts/little_loops/hooks/adapters/codex/hooks.json`) unless the implementer explicitly opts it in — the decision is required, the default is out.
- **Agent and loop counts.** `COUNT_TARGETS` already covers them and they are not implicated in this audit batch; leave their behavior untouched beyond the shared opt-out marker.
- **Any new `ll-verify-*` entry point.** Checks 3-4 extend `ll-verify-docs`; a third partial CLI inventory alongside `ll-verify-cli-allowlist` and `ll-verify-host-map` is the outcome to avoid.
- **Auto-fixing coverage gaps.** `--fix` may rewrite a numeric callout; it must never author a missing `CLI.md` section or hook paragraph.
- **Hosted CI.** Per project policy the gate is the local `python -m pytest scripts/tests/` suite; no workflow file.

## Acceptance Criteria

- [ ] The canonical skill-count definition is decided and recorded in a comment in `doc_counts.py`; `COUNT_TARGETS`/`BRIDGE_MARKER` and every documented skill callout in `README.md`, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md` agree with it. `ll-verify-docs` exits 0 on a clean tree.
- [ ] `extract_count_from_line` matches the singular "N slash command templates" phrasing, so `docs/ARCHITECTURE.md:64` is covered by the existing scan.
- [ ] Skill-count, command-count, CLI-entry-point, and hook-coverage assertions exist and derive ground truth from the filesystem/`pyproject.toml`, not from a hardcoded expected number.
- [ ] All four checks are reachable from one `doc_counts` entry point shared by the pytest gate, `ll-verify-docs`, `--fix`, `ll-doctor`, and `drift-check.sh` — no second derivation path in a test file.
- [ ] Each assertion's failure message names both the documented value and the derived value.
- [ ] The opt-out marker has a pinned syntax, is honored by both the verifier and `--fix`, and has a test covering an opted-out line.
- [ ] The three commented-out `# REMOVED (stale/false-positive, count drifted ...)` entries are deleted and superseded by derived checks.
- [ ] A negative test mutates a copy of the tree in `tmp_path` (drop a `CLI.md` section, register a hook the guide omits, bump a documented count) and asserts the check fails — verified by the suite, not by manual re-introduction.
- [ ] Re-introducing any BUG-3186/3189/3190 defect fails `python -m pytest scripts/tests/`.
- [ ] The suite still passes on a clean tree; no new third-party dependency (`tomllib` is stdlib on 3.11+).

## Motivation

Six issues in the current batch are doc rot, and at least three are re-fixes of counts
that were fixed before. Fixing them again without a gate schedules a seventh audit. The
per-item cost of these checks is a few lines each; the cost of not having them is a
recurring multi-issue audit sweep.

## Impact

- **Priority**: P3 — no user-facing defect, but it is the only item in this batch that stops the class rather than one instance.
- **Effort**: Medium — smaller than a from-scratch build for items 1–2 (the checker exists), larger than first scoped because of Step 0: the skill-count definition must be settled and four doc callouts reconciled before anything can go blocking.
- **Risk**: Low-Medium. Over-strictness on deliberately approximate prose is mitigated by the opt-out marker and by asserting count callouts rather than enumerations. The real risk is Step 0 — flipping the documented skill count 69 → 40 (or changing `BRIDGE_MARKER` semantics) touches user-facing docs and the `ll-doctor`/`drift-check.sh` output that consuming projects see.
- **Breaking Change**: No.

## Sequencing

Land **after** BUG-3186/3189/3190 (recorded as `depends_on`) so the derived assertions go
green on first run. Landing it first would red the suite until each doc fix merges.

Within this issue, Step 0 (skill-definition reconciliation) must land before the gate
becomes blocking — `ll-verify-docs` is red on the current tree, so the ordering is not
optional.

## Status

**Open** | Created: 2026-08-15 | Priority: P3
