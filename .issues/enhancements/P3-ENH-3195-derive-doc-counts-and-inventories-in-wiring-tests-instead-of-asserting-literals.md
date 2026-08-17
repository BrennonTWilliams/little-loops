---
id: ENH-3195
type: ENH
title: Derive doc counts and inventories in wiring tests instead of asserting string
  literals
priority: P3
status: done
testable: true
discovered_by: manual-review
discovered_date: '2026-08-15'
captured_at: '2026-08-15T00:00:00Z'
completed_at: '2026-08-17T16:09:28Z'
relates_to:
- BUG-3186
- BUG-3188
- BUG-3189
- BUG-3190
- BUG-3191
depends_on:
- BUG-3186
- BUG-3189
- BUG-3190
confidence_score: 98
outcome_confidence: 76
score_complexity: 12
score_test_coverage: 24
score_ambiguity: 20
score_change_surface: 20
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

On the current tree (verified 2026-08-17), `ll-verify-docs` exits 1:

```
✗ Found 4 mismatch(es):
  skills: documented=69, actual=40   README.md:183
  skills: documented=69, actual=40   CONTRIBUTING.md:176
  skills: documented=69, actual=40   docs/ARCHITECTURE.md:26
  skills: documented=69, actual=40   docs/ARCHITECTURE.md:111
```

`doc_counts` counts `skills/*/SKILL.md` (69) and then subtracts the 29 bridge skills
(`BRIDGE_MARKER`) → **40**. The docs say **69**, set that way by commit 9ac827b9.

Two consequences that must be resolved *before* any gate lands:

1. Wiring the existing checker into pytest as-is turns the suite red immediately.
2. The next `ll-verify-docs --fix` rewrites 69 → 40, reddening any derived assertion
   that picked 69. **This oscillation is the `68→42` and `39→42` drift the Current
   Behavior section quotes as evidence — it is still live.** The gate and `--fix` must
   share a single ground-truth function, over a single agreed definition of "skill."

Neither number is simply wrong, which is why this needs a decision rather than a fix.
Three of the four callouts annotate the `skills/` **directory** inside a tree diagram,
and that directory does literally contain 69 `SKILL.md` files — renumbering them to 40
makes the directory comment false. The fourth (`README.md:183`) is a product claim, and
there "69 skills" double-counts the command surface: the 29 bridges correspond exactly to
the 29 `commands/*.md`, so README simultaneously advertises 29 commands and 69 skills for
a real surface of 69.

**Decision (Step 0): the canonical skill count is 40** — authored, non-bridge, matching
`BRIDGE_MARKER`'s existing intent. The directory callouts are **reworded, not
renumbered**, so each site stays factually true:

| Site | Context | Resolution |
|---|---|---|
| `README.md:183` | product bullet | `**40 skills**` |
| `CONTRIBUTING.md:176` | ``` ``` ``` directory tree | `# 40 skill definitions + 29 command bridges` |
| `docs/ARCHITECTURE.md:26` | ` ```mermaid ` node label | `SKL[Skills<br/>40 composable skills]` |
| `docs/ARCHITECTURE.md:111` | ``` ``` ``` directory tree | `# 40 skill definitions + 29 command bridges` |

Caution when rewording: `extract_count_from_line`'s `\w*\s*` tolerates exactly **one**
filler word between the number and the category, and each line is scanned against *every*
category. `40 skill definitions + 29 command bridges` therefore yields two matches on one
line — `skills=40` and (once the extractor is widened, below) `commands=29` — both of
which happen to be correct. Any alternate wording must be re-run through `ll-verify-docs`
to confirm it still matches and does not match the wrong category.

### Blocker: the command-count miss is an extractor bug, not a missing test

`docs/ARCHITECTURE.md:63` — `# 29 slash command templates` — is in a file `doc_counts`
already scans, yet is not checked at all. `extract_count_from_line` builds
`rf"(\d+)\s+\w*\s*{category}"` with `category="commands"`; the line reads "command
**templates**" (singular), so it never matches. This is the same class as the
special-case the function already carries for `skills?`. Fixing the extractor makes that
check exist for free — no new test row needed.

Note that BUG-3191 has landed: the line reads 29 and agrees with `:24`, so this fix is
now purely **preventative** — it closes an unchecked line, it does not resolve a live
mismatch. Widening the pattern to `commands?` also widens the false-positive surface
across all of `DOC_FILES` (any "N command …" prose becomes an assertion), so the change
must be validated against a clean tree, not just against `:63`.

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

**Step 0a — reconcile the skill definition (prerequisite for checks 1–2).** Apply the
decision recorded in the Blocker section above: canonical count is **40** (non-bridge),
`BRIDGE_MARKER` semantics unchanged, and the four callouts reworded per the table so each
stays factually true in its context. Record the decision as a comment next to
`BRIDGE_MARKER`. Do not proceed to the gate while `ll-verify-docs` is red on a clean tree.

**Step 0b — close the one live hook-coverage gap (prerequisite for check 4).**
`drift-check.sh` is registered in `hooks/hooks.json` but named nowhere in
`docs/guides/BUILTIN_HOOKS_GUIDE.md` (24 registered scripts, 1 undocumented). Check 4
lands red until the guide documents it. Same rule as Step 0a: no gate goes blocking over
a red checker.

There is no equivalent Step 0 for check 3 — see below, it is already green.

Then:

1. **Skill count** — derived from the filesystem per the Step-0a definition, vs. every
   documented skill count in `README.md`, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md`.
   Mechanism already exists; this item is Step 0a plus making failure blocking.
2. **Command count** — `len(glob("commands/*.md"))` vs. documented counts, covering both
   `docs/ARCHITECTURE.md:24` and `:63`. Requires the `extract_count_from_line` fix above
   so the singular "command templates" phrasing at `:63` is matched. Both lines currently
   read 29 and agree; this closes an unchecked line rather than fixing a mismatch.
3. **CLI entry-point coverage** — console-scripts declared in `scripts/pyproject.toml`
   (parsed with stdlib `tomllib`, **not** `importlib.metadata.entry_points()`, which
   reflects a possibly-stale editable install) vs. `### ` sections in
   `docs/reference/CLI.md`. Fails on any entry point with no section. Would have caught
   `ll-compact-session`.

   **No exclusion list.** Since BUG-3186 landed, all 52 declared entry points have a
   section — including the non-`ll-` `mcp-call` and the internal `ll-generate-schemas`.
   The check is green today with zero exclusions, so require a section for *every*
   declared entry point. An earlier draft prescribed keying exclusions off the
   `# internal:` comment convention at `scripts/pyproject.toml:102`; that machinery buys
   nothing here and weakens the gate. Do not build it.
4. **Hook coverage** — handler entries in `hooks/hooks.json` vs. hooks named in
   `docs/guides/BUILTIN_HOOKS_GUIDE.md`. Fails on any registered hook the guide omits.
   Would have caught `check-private-refs.sh` and both `record-hook-event.sh` shims, and
   catches `drift-check.sh` today (see Step 0b).

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
  it to the implementer.

  A preceding-line HTML comment (`<!-- ll-doc-count: ignore -->`) is **not sufficient on
  its own**: 3 of the 4 real count sites are inside fenced blocks, where it does not work.
  `docs/ARCHITECTURE.md:24` sits in a ` ```mermaid ` block (an HTML comment breaks the
  diagram) and `CONTRIBUTING.md:176` / `docs/ARCHITECTURE.md:111` sit in ``` ``` ```
  directory-tree fences (it renders literally as tree content). Only `README.md:183` is
  plain markdown.

  Pin **both** forms, checked in this order: (a) a trailing same-line marker
  `ll-doc-count: ignore` appearing anywhere after the count — usable inside a tree fence
  as part of the existing `#` comment and inside a mermaid `%%` comment; (b) the
  preceding-line `<!-- ll-doc-count: ignore -->` for plain markdown. `is_count_opted_out`
  owns both, and both are honored by `verify_documentation` and `fix_counts`.
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
- `verify_coverage(base_dir: Path | None = None) -> VerificationResult` — new sibling holding checks 3-4, returning the same result type so `format_result_json` / `format_result_markdown` render it. **`format_result_text` does need a change**: its mismatch branch (`doc_counts.py:213-217`) prints only `category: documented=N, actual=M` then `at {file}:{line}`. A coverage gap has no line and its whole value is in the names, so it renders as an unactionable `hooks: documented=23, actual=24   at None:None`. Add a branch that prints `missing` (and omits the `file:line` row when `line is None`); mirror it in the JSON and markdown formatters.
- `declared_entry_points(pyproject: Path) -> set[str]` — new; parses `[project.scripts]` with stdlib `tomllib` and returns every declared name. No internal/external partition — see check 3, there are no exclusions.
- `documented_cli_sections(cli_md: Path) -> set[str]` — new; captures `### ` headings from `docs/reference/CLI.md`, tolerating the backtick-wrapped form (`### \`ll-doctor\``).
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

- [x] Step 0a: the canonical skill count is 40 (non-bridge), recorded in a comment next to `BRIDGE_MARKER` in `doc_counts.py`; all four documented skill callouts are reworded per the Blocker table so each is true in its context. `ll-verify-docs` exits 0 on a clean tree.
- [x] Step 0b: `docs/guides/BUILTIN_HOOKS_GUIDE.md` documents `drift-check.sh`, so check 4 is green on a clean tree.
- [x] `extract_count_from_line` matches the singular "N slash command templates" phrasing, so `docs/ARCHITECTURE.md:63` is covered by the existing scan.
- [x] The widened `commands?` pattern introduces **no new mismatches** on a clean tree — asserted by a test that runs `verify_documentation` over the real `DOC_FILES` and requires `all_match`, not just by a unit test of the `:63` line.
- [x] `ll-verify-docs --fix` is a **no-op on a clean tree** (0 files modified), and `verify → fix → verify` converges in one pass on a dirtied tree. This is the oscillation guard the Blocker section names; without it `--fix` and the gate can still disagree.
- [x] Check 3 requires a `CLI.md` section for every entry point declared in `[project.scripts]`, with no exclusion list — currently 52/52.
- [x] Skill-count, command-count, CLI-entry-point, and hook-coverage assertions exist and derive ground truth from the filesystem/`pyproject.toml`, not from a hardcoded expected number.
- [x] All four checks are reachable from one `doc_counts` entry point shared by the pytest gate, `ll-verify-docs`, `--fix`, `ll-doctor`, and `drift-check.sh` — no second derivation path in a test file.
- [x] Each assertion's failure message names both the documented value and the derived value; coverage-gap failures additionally name the specific missing entry points / hook basenames rather than only set sizes.
- [x] The opt-out marker supports both the trailing same-line and preceding-comment forms, is honored by both the verifier and `--fix`, and has a test covering an opted-out line in each of the three contexts that matter: plain markdown, a ``` ``` ``` tree fence, and a ` ```mermaid ` block.
- [x] The three commented-out `# REMOVED (stale/false-positive, count drifted ...)` entries are deleted and superseded by derived checks.
- [x] A negative test mutates a copy of the tree in `tmp_path` (drop a `CLI.md` section, register a hook the guide omits, bump a documented count) and asserts the check fails — verified by the suite, not by manual re-introduction.
- [x] Re-introducing any BUG-3186/3189/3190 defect fails `python -m pytest scripts/tests/`.
- [x] The suite still passes on a clean tree; no new third-party dependency (`tomllib` is stdlib on 3.11+).

## Motivation

Six issues in the current batch are doc rot, and at least three are re-fixes of counts
that were fixed before. Fixing them again without a gate schedules a seventh audit. The
per-item cost of these checks is a few lines each; the cost of not having them is a
recurring multi-issue audit sweep.

## Impact

- **Priority**: P3 — no user-facing defect, but it is the only item in this batch that stops the class rather than one instance.
- **Effort**: Medium — smaller than a from-scratch build for items 1–2 (the checker exists) and for item 3 (already green, needs only the assertion), larger than first scoped because of Step 0a/0b: four doc callouts reworded and one hook documented before anything can go blocking.
- **Risk**: Low-Medium. Over-strictness on deliberately approximate prose is mitigated by the opt-out marker and by asserting count callouts rather than enumerations. The two live risks are (a) Step 0a — changing the documented skill count touches user-facing docs and the `ll-doctor`/`drift-check.sh` output consuming projects see, though rewording rather than renumbering keeps each callout true and preserves `BRIDGE_MARKER` semantics; and (b) the widened `commands?` extractor turning previously-inert prose into assertions, guarded by the clean-tree AC.
- **Breaking Change**: No.

## Sequencing

**Unblocked as of 2026-08-17**: BUG-3186, BUG-3189, and BUG-3190 (the `depends_on` set)
are all `done`, along with BUG-3188 and BUG-3191. Their doc fixes are in the tree, so the
derived assertions for checks 2 and 3 go green on first run.

Within this issue the ordering is still not optional. Step 0a (skill-definition
reconciliation) must land before check 1 goes blocking — `ll-verify-docs` is red on the
current tree — and Step 0b (`drift-check.sh` in the hooks guide) must land before check 4
goes blocking.

## Status

**Open** | Created: 2026-08-15 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-08-17T16:08:43 - `2bed08d6-709a-4779-9c84-e88d155461d1.jsonl`
- `/ll:ready-issue` - 2026-08-17T15:38:26 - `86adafaa-70d2-4c08-ac9c-a7da1b885403.jsonl`
- `/ll:confidence-check` - 2026-08-17T06:08:01 - `86eb12f1-b126-4db7-a22d-252ffa585d1f.jsonl`
- `/ll:confidence-check` - 2026-08-17T05:57:22 - `dbac7370-5229-482f-9783-efd7ccbe7021.jsonl`
