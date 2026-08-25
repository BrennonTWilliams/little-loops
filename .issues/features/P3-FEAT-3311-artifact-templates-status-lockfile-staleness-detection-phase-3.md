---
id: FEAT-3311
type: FEAT
title: 'Artifact templates: status + lockfile staleness detection (Phase 3)'
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-24'
captured_at: '2026-08-24T03:57:16Z'
completed_at: '2026-08-25T14:38:47Z'
parent: EPIC-3299
depends_on:
- FEAT-3036
- FEAT-3310
labels:
- planning-hub
learning_tests_required:
- yaml
confidence_score: 90
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-3311: Artifact templates: status + lockfile staleness detection (Phase 3)

## Summary

Phase 3 of FEAT-3036's artifact-template design: add `ll-artifact status`
(staleness detection) and its backing lockfile, so a refreshed artifact can
be checked against its source(s) without re-rendering.

## Current Behavior

`ll-artifact render` (Phase 1, FEAT-3036) and `refresh` (Phase 2, FEAT-3310)
have no way to report whether a rendered artifact is stale relative to its
source(s).

## Expected Behavior

`ll-artifact status [<template> ...]` compares recorded source hashes
(sha256, stored in a machine-written `<template>.llat.lock` sibling file
next to the template — never written into `manifest.yaml`, per FEAT-3036 §
Second-pass decisions -> *Lockfile is keyed by source path, not a scalar*)
against current source content hashes, reporting `FRESH` / `STALE` /
`SOURCE-MISSING` / `OUTPUT-MISSING` per `(template, source)` pair (plus
`NO-LOCK` per template — see § Pre-implementation decisions). Exits non-zero if
anything is stale (CI-friendly; per CLAUDE.md this is exercised by a pytest test
that invokes it, not a hosted CI workflow).

The lockfile is a mapping keyed by rendered source path (not a scalar), so it
can express EPIC-3299's primary use case (one template, many source
documents), not only "one template, one source over time":

```yaml
version: 1
renders:
  docs/risk-register.md:
    sha256: 3f786850e387550fdab836ed7e6dc881de23001b  # of the source bytes
    rendered_at: 2026-08-25T04:12:33Z                 # ISO-8601 UTC, diagnostic only
    output: build/quarterly-risk-report.html          # the artifact FILE, project-root-relative
```

Keys are source paths under the shared path storage rule — project-root-relative
when inside the project root, absolute otherwise, never `..`-prefixed
(§ Pre-implementation decisions, third review; the rule and its
`lockfile.relativize_path` helper are defined in FEAT-3310). `version` is `1`;
an unknown `version` is a `LockfileError`, not a state (§ Pre-implementation
decisions, second review).

### Pre-implementation decisions (2026-08-25 review)

These close ambiguities found in a pre-implementation review of this issue and
FEAT-3310. They are decisions, not open questions.

**The lockfile writer belongs to `extract`/`refresh`, not to `render`.**
`cmd_render` (`render.py:27-88`) receives only `template`, `--data`, and `-o` —
it never reads a source document. To record `renders[<source path>].sha256` it
would have to *assume* that `manifest["source"]` produced the current
`data.json`, which is false whenever `data.json` was hand-authored (the entire
Phase-1 workflow) or extracted from a different source. A render-side write
would stamp `FRESH` against bytes render never read, and `status` would then
certify a stale artifact — inverting the feature. So:

- `cmd_refresh` (FEAT-3310) writes/updates the lockfile after a successful
  render, using the source path and bytes it already holds. **Moved to
  FEAT-3310 by the 2026-08-25 second review** — see § Scope split below.
- `cmd_render` writes a lockfile entry **only** when given a new explicit
  `--source <path>` flag, which asserts "this data.json came from this file."
  Bare `ll-artifact render` writes no lockfile and stays byte-for-byte the
  pure Phase-1 stamp it is today.

Consequences for the rest of this issue: the `cmd_render` docstring/exit-code
edits and the read-only-`templates_dir` failure-path test now apply to the
`--source` path only, and bare `render` cannot regress from 0 to 1.

**`NO-LOCK` is a fourth reported state.** (A fifth, `OUTPUT-MISSING`, is added
by the third review below.) FRESH / STALE / SOURCE-MISSING are
per-`(template, source)` pairs and presuppose a lockfile. An explicitly named
template with no `.llat.lock` (never refreshed — the default state in a fresh
clone if the lockfile is gitignored) reports `NO-LOCK` and exits non-zero,
because "I cannot tell whether this is fresh" must not read as "it is fresh."
In discovery mode (no positional args) templates without a lockfile stay
skipped, per AC below — discovery reports on what is tracked; an explicit
argument asserts the caller expects tracking.

**Exit code: non-zero for STALE, SOURCE-MISSING, and NO-LOCK alike.** Only an
all-FRESH report exits 0. The decision lives in one `_exit_code_for(results)`
function per `doctor.py:125-128`, so it is explicit and directly testable. This
resolves the gap recorded under § Program Design → Decision Rules. Exit code is
`1` (not a new code `2`), leaving `CLI.md:4468`'s `templatize`-only framing of
`2` untouched.

**The lockfile is committed, not gitignored.** The CI use case in § Use Case
only works if the lockfile is in the tree the build checks out; a gitignored
lockfile makes `status` report `NO-LOCK` for everything on a fresh clone. Add
no `.gitignore` entry. Accept that `rendered_at` re-churns the file on every
refresh — it is diagnostic, worth its diff noise, and only `sha256` is
load-bearing for classification.

**`output:` is recorded project-root-relative**, resolved the same way
`cmd_render` resolves `-o` today. One `renders[<source>]` entry holds one
`output`, so re-rendering the same source to a different `-o` is last-write-wins
on that entry. (**Amended by the third review:** `status` still classifies
staleness on `sha256` alone, but it now also checks that the recorded `output`
file *exists* — see § Pre-implementation decisions, third review → OUTPUT-MISSING.
`output`'s value is still never compared to anything.)
Document this rather than keying on `(source, output)`
— multi-destination rendering is not an EPIC-3299 use case, and the simpler key
matches FEAT-3036 § Second-pass decisions.

### Pre-implementation decisions (2026-08-25 second review)

A second review found the decisions above left the lockfile's own failure modes
and this issue's dependency coupling unresolved. These close them.

**Scope split: FEAT-3310 owns the `refresh` writer; this issue owns the reader
and the `render --source` writer.** As originally written, this issue's AC 1
required editing `cmd_refresh` — a function FEAT-3310 *creates* — so nothing
here could be tested end-to-end until FEAT-3310 landed. That coupling is this
issue's top confidence-check concern (80/75). Splitting on the file boundary
instead:

- FEAT-3310 (`extract.py`): `cmd_refresh` writes the lockfile. The write
  contract — atomic replace, merge into existing `renders`, `sha256` over the
  bytes the extraction consumed — lives in FEAT-3310 § Pre-implementation
  decisions (second review).
- This issue (`status.py`, `render.py`): the lockfile *format definition*, the
  reader, the five-state classification, `_exit_code_for`, and `render`'s
  opt-in `--source` writer.

`depends_on: [FEAT-3036, FEAT-3310]` is unchanged — the format is defined here
but consumed there, so the two must stay coordinated; the split only means each
issue's own ACs are verifiable without the other's CLI surface existing.

**`output:` records the rendered artifact FILE path, not the `-o` directory.**
The rule above says "resolved the same way `cmd_render` resolves `-o`", which is
ambiguous: `-o` is a *directory* and the artifact lands at
`output_dir / manifest["output"]` (`render.py:71-79`). The lockfile records the
full file path, project-root-relative — a bare directory would make `output`
useless as the diagnostic context it exists to be.

**A malformed lockfile is an error, not a state.** FRESH / STALE /
SOURCE-MISSING / NO-LOCK do not cover a `.llat.lock` that is unparseable YAML,
is not a top-level mapping, is missing `renders`, has a `renders` that is not a
mapping, or declares an unknown `version`. Adding a fifth reported state would
imply the file is legible enough to classify. Instead `status.py` defines
`LockfileError(ValueError)` and a `load_lockfile(path) -> dict` that fails
closed on each of those, mirroring `load_manifest`'s shape
(`artifact_templates.py:142-189`: required/optional/allowed key frozensets,
module-specific `*Error(ValueError)`). `cmd_status` catches it in a narrow
`except LockfileError` arm, logs, and returns 1 — the same handler shape every
other artifact subcommand uses. This is why FEAT-3310's writer must be atomic:
an interrupted refresh would otherwise leave a truncated file that turns every
subsequent `status` run into an exit-1 error.

**`rendered_at` is ISO-8601 UTC with a trailing `Z`** (e.g.
`2026-08-25T04:12:33Z`), second precision. It is diagnostic only: nothing reads
it back, `status` never classifies on it, and **no test may assert on its
value** — it is the sole nondeterministic field in a subsystem otherwise built
on byte-exact round-trip guarantees (FEAT-3308). Lockfile round-trip tests
assert on `sha256`/`output` and on `rendered_at`'s *format*, never its content.

**An empty report exits 0, deliberately.** Discovery mode with no
lockfile-bearing templates — or with a `templates_dir` that does not exist —
produces zero results, which are vacuously all-FRESH. `_exit_code_for([])`
returns 0. This is the right default (a project with no templates is not
"stale"), but it means a mistyped `artifacts.templates_dir` makes the CI gate
pass silently. Two mitigations, both required: `_exit_code_for`'s docstring
states the empty case explicitly and a unit test pins it; and discovery mode
logs a distinct "no templates with a lockfile found under `<dir>`" line at
info level so the CI log shows *why* it passed. An explicitly named template
still reports NO-LOCK and exits non-zero — the asymmetry is the point.

**Lock path derivation follows `resolve_template`, which is path-first.**
`resolve_template` (`artifact_templates.py:67-78`) tries `Path(template_arg)`
as a directory *before* `templates_dir/<name>.llat`, so a template given as a
path outside `templates_dir` resolves fine and its lockfile lands beside it,
wherever that is. The "lockfile is committed" decision therefore holds only for
templates inside the repo; a template under `/tmp` gets a lockfile under
`/tmp`. Document this in the `status` CLI.md section rather than restricting
resolution — narrowing `resolve_template` would be a Phase-1 behaviour change.
Discovery mode (no positional args) scans only `config.artifacts.templates_dir`
and so is unaffected.

### Pre-implementation decisions (2026-08-25 third review)

A third review found that the classifier certifies artifacts it never checks
for, that the lockfile's key format is unimplementable as written, and that two
smaller paths were unspecified. These close them. They are decisions, not open
questions.

**`OUTPUT-MISSING` is a fifth state: `status` must check that the recorded
artifact still exists.** As specified through the second review, classification
reads *only* the source's sha256. Delete `build/quarterly-risk-report.html`,
leave `docs/risk-register.md` untouched, and `status` reports FRESH and exits 0
— certifying a file that is not on disk. That inverts § Use Case ("before
trusting the last-rendered artifact, run `ll-artifact status` in CI"), which is
the entire reason the feature exists. The lockfile already records `output`
precisely so this is checkable, at the cost of one `is_file()` per entry.

Classification per `(template, source)` pair is a single state, evaluated in
this order — first match wins, so a stale source is never masked by a missing
output and vice versa:

1. `SOURCE-MISSING` — the recorded source path does not exist on disk.
2. `STALE` — the source exists and its current sha256 differs from the recorded one.
3. `OUTPUT-MISSING` — the source hash matches, but the recorded `output` path does not exist.
4. `FRESH` — source hash matches and the output file exists.

`OUTPUT-MISSING` exits non-zero like the rest; `_exit_code_for` still returns 0
only when every item is `FRESH`. Note the interaction with the second review's
"`output` is last-write-wins on the entry": re-rendering the same source to a
different `-o` and then deleting the newer artifact reports `OUTPUT-MISSING`
against the newer path, which is correct — the entry records where the artifact
*was last written*. `output` is therefore no longer purely diagnostic; its
presence is classified on, though its *value* is still never compared to
anything.

**Lockfile keys follow the shared path storage rule, not "always
project-root-relative".** § Expected Behavior above declares `renders` keys to
be project-root-relative source paths, but FEAT-3310 permits an absolute
`manifest.source` and an absolute `<source-file>` argument, and `-o` may resolve
outside the project root. Under the stated rule those become `../../…` chains,
which are fragile to interpret and useless as the diagnostic context `output`
exists to be. FEAT-3310 § Pre-implementation decisions (third review) fixes one
rule for both sides — relative when inside the project root, absolute
otherwise, never `..`-prefixed — behind an exported
`lockfile.relativize_path(path, project_root)`.

This issue's obligation is the *inverse*: `status` resolves a `renders` key (and
an `output` value) by using it as-is when `os.path.isabs`, and resolving it
against `config.project_root` otherwise — **never against cwd**. A cwd-relative
read would make `status` report `SOURCE-MISSING` for entries it wrote itself
whenever it is invoked from a subdirectory. Tested with `status` run from a
subdirectory of the project root, and with an out-of-root absolute source.

**A parseable lockfile with an empty `renders` reports `NO-LOCK` for an
explicitly named template.** `renders: {}` yields zero items, and
`_exit_code_for([])` returns 0 — so `ll-artifact status my-report` exits 0 on an
empty lockfile but 1 when the lockfile is absent, for the same amount of
knowledge. The NO-LOCK rationale ("I cannot tell whether this is fresh must not
read as fresh") covers both. An explicitly named template whose lockfile has no
`renders` entries reports `NO-LOCK`. Discovery mode keeps skipping it, matching
how it already skips lockfile-less templates.

**`render --source <path>` fails loud on a missing source, before rendering.**
`--source` is an assertion ("this data.json came from this file"), and the only
thing it does is produce a sha256. A nonexistent path cannot be hashed, and
writing an entry that is `SOURCE-MISSING` the instant it is written would be
worse than useless. `cmd_render` validates `--source` resolves to an existing
file immediately after resolving the template — before the render, so a bad
`--source` costs nothing — and exits 1 with a typed error naming the resolved
absolute path. Bare `render` (no `--source`) is unaffected.

**`render --source` uses FEAT-3310's `render_to_disk` return value for
`output`.** FEAT-3310 (§ Pre-implementation decisions, third review) extracts
the `-o` resolution / guard / mkdir / write sequence out of `cmd_render` into a
module-level `render_to_disk(...) -> Path`. The `--source` lockfile write here
records that return value; it does not re-derive `output_dir /
manifest["output"]`.

**`learning_tests_required: [yaml]` is mirrored onto FEAT-3310.** The first
machine-written YAML in this subsystem is `write_lockfile`, which ships in
FEAT-3310. The marker stays here (this issue owns the format) but is duplicated
there, where the writing code actually lands.

## Use Case

A user maintains `quarterly-risk-report.llat/`, refreshed periodically
against `docs/risk-register.md` (FEAT-3036 / FEAT-3310). Before trusting the
last-rendered `quarterly-risk-report.html`, they run `ll-artifact status` in
CI to confirm nothing has drifted since the last refresh; a non-zero exit
fails the build if the register changed without a re-render.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/cli/artifact/status.py` (new) — `cmd_status`, `add_status_parser`, the five-state classifier (FRESH / STALE / SOURCE-MISSING / OUTPUT-MISSING / NO-LOCK), and `_exit_code_for(results)`. Imports the format from `cli/artifact/lockfile.py`.
- `scripts/little_loops/cli/artifact/lockfile.py` — **created by FEAT-3310, not by this issue** (FEAT-3310 ships first and its `cmd_refresh` is the first writer). Holds `LockfileError(ValueError)`, `load_lockfile` (fail-closed, mirroring `load_manifest`'s frozenset-validation shape at `artifact_templates.py:142-189`), `write_lockfile` (atomic, merging), and `lock_path_for`. This issue specifies the format and is its only *reader*; if FEAT-3310's implementation diverges from § Expected Behavior here, this issue's spec governs.
- `scripts/little_loops/cli/artifact/render.py` (`cmd_render`, render.py:27-88) — gains a new `--source <path>` flag and, when it is supplied, an existence check on it before the render plus a lockfile-write step after the output write and before `logger.success`/`return 0`. **Third review (2026-08-25):** the output write itself moves into FEAT-3310's `render_to_disk(...) -> Path` helper, whose return value is what the `--source` path records as `output` — this issue must not re-derive `output_dir / manifest["output"]`. Today no lockfile write occurs anywhere in this function (confirmed by direct read — the function logs success and returns immediately after the file write). Note `cmd_render` today has no access to any source document — `--source` is what supplies it, and without the flag no lockfile is written (§ Expected Behavior → Pre-implementation decisions).
- ~~`scripts/little_loops/cli/artifact/extract.py` (`cmd_refresh`, FEAT-3310) — the primary lockfile writer~~ — **moved to FEAT-3310** by the 2026-08-25 second review, so this issue is testable without FEAT-3310's CLI surface existing. This issue still defines the format (`status.py`'s `load_lockfile` + constants) that FEAT-3310's writer imports.
- `scripts/little_loops/cli/artifact/__init__.py` (`main_artifact`, :40-136) — needs `add_status_parser(subparsers)` wired alongside `add_render_parser`/`add_templatize_parser` (:119-120) and a new `args.command == "status"` arm in the dispatch chain (:127-135); the module docstring (:1-15) enumerates every subcommand by originating FEAT ID and needs a `status`/FEAT-3311 entry.
- `docs/reference/CLI.md:4566` — the existing not-yet-implemented note names `status` directly and must be updated/removed once this lands. Unrelated to this issue but visible on the same line: that note also misattributes `extract` to FEAT-3309 (a different, already-completed issue) rather than FEAT-3310.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/artifact/extract.py` (FEAT-3310, not yet created) — `cmd_refresh` is the other half of "render/refresh gain a lockfile-write step" per this issue's own Program Design. FEAT-3310 is entirely unimplemented today: no `extract.py`, no `cmd_extract`/`cmd_refresh`, no `refresh`/`extract` dispatch branch, and no consumption of the manifest's `source` key anywhere in `cli/artifact/` or `artifact_templates.py` (confirmed by direct grep and read). The render-side lockfile-write step can be added independently, since `render.py`/`cmd_render` already exists and is fully implemented; the refresh-side step has no target to attach to until FEAT-3310 lands.
- `scripts/little_loops/config/core.py` (`BRConfig.artifacts`, :476-478) and `scripts/little_loops/config/features.py` (`ArtifactsConfig`, :391-402) — `templates_dir` (default `artifacts/templates`) is how `status`'s "no `<template>` args" discovery mode must enumerate templates, the same source `cmd_render`/`cmd_templatize` already read.

### Conventions in Force
- Subcommand registration: an `add_<name>_parser(subparsers)` function inside the subcommand's own module, called from `main_artifact()` — evidence: `render.py:91`, `templatize.py:965`, wired at `__init__.py:119-120`.
- Handler signature: `cmd_<name>(args, logger) -> int` with narrow `except <DomainError>` arms above a trailing `except Exception as exc: return 1` backstop — evidence: `render.py:27-88`.
- Multi-item classification + exit-code decision: two coexisting, contested shapes elsewhere in the codebase — (a) `verify_private_refs.py`'s flat `list[Finding]` where `bool(findings)` alone decides the exit code (`:200-208`, `:625-634`), and (b) `doctor.py`'s per-item `CheckResult` dataclass with a `Literal[...]` status field plus a dedicated `_exit_code_for(results)` function (`:55-74`, `:125-128`). This issue's FRESH/STALE/SOURCE-MISSING vocabulary is structurally closer to shape (b) — a `Literal[...]` tri-state per item — but neither shape is mandated by the codebase.
- sha256 content-hash pattern: `_sha256_file(path) -> str | None` (`codequery/codegraph.py:124-130`) reads bytes, hashes, and returns `None` on `OSError` rather than raising — the nearest in-repo precedent for the source-hash comparison this issue needs, but it is module-private (not exported from `codequery`) and nothing outside that module imports it, so `status.py` cannot reuse it directly and would define its own copy of the same shape.
- YAML sidecar load pattern: `load_manifest` (`artifact_templates.py:142-189`) reads via `yaml.safe_load`, validates required/optional/allowed key sets (module-level frozensets at `:25-27`), and raises a module-specific `*Error(ValueError)` on any violation — the nearest read-shape precedent for a `.llat.lock` reader. `artifact_templates.py` has no YAML *writer* anywhere to mirror for the write side; this issue's `{version, renders: {<path>: {sha256, rendered_at, output}}}` shape is the first machine-written YAML sidecar in this subsystem — no shared writer utility exists to reuse.
- "No args = act on everything discoverable": no precedent scoped to `cli/artifact/` — both `render` and `templatize` require a positional template argument. The closest codebase-wide shape is `verify_private_refs.py`'s explicit `--all` flag (`scan_all`, `:365-372`), not an implicit empty-positional-list branch — this issue's AC calls for the latter (no `<template>` args → discover all).

### Tests
- `scripts/tests/test_codequery_codegraph.py` (~lines 375-435) — the issue's own cited precedent: temp git repo fixture + inline `hashlib.sha256(...)` computed independently of the module under test + a `.status()` call + assertion on a `freshness` classification field (`"fresh"`/`"stale"`). This precedent's vocabulary is only 2-way; it has no "source missing" analog to mirror for the 3rd state.
- `scripts/tests/test_artifact_templatize.py:394-401` (`TestCmdTemplatizeEndToEnd._run`) — the established in-process end-to-end CLI pattern (save/restore `sys.argv`, call `main_artifact()` directly, no subprocess) an AC-required end-to-end `status` test would follow.
- `scripts/tests/test_feat3036_artifact_templates.py:375` (`TestCmdRender`), `:458` (`TestArtifactCLIDispatchRender`) — alternative handler-level + dispatch-mock test style, also available as precedent (contested against the templatize style above).
- No `scripts/tests/test_feat3311_artifact_status.py` (or similarly named) test file exists yet.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_decisions.py:185-208` (`TestSaveDecisions`: `test_writes_valid_yaml`, `test_round_trip_preserves_fields`) — closest existing "write YAML, read back, assert shape" round-trip pattern in the suite; use as the template for the lockfile write/read test, since `artifact_templates.py` has no prior YAML-writer precedent to mirror.
- `scripts/tests/test_artifact_templatize.py:750-813` (`TestCmdTemplatizeDiscoveryBranch._run` + `main_artifact()`) — precedent for asserting a non-zero exit code through the full CLI dispatch path; the model for `status`'s required non-zero-exit-on-stale end-to-end test.

### Configuration
- `scripts/little_loops/config-schema.json:1875-1895` — `artifacts.templates_dir` (default `artifacts/templates`), read via `BRConfig(Path.cwd())`; no lockfile-related config knob currently exists (e.g., no override for the lockfile's naming/location).

_Wiring pass added by `/ll:wire-issue`:_
- `.gitignore:47-49` — the only existing lock-file patterns (`**/.*.lock`, `**/.*.lock.lock`) are dotfile-prefixed globs scoped to "the hook system" (per the file's own comment) and do **not** match `<template-name>.llat.lock` (no leading dot). No `.gitignore` entry currently covers `artifacts/templates/**/*.llat.lock`. **Resolved 2026-08-25**: the lockfile is committed — leave `.gitignore` untouched. Rationale: § Use Case's CI check only works against a checked-out lockfile; a gitignored one makes `status` report NO-LOCK for everything on a fresh clone.

### Documentation
- `docs/reference/CLI.md:4509-4530` (`#### ll-artifact render`) — the prose → `**Flags:**` table → `**Examples:**` → `**Exit codes:**` shape a new `#### ll-artifact status` section must follow, per this issue's own AC.
- `docs/reference/CLI.md:4566` — the not-yet-implemented note naming `status` directly; must be updated/removed once this lands.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:4459-4466` — the `### ll-artifact` `**Subcommands:**` table lists only `policy-builder`/`design-md export`/`render`/`templatize`; needs a new `status` row, distinct from the new `#### ll-artifact status` prose section already noted above.
- `docs/reference/CLI.md:4468` — the top-level Exit codes summary line frames `2` as a `templatize`-only carve-out ("see `templatize` below"); if `status`'s non-zero-on-stale exit reuses `1` this line is unaffected, but if any revision gives `status` a distinct non-1 exit code, this line's phrasing needs to cover both subcommands.
- `scripts/little_loops/cli/artifact/__init__.py:65-69` — `main_artifact()`'s own argparse epilog hard-codes an `Exit codes:` block (`0`/`1`/`2` bullets) as live `--help` text, separate from CLI.md prose and from the module docstring already noted above. Needs a new bullet for `status`'s exit behavior regardless of which exit code it uses.
- `scripts/little_loops/cli/artifact/render.py:27-32` — `cmd_render`'s own docstring states "Returns 0 on success, 1 on error" and enumerates specific error causes; needs a bullet added for a lockfile-write failure once that step is inserted (see Decision Rules below), since the trailing `except Exception` (`render.py:86-88`) will now catch lockfile-write errors too.

## Program Design

### Call Path

`cmd_status` (new `cli/artifact/status.py`) reads the `<template>.llat.lock`
sibling file(s) beside each resolved template (via
`little_loops.artifact_templates.resolve_template`, unchanged from
FEAT-3036), computes current sha256 of each recorded source path, and
compares — all reads going through `cli/artifact/lockfile.py`'s `load_lockfile`
(created by FEAT-3310, specified here). `refresh` (FEAT-3310) writes that file
after a successful render — the sha256/rendered_at/output triple keyed by
source path, per FEAT-3036 § Second-pass decisions -> *Lockfile is keyed by
source path, not a scalar*. `render` gains the same write **only behind a new
`--source` flag**, since bare `cmd_render` never reads a source document and
cannot honestly hash one (§ Expected Behavior -> Pre-implementation decisions);
that `render` half is this issue's, the `refresh` half is FEAT-3310's
(§ Pre-implementation decisions, second review -> Scope split).

### Tests

New coverage follows `test_codequery_codegraph.py`'s structural template for
sha256 content-hash staleness detection (temp dir + a rendered lockfile
fixture, assert on `.status()`'s FRESH/STALE/SOURCE-MISSING/OUTPUT-MISSING classification
and exit code) — the closest in-repo precedent (FEAT-3036 § Tests).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

### Types

- The lockfile has no existing type in the codebase — this issue's own `version: 1 / renders: {<source-path>: {sha256, rendered_at, output}}` shape (issue body, § Expected Behavior) is the first place this shape appears; there is no dataclass or schema to reuse.
- `ArtifactTemplate` (`artifact_templates.py:48-64`) — existing dataclass (`root: Path`, `manifest: dict`), unchanged; `resolve_template`'s return value is used to derive the sibling lock path.
- Manifest optional key `source: str` (`artifact_templates.py:26`, `_MANIFEST_OPTIONAL_KEYS`) exists in the schema-allowed key set but is unread by `artifact_templates.py` — `status` does not need it, since the lockfile itself records source paths directly as `renders` mapping keys, independent of the manifest.

### Signatures

- `resolve_template(template_arg: str, templates_dir: Path) -> Path` (`artifact_templates.py:67`) — raises `TemplateResolutionError`; reused unchanged by `cmd_status` to resolve each `<template>` argument to its root directory, per this issue's own Call Path.
- `load_manifest(root: Path) -> dict[str, Any]` (`artifact_templates.py:142`) — raises `ManifestError`; the nearest read-shape precedent for a lockfile reader, but there is no equivalent writer in the module (see Integration Map → Conventions in Force).
- No sha256 helper is importable across modules: `_sha256_file(path: Path) -> str | None` (`codequery/codegraph.py:124-130`) is module-private and unexported — `status.py`'s current-hash computation is new code, not a reuse of an existing function.
- `render.py::cmd_render` (`render.py:27-88`) — the write point for the render-side lockfile-write step is immediately after `out_path.write_text(rendered, encoding="utf-8")` and before the trailing `logger.success(...)`/`return 0`.
- Lock path derivation: `resolve_template` returns a directory ending in `.llat` (e.g. `templates_dir / "foo.llat"`); "sibling file next to the template" (issue body, § Expected Behavior) resolves to `<that directory>.parent / f"{<that directory>.name}.lock"`, i.e. `foo.llat.lock` alongside `foo.llat/`, matching the issue's own example lockfile name.

### Decision Rules

- FRESH/STALE classification per `(template, source)` pair: FRESH iff the source path exists on disk and its current sha256 equals the `renders[source_path].sha256` recorded in the lockfile; STALE iff the source path exists but the current sha256 differs from the recorded one.
- SOURCE-MISSING: the issue's own Expected Behavior names this as a distinct third state (not folded into STALE) for a recorded source path that no longer exists on disk — this differs from `_sha256_file`'s precedent (`codequery/codegraph.py:124-130`), which returns `None` on a missing/unreadable file and lets the caller collapse that into "changed" (2-way). This issue's own tri-state vocabulary is not fully pinned by the codebase precedent it cites.
- NO-LOCK: a fourth state for an explicitly named template with no `.llat.lock` sibling (**added 2026-08-25**, § Expected Behavior → Pre-implementation decisions). Discovery mode skips lockfile-less templates instead.
- Exit-code scope — **resolved 2026-08-25**: `status` exits non-zero unless every reported item is FRESH; STALE, SOURCE-MISSING, and NO-LOCK all fail, via a single `_exit_code_for(results)` function per `doctor.py`'s precedent (`:125-128`). The exit code is `1`, so `CLI.md:4468`'s framing of `2` as a `templatize`-only carve-out needs no change. (Earlier text left this open; the issue's § Expected Behavior and ACs now pin it.)
- Empty report (**added 2026-08-25, second review**): `_exit_code_for([])` returns 0 — zero results are vacuously all-FRESH, and a project with no templates is not stale. Stated in the function's docstring, pinned by a unit test, and paired with a distinct info-level "no templates with a lockfile found under `<dir>`" log line in discovery mode so a mistyped `templates_dir` is visible in the CI log rather than passing silently.
- Malformed lockfile (**added 2026-08-25, second review**): not a fifth state. `load_lockfile` raises `LockfileError` on unparseable YAML, a non-mapping top level, a missing or non-mapping `renders`, or an unknown `version`; `cmd_status` catches it in a narrow arm and returns 1. Classification states presuppose a legible file.
- `rendered_at` (**added 2026-08-25, second review**): ISO-8601 UTC with a trailing `Z`, second precision, diagnostic only. Never classified on, and no test asserts its value — only its format.
- OUTPUT-MISSING (**added 2026-08-25, third review**): a fifth state. Classification per `(template, source)` is first-match-wins in the order SOURCE-MISSING → STALE → OUTPUT-MISSING → FRESH, so `status` never reports FRESH for an entry whose recorded `output` file has been deleted. `output`'s *presence* is now classified on; its *value* is still never compared to anything. Exits non-zero like STALE.
- Path resolution on read (**added 2026-08-25, third review**): a `renders` key or `output` value that `os.path.isabs` is used as-is; anything else resolves against `config.project_root`, never against cwd — the exact inverse of FEAT-3310's `lockfile.relativize_path` writer rule. A cwd-relative read would make `status` invoked from a subdirectory report SOURCE-MISSING for entries it wrote itself.
- Empty `renders` (**added 2026-08-25, third review**): an explicitly named template whose lockfile parses but carries zero `renders` entries reports NO-LOCK, not an empty exit-0 report. Discovery mode skips it, as it already skips lockfile-less templates.
- `render --source` validation (**added 2026-08-25, third review**): a `--source` that does not resolve to an existing file exits 1 with a typed error naming the resolved absolute path, checked immediately after template resolution and before the render — a bad `--source` must not cost a render.

_Wiring pass added by `/ll:wire-issue`:_
- No existing test asserts exhaustive output-directory contents on `cmd_render` (`test_feat3036_artifact_templates.py`'s `TestCmdRender` checks only targeted `(out_dir / "report.html")` existence/content, never directory-listing counts) — the planned lockfile-write step will not break any existing assertion there. However, no existing `TestCmdRender` case exercises a read-only/unwritable `templates_dir`, so a lockfile-write failure turning a previously-0 render into a 1 is currently untested — add this case.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

1. `cli/artifact/lockfile.py` — created by **FEAT-3310** (it ships first and its `cmd_refresh` is the first writer), holding the whole format: the `{version, renders: {<source>: {sha256, rendered_at, output}}}` shape and its key frozensets, `LockfileError(ValueError)`, `load_lockfile(path) -> dict` (fail-closed), `write_lockfile(path, entries)` (atomic temp-sibling + `os.replace`, merging into any existing `renders`), and `lock_path_for(root) -> Path`. This issue *consumes* it from `status.py` and from `render.py`'s `--source` path, and owns its spec (§ Expected Behavior); it does not create the module. `render.py::cmd_render` calls `write_lockfile` **only** when a new `--source <path>` flag is supplied; bare `render` is untouched, so `test_feat3036_artifact_templates.py`'s existing `TestCmdRender`/`TestArtifactCLIDispatchRender` suites pass unmodified (§ Expected Behavior → Pre-implementation decisions).
2. `ll-artifact status` is wired into `main_artifact()` via a new `add_status_parser`/`cmd_status` in `cli/artifact/status.py`, following the `add_<name>_parser` + `cmd_<name>(args, logger) -> int` convention every other artifact subcommand uses (`render.py:91`, `render.py:27`, `templatize.py:965`).
3. `cmd_status` reads each resolved template's `<template>.llat.lock`, resolves each recorded source path (absolute as-is, otherwise against `config.project_root`), computes its current sha256, and classifies each `(template, source)` pair first-match-wins as SOURCE-MISSING → STALE → OUTPUT-MISSING → FRESH — or the whole template as NO-LOCK when explicitly named with no lockfile *or* with an empty `renders` — per `## Program Design` → Decision Rules. A single `_exit_code_for(results)` maps the report to the exit code: 0 only if every item is FRESH.
4. With no `<template>` positional args, `status` enumerates every template under `config.artifacts.templates_dir` that has a `.llat.lock` sibling, skipping the rest — no in-repo precedent for this discovery shape exists (`render`/`templatize` both require a positional template), so this is new surface rather than an extension of an existing pattern. A missing or empty `templates_dir` yields an empty report, exit 0, plus a distinct info-level log line naming the directory scanned (§ Pre-implementation decisions, second review).
4b. A `.llat.lock` that `load_lockfile` rejects raises `LockfileError`, caught by a narrow arm in `cmd_status` that logs and returns 1 — malformed is an error, not a fifth state.
5. `docs/reference/CLI.md` gains a `#### ll-artifact status` section (flags/examples/exit codes, following the `render`/`templatize` section shape) and its existing not-yet-implemented note at line 4566 no longer names `status`.
6. `python -m pytest scripts/tests/` exits 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/reference/CLI.md:4459-4466` — add a `status` row to the `**Subcommands:**` table.
- Update `scripts/little_loops/cli/artifact/__init__.py:65-69` — add a `status` bullet to the `main_artifact()` argparse epilog `Exit codes:` block.
- Update `scripts/little_loops/cli/artifact/render.py:27-32` — add a `--source` flag and a lockfile-write-failure bullet to `cmd_render`'s docstring, scoped to the `--source` path only.
- Add a `TestCmdRender` case exercising a read-only/unwritable `templates_dir` **with `--source`** to confirm the lockfile-write failure path exits 1, plus a case confirming bare `render` on the same read-only tree still exits 0.
- **Resolved 2026-08-25**: `<template>.llat.lock` is committed, not gitignored — no `.gitignore` change (see § Expected Behavior → Pre-implementation decisions).
- Coordinate `docs/reference/CLI.md:4566` edit with FEAT-3310, which independently edits the same line.

_Second-review additions (2026-08-25):_
- The `#### ll-artifact status` CLI.md section must also document: `output`'s file-vs-directory semantics, `rendered_at`'s ISO-8601-UTC format and diagnostic-only status, that a malformed lockfile is an exit-1 `LockfileError` rather than a reported state, that an empty report exits 0, and that a template resolved by path outside `templates_dir` gets its lockfile beside it (so the "committed lockfile" guarantee holds only for in-repo templates).
_Third-review additions (2026-08-25):_
- `cmd_status` checks each entry's recorded `output` for existence (OUTPUT-MISSING), resolved by the same absolute-vs-project-root rule as the `renders` key.
- `cmd_render` validates `--source` exists before rendering, and takes its lockfile `output` from FEAT-3310's `render_to_disk` return value rather than re-deriving it.
- The `#### ll-artifact status` CLI.md section documents five states (FRESH / STALE / SOURCE-MISSING / OUTPUT-MISSING / NO-LOCK), that an empty `renders` on an explicitly named template reports NO-LOCK, and that lockfile paths are project-root-relative only when inside the project root (absolute otherwise) and are never resolved against cwd.
- Add tests for: an OUTPUT-MISSING entry (unchanged source, deleted artifact) exiting non-zero; `status` run from a subdirectory of the project root resolving relative keys correctly; an out-of-root absolute source key; an explicitly named template with `renders: {}` reporting NO-LOCK; `render --source` naming a nonexistent file exiting 1 with no artifact written.
- Do **not** add a test asserting the repo's `.gitignore` does not match `*.llat.lock` (dropped AC, see § Acceptance Criteria). little-loops ships into consuming projects whose ignore rules this repo does not control, so such a test proves nothing about the § Use Case CI scenario it would exist to protect. The decision stands as documentation.

## Impact

- **Priority**: P3 — serves EPIC-3299's secondary use case (one template,
  one bound source refreshed over time); this is where the stated
  content-drift problem is actually killed.
- **Effort**: Medium — reduced by the 2026-08-25 second review, which moved the
  `refresh` lockfile write and the `lockfile.py` module itself to FEAT-3310;
  nudged back up by the third review's fifth state (`OUTPUT-MISSING`) and its
  path-resolution tests.
- **Risk**: Low — additive. `render` gains an opt-in `--source` flag but its
  default path is byte-for-byte unchanged (FEAT-3310's `render_to_disk`
  extraction is likewise behaviour-preserving). FEAT-3310 must still land first
  (it creates `lockfile.py`), but every AC here is now verifiable against
  `status` + `render --source` alone, without `extract`/`refresh` existing —
  which was this issue's top confidence-check concern.

## Acceptance Criteria

- [ ] The lockfile format has a single home in `cli/artifact/lockfile.py`
      (created by FEAT-3310, specified here), including the shared
      `relativize_path(path, project_root)` path rule that `status` inverts on
      read: `load_lockfile` fails closed with
      `LockfileError` on unparseable YAML, a non-mapping top level, a
      missing/non-mapping `renders`, and an unknown `version` — each
      unit-tested; `write_lockfile` writes atomically (temp sibling +
      `os.replace`) and merges into an existing `renders` mapping rather than
      replacing it. `status` and `render --source` both import it; neither
      redefines the shape.
- [ ] `output` records the rendered artifact **file** path — not the `-o`
      directory — stored project-root-relative when inside the project root and
      absolute otherwise (never `..`-prefixed), per the shared path rule. `rendered_at` is ISO-8601 UTC with a trailing `Z`; the
      round-trip test asserts its format only, never its value.
- [ ] A malformed `.llat.lock` exits 1 via a narrow `except LockfileError` arm
      in `cmd_status` — it is not reported as a fifth classification state.
- [ ] ~~Phase 2's `refresh` writes/updates a `<template-name>.llat.lock`~~ —
      **moved to FEAT-3310** by the 2026-08-25 second review, so this issue is
      verifiable without FEAT-3310's CLI surface (§ Pre-implementation
      decisions, second review → Scope split). This issue still specifies the
      format that write must satisfy.
- [ ] `render` writes a lockfile entry only when given a new explicit
      `--source <path>` flag; bare `ll-artifact render` writes no lockfile and
      is behaviourally unchanged from Phase 1 (see § Expected Behavior →
      Pre-implementation decisions). A `--source` that does not resolve to an
      existing file exits 1 with a typed error naming the resolved absolute
      path, checked *before* the render so no artifact is written.
- [ ] `render --source` records `output` from FEAT-3310's `render_to_disk`
      return value; it does not re-derive `output_dir / manifest.output`.
- [ ] `ll-artifact status [<template> ...]` reports
      FRESH/STALE/SOURCE-MISSING/OUTPUT-MISSING per `(template, source)` pair,
      first-match-wins in the order SOURCE-MISSING → STALE → OUTPUT-MISSING →
      FRESH, and `NO-LOCK` for an explicitly named template with no lockfile
      **or with a lockfile whose `renders` is empty**.
- [ ] `OUTPUT-MISSING` is reported when the source hash matches but the
      recorded `output` file no longer exists — `status` never certifies an
      artifact that is not on disk (§ Pre-implementation decisions, third
      review). Tested by deleting the rendered artifact and leaving the source
      untouched: exit non-zero, state `OUTPUT-MISSING`.
- [ ] `status` resolves a `renders` key and an `output` value as absolute when
      `os.path.isabs`, otherwise against `config.project_root` — never against
      cwd. Tested with `status` invoked from a subdirectory of the project root
      (entries still resolve) and with an out-of-root absolute source key.
- [ ] `status` exits non-zero unless every reported item is FRESH — STALE,
      SOURCE-MISSING, OUTPUT-MISSING, and NO-LOCK all fail. The rule lives in a
      single `_exit_code_for(results)` function and is unit-tested per state.
- [ ] With no `<template>` args, `status` reports on every template
      discovered under `config.artifacts.templates_dir` that has a lockfile;
      lockfile-less templates are skipped in this mode (not NO-LOCK).
- [ ] `_exit_code_for([])` returns 0 — an empty report is vacuously all-FRESH.
      Stated in the function's docstring and pinned by a unit test. Discovery
      mode additionally logs a distinct "no templates with a lockfile found
      under `<dir>`" line, so a mistyped `templates_dir` is visible in the CI
      log rather than passing silently. Tested with a `templates_dir` that
      does not exist.
- [ ] A pytest test invokes `ll-artifact status` end-to-end (subprocess or
      direct `cmd_status` call) and asserts the non-zero exit on a stale
      source — this is the "CI gate" per CLAUDE.md's local-suite policy, not
      a hosted workflow.
- [ ] The lockfile is committed, not gitignored: no `.gitignore` entry is
      added. **No test asserts this** — the 2026-08-25 second review dropped
      the originally-planned ignore-rule assertion, because little-loops ships
      into consuming projects whose `.gitignore` this repo does not control,
      so a test over *this* repo's ignore rules proves nothing about the
      § Use Case CI scenario. The decision is carried as documentation in the
      `status` CLI.md section instead.
- [ ] `docs/reference/CLI.md` documents `status`, the five reported states
      (FRESH / STALE / SOURCE-MISSING / OUTPUT-MISSING / NO-LOCK) and their
      first-match-wins order, the exit-code rule (including the empty-report-exits-0 case), that a
      malformed lockfile is an error rather than a state, and the lockfile
      format — `output`'s project-root-relative **file** path and
      last-write-wins semantics (and that its *presence* is classified on, via
      OUTPUT-MISSING, while its value is never compared), the
      relative-when-inside-the-project-root / absolute-otherwise path rule for
      both keys and `output`, `rendered_at`'s ISO-8601-UTC
      diagnostic-only status, that the lockfile is committed rather than
      ignored, and that a template resolved by path outside `templates_dir`
      gets its lockfile beside it wherever that is.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-24 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-25_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 75/100 → MODERATE

### Concerns
- ~~Dependency FEAT-3310 (`extract.py`/`cmd_refresh`, the primary lockfile writer) is still `open`/unimplemented; only the `render.py --source` half of this issue is independently buildable today, so full end-to-end status coverage is blocked on FEAT-3310 landing first.~~ **Addressed 2026-08-25 (second review):** the `refresh` write moved to FEAT-3310 and every AC here is now satisfiable via `status` + `render --source`. FEAT-3310 still ships first (it creates `lockfile.py`), but this issue no longer edits a function another issue creates.
- Criterion 4 (Issue Well-Specified) is capped at 10/20 by `format-check`'s `stale_cli_flag` finding (`ll-artifact status` doesn't exist yet) — expected for a forward-looking design claim on unimplemented CLI surface, not a real specification gap.
- The FRESH/STALE/SOURCE-MISSING/NO-LOCK four-state classification has no exact in-repo precedent (`test_codequery_codegraph.py`'s sha256-staleness pattern is only 2-way) — test design for the tri/four-state cases will need original work, not a direct port.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-24_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Concerns
- `status.py`'s Program Design imports `cli/artifact/lockfile.py`, which this issue's own Integration Map assigns to FEAT-3310 to create — FEAT-3310 is still `open`. The 2026-08-25 second review already decoupled AC *testability* (every AC here is verifiable via `status` + `render --source` alone), but implementation still needs FEAT-3310 to land first (or a stub `lockfile.py`) before `status.py` has a module to import.
- Criterion 4 (Issue Well-Specified) is capped at 10/20 by `format-check`'s `stale_cli_flag` finding (`ll-artifact status` doesn't exist yet) — expected for a forward-looking design claim on unimplemented CLI surface, not a real specification gap.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-24_

**Readiness Score**: 80/100 → STOP - ADDRESS GAPS (hard override)
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Hard Override
- **DEP_FAIL**: `depends_on` lists `FEAT-3310`, whose current status is `open`
  (not `done`/`cancelled`). Confirmed by direct read: `scripts/little_loops/cli/artifact/`
  contains only `__init__.py`, `design_md.py`, `discover.py`, `policy_builder.py`,
  `render.py`, `templatize.py` — no `lockfile.py` and no `extract.py` exist yet, and
  `render.py` has no `--source` flag. This issue's own Program Design has
  `status.py` import `cli/artifact/lockfile.py`, which FEAT-3310 creates. Per the
  dependency gate, an unresolved `depends_on` on a non-done issue is a hard
  override to STOP regardless of score, even though the 2026-08-25 second-review
  scope split makes every AC here independently *testable* without FEAT-3310's
  CLI surface existing — the implementation still cannot land until FEAT-3310
  ships `lockfile.py` (or a stub of it exists).

### Gaps to Address
- Land FEAT-3310 (or at minimum its `lockfile.py` module: `LockfileError`,
  `load_lockfile`, `write_lockfile`, `lock_path_for`) before starting this
  issue's implementation.

### Concerns
- Criterion 4 (Issue Well-Specified) is capped at 15/20 by `format-check`'s
  `stale_cli_flag` finding (`ll-artifact status (no such subcommand)`) — expected
  for a forward-looking design claim on unimplemented CLI surface, not a real
  specification gap.
- `format-check`'s `soft_dep_hard_edge: [FEAT-3310]` independently confirms the
  dependency is not merely a soft/documentation coupling but a real import edge
  (`status.py` and `render.py --source` both import `lockfile.py`).

## Session Log
- `/ll:manage-issue` - 2026-08-25T14:38:23 - `831bd8a2-c37a-4552-a3b4-987cdb9a2bf3.jsonl`
- `/ll:confidence-check` - 2026-08-25T14:23:01 - `6f7c0860-0a4f-4797-a714-893d8c560ffe.jsonl`
- `/ll:confidence-check` - 2026-08-25T03:54:55 - `67559544-9757-4873-8ba3-963fe9f9ebb2.jsonl`
- `/ll:confidence-check` - 2026-08-25T03:42:12 - `3906fc07-f9f6-4960-99f5-5a221177c28d.jsonl`
- `/ll:confidence-check` - 2026-08-25T03:27:46 - `ea0c7571-8966-43cb-ad8b-4e022c051b10.jsonl`
- `/ll:wire-issue` - 2026-08-25T03:17:17 - `5da7f41e-bb5f-4d4a-b24d-114a6e916228.jsonl`
- `/ll:refine-issue` - 2026-08-25T03:09:16 - `f224d8be-3c42-4b3a-8a3e-ebc438693eb8.jsonl`
