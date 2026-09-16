---
id: FEAT-3485
type: FEAT
title: Decision-record to open-code-review rule exporter
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T04:15:42Z'
learning_tests_required:
- open-code-review
decision_needed: false
confidence_score: 98
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-3485: Decision-record to open-code-review rule exporter

## Summary

Export active required decision rules into open-code-review's (OCR, https://github.com/alibaba/open-code-review) `.opencodereview/rule.json`, so OCR's shipped review plugins enforce little-loops decisions mechanically at review time. Decisions are currently recorded but enforced only through prose (`.claude/CLAUDE.md`, and the `## Active Rules` block that `sync_to_local_md` writes into `.ll/ll.local.md`).

This is piece 1 of a two-piece OCR integration; piece 2 (a delegate-mode review loop that runs `ocr delegate preview` / `ocr delegate rule` as FSM shell states) is planned separately and consumes the same `rule.json`.

**Design stance (revised 2026-09-16):** OCR is not the first rule-export target — `sync_to_local_md()` (`scripts/little_loops/decisions_sync.py:31`) already is one, rendering active required `RuleEntry`s to Claude Code's rule surface. This issue therefore (a) extracts the rule-selection step both exporters share, (b) adds the one genuinely target-agnostic field the rules are missing (a path scope), and (c) adds OCR as a second thin exporter. It does **not** introduce a new intermediate `RuleRecord` type or a lazy-import registry — `RuleEntry` is already the IR, and the `adapters/core.py`-style registry waits for a third target (rule of three).

**Interface vs. implementation (revised 2026-09-16, review):** the *implementation* stays OCR-specific (grouping/folding logic is a consequence of OCR's first-match-wins semantics and would not be shared by per-file targets like Cursor `.mdc` or Copilot `applyTo:`), but the *user-facing surfaces* are target-keyed from day one because they are expensive to rename later (CLI subparser, docs table, config schema, `ll-adapt` mirror gates):

- CLI is `ll-issues decisions export --target ocr`, not `export-ocr`. A third target is a new choice value, not a new subcommand.
- Config key is `decisions.export.scope_globs` (target-agnostic; scope is meaningful for every target), with any future OCR-only knobs under `decisions.export.ocr.*`.
- `decisions_export.py` exposes `export_rules(rules, target, output_dir, *, scope_globs)` dispatching over a plain `_EXPORTERS: dict[str, Callable]` with one entry. Five lines, eager imports, no Protocol.

Do **not** fold this into the `ll-adapt` host emitters: OCR is a review tool, not a host, and `sync_to_local_md` has different semantics (patches a section of an existing file, auto-runs on `promote`). Sharing the selector is the right amount of coupling.

## Current Behavior

Decisions are recorded via `ll-issues decisions` (`.ll/decisions.yaml` / `.ll/decisions.d/`). The only programmatic consumer that renders them outward is `sync_to_local_md()`, which inlines the selection logic (list `type="rule"` → keep `enforcement == "required"` → `resolve_active()`) and writes free-text bullets to `.ll/ll.local.md`. Nothing consumes decision records during code review, and `RuleEntry` has no way to say which files a rule applies to.

## Expected Behavior

`ll-issues decisions export --target ocr` writes `.opencodereview/rule.json` covering all active (non-superseded) required rules, correctly shaped for OCR's first-match-wins resolution, so OCR flags violations without an agent recalling the prose. Re-running over an unchanged decision set is a no-op on file content.

## Motivation

- Closes the loop between recording a decision and enforcing it mechanically.
- Removes reliance on agent recall for checkable rules.
- Fixes the pre-existing duplication risk: a second exporter that re-inlines `sync_to_local_md`'s selection logic would drift from it. Sharing one selector makes "what counts as an exportable rule" a single definition.
- Establishes the `rule.json` shape piece 2 consumes.

## Proposed Solution

Three layers, sized to the problem:

1. **Shared selector (target-agnostic, refactor of existing code).** Add `active_required_rules(path: Path | None = None) -> list[RuleEntry]` to `scripts/little_loops/decisions.py`, lifting the three-step filter out of `sync_to_local_md()` (`decisions_sync.py:40-45`) and making `sync_to_local_md` call it. **Do not add a sort.** `load_decisions()` (`decisions.py:385`) returns flat-file entries first, then fragments sorted by `(timestamp, filename)`; that union is already deterministic but is *not* globally timestamp-ordered, so a `(timestamp, id)` sort would reorder `ll.local.md` bullets for any log where flat and fragment entries interleave in time and break AC #6. Load order is what every exporter needs for idempotency, and preserving it is what makes the `sync_to_local_md` refactor a true no-op.

2. **Path scope on the rule itself (target-agnostic, small schema addition).** Add `paths: list[str] = field(default_factory=list)` to `RuleEntry` (`decisions.py:106`); empty means repo-wide. `from_dict` must `copy.pop("paths", [])` explicitly — today unknown keys fall into `extra` (`decisions.py:137`), so without the pop a legacy `paths` key would land in both places. `to_dict` emits `paths` **only when non-empty**: `to_dict()` feeds `update_entry`, `save_decisions`, and `add_entry`, and an unconditional `paths: []` would rewrite every existing fragment/compacted YAML and trip existing `to_dict` equality tests. Expose it on `ll-issues decisions add --type rule` and `promote` as a repeatable `--path <glob>` flag; `_cmd_promote` builds the `RuleEntry` field-by-field (`cli/issues/decisions.py:938`), so that constructor call gains `paths=`. This is the only field the current model lacks that *every* plausible rule-engine target needs (OCR `path`, Cursor `.mdc` `globs:`, Copilot `applyTo:`). Do **not** add `severity`: OCR has no severity field, `enforcement` already gates inclusion, and no target consumes a graded value.

3. **Target-keyed exporter seam + OCR exporter.** New module `scripts/little_loops/decisions_export.py` holding:
   - `export_rules(rules: list[RuleEntry], target: str, output_dir: Path, *, scope_globs: list[str] | None = None) -> Path` — public entry point; looks up `target` in `_EXPORTERS: dict[str, Callable[..., Path]]` and raises `ValueError` listing `sorted(_EXPORTERS)` on an unknown target.
   - `_export_ocr(rules, output_dir, *, scope_globs) -> Path` — the only OCR-specific code; written via `atomic_write_json()`. **Pure**: it never reads config, cwd, or stderr. `scope_globs=None` means `["**/*"]`, nothing more.
   - `_EXPORTERS = {"ocr": _export_ocr}` — plain eager dict. A future Cursor/Copilot exporter is one private function plus one dict entry. No `Protocol`, no `importlib`; the `adapters/core.py` lazy-map pattern is reserved for a third target *and* an actual import cycle.

4. **Scope resolution lives in the CLI, not the library.** `_cmd_export` resolves `scope_globs` with this precedence and passes an explicit list: `--scope` (repeatable) → `decisions.export.scope_globs` from config → `[f"{config.project.src_dir.rstrip('/')}/**/*"]` → `["**/*"]` with a stderr warning about system-rule replacement. The `rstrip("/")` matters: this repo's `src_dir` is `scripts/`, and the naive f-string yields `scripts//**/*`. Keeping config out of `decisions_export.py` keeps the module testable with no project root.

### OCR emission rules (correctness, not cosmetics)

Proven in `.ll/learning-tests/open-code-review.md` (`status: proven`): `rule.json` = `{"exclude"?: string[], "rules": [{"path": <one glob>, "rule": <free text>}, ...]}`; the **first** `rules[]` entry whose glob matches a file wins, by declaration order, not specificity; a matching project entry **replaces** OCR's embedded system rules (e.g. `python.md`) for that file; no severity field exists.

Consequences the adapter must implement:

- **N repo-wide rules cannot be N entries.** Only the first `**/*` entry would ever fire. Group rules by path glob; emit one `rules[]` entry per distinct glob, most specific first; each scoped entry's `rule` body = that glob's rules **plus all repo-wide rules**, since first-match shadows anything later; the final catch-all entries (one per `scope_globs` value) hold the repo-wide set alone.
- **Specificity sort key is exactly** `_glob_sort_key(g) = (-len(literal prefix before the first wildcard char), count of "*" and "**" segments, g)`. Longest literal prefix is primary, fewer wildcards breaks ties, lexical makes it total. Examples: `scripts/fsm/**/*` < `scripts/**/*.py` < `scripts/**/*` < `**/*.py`.
- **Scoped-vs-scoped overlap is a known limitation.** Folding handles repo-wide rules only. Two scoped globs that overlap without nesting (e.g. `**/*.py` and `scripts/fsm/**/*`) still shadow each other under first-match-wins: a file under `scripts/fsm/` gets only the `scripts/fsm/**/*` entry. Document this in the guide; optionally warn on stderr when one glob's literal prefix is a prefix of another's and their suffixes differ. Do not attempt general glob-intersection folding.
- **A catch-all entry replaces OCR's built-in language rules for every matched file.** It does not merely hide them; OCR resolves exactly one entry per file and the project layer outranks the embedded `python.md`. Default `scope_globs` to the project's `src_dir` (e.g. `scripts/**/*`, which in this repo also covers `scripts/tests/`) rather than `**/*`, and prepend a fixed line to every emitted body stating that the file's language conventions (OCR's system rules) still apply and are not restated here. The docs must say "replaces", not "reminds". Piece 2 can override `scope_globs` if it wants true repo-wide coverage.
- **Rule body format** per entry: one bullet per rule, `- <rule text> (decision <id>)`, so review output is traceable back to the record. `rationale` is omitted (keeps bodies short; the id is the pointer).
- **Don't emit `exclude`.** It only gates `ocr review --preview` file selection and is a project-level choice, not a decision.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis (retained, condensed):_

- Two canonical-form-plus-adapter precedents exist: `host_runner.py`'s `resolve_host()` (single file, eager `dict[str, type]` registry) and `adapters/core.py`'s `resolve_emitter()` (one file per target, lazy `importlib`, existing **only** to break a real circular import per its docstring at `:47-52`). Neither cycle exists here, so a single eager module is correct; the lazy pattern is the model for a registry *if and when* a third target appears.
- `resolve_active()` (`decisions.py:495-503`) is a pure set-membership filter: it drops any entry whose `id` appears in another entry's `supersedes`. Only `RuleEntry` and `CouplingEntry` carry `supersedes`.
- `CouplingEntry.if_changed` is the only existing glob field, but its semantic ("when X changes, audit Y" via `then_check`) has no `rule.json` equivalent and is out of scope for this exporter.
- `generate_schemas()` (`generate_schemas.py:950-966`) and its `test_idempotent_on_second_run` (`test_generate_schemas.py:179-185`) are the write-then-compare idempotency precedent for Acceptance Criteria #2.

### Decision Rationale

**Selected: single eager module (`decisions_export.py`), `host_runner.py`-style.** Scored 12/12 vs. a two-file lazy-import split's 6/12 on consistency, simplicity, testability, risk. `decisions.py` imports nothing OCR-adjacent and nothing that would import back from the new module, so the only justification for lazy resolution in this codebase (`adapters/core.py`'s confirmed `core.py` ↔ `codex.py` cycle) is absent. Several similarly small modules (`decisions_sync.py`, 57 lines; `fsm/continuity.py`, 65 lines; `pricing.py`, 150 lines) hold multiple functions plus a dataclass in one file with eager imports.

**Rejected: a `RuleRecord` intermediate type.** It would duplicate `RuleEntry`'s fields and add two (`severity`, `path filters`) with no source on `RuleEntry` and, for `severity`, no consumer on any target. Adding `paths` directly to `RuleEntry` gives every exporter the field without a translation layer.

## Verify First

- ~~OCR's actual rule/config format.~~ **Resolved** — proven in `.ll/learning-tests/open-code-review.md` (raw output `.ll/learning-tests/raw/open-code-review.txt`); see "OCR emission rules" above.
- **Still open, resolve before step 3:** confirm OCR's glob dialect for `path` — does `scripts/**/*.py` match a file directly under `scripts/` (i.e. does `**` match zero segments)? Brace sets like `**/*.{py,pyi}` are used by system rules, so they are supported. The specificity ordering assumes zero-segment `**`; add exactly one assertion to `.ll/learning-tests/open-code-review.md` via `/ll:explore-api` and adjust `_glob_sort_key` if it fails.
- **Decision to record:** is `.opencodereview/rule.json` a committed generated artifact (like the `ll-adapt` host mirrors) or local-only? It is not gitignored today. Default: **committed**, no staleness gate in this issue; piece 2 may add a mirror-style gate. Record the answer in the guide section.

## Integration Map

### Files to Modify
- `scripts/little_loops/decisions.py` — add `paths: list[str]` to `RuleEntry` (`:106`; explicit `pop("paths", [])` in `from_dict` `:125` before the `extra=copy` catch-all; emit in `to_dict` `:145` only when non-empty); add `active_required_rules()` next to `resolve_active()` (`:495`), no sort
- `scripts/little_loops/decisions_sync.py` — replace the inline filter at `:40-45` with `active_required_rules(decisions_path)`; behaviour unchanged
- New `scripts/little_loops/decisions_export.py` — `export_rules()`, `_EXPORTERS`, `_export_ocr()` plus private helpers `_group_by_glob()`, `_glob_sort_key()`, `_render_body()`; imports only `decisions` and `file_utils`, never `config`
- `scripts/little_loops/cli/issues/decisions.py` — `--path` (repeatable, `action="append"`) on `add` (`:116` region) and `promote` (`:270` region); `_cmd_promote`'s `RuleEntry(...)` constructor (`:938`) gains `paths=list(args.path or [])`; new `export` subparser in `add_decisions_parser()` (`:15`) with required `--target` whose `choices` is a module-level literal `_EXPORT_TARGETS = ("ocr",)` (keeps parser build import-free, matching the file's lazy-import convention) pinned to `_EXPORTERS` keys by a test, `--output-dir`, `--scope` (repeatable); dispatch branch in `cmd_decisions()` (`:280`); `_cmd_export(config, args, path) -> int` following `_cmd_sync` (`:550`): lazy import in body, resolves `scope_globs` per Proposed Solution §4 using `config.project.src_dir` (`config/core.py:215`), stderr + non-zero on failure
- `scripts/little_loops/config-schema.json` — **required, not soft**: the `decisions` object is `additionalProperties: false` (`:704`), so `decisions.export.scope_globs: string[]` must be declared once the CLI reads it. Reserve `decisions.export.ocr` as an empty object for future OCR-only knobs. Schema is not enforced at config-load time, so this is a consistency fix, not a runtime gate.

### Dependent Files (Callers/Importers)
- `sync_to_local_md()` — the only existing consumer of the selection logic; becomes the first caller of `active_required_rules()`
- `_cmd_promote` (`cli/issues/decisions.py:953`) calls `_cmd_sync` after promoting a required rule; consider also calling `_cmd_export(..., target="ocr", ...)` when `.opencodereview/` already exists (soft, keeps the two surfaces in step)
- Repo-wide grep confirms zero references to `export_rules` / `decisions_export` / `active_required_rules` today

### Similar Patterns
- `decisions_sync.py`'s `sync_to_local_md` — the sibling exporter
- `file_utils.py`'s `atomic_write_json()` (tested via `TestAtomicWriteJson`) — write path
- `adapters/core.py`'s `_EMITTER_MAP` / `HostEmitter` — model for a *lazy* registry only if a third target arrives with an import cycle; `_EXPORTERS` is the eager, minimal form of the same idea

### Tests
- `scripts/tests/test_decisions.py` — `TestRuleEntry` round-trip for `paths` (present, absent, legacy dict without the key); `TestActiveRequiredRules` (advisory excluded, superseded excluded, deterministic order); `TestSyncToLocalMd` (`:491`) unchanged and still green
- New `scripts/tests/test_decisions_export.py` — fixture set with: two repo-wide rules, one `scripts/**/*.py` rule, one superseded rule, one advisory rule. Assert: superseded/advisory absent; exactly one entry per distinct glob; scoped entry listed before catch-all; scoped body contains both its own and the repo-wide rule texts; catch-all body contains only repo-wide; each bullet carries its decision id; second run yields byte-identical file (AC #2); `scope_globs=None` resolves to `src_dir`; `export_rules(..., target="nope", ...)` raises `ValueError` naming `ocr`
- `scripts/tests/test_cli_decisions.py` — `TestDecisionsCLIExport` (`--target ocr` writes file, exit 0; bad output path → exit 1; unknown `--target` → argparse exit 2; missing `--target` → exit 2); `TestDecisionsCLIAdd` gains a `--path` case; `TestDecisionsCLINoSubcommand.test_no_subcommand` unaffected

### Documentation
- `docs/reference/CLI.md` — `ll-issues decisions` table row for `export`, `**export flags:**` subsection (`--target {ocr}`, `--output-dir`, `--scope`), `--path` under add/promote flags, bash example line
- `docs/reference/API.md` — `### active_required_rules`, `### export_rules` (document `_EXPORTERS` as the extension point); note `paths` under `### RuleEntry`
- `docs/guides/DECISIONS_LOG_GUIDE.md` — "Exporting to OCR" section (including the first-match/system-rule-replacement caveats) + ToC entry; mention `--path`
- `docs/ARCHITECTURE.md` — add exporter to "Key consumers" in the Decisions Log section

### Configuration
- `decisions.export.scope_globs` (optional, target-agnostic, see above); `decisions.export.ocr` reserved, empty

### Behavior Parity

The only existing behaviour touched is `sync_to_local_md()` (`scripts/little_loops/decisions_sync.py:31`). After the refactor it must:

- Select exactly the same entries in exactly the same order: `type="rule"`, `enforcement == "required"`, not superseded via `resolve_active()`. `active_required_rules()` preserves `list_entries` order (flat entries, then timestamp-sorted fragments) and adds **no** sort; see Proposed Solution §1 for why a sort would break this.
- Render bullets as `- {r.rule}` only — no decision id, no `paths`, no rationale. OCR-style traceability suffixes are OCR-adapter concerns and must not leak into `ll.local.md`.
- Keep the `## Active Rules` replace-or-append logic and `atomic_write` call untouched.
- Guard: `TestSyncToLocalMd` (`scripts/tests/test_decisions.py:491`) passes without modification.

`.ll/learning-tests/open-code-review.md` is read-only input; nothing in it is replaced.

## Program Design

### Types

- `RuleEntry` (existing, `decisions.py:106`) gains `paths: list[str] = field(default_factory=list)`. Empty = repo-wide. This is the exporter IR; no new type.

### Signatures

- `active_required_rules(path: Path | None = None) -> list[RuleEntry]` — `list_entries(path, type="rule")` → keep `enforcement == "required"` → `resolve_active()`. Load order preserved, no sort. Target-agnostic; shared by `sync_to_local_md` and `export_rules`.
- `export_rules(rules: list[RuleEntry], target: str, output_dir: Path, *, scope_globs: list[str] | None = None) -> Path` — public entry point; `_EXPORTERS[target](rules, output_dir, scope_globs=scope_globs)`, `ValueError` on unknown target.
- `_export_ocr(rules: list[RuleEntry], output_dir: Path, *, scope_globs: list[str] | None = None) -> Path` — groups by glob, orders by `_glob_sort_key`, folds repo-wide rules into every scoped body, writes `output_dir / ".opencodereview" / "rule.json"` via `atomic_write_json`, returns the path. `scope_globs` replaces the catch-all `**/*` for repo-wide rules; `None` → `["**/*"]`. Pure: no config, cwd, or stderr access.
- `_glob_sort_key(glob: str) -> tuple[int, int, str]` — `(-len(literal prefix), wildcard segment count, glob)`; see OCR emission rules.
- `_cmd_export(config: BRConfig, args, path) -> int` (CLI) — resolves `scope_globs` (`--scope` → `decisions.export.scope_globs` → `src_dir.rstrip("/") + "/**/*"` → `["**/*"]` + warning), calls `active_required_rules(path)` then `export_rules(...)`, prints path and counts.

### Call Path

`active_required_rules()` → `export_rules(target="ocr")` → `_export_ocr()` → `.opencodereview/rule.json`
`active_required_rules()` → `sync_to_local_md()` → `.ll/ll.local.md` (existing, now shared)

## Implementation Steps

0. Close the open Verify First item (zero-segment `**` in OCR's glob dialect) with one learning-test assertion; record the commit-vs-gitignore decision for `.opencodereview/rule.json`.
1. Add `paths` to `RuleEntry` (explicit pop in `from_dict`, emit-when-non-empty in `to_dict`) with round-trip tests; add `--path` to `add`/`promote` including `_cmd_promote`'s constructor.
2. Add `active_required_rules()` without a sort; refactor `sync_to_local_md()` onto it; confirm `TestSyncToLocalMd` stays green.
3. Implement `decisions_export.py`: `_export_ocr()` with `_glob_sort_key`, grouping and folding, `None` scope → `["**/*"]`; `_EXPORTERS = {"ocr": _export_ocr}`; `export_rules()` dispatch. No config import.
4. Wire `export --target ocr` into `ll-issues decisions` (`choices` from the `_EXPORT_TARGETS` literal, pinned to `_EXPORTERS` by a test); scope precedence resolved in `_cmd_export`; add `decisions.export.scope_globs` to the config schema; optionally call export from `_cmd_promote` when `.opencodereview/` exists.
5. Tests per Integration Map; idempotency check by double-run comparison.
6. Docs per Integration Map; run `ll-adapt --host <gemini|kimi-code|qwen> --apply` if any mirrored surface changed.

## Acceptance Criteria

1. `ll-issues decisions export --target ocr` writes `.opencodereview/rule.json` containing every active required rule and no superseded or advisory rule; an unknown `--target` is rejected by argparse with the valid choices listed, and `export_rules()` raises `ValueError` for the same.
2. Idempotent: re-running over an unchanged decision set produces a byte-identical file.
3. Exactly one `rules[]` entry per distinct path glob; more-specific globs precede the catch-all; every scoped entry's body also contains all repo-wide rules; each bullet carries its decision id.
4. Repo-wide rules are scoped to `src_dir` by default, not `**/*`, and the scope is overridable.
5. `RuleEntry.paths` round-trips through YAML/JSON; legacy entries without the key load with `paths == []` and nothing in `extra`; `to_dict()` of an entry with empty `paths` is byte-identical to today's output.
6. `sync_to_local_md()` output is unchanged after the refactor onto `active_required_rules()`, including bullet order for a log that mixes flat-file and fragment entries.
7. `decisions_export.py` does not import `little_loops.config`; `_export_ocr(..., scope_globs=None)` emits a `**/*` catch-all. The CLI resolves `--scope` → `decisions.export.scope_globs` → `src_dir` (trailing slash stripped) → `**/*` with a stderr warning.

## Priority Rationale

P4 — small, unblocked, first of the two OCR pieces. Slightly larger than the original "few dozen lines" estimate because of the `paths` field and the grouping logic, but still a single-session change.

## Impact

- **Priority**: P4
- **Effort**: Small–medium — ~150 lines plus tests; one schema field addition
- **Risk**: Low — additive; the only touch to existing behaviour is the `sync_to_local_md` refactor, covered by existing tests
- **Breaking Change**: No — `paths` defaults to empty; existing decision files load unchanged

## Related Key Documentation

- `docs/guides/DECISIONS_LOG_GUIDE.md`
- `.ll/learning-tests/open-code-review.md`

## Status

**Open** | Created: 2026-09-16 | Priority: P4

## Use Case

**Who**: A little-loops maintainer running OCR-based code review on this repo.

**Context**: A required rule has been recorded via `ll-issues decisions` but is enforced only through prose.

**Goal**: Run `ll-issues decisions export --target ocr` so OCR checks the rule automatically, scoped to the files it applies to.

**Outcome**: Code review flags violations of active decisions, each traceable to its decision id, without disabling OCR's built-in language rules.

## API/Interface

```python
# decisions.py
@dataclass
class RuleEntry:
    ...
    paths: list[str] = field(default_factory=list)  # empty = repo-wide

def active_required_rules(path: Path | None = None) -> list[RuleEntry]:
    """Active (non-superseded) required rules in load order (no sort). Shared by all exporters."""

# decisions_export.py  (imports: decisions, file_utils only — never config)
def _glob_sort_key(glob: str) -> tuple[int, int, str]:
    """(-len(literal prefix), wildcard segment count, glob): most specific first."""

def _export_ocr(
    rules: list[RuleEntry],
    output_dir: Path,
    *,
    scope_globs: list[str] | None = None,  # None -> ["**/*"]; caller resolves config
) -> Path:
    """Write .opencodereview/rule.json. The only OCR-specific function. Pure."""

_EXPORTERS: dict[str, Callable[..., Path]] = {"ocr": _export_ocr}

def export_rules(
    rules: list[RuleEntry],
    target: str,
    output_dir: Path,
    *,
    scope_globs: list[str] | None = None,
) -> Path:
    """Dispatch to the exporter registered for `target`; ValueError if unknown."""
```

```bash
ll-issues decisions add --type rule --enforcement required --path 'scripts/little_loops/fsm/**/*.py' ...
ll-issues decisions export --target ocr [--output-dir .] [--scope 'scripts/**/*']
```

## Edge Cases

- No active required rules → write `{"rules": []}` (valid, idempotent) rather than deleting the file.
- Same glob on several rules → one entry, bullets in selector order.
- A rule with multiple `paths` → its text appears in each glob's entry.
- `src_dir` missing from config and no `--scope` → CLI falls back to `**/*` with a stderr warning about system-rule replacement.
- Two scoped globs overlap without nesting (`**/*.py` vs `scripts/fsm/**/*`) → both entries are emitted in sort-key order; files matching both get only the first. Documented limitation, optional stderr warning, no folding.
- `src_dir` has a trailing slash (`scripts/`) → stripped before building the default scope glob.
- Legacy fragment carrying a stray `paths` key → lands on `RuleEntry.paths`, not `extra`.

## UI/UX Details

`export --target ocr` prints the written path and the count of entries/rules on success, matching `sync`'s one-line output style.

## Session Log
- `/ll:confidence-check` - 2026-09-16T16:40:54 - `12a2d668-0dec-4681-9a8f-10450d51152d.jsonl`
- `/ll:confidence-check` - 2026-09-16T16:19:48 - `0451feb3-8293-4e5a-aa46-79c33e20da03.jsonl`
- `/ll:wire-issue` - 2026-09-16T04:59:13 - `1e024021-4acc-4b11-a8a1-c8c2d8acfc34.jsonl`
- `/ll:decide-issue` - 2026-09-16T04:49:13 - `03cedaa9-993e-49e8-a8ba-5c2ffbf2b4a2.jsonl`
- `/ll:refine-issue` - 2026-09-16T04:42:32 - `03cedaa9-993e-49e8-a8ba-5c2ffbf2b4a2.jsonl`
- `/ll:refine-issue` - 2026-09-16T04:29:14 - `3cab3e66-607f-42d5-a4a3-fd8f1228edab.jsonl`
- `/ll:format-issue` - 2026-09-16T04:19:47 - `6c5fb4c3-b655-4820-8bf8-9f99b327e9fc.jsonl`
- `/ll:capture-issue` - 2026-09-16T04:15:49 - `b650788f-edb5-4a45-abe3-046c38ae23e3.jsonl`
