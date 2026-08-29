---
id: ENH-2979
title: '--deep flag: LLM-adjudicated clustering for link-epics synthesize mode'
type: ENH
priority: P4
status: open
captured_at: '2026-08-01T21:03:45Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
parent: EPIC-2938
blocked_by:
- FEAT-2942
verify_verdict: PROPOSAL_UNSOUND
reconcile_attempted: true
decision_needed: false
confidence_score: 90
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# ENH-2979: --deep flag: LLM-adjudicated clustering for link-epics synthesize mode

## Summary

`/ll:link-epics --mode synthesize` clusters orphaned issues using plain Jaccard
word-overlap on title+summary text (`skills/link-epics/SKILL.md` Step 3, S1). This
structurally misses thematically-related issues that don't share vocabulary. Add a
`--deep` flag that swaps in an LLM-adjudicated clustering pass instead, pre-filtered
by the existing Jaccard scoring to bound the candidate set sent to the model.

## Current Behavior

`--mode synthesize` computes pairwise Jaccard scores over 3+ char alphabetic tokens
(minus a small stop-word list) from each orphan's title+summary, then union-finds
pairs at or above `MIN_SCORE` (default `0.3`) into clusters. Word-overlap-only
scoring has no stemming, no synonym/embedding awareness, and weights all words
equally — two issues about the same underlying theme phrased with different
vocabulary (e.g. "predicate" vs. "heuristic") score 0 unless they happen to reuse
words verbatim.

Validated live this session: running `/ll:link-epics --mode synthesize` against 11
real orphaned open issues produced a maximum pairwise Jaccard score of 0.06 (between
ENH-2967 and ENH-2971) — far under the 0.3 default threshold — so every orphan fell
out as a singleton despite several being plausibly related in intent (e.g. issues
about heuristic/predicate duplication across autodev.yaml and refine-issue).

## Expected Behavior

A `--deep` flag on `--mode synthesize` clusters orphans by thematic/semantic
relatedness rather than raw vocabulary overlap, while staying inspectable (grounded
in cited evidence) and bounded in cost.

## Motivation

The synthesize mode's whole purpose is to surface EPIC-worthy groupings a human
hasn't noticed yet. A purely lexical similarity metric can only find groupings that
already reuse the same words — exactly the case a human skimming titles would
already catch. The mode is least useful precisely where it's most needed: small,
jargon-heavy engineering backlogs where related issues are phrased independently.

## Proposed Solution

Design agreed with user (this session):

- Keep the existing Jaccard pass (Step 3 / S1 in `skills/link-epics/SKILL.md`) as a
  cheap pre-filter to bound the candidate list — do **not** have the LLM score all
  O(n²) pairs directly; that doesn't scale with orphan count.
- `--deep` sends the pre-filtered candidate list (or, if pre-filtering yields
  nothing, the full orphan list when count is small enough) to an LLM in **one
  batched call** — not one call per pair — to propose thematic clusters.
- The LLM step must **cite which words/phrases** in the issues' titles/summaries
  justify grouping them together — an evidence-contract requirement in the same
  spirit as MR-8's evidence-contract check for FSM `check_semantic` prompts
  (`.claude/CLAUDE.md` § Loop Authoring), applied here to skill prose instead of FSM
  YAML — so clustering output stays inspectable rather than an ungrounded judgment
  call the user can't verify.
- This is a flag on the existing `link-epics` skill (`mode: synthesize`), **not a
  new skill** — same operation, different scoring backend for the clustering step,
  matching the existing `mode: assign` / `mode: synthesize` precedent for branching
  behavior via flags rather than new skill files.
- Default behavior (no `--deep`) is unchanged: pure Jaccard threshold clustering
  exactly as it works today.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

Step 3's "merge LLM-proposed clusters with any Jaccard-only clusters (dedupe by
member overlap)" has no precedent to reuse (Program Design's Codebase Research
Findings above: no merge-by-overlap utility exists anywhere in this codebase)
and no stated rule for partial overlap or conflicting `placeholder_title`/
`evidence` between a Jaccard cluster and an LLM cluster that share only some
members. Two viable resolutions:

**Option A**: Any shared member merges the two clusters (union of both
member sets into one cluster), and the merged cluster always takes the LLM
cluster's `placeholder_title` and `evidence` (never the Jaccard cluster's,
which has no `evidence` to offer). Simple, but a single incidental shared
member can pull two otherwise-unrelated clusters together.

> **Selected:** Option A — matches the codebase's existing `_UnionFind`
> clustering behavior exactly (`link_epics.py:125-141`), which already merges
> transitively on any shared edge; Option B's majority-overlap threshold has
> no precedent anywhere in this codebase and would need a new, unjustified
> numeric threshold plus a still-unresolved tie-break rule.

**Option B**: Merge only when the smaller cluster's members are a *majority*
subset of the larger cluster's members (e.g. >50% overlap); a minority/partial
overlap is left as two separate clusters rather than merged. Avoids Option A's
transitive-chaining risk but requires picking and justifying the majority
threshold, and still needs a same tie-break rule for `placeholder_title`/
`evidence` on an actual merge.

**Recommended**: Option A for v1 — Option B's threshold is itself an
unprecedented number this codebase has no basis to pick, and Option A's
transitive-chaining risk already exists in the current Jaccard-only
`_UnionFind` clustering (a shared member already merges pairwise-linked
issues today), so `--deep` would not be introducing a new failure mode, only
extending an accepted existing one.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-29.

**Selected**: Option A — any shared member merges the two clusters

**Reasoning**: Option A's "any shared member merges" rule is exactly what the
existing `_UnionFind`-based Jaccard clustering (`link_epics.py:125-141,154-189`)
already does today — a shared edge between any two orphans transitively merges
their entire cluster, so `--deep`'s merge step introduces no new failure mode,
only extends an accepted existing one. Option B's majority-overlap threshold
has no precedent anywhere in this codebase (confirmed via repo-wide search for
merge-by-overlap/disjoint-set/majority-threshold logic — the only "overlap
threshold" hits are pairwise edge thresholds, not a two-cluster-set merge rule)
and would require inventing and justifying a new numeric threshold plus a
still-unresolved `placeholder_title`/`evidence` tie-break rule.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option B | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**:
- For Option A: `_UnionFind.union()` (`link_epics.py:137-140`) merges
  transitively on any shared member — confirmed by direct read; Option A
  applies this exact existing mechanism one level up (merging two cluster
  sets on any shared member) rather than introducing a new one.
- For Option B: repo-wide search (`grep -rn "disjoint.set\|merge.by.overlap\|
  majority.*overlap\|overlap.*threshold"`) found no existing code that merges
  two pre-built cluster sets by member-overlap fraction — every "overlap
  threshold" hit in the codebase is a pairwise edge threshold (e.g.
  `dup_overlap_threshold`, `workflow_sequence` clustering), not this shape.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/link_epics.py` — add `--deep` flag parsing to
  `add_link_epics_parser()` (line 257-292); add a batched LLM clustering step
  invoked from `synthesize_clusters()` (line 154); add an `evidence` field to
  `ClusterProposal` (line 63-79, currently four fields with no evidence field)
  and its `to_dict()` (line 72-79); extend `cmd_link_epics()`'s JSON/human-readable
  output (line 352-358) to show the cited evidence for `--deep`-sourced clusters.

### Dependent Files (Callers/Importers)
- N/A — `link-epics` is a leaf skill invoked directly via `/ll:link-epics`; no
  other skill or loop shells out to it programmatically.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py:79,879,1047` — `main_issues()`
  imports `add_link_epics_parser`/`cmd_link_epics` (line 79), registers the
  subcommand via `add_link_epics_parser(subs)` (line 879), and dispatches to
  `cmd_link_epics(config, args)` (line 1047) using the generic parsed `args`
  Namespace. No edit needed here — any new flag added inside
  `add_link_epics_parser()` (including `--deep`) reaches `cmd_link_epics()`
  automatically through this passthrough; confirmed via `ll-code callers-of
  add_link_epics_parser` / `callers-of cmd_link_epics` and direct grep. [Agent 1
  finding]

### Similar Patterns
- `.claude/CLAUDE.md` § Loop Authoring MR-8 (evidence-contract keyword check for
  FSM `check_semantic` prompts) — apply the same "cite verbatim evidence" principle
  to the new LLM clustering prompt, even though MR-8 itself only lints FSM YAML
  (see `reference_mr8_evidence_contract_scope` memory) and won't enforce this
  automatically.

### Tests
- No existing test file covers `link-epics` end-to-end (it's a prose skill, not a
  CLI); manual verification via `/ll:link-epics --mode synthesize --deep` against a
  backlog with known thematically-related-but-lexically-distinct orphans.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_link_epics_cli.py::TestSynthesizeClusters` (5 methods,
  lines 104-149) — existing coverage of `synthesize_clusters()`'s current
  two-parameter signature; confirm none of these break once a `--deep`/LLM
  path is added alongside it (parity contract already noted under Codebase
  Research Findings above). [Agent 3 finding]
- `scripts/tests/test_artifact_discover.py` (mocking pattern at lines
  196-244) — the concrete pattern new `--deep` tests must follow: `patch(
  "little_loops.cli.artifact.discover.resolve_host", ...)` and `patch(
  "little_loops.cli.artifact.discover.run_blocking_json", ...)`, i.e. mocked
  at the call-site module's own namespace. This is required, not optional:
  the session-scoped autouse fixture `_install_no_live_host_cli`
  (`scripts/tests/conftest.py:352-395`, FEAT-3329) raises if any test lets a
  real host CLI binary spawn via `subprocess.run`/`Popen`, which
  `run_blocking_json` goes through — a `--deep` test that doesn't mock at
  this boundary fails the guard rather than exercising real behavior.
  [Agent 3 finding]

### Documentation
- `skills/link-epics/SKILL.md` — usage examples section needs a `--deep` entry.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (§ `ll-issues link-epics`, ~line 2555-2579) — the
  flags table and `**Examples:**` block document `--mode`/`--threshold`/
  `--apply`/`--json`/`--config` but not `--deep`; needs a new table row plus an
  example command. [Agent 2 finding]
- `docs/reference/COMMANDS.md` (§ `/ll:link-epics`, ~line 432-440) — the flags
  list documents `--threshold` but not `--deep`. [Agent 2 finding]
- `docs/reference/API.md` (§ `little_loops.cli.issues.link_epics`, ~line
  1454-1463) — reproduces the `ClusterProposal` dataclass verbatim (its exact
  four fields plus `to_dict()` docstring); needs the new `evidence` field
  (Types section, this issue) added here in lockstep once implemented, or this
  doc goes stale the moment the dataclass changes. [Agent 2 finding]

### Configuration
- Resolved (Program Design's candidate-set-size decision, 2026-08-29 pass): no
  config-schema change. `scripts/little_loops/config-schema.json`'s
  `issues.link_epics` object (lines 159-172) is `additionalProperties: false`
  and holds only `min_score`; the 40-orphan candidate-set cap is hardcoded as
  a module constant in `link_epics.py` instead of a new config key. The
  batched LLM call's `model` parameter is likewise not config-backed: it
  follows `discover_regions()`'s own convention of hardcoding
  `model = DEFAULT_LLM_MODEL` (`fsm.schema.DEFAULT_LLM_MODEL`, value
  `"sonnet"`, used directly at `discover.py:418`) rather than threading a
  `config.advisor.model`-style knob (`advisor.py:251`) — `discover_regions()`
  is the closer precedent this issue already selected for the batched-call
  shape, and it does not read model from config either.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

- The Jaccard clustering logic this issue targets is no longer in `skills/link-epics/SKILL.md` prose — FEAT-2942 landed and moved it into `scripts/little_loops/cli/issues/link_epics.py` (`synthesize_clusters()`, line 154; `cmd_link_epics()`, line 295-359) and `scripts/little_loops/text_utils.py` (`extract_words`, line 387; `calculate_word_overlap`, line 404). `ll-issues link-epics --mode synthesize` is now a Python CLI, not a skill step. See `### Program Design` above for exact signatures and the current call path.
- CLI flag registration (where `--deep` would be added) is `add_link_epics_parser()` (`link_epics.py:257-292`) — `--mode`, `--threshold` (config-backed default via `issues.link_epics.min_score`, `config-schema.json:159-172`), and `--apply` (rejected for `--mode synthesize` at line 310-316) are the existing precedent for how a new flag is wired.
- Test coverage lives in `scripts/tests/test_link_epics_cli.py::TestSynthesizeClusters` (5 methods, lines 104-149) — all call `synthesize_clusters(orphans, min_score=...)` with the current two-parameter signature; none pass a `deep`/LLM parameter, so this suite is the parity contract for the non-`--deep` path.
- `ClusterProposal` (`link_epics.py:63-79`) has no evidence/rationale field today — the issue's evidence-citation requirement needs one added.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- A materially closer batched-call precedent than `decisions.py::_cmd_extract_from_completed()` (cited above) exists: `discover_regions()` (`scripts/little_loops/cli/artifact/discover.py:394-431`, FEAT-3315) makes exactly **one** `resolve_host().build_blocking_json(prompt=..., json_schema=_DISCOVERY_SCHEMA)` call whose schema's top-level `regions` property is a JSON array (`discover.py:37-53`) — i.e. one call proposing many grouped items, not one call per item. It fails closed on a malformed response via an `issubset` key-check (`discover.py:433-437`) mirroring `advisor.consult()`'s own key-check (`advisor.py:270-278`). This is a stronger shape match for `--deep`'s "one batched call proposing several clusters" requirement than the per-issue loop in `decisions.py`.
- The codebase's existing shape for an `evidence`-style field on a proposal dataclass is `evidence: list[str] = field(default_factory=list)`, capped in `to_dict()` — e.g. `SkillBypass.evidence` (capped at 3, `scripts/little_loops/issue_history/models.py:490,499`) and `ConfigGap.evidence` (`scripts/little_loops/issue_history/models.py:529`). `ClusterProposal`'s proposed new `evidence` field (this issue's Proposed Solution) has a precedent to follow: a capped `list[str]`, not a single string.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- Confirmed via direct grep (not just the code graph, which returned an empty importers list): `scripts/little_loops/cli/issues/__init__.py:79` is the sole importer of `link_epics.py` (`from little_loops.cli.issues.link_epics import add_link_epics_parser, cmd_link_epics`), wired at `__init__.py:879` (parser registration) and `__init__.py:1047` (dispatch). No skill, loop, or other CLI module imports it — the "N/A, leaf skill" claim above is confirmed current, not just asserted.
- `--deep` test suite should mock `resolve_host`/`run_blocking_json` in `link_epics.py`'s own namespace (the `discover.py`/`advisor.py` convention — see Program Design findings), not `subprocess.run` directly (the older `decisions.py` convention) — the two existing test-mocking styles in this codebase disagree, and the module's own proposed use of `resolve_host().build_blocking_json(...)` determines which applies.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Documentation claim was understated, not just incomplete**: `skills/link-epics/SKILL.md` is the primary user-facing invocation surface (Summary of this issue: "`/ll:link-epics --mode synthesize` clusters..."), and it does more than need "a usage example." Direct read confirms: Step 1 ("Parse Arguments", lines 41-46) extracts only `MODE`/`THRESHOLD`/`AUTO` from raw argument text — no `--deep` extraction; S1 ("Get Cluster Proposals", line 118) hardcodes `ll-issues link-epics --mode synthesize --json ${THRESHOLD:+--threshold "$THRESHOLD"}` with no flag passthrough for `--deep`; S2 ("Name and Validate Clusters", lines 130-137) reviews only `placeholder_title`/`member_ids`, with no step reading or displaying an `evidence` field. `argument-hint` (SKILL.md:6) and the `flags` argument description (SKILL.md:17) also omit `--deep`. Without edits to all four of these (argument-hint/flags doc, Step 1 parsing, S1's Bash invocation, S2's review), `--deep` added only to the CLI parser is unreachable via the documented `/ll:link-epics --mode synthesize --deep` invocation — it would only work when calling `ll-issues link-epics --deep` directly, bypassing the skill. This corrects (does not replace) the original Documentation bullet above, which undersold this as a docs-only touch.
- **Tests claim above is stale**: the original Tests bullet ("No existing test file covers `link-epics` end-to-end") is false as of the current tree — `scripts/tests/test_link_epics_cli.py::TestLinkEpicsCLI` (line 193) already exercises `cmd_link_epics()` end-to-end, including `test_synthesize_mode_json` (line 295) for the exact `--mode synthesize --json` path `--deep` would extend. This class is additional parity-contract coverage alongside `TestSynthesizeClusters` (already noted by the wiring pass above) — both classes' current tests must keep passing unmodified when `--deep` lands, and neither one yet has a `--deep`-path test (see Program Design's test-mocking-convention finding for what that new test must follow).
- **Citation correction**: the "materially closer batched-call precedent" bullet above (2026-08-29 pass) cites `discover_regions()` at `scripts/little_loops/cli/artifact/discover.py:394-431`. Direct read confirms the function is actually defined at line 395 and its body runs through line 464 (`return DiscoveryResponse(...)`), matching the citation already given correctly elsewhere in this issue (Program Design → Codebase Research Findings, third 2026-08-29 bullet: `discover.py:395-464`). The `394-431` figure in this section is the one to disregard; `395-464` is correct.
- **Configuration is not settled `N/A`**: `scripts/little_loops/config-schema.json`'s `issues.link_epics` object (lines 159-172) is declared `"additionalProperties": false` and currently holds only `min_score`. If `--deep` needs any config-backed knob (see Program Design's candidate-set-size decision below), that schema object must be edited to add the property explicitly — it will reject an unlisted key rather than silently accept it. This section should read "Pending — see Program Design's candidate-set-size decision" rather than `N/A` until that decision is applied (or confirmed to need no new config key).

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Documentation AC has no CI backstop today — a fix exists in-repo**: `scripts/tests/test_wiring_reference_docs.py`'s parametrized `DOC_STRINGS_PRESENT` list already pins exactly this class of requirement elsewhere (e.g. `("docs/reference/CLI.md", "unproven_mechanism", "ENH-3350")`) — a one-line addition per doc file, asserting the file contains the literal string `--deep`, would give the "each doc mentions `--deep`" Acceptance Criteria bullet a machine-checkable regression guard instead of relying on human review. This should be added alongside the doc edits themselves, not left for a later pass.
- **`--deep`-path test target, concretely named**: the new automated test required by the Acceptance Criteria bullet added this pass belongs in `test_link_epics_cli.py`, sibling to `TestSynthesizeClusters` and `TestLinkEpicsCLI`, and must use the `discover.py`/`advisor.py` mocking convention already pinned above (`patch("little_loops.cli.issues.link_epics.resolve_host", ...)` / `patch("little_loops.cli.issues.link_epics.run_blocking_json", ...)`) — not `decisions.py`'s `subprocess.run`-level mocking, and not a real host CLI spawn (the session-scoped `_install_no_live_host_cli` fixture forbids that).

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- Stale anchor: the Signatures subsection above cites `extract_words`/`calculate_word_overlap` at `text_utils.py:387`/`text_utils.py:404`. As of the current tree these have moved to `text_utils.py:460` and `text_utils.py:477` respectively — the file grew between the 2026-08-11 refine pass and now. Re-verify at implementation time rather than trusting either citation.
- Mislabeled anchor: the Call Path subsection's `[extract_words, calculate_word_overlap] (text_utils.py:170,176, called inside the pairwise loop)` citation names the wrong file — lines 170 and 176 are the *call sites* inside `synthesize_clusters()` in `link_epics.py` itself (confirmed: `link_epics.py:170` is `extract_words(info.title)`, `link_epics.py:176` is `calculate_word_overlap(words_a, words_b)`), not locations in `text_utils.py`. The definitions live at `text_utils.py:460`/`text_utils.py:477` (see stale-anchor note above).

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Stale anchors in Signatures**: `extract_words`/`calculate_word_overlap` are cited at `text_utils.py:387`/`text_utils.py:404` in this section's own earlier pass — both are wrong. Current definitions: `extract_words()` at `text_utils.py:460`, `calculate_word_overlap()` at `text_utils.py:477` (confirmed by direct read).
- **Call Path anchor conflates call-site and definition lines**: the `text_utils.py:170,176` citation names the wrong file — 170 and 176 are `link_epics.py` line numbers (the call sites inside `synthesize_clusters()`, which locally imports both functions at `link_epics.py:165`), not `text_utils.py` lines. This is also why the code graph's `callees_of(synthesize_clusters)` query missed both functions: the import is function-scoped, not module-level, which some call-graph tooling doesn't resolve as a callee edge. Corrected call path: `synthesize_clusters()` (`link_epics.py:154`) → local import (`link_epics.py:165`) → `extract_words()` call (`link_epics.py:170`, defined `text_utils.py:460`) and `calculate_word_overlap()` call (`link_epics.py:176`, defined `text_utils.py:477`).
- **Stronger batched-LLM precedent exists than the one cited above**: `discover_regions()` (`scripts/little_loops/cli/artifact/discover.py:395-464`) is a closer model for `--deep` than `decisions.py::_cmd_extract_from_completed()` — it makes one `resolve_host().build_blocking_json(prompt=prompt, model=model, json_schema=_DISCOVERY_SCHEMA)` call covering an entire batch of items in a single request, with a schema whose top-level shape is an array of structured items (`_DISCOVERY_SCHEMA`, `discover.py:37-80`) — directly analogous to a clustering response needing an array of clusters. It routes through the shared `run_blocking_json()` helper (`host_runner.py:2114-2258`), which centralizes timeout/missing-binary/non-zero-exit/empty-stdout/envelope-parsing error handling (raising `BlockingJsonError` with a `.details` dict) rather than hand-rolling `subprocess.run` the way `decisions.py` does. `advisor.py::consult()` (`advisor.py:149-158,267-280`) shares this same `build_blocking_json` → `run_blocking_json` → post-hoc key-set validation idiom (`_VERDICT_KEYS.issubset(result.keys())`).
- **`json_schema` enforcement is host-dependent, not guaranteed**: `build_blocking_json`'s `json_schema` param is silently dropped by the Claude Code host builder (`host_runner.py:442-471`, comment at 458-465) — every caller that uses it re-validates the raw response's key set itself after the call (`discover.py`'s `_DISCOVERY_KEYS.issubset(...)`, `extract.py`'s `validate_top_level_data(...)`, `advisor.py`'s `_VERDICT_KEYS.issubset(...)`). A `--deep` implementation needs this same post-hoc validation, not reliance on schema enforcement alone.
- **Evidence-citation mechanism precedent**: `discover.py`'s prompt template (`_PROMPT_TEMPLATE`, lines 84-132) requires exact byte-for-byte quoted text, and this is mechanically re-verified downstream via `_resolve_span()`'s substring search (`bytes.index`/`bytes.find`, lines 153-220), raising `RegionMapError` if a quote isn't found verbatim — a stronger technique than trusting the LLM's citation by instruction alone. Separately, `CHECK_SEMANTIC_EVIDENCE_CONTRACT` (`fsm/evaluators.py:68-81`) is genuine reusable Python prompt-text (not only a lint rule) requiring a verbatim quote per verdict, but it is scoped to FSM `check_semantic` evaluators only — no other module (`discover.py`, `decisions.py`, `advisor.py`) imports or reuses it; each writes its own inline evidence instructions.
- **No existing "cheap-default, `--flag`-enables-LLM" convention**: repo-wide search found no CLI flag anywhere matching the shape `--deep` proposes (boolean, off by default, swaps a deterministic algorithm for an LLM-adjudicated one while keeping the deterministic algorithm as the unflagged default). The nearest sibling, `ll-artifact templatize`'s `--regions` flag (`cli/artifact/templatize.py:1322-1417`), has inverted polarity: supplying the flag's explicit input *skips* the LLM call, and *omitting* it triggers the LLM path — the reverse of what `--deep` needs.
- **No existing merge-by-overlap utility for two independently-produced groupings**: `_UnionFind` (`link_epics.py:125-141`) operates over pairwise edges between individual issues, not over merging two already-built cluster lists (Jaccard-only clusters vs. LLM-proposed clusters). No shared utility for this exists elsewhere in the codebase (repo-wide search for union-find/disjoint-set/merge-by-overlap patterns found none) — the merge step this issue's Call Path describes has no precedent to reuse and will need fresh design.
- **Adding `evidence` to `ClusterProposal` is confirmed non-breaking**: none of the 5 `TestSynthesizeClusters` tests (`test_link_epics_cli.py:109,119,129,137,148`) call `.to_dict()` or compare a full dict — they assert on individual `ClusterProposal` attributes directly. `NormalizeFinding` (`cli/issues/normalize.py:93-115`) is this codebase's precedent for adding a new dataclass field with a trailing default plus an unconditional (never-omitted) key in `to_dict()`.
- **Test-mocking convention split for a `--deep` implementation**: `decisions.py`'s tests mock at the `subprocess.run` level (`test_cli_decisions.py:1629-1978`) because that module calls `subprocess.run` directly rather than the shared helper. `discover.py`/`advisor.py`'s tests instead mock `resolve_host`/`run_blocking_json` as imported into the call-site module's own namespace (e.g. `little_loops.cli.artifact.discover.resolve_host`) because those modules route through `run_blocking_json()`. Since this issue's Proposed Solution already names `resolve_host().build_blocking_json(...)`, a `--deep` test suite should follow the `discover.py`/`advisor.py` mocking convention, not `decisions.py`'s.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Signatures citation correction**: the Signatures subsection above cites `resolve_host().build_blocking_json(...)` as "declared at `host_runner.py:262-270`." Direct read shows lines 262-270 fall inside the preceding `build_streaming()` method's docstring, not `build_blocking_json()`. The `HostRunner` Protocol actually declares `build_blocking_json` at `host_runner.py:304-312`; the concrete Claude-host implementation (where `json_schema` is silently dropped, per the finding already recorded above) is at `host_runner.py:442-471`.
- **Step 2's title+summary premise has no data to back it**: `IssueInfo` (`scripts/little_loops/issue_parser.py`, dataclass at line 3370, attribute docstring lines 3371-3390+) has no `summary` field — confirmed by direct read of its full attribute list. The existing Jaccard pass already only reads `.title` (noted in Signatures above); the `orphans: list[IssueInfo]` objects flowing into `synthesize_clusters()` (and reusable for a `--deep` prompt) carry no summary text today. `issue_parser.py` already has the extraction primitive needed — `_section_body(content, "Summary")` (defined `issue_parser.py:491`, used internally at `issue_parser.py:1079` to pull a Summary section for a different purpose) — but nothing in the current pipeline calls it for orphans before they reach `synthesize_clusters()` or a `--deep` prompt-builder. A `--deep` implementation must read each orphan's raw file content and extract its Summary section by this same route (or add a `summary` field to `IssueInfo` itself) before any evidence can cite summary text, matching this issue's own Proposed Solution framing ("title+summary").
- **Candidate-set definition decided (this pass)**: Proposed Solution's "the full orphan list when count is small enough" is underspecified in a way that defeats the issue's own motivating case — `synthesize_clusters()`'s return value is empty whenever no pair clears `min_score` (exactly the validated repro in Current Behavior: 11/11 orphans singletons), so if "candidate set" meant that return value, the LLM call would run over zero candidates in precisely the scenario `--deep` exists to fix. Resolution: the candidate set fed to the LLM is the full `orphans: list[IssueInfo]` list whenever `synthesize_clusters()` returns zero clusters with 2+ members (not that function's own output), capped at 40 orphans — chosen because no existing single-call LLM site in this codebase batches more than a few dozen structured items per request (`discover_regions()`'s region batches are page-bounded, not count-bounded, so it is not a numeric precedent to reuse directly) and a title+summary pair is small enough that 40 of them stays well inside typical prompt budgets. Above 40 orphans, `--deep` must skip the full-list fallback and process only the (still-empty, in this scenario) Jaccard-pre-filtered candidates, returning the pure-Jaccard result rather than chunking — chunking a semantic-clustering prompt across multiple calls risks splitting one real cluster across chunks with no cross-chunk reconciliation step, which is worse than falling back silently. This numeric cap has no existing config key; per the Integration Map finding above, adding one requires an explicit edit to `config-schema.json`'s `issues.link_epics` object (`additionalProperties: false`) — until then, hardcode the cap as a module constant in `link_epics.py` rather than leaving it configurable.
- **LLM-call failure mode decided (this pass)**: no Implementation Step specifies what `cmd_link_epics()` does when the batched `--deep` call raises `BlockingJsonError` (timeout/missing-binary/non-zero-exit/empty-stdout, per `run_blocking_json()`'s documented contract, already cited above) or returns a response that fails the post-hoc key-set check. Resolution, following this same file's own existing convention for a different `--mode synthesize` validation failure (`cmd_link_epics()`'s `--apply`-with-synthesize rejection, `link_epics.py:310-316`: print an `Error: ...` message to stderr and `return 1`): a `--deep` call that fails must print an `Error: ...` message to stderr identifying the failure and exit 1 — it must not silently fall back to Jaccard-only clusters (which would misrepresent `--deep`'s output as semantically-adjudicated when it is not) and must not let the raw exception propagate uncaught.
- **`ClusterProposal.evidence` field shape decided (this pass)**: of the two precedents already recorded above (`SkillBypass.evidence`, capped at 3; `ConfigGap.evidence`, uncapped), this issue adopts the capped shape: `evidence: list[str] = field(default_factory=list)`, capped at 3 entries in `to_dict()` the same way `SkillBypass` caps its own — a cluster's justification is a small number of quoted title/summary fragments, not an open-ended log, and capping bounds CLI output size the way `--deep`'s cited MR-8-style evidence-contract requirement (Proposed Solution) intends without needing a second design pass later.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **`ClusterProposal.to_dict()` must omit `evidence` when empty (decided this pass, overrides the `NormalizeFinding` precedent)**: `NormalizeFinding.to_dict()` (`normalize.py:105-115`) emits its new `priority_defaulted` key unconditionally on every call. Following that precedent literally for `ClusterProposal.evidence` would add an `"evidence": []` key to every `--mode synthesize` JSON response — including when `--deep` is not passed — contradicting Acceptance Criteria bullet 1's "byte-identical when `--deep` is omitted" requirement. Resolution: `to_dict()` includes the `evidence` key only when the list is non-empty (i.e., only for `--deep`-sourced clusters). This deliberately deviates from the `NormalizeFinding` shape to satisfy the compat requirement; where the two conflict, AC1 wins.
- **Signatures citation corrections (second pass)**: (1) `resolve_host().build_blocking_json(...)` is declared on the `HostRunner` Protocol at `host_runner.py:304-312`, not `host_runner.py:262-270` (which falls inside the preceding `build_streaming()` method's docstring) — this is a second, independent citation error beyond the one already corrected above. (2) `HostCapabilities.structured_output` is declared at `host_runner.py:146` (`structured_output: bool = False`, inside the `HostCapabilities` dataclass, lines 127-152), not `host_runner.py:301` (also inside `build_streaming()`'s docstring, several methods away from any `structured_output` reference).
- **`ConfigGap.evidence` is capped, not uncapped (citation correction)**: the "ClusterProposal.evidence field shape decided" bullet above contrasts "SkillBypass.evidence, capped at 3" against "ConfigGap.evidence, uncapped" to justify the capped shape chosen for `ClusterProposal.evidence`. `ConfigGap.to_dict()` (`issue_history/models.py:539`) actually does `"evidence": self.evidence[:10]` — capped at 10, not uncapped. Both cited precedents are capped (at different limits); the capped-vs-uncapped contrast used to justify the choice is factually wrong, though the capped shape itself is still correct — both real precedents support it.
- **`_resolve_span()` citation correction**: the "Evidence-citation mechanism precedent" bullet above cites `_resolve_span()`'s substring search as `bytes.index`/`bytes.find`, lines 153-220. Confirmed by direct read: `_resolve_span()` is defined at `discover.py:166-220`; lines 153-163 are a separate helper, `_find_candidates()`, which `_resolve_span()` calls internally. The only substring-search call in this path is `haystack.find(...)` inside `_find_candidates` (`discover.py:158`) — `bytes.index` never appears as an actual call in this code path; it appears only in an unrelated docstring for `_resolve_offsets()` (~line 230) describing a conceptual cursor idea, not an invocation `_resolve_span()` makes.

### Types
- `ClusterProposal` — exactly four fields: `member_ids: list[str]`, `placeholder_title: str`, `modal_priority: str`, `pairwise_min_score: float`; defined at `scripts/little_loops/cli/issues/link_epics.py:63-79`. `to_dict()` (line 72-79) serializes exactly those four. No `evidence`/`justification`/`rationale` field exists on this dataclass or on `EpicProposal` (the `--mode assign` sibling, line 44-60). `--deep`'s evidence-citation requirement (this issue's Proposed Solution) needs a new field added here — none of `TestSynthesizeClusters`'s five assertions probe such a field, so adding one is additive, not breaking.

### Signatures
- `synthesize_clusters(orphans: list[IssueInfo], min_score: float) -> list[ClusterProposal]` — the sole function computing clusters today, defined at `link_epics.py:154`. Its five callers in `scripts/tests/test_link_epics_cli.py::TestSynthesizeClusters` (lines 109, 119, 129, 137, 148 — no-edges, chain-via-union-find, modal-priority, placeholder-title-frequency, single-member-not-clustered) all invoke it with exactly this two-parameter signature and none pass a `deep`/LLM parameter, so changing this signature (vs. adding a parallel path) breaks all five.
- `extract_words(text: str) -> set[str]` and `calculate_word_overlap(words1: set[str], words2: set[str]) -> float` — the Jaccard primitives `synthesize_clusters` calls (title only, not summary, despite this issue's "title+summary" framing), defined at `text_utils.py:387` and `text_utils.py:404` respectively. Both are shared by 8+ other modules (`find_similar.py`, `fingerprint.py`, `issue_discovery/matching.py`, `issue_discovery/search.py`, `issue_history/doc_synthesis.py`, `cli/verify_skill_prose.py`, `loops/sft-corpus.yaml`), so changing their existing contract (as opposed to adding new call sites) has blast radius beyond link-epics.
- `resolve_host().build_blocking_json(*, prompt: str, model: str | None = None, json_schema: dict | None = None) -> HostInvocation` — the existing, already-shipped mechanism for a CLI command to make a synchronous LLM call, declared at `host_runner.py:262-270`. Precedent: `decisions.py::_cmd_extract_from_completed()` (line ~716-828) builds a per-issue prompt, calls `build_blocking_json`, conditionally adds `--json-schema` when `HostCapabilities.structured_output` is `True` (`host_runner.py:301`), then runs `subprocess.run([invocation.binary, *invocation.args, ...], capture_output=True, text=True, timeout=120)` with `TimeoutExpired`/`FileNotFoundError`/non-zero-exit handling inline. That precedent calls once per issue in a loop, not batched — a `--deep` implementation wanting one batched call across all candidates would need a new prompt shape, not a reused loop.

### Call Path
`cmd_link_epics()` (`link_epics.py:295-359`, synthesize tail at 349-359) -> `synthesize_clusters(orphans, min_score=threshold)` (`link_epics.py:154`) -> [`extract_words`, `calculate_word_overlap`] (`text_utils.py:170,176`, called inside the pairwise loop) -> result presented via `print_json({"clusters": [...], "applied": []})` or the human-readable `f"[{title}] {ids} (min score: {score:.3f}, modal priority: {priority})"` line (`link_epics.py:352-358`).

A `--deep` path would add: CLI arg parsing in `add_link_epics_parser()` (`link_epics.py:257-292`, alongside `--threshold`/`--apply`, both of which already exist as the flag-registration precedent) -> a pre-filter step feeding into (a modified or wrapped) `synthesize_clusters` to bound the candidate set -> one `resolve_host().build_blocking_json(...)` call (mechanism confirmed above, batching shape not yet precedented) -> a merge of LLM-proposed clusters with Jaccard-only clusters -> an extended `ClusterProposal`/output surface carrying cited evidence, since neither the dataclass nor `cmd_link_epics`'s JSON/human-readable output currently has a field for it.

**Corrected citation** (this pass): the first paragraph above cites
`[extract_words, calculate_word_overlap] (text_utils.py:170,176, called
inside the pairwise loop)`. Confirmed by direct read: `text_utils.py:170`
and `text_utils.py:176` are unrelated code (BUG-3194's `_GLOB_CHARS`/
`_EXTENSION_LIKE_COMPONENT_RE`), not these functions. The actual call sites
are `link_epics.py:170` (`extract_words(info.title)`) and `link_epics.py:176`
(`calculate_word_overlap(words_a, words_b)`), reached via a function-scoped
import at `link_epics.py:165`; the definitions themselves live at
`text_utils.py:460` and `text_utils.py:477`. Corrected call path:
`synthesize_clusters()` (`link_epics.py:154`) → local import
(`link_epics.py:165`) → `extract_words()` (`link_epics.py:170`) and
`calculate_word_overlap()` (`link_epics.py:176`) → result presented via
`print_json(...)` / the human-readable line (`link_epics.py:352-358`).

### Decision Rules
N/A — no new gap kind, gate, or threshold; `--deep` swaps the clustering mechanism rather than introducing a classification rule.

## Implementation Steps

1. Add `--deep` flag parsing to `add_link_epics_parser()` (`link_epics.py:257-292`),
   alongside the existing `--mode`/`--threshold`/`--apply` flags.
2. When `synthesize_clusters()` (`link_epics.py:154`) returns zero clusters
   with 2+ members, build the LLM candidate set from the full
   `orphans: list[IssueInfo]` list, capped at 40 orphans — above that cap,
   skip the LLM path entirely and return the pure-Jaccard result rather than
   chunking. Make one batched call via `little_loops.host_runner.run_blocking_json(...)`
   (wrapping `resolve_host().build_blocking_json(prompt=..., model=...,
   json_schema=...)`, declared on the `HostRunner` Protocol at
   `host_runner.py:304-312`) — not a per-issue loop or a manual
   `subprocess.run()` — following the `discover_regions()` precedent
   (`discover.py:395-464`: one call, array-shaped schema) rather than
   `decisions.py::_cmd_extract_from_completed()`'s per-issue loop. The prompt
   requests a top-level `clusters` array whose items each carry
   `member_ids: list[str]`, `placeholder_title: str`, and `evidence: list[str]`
   (capped at 3, quoted title/summary fragments). Validate the response with a
   post-hoc key-set check (`{"clusters"}.issubset(response.keys())`, then per
   item `{"member_ids", "placeholder_title", "evidence"}.issubset(item.keys())`);
   a check failure or a `BlockingJsonError` is handled per Step 7.
3. Merge LLM-proposed clusters with any Jaccard-only clusters before the
   placeholder-title step (`_placeholder_title()`, `link_epics.py:143-151`):
   any shared member merges the two clusters into one (Option A, Decision
   Rationale above — matches `_UnionFind.union()`'s existing transitive-merge
   behavior, `link_epics.py:125-141,154-189`). A merged cluster always takes
   the LLM cluster's `placeholder_title` and `evidence` (a pure-Jaccard
   cluster has no `evidence` to offer); `_placeholder_title()` must not
   re-run on merged members and overwrite them.
4. Add an `evidence` field to `ClusterProposal` (`link_epics.py:63-79`) and its
   `to_dict()` (line 72-79), then extend `cmd_link_epics()`'s JSON and
   human-readable output (`link_epics.py:352-358`) to show the cited evidence
   alongside each `--deep`-sourced cluster so the user can verify the grouping.
5. Add a `--deep` usage example to the CLI's `--help` text in
   `add_link_epics_parser()`.
6. `skills/link-epics/SKILL.md`'s four `--deep`-forwarding sites — the
   `argument-hint`/`flags` doc (lines 6, 17), Step 1's argument parsing
   (lines 41-46), S1's CLI invocation (line 118), and S2's cluster review
   (lines 130-137) — all recognize and pass through `--deep`, and S2 renders
   the new `evidence` field alongside `placeholder_title`/`member_ids`.
   Verified by running `/ll:link-epics --mode synthesize --deep` end-to-end
   and confirming the flag reaches the CLI and the evidence renders
   (Acceptance Criteria bullet 4) — CLI-only wiring (Steps 1-5) does not
   produce this on its own.
7. A batched `--deep` call that raises `BlockingJsonError` or fails the
   post-hoc key-set check (Program Design's failure-mode decision above)
   causes `cmd_link_epics()` to print an `Error: ...` message to stderr and
   exit 1 — matching the existing `--apply`-with-synthesize convention
   (`link_epics.py:310-316`) — rather than silently falling back to
   Jaccard-only output or letting the exception propagate uncaught
   (Acceptance Criteria bullet 5).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Execute the Step 2 invocation via `little_loops.host_runner.run_blocking_json(
  invocation, schema=..., timeout=...)` (`host_runner.py:2114`), not a manual
  `subprocess.run(...)` call. `run_blocking_json` already handles the
  structured-output flag variants, the empty-stdout-with-exit-0 guard,
  JSON-envelope parsing, and `cleanup_paths` unlinking, raising
  `BlockingJsonError` with a passthrough `.details` dict on failure — all of
  which `decisions.py::_cmd_extract_from_completed()` (Step 2's currently-cited
  precedent) reimplements inline instead of reusing. It is the standard call
  path used by `advisor.py`, `cli/artifact/discover.py`,
  `cli/artifact/extract.py`, and `fsm/evaluators.py` (see Program Design
  Codebase Research Findings above for the full comparison).
- Update `docs/reference/CLI.md`, `docs/reference/COMMANDS.md`, and
  `docs/reference/API.md` per the Documentation subsection in the Integration
  Map above.
- No change needed in `scripts/little_loops/cli/issues/__init__.py` — see
  Dependent Files (Callers/Importers) in the Integration Map above.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Missing step: `skills/link-epics/SKILL.md` wiring (supersedes old Step 5's false premise above)** — `--deep` added only to the CLI parser is unreachable through the documented `/ll:link-epics --mode synthesize --deep` invocation until the skill itself is updated. Four sites need `--deep` support, all cited concretely under Integration Map's Codebase Research Findings above: the `argument-hint`/`flags` doc (SKILL.md:6,17), Step 1's argument parsing (SKILL.md:41-46), S1's CLI invocation (SKILL.md:118, currently no flag passthrough), and S2's cluster review (SKILL.md:130-137, currently reviews only `placeholder_title`/`member_ids`, must also surface `evidence`). All four must land together — parsing `--deep` without forwarding it, or forwarding it without displaying the resulting `evidence`, leaves the flag either inert or its output invisible to the reviewing user.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Step 2's candidate-set algorithm, restated inline** (so a reader of this section alone has the full rule, not just a pointer): when `synthesize_clusters()` returns zero clusters with 2+ members, the LLM candidate set is the full `orphans: list[IssueInfo]` list, capped at 40 orphans. Above 40 orphans, `--deep` skips the full-list fallback entirely and returns the pure-Jaccard result without making the LLM call — it does not chunk the request across multiple calls (Program Design's "Candidate-set definition decided" finding has the full rationale).
- **Step 2's batched-call response shape, defined** (no section previously pinned this, and it is required for the post-hoc key-set check Acceptance Criteria bullet 5 depends on): following `discover.py`'s `_DISCOVERY_SCHEMA`/`_DISCOVERY_KEYS` pattern (`discover.py:37-53`, `:433-437`), the response must have a top-level `clusters` array, each item carrying `member_ids` (`list[str]`), `placeholder_title` (`str`), and `evidence` (`list[str]`, capped at 3). Post-hoc validation asserts `{"clusters"}.issubset(response.keys())` and, per item, `{"member_ids", "placeholder_title", "evidence"}.issubset(item.keys())`; a response failing either check is the "fails the post-hoc key-set check" condition Acceptance Criteria bullet 5 and Step 7 above require to fail closed with `Error: ...` plus exit 1.

## Scope Boundaries

- Not in scope: changing `--mode assign`'s existing-EPIC scoring (Step A2) — this
  issue is scoped to the synthesize-mode clustering step (S1) only.
- Not in scope: replacing Jaccard scoring wholesale or removing the non-`--deep`
  path — `--deep` is strictly additive.
- Not in scope: embeddings/vector-store-based similarity — that's a heavier
  infrastructure lift (model calls per issue + a vector store) than a flag on an
  existing skill; considered and rejected in favor of a batched LLM clustering call
  during design discussion.

## Acceptance Criteria

- [ ] `add_link_epics_parser()` (`link_epics.py:257-292`) accepts `--deep` as a
      boolean flag, default off; omitting it leaves `--mode synthesize`'s
      output byte-identical to today's, and `TestSynthesizeClusters`'s 5
      existing methods (`test_link_epics_cli.py:104-149`) plus
      `TestLinkEpicsCLI::test_synthesize_mode_json` (line 295) pass unmodified.
- [ ] With `--deep`, `synthesize_clusters()`'s own (possibly-empty) Jaccard
      output is never treated as the LLM candidate set — the candidate set is
      the full orphan list whenever Jaccard alone returns zero multi-member
      clusters, capped at 40 orphans (see Program Design's candidate-set
      decision), and running `--deep` against this project's live 11-orphan
      backlog (Current Behavior's validated repro) produces at least one
      multi-member cluster instead of 11 singletons.
- [ ] Each `--deep`-sourced `ClusterProposal.evidence` is a non-empty
      `list[str]` (capped at 3, per Program Design's field-shape decision) of
      quoted title/summary fragments — an empty `evidence` list on a
      `--deep`-sourced cluster is a bug, not a valid output.
- [ ] `/ll:link-epics --mode synthesize --deep` (the skill invocation, not
      only the raw `ll-issues link-epics --deep` CLI call) forwards `--deep`
      through `skills/link-epics/SKILL.md` Step 1 and S1, and S2 displays the
      cited `evidence` for review — confirms the Implementation Steps'
      SKILL.md-wiring finding was applied, not just the CLI parser.
- [ ] A batched LLM call that raises `BlockingJsonError` or fails the
      post-hoc key-set check causes `cmd_link_epics()` to print an `Error:
      ...` message to stderr and exit 1 (matching the existing
      `--apply`-with-synthesize convention at `link_epics.py:310-316`) —
      it does not silently fall back to Jaccard-only output or propagate an
      uncaught exception.
- [ ] `docs/reference/CLI.md`, `docs/reference/COMMANDS.md`,
      `docs/reference/API.md`, and `skills/link-epics/SKILL.md` each document
      `--deep` — none is left describing only `--mode`/`--threshold`/`--apply`.
- [ ] The `--deep` path is exercised by an automated test, not manual CLI
      verification alone: a new test class/method in
      `test_link_epics_cli.py` mocks `resolve_host`/`run_blocking_json` in
      `link_epics.py`'s own namespace (the `discover.py`/`advisor.py`
      convention already documented above, not `decisions.py`'s
      `subprocess.run`-level mocking) and asserts candidate-set selection,
      non-empty capped `evidence`, and the `BlockingJsonError`/key-check
      failure-mode's stderr message plus exit 1.
      _(Added by `/ll:refine-issue` — 2026-08-29 gap-analysis pass: none of
      the preceding ACs required new automated coverage of the `--deep`
      path itself.)_

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Bullet 2's live-backlog clause is illustrative, not the durable test**: "running `--deep` against this project's live 11-orphan backlog produces at least one multi-member cluster" depends on this project's current backlog composition (which drifts) and a live, non-deterministic LLM call — neither is something a CI run can assert. The durable, testable version of this criterion is the candidate-set-selection algorithm itself (Implementation Steps' restated candidate-set bullet: never treat `synthesize_clusters()`'s own return as the candidate set; use the full orphan list, capped at 40, when Jaccard yields zero multi-member clusters) — that is what the new automated `--deep` test (this section's test-coverage bullet) must assert against a small fixed synthetic fixture with a mocked LLM response, not the live backlog.
- **Bullet 4 has no re-verification mechanism, unlike this issue's own cited evidence-citation precedent**: `SKILL.md` is prose interpreted at invocation time, not code with a test harness (confirmed: `test_link_epics_cli.py` exercises only the Python CLI, never skill markdown) — this bullet can only be confirmed by a human reading a live run's rendered output. This issue's Program Design notes `discover.py`'s evidence citations are mechanically re-verified via `_resolve_span()`'s substring search, calling that "a stronger technique than trusting the LLM's citation by instruction alone"; bullet 4's SKILL.md-forwarding check has no equivalent re-verification step, and none is proposed here — it remains a manual-review-only criterion.

## Impact

- **Priority**: P4 - Quality-of-life improvement to an existing skill; no user is
  currently blocked, but `--mode synthesize` is close to a no-op on backlogs like
  this project's current one (11/11 orphans landed as singletons).
- **Effort**: Small - Additive flag on an existing skill's existing mode; reuses
  the current orphan-discovery and Jaccard pre-filter machinery (Step 2, Step 3),
  adds one new batched LLM adjudication step and one new proposal-flow branch.
- **Risk**: Low - Default (non-`--deep`) behavior is unchanged; the new path is
  opt-in.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Note (2026-08-03)

Parented under **EPIC-2938** (Offload mechanical work from `/ll:` skills/commands
into `ll-* Python CLIs`) — this is a sibling of the epic's **FEAT-2942**
(`ll-issues link-epics --mode assign|synthesize`), the same CLI surface this
issue extends.

Worth weighing against the parent epic before implementation: EPIC-2938's
"Shared Conventions" and Motivation are explicitly about *removing*
non-determinism (`--check` gates narrated by the model, Jaccard duplicated in
prose vs. `text_utils.py`) and moving mechanical scoring into deterministic
Python. This issue proposes the opposite direction for one step of that same
CLI — swapping deterministic Jaccard clustering for an LLM-adjudicated pass.
That may still be the right call (the motivation here — pure lexical overlap
structurally misses same-theme, different-vocabulary orphans — is real and
distinct from the determinism concern), but it should be an explicit,
acknowledged tradeoff against EPIC-2938 §Motivation point 2, not an implicit
one. The `--deep` opt-in gate (default path stays deterministic Jaccard) is
the mitigation already designed into this issue.

## Verification Notes

**2026-08-10** (`/ll:verify-issues`): OUTDATED as of 2026-08-10: blocking
dependency FEAT-2942 has landed (status: done), and as a result the Jaccard
clustering logic this issue targets has moved out of
skills/link-epics/SKILL.md prose entirely into
scripts/little_loops/text_utils.py and
scripts/little_loops/cli/issues/link_epics.py (now a Python CLI: `ll-issues
link-epics --mode synthesize`). The issue's Current Behavior/Proposed
Solution describe modifying skill prose (Step 3, S1 scoring) that no longer
contains the scoring logic — needs rework to target the CLI code instead of
skill markdown.

## Status

**Open** | Created: 2026-08-01 | Priority: P4


## Session Log
- `/ll:reconcile-issue` - 2026-08-29T21:45:28 - `322e1b2a-53a1-4728-8048-b3876fc3c8b8.jsonl`
- `/ll:confidence-check` - 2026-08-29T20:39:31 - `56a8dea0-aa3e-460a-b690-91edf1aee623.jsonl`
- `/ll:refine-issue` - 2026-08-29T20:24:37 - `1af8753e-4f9c-4ef2-97a5-4e6f8d5943ea.jsonl`
- `/ll:decide-issue` - 2026-08-29T20:14:32 - `56a8dea0-aa3e-460a-b690-91edf1aee623.jsonl`
- `/ll:confidence-check` - 2026-08-29T20:08:40 - `56a8dea0-aa3e-460a-b690-91edf1aee623.jsonl`
- `/ll:refine-issue` - 2026-08-29T19:54:17 - `56a8dea0-aa3e-460a-b690-91edf1aee623.jsonl`
- `/ll:confidence-check` - 2026-08-29T19:46:36 - `56a8dea0-aa3e-460a-b690-91edf1aee623.jsonl`
- `/ll:wire-issue` - 2026-08-29T19:33:43 - `095cbd0a-db00-46a3-adc4-bd813f5370ea.jsonl`
- `/ll:refine-issue` - 2026-08-29T19:29:50 - `56a8dea0-aa3e-460a-b690-91edf1aee623.jsonl`
- `/ll:refine-issue` - 2026-08-29T19:26:10 - `56a8dea0-aa3e-460a-b690-91edf1aee623.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:11 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:reconcile-issue` - 2026-08-11T22:00:08 - `4fa39a29-8b93-4a9a-adb4-d7d71347e160.jsonl`
- `/ll:refine-issue` - 2026-08-11T21:55:43 - `d5d81416-64f3-45f6-83b0-ea146a218034.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:26:29 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-04T20:31:46 - `ec47aff0-f647-498d-ad44-7606e8c8054f.jsonl`
- `/ll:capture-issue` - 2026-08-01T21:04:44 - `2cabd1bc-5bca-411b-af7d-d8f7d41a247b.jsonl`
