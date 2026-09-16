---
id: FEAT-3474
type: FEAT
title: Web GUI for issue-lifecycle FSM loops driven by frontmatter rules
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-14'
captured_at: '2026-09-14T17:11:03Z'
parent: EPIC-3299
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 85
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-3474: Web GUI for issue-lifecycle FSM loops driven by frontmatter rules

## Summary

A self-contained `.html` GUI (`file://`, no install) that lets a user author their
own simplified issue-lifecycle FSM loop — prepare, refine, gate, implement, verify
— driven by an Issue file's YAML frontmatter, without hand-writing FSM YAML. This
is a **third grammar/mode** (`issue_lifecycle`) alongside FEAT-2301's existing
`decision_table` and `rubric` modes on the same self-contained-HTML builder shell
(EPIC-3299), not a generator for `scripts/little_loops/loops/autodev.yaml` itself.

The emitted artifact is a **thin standalone loop YAML with the same shape
`decision_table` mode already emits** (imports `lib/policy-router.yaml`, carries
the rule table in `context.policy_rules`, dispatches via `policy_table_dispatch`),
with one substitution: the LLM `rubric_score` + `policy_parse_scores` states are
replaced by a single **deterministic frontmatter scorer** state that reads the
issue file and writes the per-dimension score files the dispatch fragment
already consumes. One issue per run; no queue/retry/rate-limit machinery.

## Current Behavior

No GUI exists for authoring an issue-lifecycle-shaped loop. Today a user who wants
an autodev-like loop for their own issue conventions must either hand-write FSM
YAML from scratch, or copy and heavily edit `autodev.yaml` (a large, tightly
coupled file with little-loops-specific assumptions throughout).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- The self-contained builder shell this issue extends already dispatches on `model.mode` via string-literal comparison, not a registry: `serializeLoopYaml()` (`scripts/little_loops/templates/policy_builder_core.mjs:645`) returns `_serializeRubric(model)` only when `model.mode === "rubric"`; every other value falls through to `_serializeDecisionTable(model)` with no error path. `blankModel()` (`:300`) and `seedExample()` (`:247`) in the same file take no `mode` argument and always hardcode `mode: "decision_table"` — there is no existing per-mode branch in either function to extend by example.
- Roughly ten additional `model.mode`/`state.mode` comparisons live in `scripts/little_loops/templates/policy-router-builder.html.tmpl`'s inline script (`computeSummary`, `renderTryIt`, `updateTryIt`, `renderMessages`, `renderAll`, `applyModeVisibility`, the `#mode-switch` change handler, `#start-blank-btn`'s click handler) — a third mode's UI wiring touches this file, not only `policy_builder_core.mjs`.
- `cmd_policy_builder()` in `scripts/little_loops/cli/artifact/policy_builder.py` assembles the emitted artifact by loading `grammar_spec()` and `_load_skill_catalog()`, then stamping four literal placeholders into the read `.tmpl`/`.mjs` text (theme CSS vars, grammar-spec JSON, skill-catalog JSON, the core JS itself) via sequential `str.replace()` calls — there is no general templating engine and no `--mode` CLI flag; mode is a pure runtime/browser concept never inspected server-side. `_load_skill_catalog()` returns a flat `list[dict]` of `{"name": str, "description": str}` with no verb/category field to filter by lifecycle stage.

_Added by review — 2026-09-16 — based on codebase analysis:_

- `ll-issues show --json` (the deterministic scorer precedent used by `loops/rn-remediate.yaml:351-368`) returns a **fixed, curated key set** and **renames** fields: frontmatter `confidence_score` → JSON `confidence`, `outcome_confidence` → `outcome`. Arbitrary custom frontmatter keys (e.g. `severity`, `review_status`) are **not** passed through. It therefore cannot back the custom-field acceptance criterion; the scorer must read raw frontmatter via `little_loops.frontmatter.parse_frontmatter(content, coerce_types=True)` (`scripts/little_loops/frontmatter.py:255`).
- The builder's dimension types are exactly `numeric` and `boolean` (`.tmpl:163-166`); there is no `string` type. `_serializeRulesText()` (`policy_builder_core.mjs:392`) compiles boolean predicates to numeric `>=50`/`<50` because the LLM rubric encodes booleans as 100/0 (`.tmpl:169` help text). The engine itself already supports string `==`/`!=` with numeric-first coercion (`fsm/policy_rules.py:188-225`), and ordered ops require numeric values at parse time.
- `policy_table_dispatch` (`lib/policy-router.yaml:140-184`) is scorer-agnostic: it reads every `rubric-dim-<name>.txt` in `${context.run_dir}/` plus optional `rubric-aggregate.txt`, coercing each to float when possible and leaving it a string otherwise. Dimension file names are lowercased with spaces→hyphens (`normalizeDimName()`, `policy_builder_core.mjs:90`); underscores pass through unchanged, so `confidence_score` → `rubric-dim-confidence_score.txt`.
- Emitted outcome states are produced by `_outcomeStateLines()` (`policy_builder_core.mjs:458-482`): `actionType` is one of `none | prompt | slash_command`, and `slash_command` bodies are emitted verbatim as `action: <body>`. The lifecycle verbs therefore map cleanly onto `slash_command` outcomes whose body embeds an issue-identity context variable.
- `loops/rn-remediate.yaml:11-36` is the precedent for a per-issue loop: `issue_id` is a `parameters:` self-declaration (`rn-remediate.yaml:35`), not `with:` (`with:` is the caller-side key for sub-loop/fragment invocations, `fsm/schema.py:684`), and the loop is run as `ll-loop run rn-remediate --context issue_id=<ID>`.

_Added by pre-implementation review (4th pass) — 2026-09-16 — based on codebase analysis:_

- **Terminal states never run their action.** `FSMExecutor` returns the instant it enters a `terminal: true` state (`fsm/executor.py:816`, "Check terminal" precedes action execution). `_outcomeStateLines()` (`policy_builder_core.mjs:458-482`) emits a `finish` outcome that has an action as `action: …` + `terminal: true` in a **single** state, so that action is dead code. `ll-loop validate` already flags this on the shipped decision-table golden (`sample-decision-table.yaml`'s `escalate` state, BUG-2813 WARNING via `_validate_terminal_action_ok`, `fsm/validation/evaluator_rules.py:32`). Because the Verb Table defaults `implement` and `verify` to `finish`, a naive reuse of `_outcomeStateLines()` would emit an `implement` state whose `/ll:manage-issue` never executes.
- **`ll-loop validate` on the existing decision-table golden emits three WARNINGs today**, all of which the lifecycle emit would inherit: (1) BUG-2813 terminal-action (above); (2) `scope:` undeclared ("falls back to a repo-root lock that false-conflicts with every other concurrently running loop"); (3) MR-12 `_validate_pruning_profile` check 3 (`evaluator_rules.py:251-360`) — fires for **every** state whose `action` starts with `/` and matches `_SKILL_INVOKE_RE` (`/ll:([a-zA-Z0-9_-]+)`, `_base.py:192`) when neither the state nor the loop declares `pruning_profile:`; suppressed only by loop-level `pruning_profile_ok: true`. Every verb state is a `/ll:` slash command, so this fires once per emitted verb. rn-remediate carries the same MR-12 warning on its `re_assess` state.
- `ll-issues path <ID>` (`cli/issues/path_cmd.py`) exists, exits 1 when the ID does not resolve, and prints the path **relative to `config.project_root`** (or `{"path": …}` with `--json`), not relative to the shell cwd.
- `renderDimensions()` (`.tmpl:281-299`) attaches a `✕` delete button to every dimension row unconditionally; there is no per-row lock today.
- `_validate_policy_dimensions_scored` is covered in `scripts/tests/test_fsm_validation_reachability.py` (the only test file that references it).
- Fragment deep-merge (`fsm/fragments.py:66-150`) is "fragment is the base, state fields override", so caller-supplied `next:`/`on_error:` on a `fragment: frontmatter_scores` state survive — confirmed, no gap.
- `parse_frontmatter` behaviour reproduced live: `decision_needed: true` → `'true'`; `blocked_by: []` → `[]`; `blocked_by: BUG-1` → `'BUG-1'`; `deferred_reason:` → `None`; `confidence_score: 007` → `'007'` (`coerce_types=False`) / `7` (`True`); `status: completed` → `'done'`; `title: 'a: b'` → `'a: b'`. Matches the Encoding Rules.

_Added by pre-implementation review (5th pass) — 2026-09-16 — based on codebase analysis:_

- **`/ll:refine-issue` never writes `confidence_score`.** The only writer is `/ll:confidence-check`, via `ll-issues set-scores <ID> --confidence … --outcome …` (`skills/confidence-check/SKILL.md:398-405`); `commands/refine-issue.md` touches `decision_needed` only (`:545`). Any seed whose only path to `gate` is `confidence_score:>=N` while `refine` rescores in place can therefore never reach `gate`, and a `gate → rescore` default re-fires the same `>=N` rule forever. See the corrected Verb Table and Use Case.
- **`/ll:manage-issue` takes `<issue_type> <action> [issue_id]` positionals, both required** (`skills/manage-issue/SKILL.md:9-16`); `/ll:manage-issue FEAT-1` parses `FEAT-1` as `issue_type`. No loop in the repo invokes `/ll:manage-issue`; both production per-issue loops implement via a shell state running `ll-auto --only "$ID"` (`rn-remediate.yaml:470-486`; autodev's `implement_current` per `autodev.yaml:29-38`).
- **The default verb skills are interactive unless `--auto` is passed.** `format-issue` (`skills/format-issue/SKILL.md:31,51`), `refine-issue` (`commands/refine-issue.md:76`), `confidence-check` (`SKILL.md:55`), and `verify-issues` (`commands/verify-issues.md:489`) all gate non-interactive behaviour on `--auto`; rn-remediate appends it to every one of its slash-command states (`rn-remediate.yaml:132,148,619-725`).
- A `slash_command` state reaches `on_error` only when the host CLI exits non-zero (`executor.py:2161-2179`); a skill that reports a quality failure in prose exits 0 and advances to `next`. `on_error: failed` therefore catches infra failures, not skill-level failures.
- `on_max_steps:` is a real top-level key (`executor.py:653-697`): when the step cap is hit the executor runs that state instead of finishing with `terminated_by: max_steps`.
- `_serializeDecisionTable` places no restriction on outcome names and `fallbackState` itself defaults to `"done"` (`policy_builder_core.mjs:544`), so a decision-table outcome may legitimately be named `done`.
- `validate_fsm` has no INFO severity (only ERROR/WARNING across `fsm/validation/*.py`), so asserting `validate_fsm(fsm) == []` is safe.
- The visible-markup jargon denylist is `["Axis A", "Axis B", "context.subject", "policy_rules", "predicate"]` (`test_policy_builder_emit.py:133`).

## Expected Behavior

A new `issue_lifecycle` mode on `policy-router-builder.html.tmpl` where:

- **Subject** is a single Issue file's YAML frontmatter (as in `.issues/*.md`),
  identified at run time by `--context issue_id=<ID>`.
- **Dimensions** in the rule builder are frontmatter fields:
  - little-loops' own built-in fields as pre-typed, pre-populated dimensions
    (see the Built-in Dimension Table below).
  - PLUS arbitrary user-declared **custom** frontmatter fields — the user names
    the key and picks a type (`numeric`, `boolean`, `string`, `list`);
    little-loops needs no prior knowledge of the field. This is the key
    differentiator from a little-loops-only tool.
  - Operators offered per type: `numeric` and `list` → all six; `boolean` →
    `==true` / `==false`; `string` → `==` / `!=` only. (`string` and `list`
    are **new** builder types; the existing `opsForType()` only special-cases
    `boolean`.)
- **Actions** per rule/outcome are the five lifecycle verbs — prepare, refine,
  gate, implement, verify — four pre-bound to a default `/ll:*` slash command
  plus per-verb default args (`--auto`), and `implement` pre-bound to a shell
  action `ll-auto --only ${context.issue_id}` (see Verb Table). Every verb is
  overridable from the same emit-time skill catalog FEAT-2301's "run a skill"
  dropdown already surfaces, with a free-text **args** input beside it. The
  verb set is **fixed**: verbs cannot be deleted and no new outcomes can be
  added in this mode (`#add-outcome` hidden, `✕ outcome` disabled); only the
  skill binding, args, and transition are editable.
- **Try it** panel accepts a pasted frontmatter block and shows which rule
  fires, using the same evaluator the emitted loop uses. It must evaluate the
  **compiled** rule text — `evaluateRules(parseRuleTable(_serializeRulesText(model)), scores)`
  — not `model.rules` (see Encoding Rules § Try-it evaluates compiled rules).
- Reuses FEAT-2301/FEAT-2390's shipped patterns (self-contained `file://`
  HTML, ordered reorderable rule list, pinned "Otherwise" footer, demoted YAML,
  seeded example, theme handling, pure-function `.mjs` core + `node --test`
  gate, jargon-denylist for on-screen labels).

### Built-in Dimension Table

| Frontmatter key | Type | Scorer encoding |
|---|---|---|
| `status` | string | verbatim; absent → no file |
| `priority` | string | verbatim (`P0`..`P5`); absent → no file |
| `priority_rank` | numeric | **derived** from `priority`: leading `P` stripped → `0`..`5`, so ordered ops work (`priority_rank:<=2`); absent or non-`P<digit>` → no file |
| `confidence_score` | numeric | verbatim; absent → no file |
| `outcome_confidence` | numeric | verbatim; absent → no file |
| `decision_needed` | boolean | `100` / `0` (string-truthiness, see Encoding Rules) |
| `spike_needed` | boolean | `100` / `0` (string-truthiness, see Encoding Rules) |
| `blocked_by` | list | count (see Encoding Rules § list); always written, `0` when absent/empty/`null` |
| `deferred_reason` | string | verbatim; absent/`null` → no file |

`priority_rank` is the one built-in that is not a raw frontmatter key; the
scorer synthesizes it from `priority` (the Try-it encoder mirrors this). It is
the only derived dimension — custom fields are never transformed.

### Encoding Rules

These rules are shared verbatim by the `frontmatter_scores` fragment (Python)
and the Try-it `encodeFrontmatterScores` mirror (JS), and are the contract the
scorer pytest and `node --test` cases pin.

- **Frontmatter values are strings.** `parse_frontmatter` loads with
  `yaml.BaseLoader` (`scripts/little_loops/frontmatter.py:255-268`), so
  `decision_needed: true` arrives as the string `"true"`; `coerce_types=True`
  only turns bare digit scalars into `int`. Every rule below is defined on
  string/list/`None` inputs, never on Python `bool`/`float`.
- **boolean** → `100` when the value, lowercased and stripped, is one of
  `true`, `yes`, `on`, `1`; otherwise `0` (including absent, `null`, empty,
  and any other string). The file is always written.
- **numeric** → scalar written verbatim (the dispatch fragment coerces to
  float; a non-numeric scalar such as `confidence_score: high` is written
  as-is and the engine's string fallback applies — `==`/`!=` compare as
  strings, ordered ops evaluate False). A list value under `numeric` →
  `len(list)`. Absent/`null` → **no file** (engine missing-dimension
  semantics: `!=` matches, everything else does not).
- **list** → count semantics: a list → `len(list)`; a non-empty non-list
  scalar (`blocked_by: BUG-1`) → `1`; absent/`null`/empty list → `0`. The
  file is **always written**, so `blocked_by:==0` / `blocked_by:<1` match an
  issue with no `blocked_by` key — the common "not blocked" case. This type
  exists because the scorer cannot infer "a list was expected" from a
  `numeric` declaration: under `numeric`, `blocked_by: BUG-1` is a
  non-numeric scalar and is written verbatim as `BUG-1`. Operators: all six.
- **string** → `str(value).strip()` written verbatim. Absent/`null`/empty →
  **no file**. There is deliberately no "empty string" encoding: the rule
  grammar requires a non-empty predicate value (`_PRED_PATTERN`,
  `fsm/policy_rules.py:32`), so `deferred_reason:==` cannot be authored, and
  an empty file evaluates identically to a missing dimension anyway.
- **Derived `priority_rank`.** When `priority` is present and matches
  `^P(\d)$` (after strip), the scorer also writes
  `rubric-dim-priority_rank.txt` containing the digit. Any other value (absent,
  `null`, `high`) → no `priority_rank` file. This is the only synthesized
  dimension.
- **Name normalization.** `context.frontmatter_dimensions` carries the
  **raw** frontmatter key (case-sensitive, as the user typed it) for lookup;
  the output filename uses the normalized form (`normalizeDimName()`:
  lowercase, spaces→hyphens, underscores untouched) so it matches the dim
  name `_serializeRulesText()` emits into `context.policy_rules`.
- **String-value validation (builder side).** `parse_rules` splits the LHS
  on `&`, partitions on the first `->`, and treats `#`-leading lines as
  comments. The `string` type's value input must reject empty values and
  values containing `&` or `->`. Values with internal spaces are fine
  (`\S.*?` + `strip()`).
- **Numeric-first coercion on `==`/`!=`.** The engine tries `float()` on both
  sides first, so `severity:==1` matches frontmatter `severity: "1"` and
  `severity: 1.0` alike. Pin this in the conformance corpus.
- **Clean slate on every score pass.** `${context.run_dir}` persists for the
  whole run and `policy_table_dispatch` reads *every* `rubric-dim-*.txt`
  present (`lib/policy-router.yaml:157-164`). "Absent → no file" is therefore
  only true if the scorer first **deletes all `rubric-dim-*.txt` and
  `rubric-aggregate.txt`** in `${context.run_dir}` before writing. Without
  this, a field present on pass 1 and cleared by pass 2 (e.g. `deferred_reason`
  removed by refine-issue) keeps its pass-1 file and missing-dimension
  semantics never occur after the first score. The fragment pytest pins this
  with a two-pass case (write, clear the field, re-run, assert the file is
  gone).
- **Null/empty normalization and status synonyms.** `parse_frontmatter`
  normalizes `""`, `null`, and `~` scalars to `None` (`frontmatter.py:139`)
  and canonicalizes `status` synonyms (`completed` → `done`,
  `frontmatter.py:246`, via `STATUS_SYNONYMS`). The Try-it mini-parser must
  mirror both, or Try-it and the emitted loop disagree on the seed rule
  `status:==done` for an issue whose frontmatter says `status: completed`.
- **Coercion mode.** The scorer calls `parse_frontmatter(content,
  coerce_types=False)`: it writes text and `policy_table_dispatch` does the
  float coercion, so `coerce_types=True` buys nothing and loses leading zeros
  (`"007"` → `7`). Every value is therefore `str`, `list`, or `None`.
- **Custom key names.** The builder rejects custom frontmatter keys containing
  `:` or `|` (they break the `name:type|name:type` encoding of
  `context.frontmatter_dimensions`) and keys that normalize to an existing
  dimension's name (including `priority_rank`).
- **Try-it evaluates compiled rules.** The existing decision-table Try-it
  (`.tmpl:556-570`) passes `buildModel().rules` — raw predicates whose `op` is
  the UI token `==true`/`==false` — straight to `evaluateRules`.
  `evalPredicate` (`policy_builder_core.mjs:136-150`) knows only `==`/`!=`
  and the ordered ops, so `==false` falls into the `!=` string branch and
  fires on `100` and `0` alike (verified with `node`: a `has-citations:==false`
  rule wins against `{"has-citations": 100}`). The lifecycle Try-it must
  therefore evaluate `parseRuleTable(_serializeRulesText(model))` — the same
  compiled text the emitted YAML carries — so `decision_needed:==false`
  behaves as the loop will. This is a pre-existing decision_table defect;
  file it as a separate BUG and fix both sites together.
- **Quoted scalars and colons in values (Try-it mini-parser).** Real
  frontmatter carries `discovered_date: '2026-09-14'`,
  `captured_at: '2026-09-14T17:11:03Z'`, and titles containing `:`.
  `parseFrontmatterBlock` splits each line on the **first** `:` only and
  strips one pair of matching single or double quotes from the value
  (`'open'` → `open`). `parse_frontmatter` (BaseLoader) already does both;
  the corpus pins them so the two encoders agree.

### Verb Table

| Verb | `actionType` | Default `body` | Default `args` | Emitted `action:` | Default transition |
|---|---|---|---|---|---|
| prepare | `slash_command` | `/ll:format-issue` | `--auto` | `/ll:format-issue ${context.issue_id} --auto` | rescore ("Score again") |
| refine | `slash_command` | `/ll:refine-issue` | `--auto` | `/ll:refine-issue ${context.issue_id} --auto` | **goto gate** ("Go to… gate") |
| gate | `slash_command` | `/ll:confidence-check` | `--auto` | `/ll:confidence-check ${context.issue_id} --auto` | rescore ("Score again") |
| implement | `shell` | `ll-auto --only` | _(empty)_ | `ll-auto --only ${context.issue_id}` | finish ("Stop here") |
| verify | `slash_command` | `/ll:verify-issues` | `--auto` | `/ll:verify-issues ${context.issue_id} --auto` | finish ("Stop here") |

**Body vs. emitted action.** The outcome model stores the **bare** skill
(`/ll:<name>`), exactly what the existing skill `<select>` (`.tmpl:366-372`)
writes and what `renderMessages`'s unknown-skill check (`.tmpl:589-593`)
compares against the catalog by exact string. A separate per-outcome `args`
string (new model field, free-text input beside the skill dropdown, seeded
from the table) carries flags. `_serializeIssueLifecycle` emits each
`slash_command` verb as `<body> ${context.issue_id} <args>` (args omitted
when empty). If the model stored the argument-bearing form, every verb would
render as an "unknown skill" error and be unselectable in the dropdown. The
four slash-command defaults are in `_load_skill_catalog()`'s output (it globs
both `skills/*/SKILL.md` and `commands/*.md`, `policy_builder.py:31-46`).

**Why `--auto`.** format-issue, refine-issue, confidence-check, and
verify-issues are interactive by default and only run unattended with
`--auto` (5th-pass findings); rn-remediate appends it to every one of its
slash-command states. When the user overrides a verb with a catalog skill
that may not accept `--auto`, they clear the args field; the builder does not
guess.

**Why `implement` is a shell action, not `/ll:manage-issue`.** manage-issue
requires `<issue_type> <action>` positionals ahead of the ID and the type is
unknowable at emit time; both production per-issue loops implement via
`ll-auto --only "$ID"` (`rn-remediate.yaml:470-486`). `implement` is
therefore emitted as `action_type: shell` with `action: ll-auto --only
${context.issue_id}` (a `shell` `actionType` on the outcome model, exempt
from the unknown-skill check). Selecting a catalog skill for `implement` in
the UI switches it back to `slash_command` with the standard `<body>
${context.issue_id} <args>` emit.

Transitions use the shell's existing per-outcome selector (`.tmpl:383`:
"Score again" / "Go to…" / "Stop here") and remain user-editable. `refine`
defaults to **`goto gate`** rather than `rescore` because refine-issue does
not write `confidence_score` — only confidence-check does (5th-pass findings)
— so rescoring straight after refine re-fires the same rule; routing through
`gate` first is what makes "refine, then gate on confidence" progress within
one run (refine → confidence-check rescores the issue → the next score pass
routes on the new value). `gate` rescores. `max_steps` bounds a
non-converging refine/gate cycle, exactly as it bounds `deep_repair → score`
in `decision_table` mode, and the emitted `on_max_steps: failed` (§2) makes
that ending land on the failure terminal rather than a bare `max_steps` stop.

**`finish` is emitted as `next: done`, not `terminal: true`.** A terminal
state's action never executes (`executor.py:816`), so `implement`/`verify`
would be no-ops if emitted as terminal-with-action. See Proposed Solution §2
"Finish transitions must not be emitted as terminal-with-action".

## Motivation

`autodev.yaml` (2652 lines) is little-loops' own hand-tuned production loop for
driving issues through prepare → refine → gate → implement → verify. It is not a
realistic target for a rules-GUI to reproduce faithfully — it has bespoke queue
management, decision/blocker/gate pre-flight checks, repair cycles, rate-limit
handling, and infra-vs-quality failure classification built up over dozens of
issues. But its *shape* — route an issue through lifecycle stages based on
frontmatter conditions — is a pattern other users (and other little-loops
consumers with their own issue conventions) plausibly want a smaller, self-service
version of, the same way FEAT-2301 gave non-experts a GUI for the `policy-router`
grammar instead of hand-written `route:` maps.

## Proposed Solution

Extend the existing self-contained HTML builder shell rather than building a new
one. Add a third mode literal `"issue_lifecycle"` to `policy_builder_core.mjs`
and the template's inline script. Three pieces of work:

### 1. Scorer fragment (new, in `lib/policy-router.yaml`)

Add a `frontmatter_scores` fragment alongside `policy_parse_scores`. It is a
shell state that:

- resolves `${context.issue_id}` to a path via `ll-issues path <ID> --json`
  and joins the returned `path` onto the project root (the command prints a
  path relative to `config.project_root`, not the shell cwd — `path_cmd.py`);
- **deletes every `rubric-dim-*.txt` and `rubric-aggregate.txt`** in
  `${context.run_dir}` (see Encoding Rules § Clean slate);
- parses the file with `parse_frontmatter(content, coerce_types=False)`;
- for each `name:type` pair in `${context.frontmatter_dimensions}`
  (pipe-separated, raw keys, e.g. `status:string|confidence_score:numeric|decision_needed:boolean|blocked_by:list|severity:string`)
  looks up the raw key in the parsed frontmatter and writes
  `${context.run_dir}/rubric-dim-<normalized-name>.txt` per the **Encoding
  Rules** section above (boolean → `100`/`0` by string-truthiness, always
  written; numeric → verbatim or list length, absent → no file; list →
  count, always written; string → verbatim, absent/empty → no file;
  `priority_rank:numeric` is synthesized from `priority`).
- exits non-zero when the issue ID does not resolve. **This only has an
  effect if the calling state sets `on_error`:** for a `next:`-chained shell
  state with no `on_error`, the executor advances to `next` regardless of
  exit code (`fsm/executor.py:2161-2179`). rn-remediate's BUG-2003 AC5
  contract works because its `diagnose` state sets `on_error:
  emit_implement_failed`. The emitted `score` state therefore carries
  `on_error: failed` (see §2); without it a typo'd ID yields empty scores,
  the catch-all fires, and `/ll:refine-issue BAD-ID` runs.

**Shell-interpolation pattern.** Copy `policy_table_dispatch`
(`lib/policy-router.yaml:140`), not rn-remediate's bash scorer: pass
`LL_ARG_ISSUE_ID=${context.issue_id:shell}` and
`LL_ARG_FRONTMATTER_DIMS=${context.frontmatter_dimensions:shell}` as env vars
into a `$${LL_PYTHON:-python3} << 'PYEOF'` heredoc, and escape any literal
bash `${...}` as `$${...}` (the FSM interpolates the whole action string
before bash sees it).

Booleans are encoded 100/0 so the existing `compileBooleanPredicate` path in
`_serializeRulesText()` is reused unchanged (`==true` → `>=50`, `==false` →
`<50`; an absent boolean writes `0` and therefore satisfies `==false`); no
engine changes are needed.

**Validator change (`fsm/validation/reachability.py`).**
`_validate_policy_dimensions_scored()` (`:154-238`) builds its "scored" set
from `context.rubric_dimensions` plus literal `rubric-dim-<name>.txt` strings
found in shell actions (`:201-218`). The fragment builds the filename
dynamically, so nothing matches and `ll-loop validate` emits one false
"referenced in policy_rules but never scored … predicates are inert" WARNING
per dimension for every `issue_lifecycle` loop. Extend the validator to also
parse `context.frontmatter_dimensions` (`name:type|…`, names normalized the
same way as `rubric_dimensions`). Do **not** suppress with
`policy_dims_scored_ok: true` in the emitted YAML — that discards the real
check for typo'd dimension names.

### 2. Core (`policy_builder_core.mjs`)

- `blankModel()` / `seedExample()` gain a `mode` parameter (default
  `"decision_table"`, preserving today's zero-arg behaviour). The
  `issue_lifecycle` branch pre-populates `dimensions` from the Built-in
  Dimension Table and `outcomes` from the Verb Table.
- `serializeLoopYaml()` gains an explicit `mode === "issue_lifecycle"` branch
  **before** the decision-table fallback, calling `_serializeIssueLifecycle()`,
  which emits:
  - `import: [lib/policy-router.yaml]` (no `rubric-router`);
  - `context.frontmatter_dimensions` and `context.policy_rules`;
  - a top-level `parameters: { issue_id: { type: string, required: true } }`
    block (the emitted loop's own self-declaration — see rn-remediate.yaml:35
    for the shape; `with:` is the caller-side key used when *invoking* a
    sub-loop/fragment, per `fsm/schema.py:684`, not a self-declaration key —
    corrected 2026-09-16, see Verification Notes);
  - top-level `scope: ["."]` (the loop edits an issue file and whatever the
    verb skills touch; without `scope:` validate WARNs about the repo-root
    lock fallback) and `pruning_profile_ok: true` with a preceding YAML
    comment (`# every verb is a /ll: skill; MR-12 would otherwise warn per
    verb state`). Both are required for the zero-warnings AC — see the 4th-pass
    findings.
  - top-level `on_max_steps: failed`, so a refine/gate cycle that never
    converges ends on the failure terminal instead of `terminated_by:
    max_steps` (5th-pass findings).
  - `initial: score` → `score: {fragment: frontmatter_scores, next:
    policy_dispatch, on_error: failed}` → `policy_dispatch` (route-map
    generation as in `_serializeDecisionTable`, except the `_error` sentinel
    routes to `failed`) → **one outcome state per emitted verb** (see
    "Emitted-verb closure" below; not one per model outcome, unlike
    `_serializeDecisionTable`, which would emit all five verb states for a
    three-verb loop), each `slash_command` verb emitted as `<body>
    ${context.issue_id} <args>` and the `shell` verb (`implement` default)
    emitted as `action_type: shell` / `action: <body> ${context.issue_id}`,
    with `on_error: failed` on every verb state (catches host-CLI /
    `ll-auto` non-zero exits — infra failures — so they surface as `failed`
    rather than advancing to `score`; a skill that reports a quality failure
    in prose exits 0 and is bounded by `max_steps`/`on_max_steps` instead) → a bare
    `done: {terminal: true}` state → a fixed `failed: {terminal: true}` state
    (the unresolved-issue-ID exit; see §1). `failed` is in
    `FAILURE_TERMINAL_NAMES` (`fsm/schema.py:34`), so the run is reported as a
    failure terminal without declaring `failure: true`.
  - **Finish transitions must not be emitted as terminal-with-action.** The
    executor never runs a terminal state's action (`executor.py:816`), so a
    verb with `transition.kind === "finish"` is emitted as a **non-terminal**
    state with `next: done`, and `done: {terminal: true}` is emitted bare.
    This is why `implement`/`verify` (Verb Table defaults `finish`) actually
    run. `_outcomeStateLines()` produces the broken shape today for any
    finish outcome that has an action (the decision-table golden's `escalate`
    state trips BUG-2813); fix it **in `_outcomeStateLines()` itself** so
    both modes benefit, regenerate `sample-decision-table.yaml` +
    `sample-decision-table.model.json`'s golden output accordingly, and note
    the golden change in the commit. (This relaxes the "existing goldens
    byte-unchanged" AC to: unchanged **except** for the BUG-2813 fix, which
    is a deliberate, called-out regeneration.) An outcome with
    `actionType: none` and `finish` may still be emitted as a bare terminal.
    **Done-state name collision:** decision-table outcomes may be named
    anything, including `done` (`fallbackState` even defaults to `"done"`,
    `policy_builder_core.mjs:544`). An outcome named `done` with an action
    and a `finish` transition would emit `next: done` on itself plus a
    duplicate bare `done:` key. `_outcomeStateLines`'s caller picks the
    done-state name at emit time: `done` unless an outcome/verb already uses
    it, else `finished` (pure helper `_doneStateName(model)`, exported for
    `node --test`); the lifecycle mode's fixed verb set can never collide.
  - **Emitted-verb closure.** The set of emitted verb states is the
    transitive closure of: verbs targeted by a rule, the fallback verb, and
    any verb named as the `goto` target of an already-emitted verb. Without
    the `goto` step, "refine → Go to gate" with no rule targeting `gate`
    emits `next: gate` to a nonexistent state (a validate ERROR).
- `_serializeRulesText()` needs **no change** for `string` or `list`:
  non-boolean dims already pass their op and value through verbatim. Both
  types are enforced only at the UI layer (`opsForType()` and value
  validation in the template).
- Export the new functions and constants from the `window.PolicyBuilderCore`
  browser global (`policy_builder_core.mjs:654-666`) — the template's inline
  script can only reach the core through that object.
- Dimension model shape stays `{name, type}`; no `kind` discriminator — the
  model is already open. Built-in vs custom is purely a UI concern (built-ins
  are pre-populated and their type is locked).

### 3. Template (`policy-router-builder.html.tmpl`)

- Third `<option>` on `#mode-switch`; `applyModeVisibility()` shows the
  dimensions/outcomes/rules fieldsets and a new `frontmatter-tryit-fieldset`
  for this mode, hides `threshold-fieldset`.
- **Mode-switch semantics.** Today's `#mode-switch` handler (`.tmpl:632-638`)
  only reassigns `state.mode` and `maxSteps`; it never reseeds collections.
  Switching **into** `issue_lifecycle` replaces `state` with
  `seedExample("issue_lifecycle")` (same data-loss contract as "Start blank");
  switching **out** replaces it with `seedExample(<new mode>)`.
  `#start-blank-btn` calls `blankModel(state.mode)` so a blank lifecycle model
  still carries the locked built-in dimensions and the five verbs.
- **Built-in dimensions are locked, not deletable.** `renderDimensions()`
  (`.tmpl:281-299`) puts a `✕` on every row; in this mode the button is
  omitted for rows whose normalized name is in
  `BUILTIN_FRONTMATTER_DIMENSIONS` (custom rows keep it). Rationale: deleting
  `priority` while a rule uses `priority_rank` would still score at runtime
  (the scorer keys off the `priority_rank:numeric` entry) but would drop the
  entry from the rule editor's dimension dropdown, leaving an orphaned
  predicate the UI can no longer edit.
- `#dim-type` gains `string` and `list` options; `opsForType()` restricts
  `string` to `==`/`!=` (`list` keeps all six); the rule-value input for
  `string` dims rejects empty values and values containing `&` or `->`; the
  custom-dimension name input rejects `:` and `|` (see Encoding Rules §
  String-value validation and § Custom key names).
- Outcome fieldset in this mode shows the five verbs with their default
  skills pre-selected in the existing skill-catalog dropdown (bare `/ll:<name>`
  bodies, see Verb Table § Body vs. emitted action), a free-text **args**
  input beside the dropdown seeded with `--auto`, and `implement` shown as
  its shell default (`ll-auto --only`) with the dropdown offering catalog
  skills as an override. `#add-outcome` is hidden and each verb's `✕ outcome`
  button is disabled. `renderMessages`'s "has no rule and isn't the fallback"
  warning (`.tmpl:581-587`) is **suppressed** in this mode — unused verbs are
  expected, not a mistake, and are simply not emitted. The unknown-skill
  check skips `shell` outcomes.
- **On-screen copy constraint.** `test_no_internal_jargon_in_visible_markup`
  denylists `predicate` and `policy_rules` (among others) in visible markup;
  the new fieldset labels, Try-it help text, and validation messages must
  say "condition"/"rule" instead.
- Try-it: a `<textarea>` for pasted frontmatter; the page parses it with a
  minimal YAML-frontmatter reader (scalars with optional matching quotes,
  first-`:` split, booleans, flow/dash lists — no nested maps; `""`/`null`/`~`
  → absent; `status` synonyms canonicalized per `STATUS_SYNONYMS`), encodes
  the scores (including the derived `priority_rank`), and runs the JS
  `evaluateRules` mirror over the **compiled** rule table
  (`parseRuleTable(_serializeRulesText(model))`), not `buildModel().rules`
  (see Encoding Rules § Try-it evaluates compiled rules). This is the only
  new JS parser; keep it pure and covered by `node --test`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- The generic rule-table engine (`fsm/policy_rules.py`'s `parse_rules`/`evaluate_rules`) has exactly two known consumers today: `scripts/little_loops/loops/policy-refine.yaml` (a loop supplying `context.policy_rules` as plain text, routed via the `policy_table_dispatch` fragment from `lib/policy-router.yaml`) and `ll-loop edit-routes` (`cli/loop/edit_routes.py`, a CLI editor over that same `policy_rules` text via `PolicyRuleExtractor`/`CompoundGridRenderer`/`PolicyRuleApplier` in `fsm/route_table.py`). No third consumer exists in the repo.
- Testing convention for the two existing modes: each gets its own dedicated golden model+YAML fixture pair under `scripts/tests/fixtures/policy_builder/` (`sample-decision-table.model.json`/`.yaml`, `sample-rubric.model.json`/`.yaml`). Each mode's "golden YAML validates" test is a separate, non-parametrized function (`test_golden_yaml_validates`, `test_golden_rubric_yaml_validates` in `test_policy_builder_emit.py`), while the node-gate round-trip test (`test_round_trip_yaml_validates_for_each_mode` in `test_policy_builder_node_gate.py`) is parametrized across both mode fixtures in one function.
- Mode-switcher UI convention: a single `<select id="mode-switch">` in the page header (not tabs, `.tmpl:121-124`), with per-mode visibility controlled by direct `.hidden` boolean toggles on four fixed fieldset IDs in `applyModeVisibility()` (`.tmpl:624-628`) — there is no `data-mode` attribute or CSS-scoping convention anywhere in this template.
- Jargon-denylist enforcement is a single hardcoded Python list literal inline in one test function (`test_no_internal_jargon_in_visible_markup`, `test_policy_builder_emit.py:130-135`), checked against the emitted HTML with `<script>`/`<style>`/comment blocks stripped first (`_strip_script_style_comments`, `:22-34`). There is no separate reusable jargon-validator module — a third mode's own jargon terms would need direct additions to that same inline list.
- `serializeLoopYaml()` has no explicit `"decision_table"` branch — any `model.mode` other than the literal `"rubric"` silently falls through to `_serializeDecisionTable(model)` with no error. A third mode's branch must be added explicitly ahead of that fallback.
- Full inventory of `model.mode`/`state.mode` branch sites in the template beyond the three core functions: `computeSummary` (`:265`), `renderTryIt` (`:527`, early-return decision-table-only), `updateTryIt` (`:558`, same guard), `renderMessages` (`:581`, decision-table-only unreachable-outcome check), `renderAll` (`:610`), `applyModeVisibility` (`:624-628`, toggles `.hidden` on `threshold-fieldset`/`outcomes-fieldset`/`rules-fieldset`/`tryit-fieldset`), the `#mode-switch` `onchange` handler (`:632-638`, the only place `state.mode` is reassigned from user input, driven by a two-option `<select>` at `:121-124`), and `#start-blank-btn`'s `onclick` (`:684-693`).
- Because `policy_builder_core.mjs` is stamped verbatim into the emitted HTML, every one of these dispatch sites is also byte-mirrored in `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`.
- `cmd_policy_builder()` (`policy_builder.py:56-107`) has exactly four data-injection points into the template: `/*__THEMED_CSS_VARS__*/`, `/*__GRAMMAR_SPEC_JSON__*/`, `/*__SKILL_CATALOG_JSON__*/`, `/*__BUILDER_CORE_JS__*/` (each a literal `str.replace`). This issue needs no fifth placeholder: the Built-in Dimension Table and Verb Table are constants in the core `.mjs`, not emit-time data.
- The actual `opsForType(type)` at `.tmpl:274-276` is `return type === "boolean" ? ["==true", "==false"] : GRAMMAR.all_ops;` — it special-cases only `"boolean"`; every other type string receives the full unrestricted `GRAMMAR.all_ops` set. Adding `string` requires a second branch there.
- `grammar_spec()`'s `_PRED_PATTERN` (`fsm/policy_rules.py:32-34`) matches any word-ish dimension name, not a closed enum — a GUI author can already add an arbitrary dimension name today with no allowlist check (`.tmpl:646-652`). No engine or grammar change is needed for custom fields.
- `cmd_policy_builder`'s only error handling is a single outer `try/except Exception: logger.error(...); return 1` (`policy_builder.py:65,105-107`); there is no mode-specific validation in the Python CLI layer and no `--mode` flag — mode is purely a runtime/browser `state.mode` concept. This issue keeps it that way.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/lib/policy-router.yaml` — add the
  `frontmatter_scores` fragment (Proposed Solution §1) next to
  `policy_parse_scores`; update the header comment's fragment list and the
  "Score-source agnosticism" note to cite it as the deterministic scorer.
- `scripts/little_loops/templates/policy_builder_core.mjs` — `mode` parameter
  on `blankModel()`/`seedExample()`; `_serializeIssueLifecycle()` (including
  the `on_error: failed` / `failed` terminal wiring); explicit
  `issue_lifecycle` branch in `serializeLoopYaml()`; Built-in Dimension Table
  and Verb Table constants; pure frontmatter mini-parser + encoder for Try-it;
  `window.PolicyBuilderCore` exports for all of the above.
- `scripts/little_loops/fsm/validation/reachability.py` —
  `_validate_policy_dimensions_scored()` also reads
  `context.frontmatter_dimensions` into its scored set (Proposed Solution §1,
  "Validator change").
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — third
  mode option, `string` dim type, `opsForType()` branch, verb-outcome UI,
  frontmatter Try-it fieldset, and every `state.mode` dispatch site listed in
  the findings inventory.
- `scripts/tests/fixtures/policy_builder/sample-decision-table.yaml` (and the
  JS golden text in `policy_validator.test.mjs` if it inlines it) — regenerate
  for the BUG-2813 `_outcomeStateLines()` fix (the `escalate` finish outcome
  becomes `next: done` + bare `done:`). Diff must be limited to those lines.
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` —
  byte-mirrored golden fixture of the full stamped template;
  `test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture`
  does a hard byte-diff against it, so it MUST be regenerated once the
  template changes.
- `scripts/little_loops/loops/README.md` — update the `lib/policy-router.yaml`
  row (`:217`) to list `frontmatter_scores`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/artifact/policy_builder.py` — no code change
  expected (mode is browser-side; no new placeholder). Confirm only.
- `scripts/little_loops/fsm/validation/reachability.py` —
  `_validate_policy_dimensions_scored()` (line 154) calls `parse_rules()`
  (line 184) to lint FSM policy-rule text; the emitted rule text uses the same
  grammar (string `==`/`!=`, numeric ordered ops, compiled booleans) so it
  parses. Its scored-dimension check does **not** see the fragment's dynamic
  filenames, hence the change listed under Files to Modify. Verify with
  `ll-loop validate` on the golden YAML and assert **zero warnings**, not just
  zero errors (the existing `test_golden_yaml_validates` filters to ERROR
  only, which would let the false "never scored" warnings through).
- `scripts/little_loops/loops/policy-refine.yaml` — existing consumer of
  `policy_table_dispatch`; unaffected, but re-run its validate as a regression
  check after editing the shared fragment file.
- `docs/guides/POLICY_ROUTER_GUIDE.md` and `docs/reference/CLI.md` — both
  document the existing `policy-router`/`rubric` modes and need a third entry.

### Similar Patterns
- `scripts/little_loops/loops/rn-remediate.yaml:351-377` — deterministic
  shell scorer + first-match routing over issue scores; the `frontmatter_scores`
  fragment generalizes this using raw frontmatter instead of `show --json`.
- `scripts/little_loops/loops/rn-remediate.yaml:35` — `parameters: { issue_id:
  {...} }` self-declaration contract to copy for the emitted loop (not `with:`,
  which is a caller-side sub-loop-invocation key only — corrected 2026-09-16).
- `scripts/tests/js/policy_validator.test.mjs` — the `node --test`
  conformance pattern the new mode's core functions must follow.

### Tests
- `scripts/tests/test_policy_builder_emit.py` — add
  `test_golden_issue_lifecycle_yaml_validates` (non-parametrized, per
  convention); extend the jargon-denylist list literal if the mode introduces
  on-screen terms.
- `scripts/tests/test_policy_builder_node_gate.py:125` — add
  `"sample-issue-lifecycle.model.json"` to the hardcoded two-entry
  `@pytest.mark.parametrize` list.
- `scripts/tests/js/policy_validator.test.mjs` — add
  `test("serializeLoopYaml matches golden issue-lifecycle fixture", ...)`,
  plus tests for the frontmatter mini-parser/encoder driven by the shared
  encoding corpus below.
- New: `scripts/tests/fixtures/policy_builder/frontmatter_encoding_corpus.json`
  — the cross-language encoding contract (pasted frontmatter text +
  `name:type` dims → expected score map, including absent keys), consumed by
  **both** `test_policy_builder_corpus.py` (against the Python encoder) and
  `policy_validator.test.mjs` (against `parseFrontmatterBlock` +
  `encodeFrontmatterScores`), exactly as `conformance_corpus.json` pins
  `evaluate_rules`. Separate per-language tests would let the two encoders
  drift.
- `scripts/tests/test_fsm_validation_reachability.py` (the file that covers
  `_validate_policy_dimensions_scored`) — a loop with
  `context.frontmatter_dimensions` and no `rubric_dimensions` produces zero
  "never scored" warnings; a predicate on a dim absent from both still warns.
- `test_golden_issue_lifecycle_yaml_validates` must assert on **all**
  severities (`validate_fsm(fsm) == []`), not filter to ERROR as
  `test_golden_yaml_validates` does (`test_policy_builder_emit.py:101`) —
  otherwise the three inherited warnings (BUG-2813 terminal-action, missing
  `scope:`, MR-12 pruning-profile) pass silently and the zero-warnings AC is
  unenforced.
- `scripts/tests/js/policy_validator.test.mjs` — a case pinning the
  emitted-verb closure: model with rules → `refine` only, `refine.transition
  = {kind: "goto", target: "gate"}`, assert the YAML contains a `gate:` state
  and `ll-loop validate` passes; and a case asserting a `finish` verb with a
  `slash_command` emits `next: done` plus a bare `done:` terminal, never
  `terminal: true` alongside `action:`; a case asserting the seeded
  `implement` verb emits `action_type: shell` / `action: ll-auto --only
  ${context.issue_id}` and the seeded `refine` verb emits
  `action: /ll:refine-issue ${context.issue_id} --auto` with `next: gate`;
  and a `_doneStateName` case for a decision-table model whose outcome is
  named `done`.
- `scripts/tests/fixtures/policy_builder/sample-issue-lifecycle.model.json`
  and `.yaml` — new golden fixture pair; the YAML must pass `ll-loop validate`.
- `scripts/tests/test_policy_builder_corpus.py` /
  `scripts/tests/fixtures/policy_builder/conformance_corpus.json` — the
  corpus is numeric-only today; add cases for string `==`/`!=` predicates,
  missing-dimension semantics (`!=` matches, `==` does not), and the
  numeric-first coercion case (`severity:==1` against `"1"` and `"1.0"`) so
  the JS mirror and `evaluate_rules` agree on string handling.
- New: a pytest for the `frontmatter_scores` fragment that builds a temp
  issue file with built-in, custom, boolean (`true`/`yes`/`false`/absent as
  **strings**, since `BaseLoader` never yields `bool`), `list` (list /
  scalar / absent → count), non-numeric-under-numeric, `priority`
  (`P2` → `priority_rank` `2`; `high` → no file), `null`, and missing
  fields, runs
  the fragment's Python body, and asserts the exact `rubric-dim-*.txt` set
  and contents per the Encoding Rules, including the two-pass clean-slate
  case and the unresolved-ID non-zero exit (follow the fragment-testing pattern used for
  `policy_parse_scores` if one exists; otherwise extract the body to
  `little_loops.fsm.frontmatter_scores` and shell into it, matching how
  `policy_table_dispatch` imports `policy_rules`).

### Documentation
- `docs/guides/POLICY_ROUTER_GUIDE.md` — add the `issue_lifecycle` mode with
  the Built-in Dimension Table, Verb Table, and encoding rules.
- `docs/ARCHITECTURE.md` § "Project-enriched artifacts" — cites the catalog
  loader as `cli/action.py:_load_skills()`; the correct symbol is
  `cli/artifact/policy_builder.py:_load_skill_catalog()`. Fix while touching
  this area.

### Configuration
- N/A — no `.ll/ll-config.json` schema changes.

## Implementation Steps

1. Add the `frontmatter_scores` fragment to `lib/policy-router.yaml`
   (extracting its Python body to an importable module if that is how the
   fragment test is written). Unit-test the encoding rules. Extend
   `_validate_policy_dimensions_scored()` to read
   `context.frontmatter_dimensions`.
2. Add the `issue_lifecycle` mode to `policy_builder_core.mjs`: `mode`
   parameter on `blankModel`/`seedExample`, constants for the two tables,
   `string`/`list` type support, `_serializeIssueLifecycle` (referenced
   verbs only, `${context.issue_id}` appended), explicit dispatch branch,
   frontmatter mini-parser/encoder. Write the golden fixture pair and
   `node --test` cases; confirm the golden YAML passes `ll-loop validate`.
3. Add the mode's UI to `policy-router-builder.html.tmpl` (mode option,
   `string` dim type, `opsForType` branch, verb outcomes with catalog
   override, frontmatter Try-it), touching every `state.mode` site in the
   inventory. Regenerate the golden HTML fixture.
4. Update the parametrize list, corpus, jargon list, loops README row, and
   docs.
5. End-to-end: author the Use Case rules in the GUI, save the YAML into a
   scratch project, run `ll-loop run <name> --context issue_id=<ID>` against
   an issue with a custom `severity` field, and confirm the expected verb
   state fires. Repeat with a missing custom field to confirm the
   "Otherwise" catch-all fires.

### Wiring Phase (added by `/ll:wire-issue`)

- Regenerate `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`
  once template changes land — the byte-diff test will otherwise fail
  unconditionally. There is no regen script: run
  `ll-artifact policy-builder --output <tmpdir>` and copy the emitted
  `policy-router-builder.html` over the fixture.
- Add `"sample-issue-lifecycle.model.json"` to the `@pytest.mark.parametrize`
  list in `scripts/tests/test_policy_builder_node_gate.py:125`.
- Add the new mode's golden fixture pair and a matching `test(...)` block in
  `scripts/tests/js/policy_validator.test.mjs`.
- Naming-collision note (no code change, awareness only): the mode literal
  `"issue_lifecycle"` is a plain string match for the pre-existing, unrelated
  production module `scripts/little_loops/issue_lifecycle.py` (issue
  status-transition helpers, imported by `parallel/orchestrator.py` and
  `cli/issues/skip.py`); grep-based searches will hit both — disambiguate in
  commit messages and comments.

## Impact

- **Priority**: P3 - self-service tooling for other little-loops consumers,
  not blocking any in-repo workflow (little-loops itself keeps hand-tuned
  `autodev.yaml`).
- **Effort**: Large - a new grammar/mode on an existing shell, one new
  fragment, `string` and `list` dimension types, a small pure JS frontmatter
  parser, plus new `node --test` and pytest coverage.
- **Risk**: Low - additive third mode alongside `decision_table`/`rubric`;
  the new fragment is additive to `lib/policy-router.yaml`; neither existing
  mode's emitted YAML changes (verified by the existing golden fixtures).
- **Breaking Change**: No — the one shared-code change (`_outcomeStateLines`
  BUG-2813 fix) alters `decision_table` emitted YAML for finish-with-action
  outcomes, but only from a shape whose action never ran to one where it
  does; no consumer could have depended on the dead action.

## Design Decision: emitted-artifact shape (resolved)

**Selected:** the emitted artifact is a thin standalone loop YAML of the same
shape `decision_table` mode already emits, with the LLM scorer replaced by a
deterministic `frontmatter_scores` state. It is run per issue with
`ll-loop run <name> --context issue_id=<ID>`.

**Reasoning:** The earlier framing ("Option A: standalone FSM loop that
generates queue/retry/rate-limit states" vs. "Option B: policy config consumed
by a generic sub-loop") was a false dichotomy. `decision_table` mode already
proves the middle path: a standalone loop that is thin *because* the engine
lives in `lib/policy-router.yaml`. Neither a generic queue/retry/rate-limit
sub-loop nor per-artifact code generation of that machinery is needed, and
both are explicitly out of scope (see Non-goals). The only genuinely missing
piece is a deterministic scorer that turns frontmatter into the
`rubric-dim-*.txt` files `policy_table_dispatch` consumes; `ll-issues show
--json` cannot fill that role because it drops custom keys and renames
built-in ones, so the scorer reads raw frontmatter via `parse_frontmatter`.

**Superseded evidence retained for context:** `oracles/resolve-decision.yaml:163-181`
and `autodev.yaml:489-494` document that a `loop:` call state cannot observe a
child's rate-limit-exhaustion terminal. That gap is real but irrelevant here
because the emitted loop makes no sub-loop calls.

## Acceptance Criteria

- [ ] The GUI is a single self-contained `.html` file that opens over `file://`
  with no install step and no network dependency, matching FEAT-2301's shell.
- [ ] In `issue_lifecycle` mode the dimension list is pre-populated with the
  Built-in Dimension Table entries (including the derived `priority_rank`),
  each with its type locked and operators restricted by type (`numeric` and
  `list` all six; `boolean` `==true`/`==false`; `string` `==`/`!=`).
- [ ] A user can declare an arbitrary custom frontmatter field name with a
  chosen type (`numeric`, `boolean`, `string`, `list`) and use it as a rule
  dimension, and the emitted loop routes on it at run time without any
  little-loops code knowing the field — verified end to end against an issue
  file carrying a custom `severity` key.
- [ ] Each rule's outcome is one of the five lifecycle verbs, pre-bound to the
  Verb Table default skill/args and overridable from the emit-time skill
  catalog dropdown plus a free-text args input, with no "unknown skill"
  message for any default; verbs cannot be deleted and no outcome can be
  added. A `slash_command` verb's **emitted `action:`** is
  `<skill> ${context.issue_id} <args>` (`--auto` by default); the
  `implement` default is emitted as `action_type: shell` /
  `action: ll-auto --only ${context.issue_id}`, never as
  `/ll:manage-issue <ID>` (manage-issue requires `<type> <action>`
  positionals first). Only verbs referenced by a rule or the fallback are
  emitted.
- [ ] Rules are ordered/reorderable and read as a first-match list with a
  pinned non-input "Otherwise" catch-all, per FEAT-2301/FEAT-2390's shipped
  shell conventions.
- [ ] The emitted YAML imports only `lib/policy-router.yaml`, declares
  `parameters: { issue_id: {...} }`, `scope: ["."]`, and
  `pruning_profile_ok: true` (commented), uses `frontmatter_scores` →
  `policy_table_dispatch`, and passes `ll-loop validate` with **zero
  warnings of any rule** — the validator recognizes
  `context.frontmatter_dimensions` as a score source, and no BUG-2813,
  `scope:`, or MR-12 warning is emitted. The pytest asserts on every
  severity, not ERROR only.
- [ ] A verb whose transition is `finish` is emitted as a **non-terminal**
  state with `next: done` plus a bare `done: {terminal: true}`; the emitted
  YAML never pairs `action:` with `terminal: true`. The seeded example's
  `implement` state actually invokes `/ll:manage-issue` in an end-to-end run
  (observable in the run's events log), not a silent finish.
- [ ] The emitted verb set is the transitive closure over rule targets, the
  fallback, and `goto` targets of emitted verbs: a `goto` to an otherwise
  unreferenced verb emits that verb's state and validates clean.
- [ ] Every emitted verb state carries `on_error: failed`, and the YAML
  declares top-level `on_max_steps: failed`; a run whose refine/gate cycle
  never converges ends on `failed`, not `terminated_by: max_steps`.
- [ ] `_doneStateName` avoids the collision: a `decision_table` model with an
  outcome named `done` (action + finish) emits `next: finished` and a bare
  `finished:` terminal, never a self-loop or duplicate `done:` key; pinned by
  a `node --test` case.
- [ ] No visible markup in the new mode contains `predicate` or
  `policy_rules` (existing jargon-denylist test passes unchanged).
- [ ] Built-in dimensions show no delete control in `issue_lifecycle` mode;
  custom dimensions remain deletable.
- [ ] The emitted `score` state sets `on_error: failed` and the YAML carries a
  `failed: {terminal: true}` state; running the loop with an unresolvable
  `issue_id` ends in `failed` without invoking any verb.
- [ ] `frontmatter_scores` clears all `rubric-dim-*.txt` and
  `rubric-aggregate.txt` in `${context.run_dir}` before writing, then encodes
  values per the Encoding Rules (boolean → 100/0 by string-truthiness on
  `true/yes/on/1`, always written; `list` → count, always written, absent →
  `0`, scalar → `1`; non-numeric scalar under `numeric` → verbatim;
  missing/`null` numeric or string → no file; `priority_rank` synthesized
  from `P<digit>`) and exits non-zero on an unresolved issue ID; covered by
  a pytest whose fixture values are strings, matching `BaseLoader` output,
  including a two-pass case where a field cleared between passes leaves no
  stale file.
- [ ] The Python encoder and the JS `parseFrontmatterBlock` +
  `encodeFrontmatterScores` pair agree on every case in a shared
  `frontmatter_encoding_corpus.json`, including `""`/`null`/`~` → absent,
  `status` synonym canonicalization, quoted scalars (`'open'`, `'2026-09-14'`),
  values containing `:`, and `priority` → `priority_rank` derivation.
- [ ] Try-it evaluates the compiled rule table: a `decision_needed:==false`
  rule does **not** fire against pasted `decision_needed: true`, and a
  `node --test` case pins this against `evaluateRules` on the compiled text.
- [ ] Each verb outcome seeds the Verb Table's default transition
  (prepare/gate → rescore, refine → goto gate, implement/verify → finish) and
  remains editable via the existing outcome transition selector; in an
  end-to-end run on an unscored issue the seeded example fires gate first,
  then refine → gate → implement once `confidence_score` reaches 85
  (observable in the run's events log).
- [ ] The Try-it panel accepts a pasted frontmatter block and reports the
  firing rule, agreeing with `evaluate_rules` on every conformance-corpus case.
- [ ] The new mode's pure-function core logic ships with `node --test`
  conformance coverage, gated into `python -m pytest scripts/tests/` the same
  way `test_policy_builder_node_gate.py` gates the existing modes.
- [ ] The `rubric` golden YAML fixture is byte-unchanged. The
  `decision_table` golden changes **only** in the BUG-2813 fix (finish
  outcomes with an action become `next: done` + bare `done:`); the diff is
  limited to those lines and is called out in the commit message.
- [ ] The GUI does not attempt to reproduce `autodev.yaml`'s queue/retry/rate-
  limit/repair-cycle machinery (see Non-goals).

## Program Design

### Types

- `mode: "issue_lifecycle"` — new literal value for the existing `model.mode`
  field, alongside `"decision_table"` and `"rubric"`.
- `dimension: {name: string, type: "numeric" | "boolean" | "string" | "list"}`
  — the existing shape with `"string"` and `"list"` added; no `kind`
  discriminator.
- `outcome: {name: "prepare" | "refine" | "gate" | "implement" | "verify",
  actionType: "slash_command" | "shell", body: string, args?: string, transition: {kind: "rescore" | "goto" | "finish", target?: string}}`
  — existing outcome shape plus a new optional `args` string and a new
  `"shell"` `actionType` value (both modes; absent `args` serializes as
  before, so existing model fixtures are unaffected). Seeded from the Verb
  Table (rescore for prepare/gate, goto gate for refine, finish for
  implement/verify; `args: "--auto"` on the four slash-command verbs;
  `implement` is `{actionType: "shell", body: "ll-auto --only"}`). `body` is
  the bare `/ll:<name>` or shell command; ` ${context.issue_id}` and then
  ` <args>` are appended at emit time.
- `BUILTIN_FRONTMATTER_DIMENSIONS: ReadonlyArray<dimension>` and
  `LIFECYCLE_VERBS: ReadonlyArray<outcome>` — new exported constants in
  `policy_builder_core.mjs`.

### Signatures

- `blankModel(mode = "decision_table") -> Model` — adds an optional parameter
  to the existing zero-arg function (`policy_builder_core.mjs:300`); the
  `issue_lifecycle` branch seeds dimensions and outcomes from the constants.
- `seedExample(mode = "decision_table") -> Model` — same treatment
  (`policy_builder_core.mjs:247`); the example encodes the Use Case rules.
- `serializeLoopYaml(model: Model) -> string` — new explicit
  `mode === "issue_lifecycle"` branch ahead of the decision-table fallback
  (`policy_builder_core.mjs:645`).
- `_serializeIssueLifecycle(model: Model) -> string` — new; emits the shape
  in Proposed Solution §2 (including `scope`, `pruning_profile_ok`, `done`,
  `failed`), reusing `_serializeRulesText`, the route-map builder, and
  `_outcomeStateLines`; emits the goto-closed verb set and appends
  ` ${context.issue_id}` to each `slash_command` body.
- `_emittedVerbs(model: Model) -> string[]` — new pure helper; transitive
  closure over rule targets, `model.fallback`, and `transition.target` of
  `goto` outcomes already in the set. Exported for `node --test`.
- `_outcomeStateLines(outcome, {doneState = "done", issueArg = false} = {}) -> string[]` —
  existing (`policy_builder_core.mjs:458`); changed so a `finish` transition
  on an outcome **with** an action emits `next: <doneState>` instead of
  `terminal: true` (BUG-2813 fix, both modes); gains the `shell` action type
  (`action_type: shell` / `action: <body>`) and, when `issueArg` is set,
  appends ` ${context.issue_id}` and then ` <outcome.args>` (if non-empty)
  to `slash_command`/`shell` bodies. Callers must emit the bare
  `<doneState>: {terminal: true}` once. `finish` with `actionType: none`
  keeps emitting `terminal: true`.
- `_doneStateName(model) -> string` — new pure helper; returns `"done"`
  unless an outcome, rule target, or fallback already uses that name, else
  `"finished"`. Used by `_serializeDecisionTable` for the BUG-2813 fix;
  exported for `node --test`.
- `serializeFrontmatterDimensions(model: Model) -> string` — new; produces
  the `name:type|name:type` text for `context.frontmatter_dimensions`.
- `parseFrontmatterBlock(text: string) -> Record<string, unknown>` — new pure
  mini-parser for Try-it (scalars with optional matching quotes, first-`:`
  split, booleans, flow and dash lists).
- `encodeFrontmatterScores(fm: Record<string, unknown>, dims: dimension[]) -> Record<string, number | string>`
  — new pure encoder mirroring the fragment's rules (including `list` count
  and the derived `priority_rank`); keys are **normalized** dim names, matching
  the runtime `scores` dict built from filenames; shared by Try-it.
- `opsForType(type: string) -> string[]` (template, `.tmpl:274`) — add the
  `"string"` branch returning `["==", "!="]` (`"list"` falls through to
  `GRAMMAR.all_ops`).
- `frontmatter_scores` fragment (YAML, `lib/policy-router.yaml`) — shell
  state reading `${context.issue_id}`, `${context.frontmatter_dimensions}`,
  `${context.run_dir}`; clears then writes `rubric-dim-*.txt`; `next` and
  `on_error` supplied by caller.
- `_validate_policy_dimensions_scored(fsm: FSMLoop) -> list[ValidationError]`
  (`fsm/validation/reachability.py:154`) — existing; its scored-set builder
  additionally splits `context.frontmatter_dimensions` on `|`, takes the part
  before the first `:` of each entry, and normalizes it like
  `rubric_dimensions`.

### Call Path

`cmd_policy_builder` -> `_load_skill_catalog` (both
`scripts/little_loops/cli/artifact/policy_builder.py`) -> stamps
`policy_builder_core.mjs` into `policy-router-builder.html.tmpl` -> user
selects `issue_lifecycle`, authors rules -> `serializeLoopYaml` ->
`_serializeIssueLifecycle` (emits a top-level `parameters: { issue_id:
{...} }` self-declaration, not `with:` — corrected 2026-09-16) -> saved YAML
run via `ll-loop run <name> --context issue_id=<ID>` -> `frontmatter_scores`
(fragment; non-zero exit -> `on_error` -> `failed`) -> `policy_table_dispatch`
(fragment; `parse_rules` / `evaluate_rules` in `fsm/policy_rules.py`) -> verb
outcome state (`slash_command`).

## Use Case

A little-loops consumer has their own issue frontmatter conventions (e.g. a
custom `severity` field, or a `review_status` field that isn't part of
little-loops' schema) and wants a lightweight lifecycle loop — "when severity is
critical and review_status is approved, implement immediately; otherwise gate on
confidence_score >= 70" — without hand-writing FSM YAML or understanding
`autodev.yaml`'s internals. They open the GUI over `file://`, add `severity`
and `review_status` as `string` dimensions, author the two rules plus the
"Otherwise → refine" catch-all, paste an issue's frontmatter into Try-it to
confirm which rule fires, save the YAML, and run it with
`ll-loop run my-lifecycle --context issue_id=BUG-42`.

Seeded example rules (also the `seedExample` content):

```
status:==done -> verify
severity:==critical & review_status:==approved -> implement
confidence_score:>=85 -> implement
confidence_score:<85 -> refine
* -> gate
```

The rule order relies on the documented missing-dimension semantics: an
issue with no `confidence_score` fails both ordered rules and falls to the
`* -> gate` catch-all, which is the one verb that writes the score. With the
Verb Table's default transitions a single run on an unscored issue goes
gate (writes `confidence_score: 40`) → rescore → `<85` → refine → **goto
gate** (rescores the issue) → rescore → `>=85` → implement → done. If refine
never lifts the score, the refine/gate cycle ends at `max_steps` on the
`failed` terminal via `on_max_steps`. `implement` is a finish transition, so
`status:==done -> verify` fires on a **subsequent** `ll-loop run` against
the same issue, not within the run that implemented it. (The earlier seed —
`confidence_score:>=70 -> gate` / `* -> refine` with refine → rescore —
could never reach `gate`, because refine-issue does not write the score;
corrected in the 5th pass.)

## UI Notes

No separate mockup: this mode reuses the shipped FEAT-2301 shell (theme
tokens, `#mode-switch`, fieldset layout, demoted YAML rail, pinned
"Otherwise" footer) unchanged. Only three surfaces are new; decisions below so
the implementer does not guess. Existing classes only (`rule-row`, `row`,
`help`, `hint`, `secondary del`, `rule-winner`) — no new CSS beyond one
`.locked` rule.

- **Locked built-in dimension rows.** Rendered in the same `#dim-list` as
  custom rows, built-ins first in Built-in Dimension Table order, then custom
  rows in insertion order. A built-in row omits the `✕` button entirely (never
  a disabled one) and shows a `<small class="help">built-in</small>` tag after
  the `(type)` marker. `priority_rank` additionally reads
  `(numeric, derived from priority)`. One fieldset-level help line replaces
  the current boolean-help text in this mode: "Built-in fields come from the
  issue's frontmatter and can't be removed. Add your own fields below."
- **Fixed verb outcomes.** The five verbs render as rows with no `✕` button
  (omitted, not disabled — a disabled control reads as broken) and
  `#add-outcome` hidden. Each row is: verb name in `<strong>`, the existing
  skill-catalog `<select>` pre-set to the default, the free-text `args`
  input (placeholder `--auto`, blank for `implement`), and the transition
  `<select>`. `implement`'s row shows its shell default as a read-only
  `<code>ll-auto --only $ISSUE</code>` in place of a selected catalog entry
  until the user picks a skill. Verbs stay in Verb Table order; no drag
  handle. Help line:
  "Every verb is available as a rule target; verbs no rule routes to are left
  out of the saved loop."
- **Frontmatter Try-it.** `#frontmatter-tryit-fieldset` holds one
  `<textarea rows="8">` with placeholder
  `status: open\npriority: P2\nconfidence_score: 40` and
  `aria-label="Paste issue frontmatter"`. Winner feedback reuses
  `rule-winner` on the matching rule card exactly as decision-table Try-it
  does; no separate result box. A `<p class="hint">` under the textarea shows
  either the encoded scores as `key=value` pairs (so users see
  `priority_rank=2` and `blocked_by=0` appear) or, on a mini-parser failure,
  the first unparseable line prefixed `Can't read line N:`; parse failure
  clears any winner highlight. The `---` fence lines are tolerated and
  ignored.

## Non-goals

- Not a generator for `autodev.yaml` itself, and not a replacement for it in this
  repo.
- No queue management, retries, rate-limit handling, or repair cycles. One
  issue per run; users batch with `ll-auto`, a shell loop, or a wrapping FSM.
- No generic issue-lifecycle sub-loop; the emitted loop is self-contained.
- No round-trip editing of existing loops (consistent with FEAT-2301's scope cut).
- No nested-map frontmatter support in Try-it's mini-parser (scalars, booleans,
  and lists only); the runtime scorer uses the full `parse_frontmatter`.

## Related Key Documentation

- `scripts/little_loops/loops/autodev.yaml` — the production loop whose *shape*
  (not implementation) motivates this issue; explicitly out of scope to clone.
- `.issues/features/P3-FEAT-2301-self-contained-html-builder-for-policy-router-and-rubric-fsm-loops.md`
  — shipped sibling grammar/mode on the same builder shell.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` /
  `policy_builder_core.mjs` — the existing shell + pure-function core this issue
  extends.
- `scripts/little_loops/loops/lib/policy-router.yaml` — the fragment file that
  gains `frontmatter_scores`.
- `scripts/little_loops/loops/rn-remediate.yaml` — precedent for a per-issue
  deterministic scorer loop and the `parameters: { issue_id: {...} }` contract.

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the
same pass, so the issue as it now reads is up to date — this section is a
record of what was wrong and fixed, not an outstanding action item).

- **Schema-key error (4 occurrences, corrected):** the issue claimed the
  emitted loop's parameter self-declaration is `with: { issue_id:
  {required: true} }`, citing `rn-remediate.yaml:11-36` as precedent. That's
  wrong — `rn-remediate.yaml:35` self-declares via `parameters: {...}`, and
  `with:` is exclusively a **caller-side** key for sub-loop/fragment
  invocations (`fsm/schema.py:684`: "Explicit parameter bindings for sub-loop
  calls"). No loop in the codebase self-declares parameters via `with:`. As
  originally written, following the Proposed Solution literally would emit a
  loop YAML using a nonexistent self-declaration key, likely failing
  `ll-loop validate` or silently not registering `--context issue_id=`.
  Corrected in Proposed Solution §2, Similar Patterns, the AC bullet, and
  Program Design's Call Path.
- **Minor, not corrected — informational only:** the Integration Map's
  "`cmd_policy_builder()` ... stamps four literal placeholders ... via
  sequential `str.replace()` calls" is slightly imprecise: only 3 of the 4
  (`__GRAMMAR_SPEC_JSON__`, `__SKILL_CATALOG_JSON__`, `__BUILDER_CORE_JS__`)
  are literal `str.replace()` calls inside `cmd_policy_builder()`
  (`policy_builder.py:92-94`); the 4th (`__THEMED_CSS_VARS__`) is stamped via
  the shared `stamp_page_shell()` helper (`artifact_template_kit.py:70`),
  called earlier in the same function. Doesn't change the conclusion ("no
  code change expected... confirm only").
- All other file:line claims across both "Codebase Research Findings"
  sections, the Program Design section, and the Similar Patterns /
  Dependent Files lists (~25 distinct citations) were checked against the
  current codebase and confirmed accurate, including the `ARCHITECTURE.md:1058`
  `_load_skills()` mis-citation the issue itself flags as needing a fix
  elsewhere.
- Decisions log: no active required rules — clean.
- Evidence-quote check (`ll-verify-evidence`): clean, 0 findings.
- Graph: provider=`codegraph` freshness=`fresh` — used for anchor
  confirmation only, no verdict originated from it alone.

## Status

**Open** | Created: 2026-09-14 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-09-16T19:10:06 - `3d7f4fbe-8b24-4254-ace7-f059ce8a9849.jsonl`
- pre-implementation review (5th pass) - 2026-09-16 - five fixes: (1) **blocking** — seed rules and Verb Table defaults never converged: refine-issue does not write `confidence_score` (only confidence-check does via `ll-issues set-scores`), so `* -> refine` + rescore spun until `max_steps` and `gate` + rescore re-fired forever; seed reordered (`>=85 -> implement`, `<85 -> refine`, `* -> gate`), `refine` defaults to goto gate, `on_max_steps: failed` emitted; (2) **blocking** — `/ll:manage-issue ${context.issue_id}` is malformed (skill requires `<type> <action>` positionals, type unknowable at emit time); `implement` now defaults to a `shell` outcome `ll-auto --only ${context.issue_id}`, matching rn-remediate:470/autodev; (3) the four slash-command verbs need `--auto` to run unattended — new per-outcome `args` field, emitted as `<skill> ${context.issue_id} <args>`; (4) BUG-2813 fix's `done` state can collide with a user outcome named `done` — `_doneStateName` helper; (5) `on_error: failed` rationale corrected (infra-only) and jargon-denylist constraint (`predicate`, `policy_rules`) recorded for new UI copy. Confirmed fine: `:shell` modifier, `scope`/`pruning_profile_ok` keys, `ll-issues path --json` shape, run pre-flight rejects missing `issue_id`, no INFO validator severity.
- pre-implementation review (4th pass) - 2026-09-16 - seven fixes: (1) **blocking** — `finish` verbs (`implement`/`verify` defaults) were emitted terminal-with-action and the executor never runs a terminal's action (executor.py:816); now `next: done` + bare `done:`, fixed in shared `_outcomeStateLines()` (BUG-2813) with a called-out decision-table golden regen; (2) zero-warnings AC was unreachable — live validate on the decision-table golden emits BUG-2813, missing-`scope:`, and MR-12 pruning-profile warnings; emit `scope: ["."]` + commented `pruning_profile_ok: true`, and the golden pytest asserts all severities; (3) emitted-verb set is now the `goto`-transitive closure (dangling `next:` otherwise); (4) `on_error: failed` on verb states; (5) built-in dims locked against `✕` delete; (6) `ll-issues path` prints project-root-relative — fragment uses `--json` and joins; (7) validator test file named (`test_fsm_validation_reachability.py`). Confirmed no gap: fragment deep-merge preserves caller `on_error`; `parse_frontmatter` claims reproduced live.
- `/ll:verify-issues` - 2026-09-16T17:34:14 - `28136058-041a-417b-9160-4c1439302c2e.jsonl`
- pre-implementation review (3rd pass) - 2026-09-16 - six fixes: (1) resolved `blocked_by` absent→0 vs numeric absent→no-file contradiction by adding a `list` type (count, always written); (2) verb bodies stored bare (`/ll:<name>`), `${context.issue_id}` appended at emit time — the argument-bearing form trips the exact-match skill `<select>` and unknown-skill check; (3) Try-it must evaluate compiled rule text — existing decision_table Try-it passes raw `==true`/`==false` ops to `evaluateRules`, which treats them as `!=` (node-verified; separate BUG); (4) only rule/fallback-referenced verbs emitted, verbs locked, unreachable-outcome message suppressed; (5) derived numeric `priority_rank` so `P0–P2` rules work; (6) mini-parser handles quoted scalars and first-`:` split. Noted `failed` ∈ `FAILURE_TERMINAL_NAMES`.
- `/ll:confidence-check` - 2026-09-16T17:18:27 - `59d9bf8a-daa3-4ac7-90d2-36e60eb01134.jsonl`
- pre-implementation review (2nd pass) - 2026-09-16 - three executor/validator mismatches fixed: clean-slate deletion of stale `rubric-dim-*.txt` on rescore (run_dir persists; dispatch reads every file), `on_error: failed` + `failed` terminal (next-chained shell states ignore exit code without `on_error`, executor.py:2161), validator extension for `context.frontmatter_dimensions` (reachability.py:201-218 would warn "never scored" per dim). Also: shell-interpolation pattern pinned to `policy_table_dispatch`, shared encoding corpus, mode-switch semantics, `coerce_types=False`, `:`/`|` key rejection, `_serializeRulesText` needs no string branch, `PolicyBuilderCore` exports, golden HTML regen command, Use Case "next pass" wording
- pre-implementation review - 2026-09-16 - added Encoding Rules (BaseLoader string-truthiness for booleans, dropped unexpressable "missing string → empty" encoding, defined non-numeric/scalar-where-list cases, name-normalization and string-value validation contracts); Verb Table gains default transitions (rescore for prepare/refine/gate); corpus/test/AC bullets updated to match
- `/ll:verify-issues` - 2026-09-16T16:43:24 - `40a29daf-d13d-4b50-8d3f-07379ec26437.jsonl`
- review rewrite - 2026-09-16 - resolved emitted-artifact shape, added `frontmatter_scores` scorer, value-encoding rules, `string` type, verb defaults, Try-it; removed refuted directive claims
- `/ll:refine-issue` - 2026-09-16T16:03:25 - `80866648-631d-42a2-9297-c19a0708559a.jsonl`
- `/ll:wire-issue` - 2026-09-16T15:55:33 - `30351525-6d5f-4f17-875c-0966e887e75a.jsonl`
- `/ll:refine-issue` - 2026-09-16T15:42:26 - `5f7a02ee-f693-4547-b06c-90ac4758be6a.jsonl`
- `/ll:refine-issue` - 2026-09-16T15:36:40 - `5f7a02ee-f693-4547-b06c-90ac4758be6a.jsonl`
- `/ll:decide-issue` - 2026-09-16T15:29:10 - `0f1bb5c4-ede6-454e-91d0-c97fb496e2cd.jsonl`
- `/ll:decide-issue` - 2026-09-16T05:02:58 - `8f3ac7b1-a0c3-4119-9504-bcaf52b84b4c.jsonl`
- `/ll:format-issue` - 2026-09-14T17:26:12 - `935702d4-fd79-4fcc-b1ed-24d764f51e14.jsonl`
- `/ll:capture-issue` - 2026-09-14T17:11:14 - `b2c42f0a-8e12-495a-9786-d532e21cd8a7.jsonl`
