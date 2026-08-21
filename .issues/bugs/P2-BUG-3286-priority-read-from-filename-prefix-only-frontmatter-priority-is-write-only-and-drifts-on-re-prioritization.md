---
id: BUG-3286
type: BUG
title: 'Priority split across filename prefix and frontmatter with no shared resolver:
  IssueParser reads only the prefix, seven other sites read only frontmatter, and
  the two drift on re-prioritization'
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T17:37:01Z'
completed_at: '2026-08-21T21:48:16Z'
labels:
- parser
- frontmatter
- planning-hub
- multi-repo
- mcp
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3286: Priority split across filename prefix and frontmatter with no shared resolver

_Title corrected 2026-08-21 during pre-implementation review. The original — "frontmatter `priority:` is write-only" — was factually wrong: seven sites read it. The filename slug still carries the old wording; rename with `ll-issues normalize` if the slug drift matters._

## Summary

`IssueParser` resolves an issue's priority exclusively from the `P<n>-` filename prefix and never consults the frontmatter `priority:` key, so prefix-less issue files silently flatten to P5. Priority is stored twice with no designated authority: several modules read it from the filename with three different no-priority defaults (`P5`, `None`, `P3`), and seven other sites read it from frontmatter — including `rn-implement`'s next-issue selection and one site (`session_store/writers.py:_derive_type_priority`) that already implements a frontmatter-first resolver with the *opposite* precedence to the one proposed here. Nothing keeps the two copies in agreement: `prioritize --apply` and `skip` rewrite the filename without touching frontmatter, and `normalize --auto` invents a `P3-` prefix for prefix-less files, overriding whatever the frontmatter declared.

## Current Behavior

Priority has two sources of truth in little-loops, each read by a different set of modules, with nothing keeping them in agreement.

**The write side.** `ll-issues create` writes `priority` into the frontmatter dict at `scripts/little_loops/cli/issues/create.py:311` and builds the filename with the same value at `create.py:454`. Both are in sync at creation.

**The read side.** `IssueParser.parse_file` sets priority from `self._parse_priority(filename)` at `scripts/little_loops/issue_parser.py:2883` and nothing else. Nine lines later it calls `parse_frontmatter(content)` at `:2892` and pulls a dozen fields off it — `discovered_by`, `epic`, `size`, `effort`, `impact`, `confidence_score`, `outcome_confidence`, `score_*`, `testable`, `decision_needed` — but never `priority`. `_parse_priority` at `issue_parser.py:3043-3056` does a bare `filename.startswith(f"{p}-")` scan over the priority list from `BRConfig.issue_priorities` (`scripts/little_loops/config/core.py:714`) and falls through to its last element (P5) when no prefix matches. `_ANCHORED_FILENAME_RE` at `issue_parser.py:58` likewise makes the priority group optional and yields `None`.

**The frontmatter key is not write-only** (corrected 2026-08-21 during pre-implementation review; the original capture asserted it was). `IssueParser` never reads it, but seven sites across five modules do — and none of them agree with the parser about where priority comes from:

| Site | What it drives | Resolution shape |
|---|---|---|
| `scripts/little_loops/loops/rn-implement.yaml:363` | `fm.get("priority", "P3")` → `composite_score()` (`:348-353`) → **which issue the autonomous implement loop picks next** (`:355-371`) | frontmatter-only |
| `scripts/little_loops/cli/issues/format_check.py:329` | `--fix` substitutes the frontmatter value into the body's `Status: [P0-P5]` / `Impact: [P0-P5]` placeholders (`_TEMPLATE_PLACEHOLDER_FIXABLE`, `:284-289`) | frontmatter-only |
| `scripts/little_loops/cli/issues/set_status.py:173` | `record_issue_event(..., priority=fm.get("priority"))` → history DB `issue_events` | frontmatter-only |
| `scripts/little_loops/session_store/writers.py:383` | `issue_snapshots.priority` on live ingest | frontmatter-only |
| `scripts/little_loops/session_store/writers.py:2542`, `:2666` | `issue_snapshots.priority` on backfill | frontmatter-only |
| `scripts/little_loops/session_store/writers.py:2490-2510` `_derive_type_priority` (used at `:2622`) | history-DB `issue_events` type/priority | **frontmatter first, filename regex (`_FILENAME_PRIORITY_RE`, `:2433`) as fallback** |

The last row matters most: `_derive_type_priority` **already is the shared resolver this issue proposes to add**, with the precedence inverted. Any fix must reckon with it rather than introduce a second, contradictory rule — see Decision Rules § Precedence divergence.

In this repo's own `.issues/`, **3,194** files carry a filename prefix, **2,089** carry a frontmatter `priority:`, and **0** lack a filename prefix (re-derive rather than trusting these numbers). So Consequence 1 below is an external-repo symptom, while Consequences 2-5 are live here. Note the arithmetic: **1,105 prefixed files carry no frontmatter `priority:` at all** — that population, not the four drifted files, is the largest live defect and is Consequence 5.

**Consequence 1 — prefix-less repos flatten to P5.** Reproduced in a throwaway project outside this repo (see Steps to Reproduce) whose sole issue file has no `P<n>-` prefix and a frontmatter `priority: P1`:

```
ENH-279-foo.md -> 'P5'  priority_int=5
```

**Consequence 2 — the two sources drift in this repo already.** `ll-issues prioritize --apply` renames the file and never opens it: `apply_priorities` at `scripts/little_loops/cli/issues/prioritize.py:99-148` computes `new_name`, calls `git_mv_with_fallback(path, new_path)` at `:142`, and returns. `ll-issues skip` (`skip.py:47`) does the same via a bare `re.sub` on the prefix. The frontmatter copy goes stale on every re-prioritization. Four live mismatches in `.issues/` today (filename prefix vs. frontmatter):

| File | Filename says | Frontmatter says |
|---|---|---|
| `P3-BUG-3109-loop-info-show-effective-scope.md` | P3 | P4 |
| `P2-ENH-2746-f3-compaction-shrink-ratio-outside-gate-band.md` | P2 | P3 |
| `P2-ENH-2988-expand-skill-ships-documentation-shaped-prompts-with-no-directive-to-act.md` | P2 | P3 |
| `P2-ENH-3047-confidence-check-consume-claim-and-parity-gaps.md` | P2 | P3 |

This drift is **not cosmetic**, because of the frontmatter readers above. For each of those four issues, `rn-implement` is already scoring them at the stale priority when choosing what to implement next, the history DB has already stored the stale value in `issue_events`/`issue_snapshots`, and `format-check --fix` will bake the stale value into the body's `Status:`/`Impact:` lines — where it lands as prose that no lint inspects.

**Consequence 3 — six independent readers disagree on the same input.** `ll-issues show` does not use `IssueParser`; it carries its own filename regex at `scripts/little_loops/cli/issues/show.py:80-81` and yields `None` when there is no prefix, where the parser yields `P5`. It is not a pair — the readers below each carry their own regex and produce three distinct answers (`P5` / `None` / `P3`) for the same prefix-less file, while the last resolves the field frontmatter-first instead. (`prioritize.py:129`'s `_priority_prefix_re` is a seventh filename regex, used to report `old_priority` during the rewrite.)

| Site | Prefix-less result | Notes |
|---|---|---|
| `scripts/little_loops/issue_parser.py:3043` `_parse_priority` | `P5` | the canonical reader |
| `scripts/little_loops/cli/issues/show.py:80` | `None` | card rendering |
| `scripts/little_loops/cli/issues/normalize.py:120` | `P3` | **and writes it to the filename** — see Consequence 4 |
| `scripts/little_loops/sync.py:320` | `None` | wrong/absent GitHub priority label on push |
| `scripts/little_loops/issue_history/parsing.py:58, 744` | `"P5"` | historical analytics; defaults to `P5` before the regex, like the parser |
| `scripts/little_loops/session_store/writers.py:2433` | frontmatter value, else `None` | **not a filename-only reader** — `_FILENAME_PRIORITY_RE` is only the fallback inside `_derive_type_priority` (`:2490-2510`), which consults frontmatter *first* |

**Consequence 4 — `ll-issues normalize --auto` stamps an invented priority over the declared one.** `_priority_and_defaulted` (`scripts/little_loops/cli/issues/normalize.py:118-121`) returns `("P3", True)` when the filename carries no prefix, and that value is interpolated straight into `proposed_path` at `:292` and `:339`. On a prefix-less repo, normalizing `ENH-279-foo.md` (frontmatter `priority: P1`) renames it to `P3-ENH-279-foo.md`. Under this issue's own filename-wins precedence the stamped `P3` then becomes authoritative, silently overriding the declared `P1` for every filename-based reader.

**Not data loss, though** (corrected during pre-implementation review — the original capture said the `P1` was "unrecoverable"). `apply_normalize` (`normalize.py:432-464`) only ever writes `{"id": ...}` into frontmatter; it never touches `priority:`. So the declared `P1` survives on disk, the frontmatter readers listed above keep seeing it (making the two halves of the system disagree outright), and step 6's new drift lint reports the disagreement. The harm is a silently wrong resolved priority, recoverable and detectable — not destruction. `_priority_and_defaulted` must still consult frontmatter before defaulting.

**Consequence 5 — 1,105 prefixed files have no frontmatter `priority:` at all, so every frontmatter-only reader is wrong for ~35% of this repo's corpus.** (Added by pre-implementation review 2026-08-21; the capture and the first review both counted only files where the two sources *disagree*.) Re-derive with:

```bash
python3 -c "
import re, pathlib
tot = nofm = 0
for p in pathlib.Path('.issues').rglob('*.md'):
    if not re.match(r'^P[0-5]-', p.name): continue
    tot += 1
    if not re.search(r'^priority:', p.read_text(errors='ignore'), re.M): nofm += 1
print('prefixed:', tot, ' missing frontmatter priority:', nofm)
"
# prefixed: 3194   missing frontmatter priority: 1105
```

This is a **larger defect than Consequences 2-4 by an order of magnitude**, and it falsifies this issue's own "transitively fixed by step 5" claim for the frontmatter-only readers:

- `loops/rn-implement.yaml:363` — `priority = fm.get("priority", "P3")` feeds `PRIO_WEIGHT` (`:346`), the dominant term of `composite_score` (`:348-353`): P-tiers are spaced 20 apart while the `impact/effort * 10` term swings at most ~20. **All 1,105 of those issues — including any P0 or P1 — are scored as P3 in the autonomous implement queue today**, losing to any P2 that happens to carry the frontmatter key. A one-tier drift on four files is a rounding error next to this.
- `cli/issues/set_status.py:173` and `session_store/writers.py:383`, `:2542`, `:2666` write `priority=None` into `issue_events` / `issue_snapshots` for every one of them.
- `session_store/writers.py:2622` is the sole correct reader, precisely *because* `_derive_type_priority` falls back to the filename. Its much-maligned frontmatter-first precedence is the only thing keeping history-DB ingest right for a third of the corpus — see Decision Rules § Precedence divergence, which must not lose that fallback.

Step 5's prefix-rewrite sync rule does **not** reach these files: it writes frontmatter only when a prefix is *rewritten*, so an issue nobody re-prioritizes stays absent forever. Step 6's drift rule ("both present and differing") is silent on all 1,105 by construction. Two new sub-consequences follow:

**5a — `sync.py`'s GitHub pull path manufactures more of them.** `_create_local_issue` (`sync.py:660-745`) derives `priority` from GitHub labels (`:669-674`, defaulting to `"P3"`), then writes it into the filename (`:682`), the `Impact` body block (`:727`), and the `Status` line (`:732`) — but the frontmatter dict at `:713-719` has **no `priority` key**. Every GitHub-pulled issue is born into the absent-frontmatter state. This is a fifth issue-creation site and the only one that disagrees with `create.py:311`/`:399`, which do write the key.

**5b — the body prose is written at pull time and never revisited**, the same staleness class the Fix-order rule addresses for `_fix_template_placeholders`.

## Expected Behavior

- Priority resolution consults the frontmatter `priority:` key when the filename carries no `P<n>-` prefix, and defaults to P5 only when neither source specifies one.
- When a filename prefix and a frontmatter value disagree, the filename wins (see Decision Rules) — deliberately, and documented.
- The fallback lives in **one shared resolver**, not copied per call site; `ll-issues show`, `normalize`, and `sync` call it rather than carrying their own regex.
- `ll-issues normalize --auto` no longer stamps a `P3-` prefix onto a file whose frontmatter declares a different priority.
- `ll-issues prioritize --apply` and `ll-issues skip` update the frontmatter `priority:` alongside the rename, **including when the filename is already at the target priority** (the exact state of today's four mismatches), so the two sources stop diverging.
- A format-check rule reports filename↔frontmatter priority disagreement, and the four existing mismatches are reconciled.
- `ll-issues show` and `IssueParser` agree on the resolved priority for any given file.
- The existing frontmatter-first resolver `session_store/writers.py:_derive_type_priority` adopts the shared `resolve_priority(..., default=None)` resolver, replacing its inverted precedence (see Decision Rules § Precedence divergence) — the codebase does not end up with two contradictory precedence rules.
- `format-check --fix` does not bake a stale frontmatter priority into the body's `Status:`/`Impact:` placeholder lines.
- `rn-implement`'s next-issue scoring reflects an issue's real priority even when its frontmatter carries no `priority:` key — it resolves filename-first rather than defaulting 1,105 issues to P3 (Consequence 5).
- `sync.py`'s GitHub pull path writes `priority:` into frontmatter, so pulled issues are not born in the absent-frontmatter state (Consequence 5a).
- The existing 1,105 absent-frontmatter files are backfilled, so the frontmatter-only readers that this issue declines to convert are correct for the whole corpus rather than for the 65% that happen to carry the key.

## Motivation

Priority is the core planning signal. Every consumer downstream of it — `ll-issues next-issue`, `ll-sprint` sequencing, `backlog_snapshot.by_priority`, ll-mcp `issues_query` summary cards — silently produces meaningless output when every issue ties at P5. There is no crash, so the failure is invisible until someone notices the ordering is arbitrary — and per Consequence 4 there *is* data loss the moment `normalize --auto` runs on such a repo.

Two motivations, not one:

<!-- ll-private-ok: external planning hub demonstrates issue scope -->
1. **Multi-repo generalization.** Any repo using the frontmatter-priority convention without a filename prefix (the ll-product planning hub today, any future planning-hub or convention repo) gets a dead priority ordering.
2. **Internal correctness.** Even in this repo, where the prefix convention holds and every file has a prefix, little-loops maintains two priority sources, syncs them only at creation, and has no reconciliation or lint between them — while *both* are actively read by different subsystems. This is not latent: for the four drifted issues, `rn-implement` scores them at the stale frontmatter value when picking the next issue to implement, `issue_events`/`issue_snapshots` have already recorded the stale value, and `format-check --fix` will copy it into the issue body. Fixing only (1) would also formalize a field that goes stale on every re-prioritization — making a known-unreliable source authoritative for one class of repo.

## Proposed Solution

Six coordinated changes, lettered **A-F** to keep them distinct from the numbered Implementation Steps below (the two lists are not 1:1 — the mapping is given per change). **A** alone closes the reported symptom; **B** is required so the fix does not become destructive; **C** and **D** prevent the fix from resting on a field that silently rots; **E** and **F** were added by pre-implementation review to address Consequence 5, which the earlier four-change plan assumed away.

**A. One shared priority resolver with a frontmatter fallback.** _(Implementation Steps 1, 2, 4.)_ Following the `resolve_issue_path()` precedent (BUG-3229 — duplicate readers consolidated into one shared resolver rather than reconciled after the fact; see Codebase Research Findings), add a **module-level** function in `issue_parser.py` rather than a private method, so every current reader can call it:

```python
def resolve_priority(
    filename: str,
    frontmatter: dict[str, Any],
    config: BRConfig,
    *,
    default: str | None = None,
) -> str | None:
    """Resolve an issue's priority: filename prefix wins, frontmatter is the fallback.

    Returns ``default`` when neither source specifies one, so each caller keeps
    its own no-priority sentinel (parser: ``issue_priorities[-1]``; show: ``None``;
    normalize: ``"P3"``).
    """
    for priority in config.issue_priorities:
        if filename.startswith(f"{priority}-"):
            return priority
    fm_priority = frontmatter.get("priority")
    if isinstance(fm_priority, str) and fm_priority.upper() in config.issue_priorities:
        return fm_priority.upper()
    return default
```

`IssueParser._parse_priority` becomes a thin wrapper passing `default=config.issue_priorities[-1]`. `parse_file` already reads content and calls `parse_frontmatter` — the resolution call moves below that, so no extra file read.

Call sites converted in this issue: `cli/issues/show.py:80-81` (`_parse_card_fields` already receives `config`, so no plumbing needed), `cli/issues/normalize.py:118-121`, and `sync.py:320`. At `sync.py` the frontmatter is **already parsed five lines below** the priority regex (`:324-325`, feeding the `blocked-by` and `labels` handling), so the conversion is a reorder — move that read above the priority branch — not a new file read. The `Sync` class holds `self.config: BRConfig` (`sync.py:246, 257`), so no plumbing is needed there either.

Note the config-driven widening this implies: `show.py:80` hardcodes `^(P\d)-`, `skip.py:47` hardcodes `^P\d-`, and `sync.py:320` / `normalize.py:120` hardcode `^(P[0-5])-`, while `resolve_priority` iterates `config.issue_priorities`. For a project that customizes `issues.priorities`, these four sites change behavior (more correctly, but not identically — e.g. `show.py` stops matching a hypothetical `P7-`). `prioritize.py` is already config-driven via `_priority_prefix_re(config)` (`:60-61`) and needs no widening.

**Resolved during pre-implementation review 2026-08-21** (this was previously an open confirmation item): `BRConfig.issue_priorities` and `config.issues.priorities` are the *same object*, not merely equal — `config/core.py:714-716` is a property returning `self._issues.priorities`, the identical list `prioritize.py:119` reads. `resolve_priority` may take `BRConfig` with no reconciliation and no extra test.

**Out of scope, stated deliberately** — two filename-only priority reads keep their current behavior:

- `issue_history/parsing.py:58,744` reads past filenames for analytics, not live planning signal (note it defaults to `"P5"`, not `None`).
- `issue_parser.py:272` — inside `resolve_issue_path`, `pool` entries are filtered by `p.name.upper().startswith(f"{priority}-")` as a *duplicate-path disambiguation tiebreaker*, not as a priority read. It answers "which of these same-numbered files did the caller mean," where the caller supplied the prefix from a path string. Leave it filename-only. (Flagged explicitly because it uses `startswith`, not a regex, so step 10's completeness grep cannot see it at all — it is caught by reading or not at all. See Tests § Completeness verification.)

**Frontmatter-only readers — status after review (previously "unresolved"):**

- `loops/rn-implement.yaml:363` — **now in scope, Implementation Step 11.** The earlier plan said "no change, covered by step 5." **That was wrong**: step 5 syncs frontmatter only on a prefix *rewrite*, so the 1,105 files of Consequence 5 keep defaulting to P3 forever. Fix it directly — `issue_idx.get(issue_id)` (`:301`) already yields the `Path`, so the change is to derive the prefix from `p.name` first and fall back to `fm.get("priority")`, then `"P3"`.
- `cli/issues/set_status.py:173`, `session_store/writers.py:383`, `:2542`, `:2666` — frontmatter-only history-DB ingest. Genuinely transitive **only once change F's backfill lands**; until then they record `None` for the Consequence 5 population. Left unconverted deliberately (they are ingest sites, not planning signal), but the backfill is what makes that defensible — not step 5.
- `session_store/writers.py:2490-2510` `_derive_type_priority` — the one that genuinely conflicts; see Decision Rules § Precedence divergence. Note it is the *only* reader correct for the Consequence 5 population today.
- `cli/issues/format_check.py:329` `_fix_template_placeholders` — see the Fix-order rule below. The function already has `config`, `path`, `content`, and the parsed `fm` in scope (`format_check.py:303, 327-329`), so sourcing from `resolve_priority` is a one-line substitution.

**B. Stop `normalize` from stamping a wrong prefix.** _(Implementation Step 3.)_ `_priority_and_defaulted` calls `resolve_priority(..., default=None)` and only falls back to `"P3"` (with `defaulted=True`) when that returns `None`. Without this, change A's filename-wins precedence promotes normalize's invented `P3` over the real frontmatter value — see Consequence 4.

Two corrections to the earlier plan for this function, both from pre-implementation review:

- **It needs `config`, not just `frontmatter`.** The signature given in Program Design (`_priority_and_defaulted(filename, frontmatter)`) cannot call `resolve_priority`, which requires a `BRConfig`. The real signature is `_priority_and_defaulted(filename: str, frontmatter: dict[str, Any], config: BRConfig) -> tuple[str, bool]`. `config` is already in scope at every call site.
- **It has three call sites, not two.** `normalize.py:290` (`missing_id`), `:317` (the duplicate-number branch, inside the `ordered[1:]` loop), and `:338` (the single-entry non-normalized branch). The Location section previously listed only `:292` and `:339` — off by two, and omitting `:317` entirely. All three must be plumbed or normalize stays half-fixed.
- **This adds a file read per candidate.** None of the three sites has content in hand — the scan function works on `path.name` alone (`normalize.py` reads content only at `:198`, `:411`, `:456`, in other functions). The candidate set is bounded to files with missing/duplicate IDs, not the whole corpus, so the cost is acceptable; noted so it is a decision rather than a surprise.

**C. Keep frontmatter in sync on every prefix rewrite.** _(Implementation Step 5.)_ Two writers, not one:

- `apply_priorities` (`prioritize.py:99-148`) — use the established rename+write-as-one-operation idiom: `update_frontmatter(content, {"priority": priority})` then `git_mv_with_fallback(path, new_path, content=updated)`. **Critically, the early-return no-op branch at `:134-141` (`new_path == path`) must also reconcile frontmatter** — that branch is the exact state of all four existing mismatches, so leaving it untouched means step 8's reconciliation cannot be performed with the tool itself.
- `ll-issues skip` (`skip.py:47-56`) rewrites the prefix with a bare `re.sub` and never touches frontmatter — the same defect, with the same already-at-target early return at `:49`. The write itself is cheap: `skip_issue` (`issue_lifecycle.py:1365-1397`) already reads `raw_content` and threads it through `git_mv_with_fallback(content=...)`, so it only needs `update_frontmatter(raw_content, {"priority": <derived from new_path.name>})` folded in ahead of `_build_skip_section`. The `path == new_path` early return in `skip.py:49-56` returns before `skip_issue` is ever called, so it needs its own reconciliation. Without both, `skip` keeps manufacturing exactly the drift step 6's lint reports.

**D. Drift lint + one-time reconciliation.** _(Implementation Steps 6 and 8.)_ A `format-check` rule reporting filename↔frontmatter disagreement, plus a pass over the four existing mismatches to bring them into agreement.

Scope note: the rule fires only when **both** sources are present and differ. It is therefore silent on the 1,105 absent-frontmatter files of Consequence 5 — deliberately, because "frontmatter key absent" is not drift, it is the normal state for two-thirds of the corpus until change F lands. Do **not** widen this rule into a "missing `priority:`" gap kind; that would report 1,105 gaps on this repo and break the paired `TestCorpusHasNo…` self-check that every gap kind ships with.

**E. Fix `rn-implement`'s queue scoring directly.** _(Implementation Step 11.)_ `loops/rn-implement.yaml:363` resolves the filename prefix first (via `issue_idx[issue_id].name`, already in scope at `:301`), falling back to `fm.get("priority")` and then `"P3"`. This is the only frontmatter-only reader that drives a *decision* rather than a record, and per Consequence 5 it is wrong for 1,105 issues today. Not covered by change C.

**F. Backfill the absent `priority:` frontmatter across the corpus.** _(Implementation Step 12.)_ A one-time pass writing `priority:` (derived from the filename prefix, i.e. `resolve_priority`'s own precedence) into the 1,105 prefixed files that lack the key, plus the `sync.py:713-719` one-liner so the GitHub pull path stops manufacturing new ones (Consequence 5a). This is what makes "left unconverted, fixed transitively" an honest description of the four history-DB ingest sites rather than an assumption. Land it **after** changes A-C so the value written is the resolved one.

## Integration Map

| File | Change |
|---|---|
| `scripts/little_loops/issue_parser.py` | New module-level `resolve_priority()`; `_parse_priority` becomes a wrapper; call site moves below `parse_frontmatter` |
| `scripts/little_loops/cli/issues/show.py` | `:80-81` regex → `resolve_priority(..., default=None)` so `show` agrees with the parser |
| `scripts/little_loops/cli/issues/normalize.py` | `_priority_and_defaulted` (`:118-121`) consults frontmatter before defaulting to `P3` — stops `--apply` stamping a wrong prefix |
| `scripts/little_loops/sync.py` | `:320` regex → `resolve_priority(..., default=None)` so GitHub labels match the resolved priority (move the existing `:324-325` frontmatter read above it); **plus** `_create_local_issue`'s frontmatter dict (`:713-719`) gains `"priority": priority` so pulled issues are not born key-less (Consequence 5a) |
| `scripts/little_loops/loops/rn-implement.yaml` | `:363` — resolve the filename prefix from `issue_idx[issue_id].name` before falling back to `fm.get("priority")`; change E |
| `scripts/little_loops/cli/issues/prioritize.py` | `apply_priorities` threads updated content through `git_mv_with_fallback(content=...)`; **no-op branch (`:134-141`) reconciles frontmatter too** |
| `scripts/little_loops/cli/issues/skip.py` | `:47-56` — same frontmatter sync on prefix rewrite, including the already-at-target early return at `:49` |
| `scripts/little_loops/cli/issues/format_check*.py` | New drift gap kind; **plus** `_fix_template_placeholders` (`:329`) must not substitute a priority the drift rule considers stale — see step 6 |
| `scripts/little_loops/session_store/writers.py` | `_derive_type_priority` (`:2490-2510`) — adopt `resolve_priority` or document the inverted precedence (Decision Rules § Precedence divergence) |
| `docs/reference/ISSUE_TEMPLATE.md` | Document the frontmatter `priority:` field and the precedence rule |
| `scripts/tests/test_issue_parser*.py` | Fallback, precedence, and regression coverage |
| `.issues/` (4 files) | Reconcile existing mismatches |
| `.issues/` (1,105 files) | Backfill absent frontmatter `priority:` from the filename prefix (change F) |

**Explicitly out of scope** (decision, not oversight): `scripts/little_loops/issue_history/parsing.py:58,744` and `scripts/little_loops/issue_parser.py:272` keep their filename-only priority reads — the first is historical analytics rather than live planning signal, the second is a duplicate-path disambiguation tiebreaker inside `resolve_issue_path`, not a priority read. `parsing.py` is an allowlist entry in step 10; `issue_parser.py:272` is invisible to that grep (it uses `startswith`) and is recorded here instead.

**Frontmatter-only readers left unconverted** (a decision, and *conditional* on change F): `cli/issues/set_status.py:173`, `session_store/writers.py:383`, `:2542`, `:2666`. Each reads frontmatter directly for history-DB ingest and is correct once the key is present everywhere — which is change F's job, **not** step 5's. The earlier claim that step 5 alone fixed these was wrong (see Consequence 5) and `loops/rn-implement.yaml:363` has been promoted out of this list into change E. Add a regression test that a re-prioritized issue's next-issue ordering and history-DB row both reflect the new priority, plus one that an *absent-frontmatter* issue is scored at its filename priority, so the transitivity is asserted rather than assumed.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_prioritize.py` — `TestApplyPriorities` (lines ~160-256, 8 test methods) calls `apply_priorities` directly; none currently reads or asserts on the frontmatter `priority:` value, so the new `update_frontmatter` call in **step 5** has zero coverage until this file is extended [Agent 1/3 finding; step reference corrected during pre-implementation review — the `apply_priorities` write is step 5, not step 3]
- `scripts/tests/test_show.py` — `TestParseCardFields` (~lines 289-590+, 20+ test methods) exercises `_parse_card_fields` directly, the exact function step 2 modifies; no existing case covers a prefix-less filename with a frontmatter `priority:` present [Agent 1/3 finding]
- `scripts/little_loops/mcp_server/tools.py:141` and `scripts/little_loops/mcp_server/resources.py:234` — **both call `_parse_card_fields(path, config)` directly** [added by pre-implementation review]. Step 2 therefore fixes the ll-mcp `issues_query` summary cards named in Motivation *transitively*, at no extra cost — the ll-mcp half of the motivation is discharged by the `show.py` change alone. Check `scripts/tests/test_mcp_*` for any card-priority assertion that pins today's `None`-for-prefix-less behavior and would flip.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_prioritize.py::TestApplyPriorities` — existing tests to update: none assert frontmatter content today (`test_already_at_target_priority_is_noop`, `test_apply_is_idempotent`, ~lines 188-209) — add assertions that `priority:` in frontmatter matches the renamed prefix after `apply_priorities` runs [Agent 2/3 finding]
- `scripts/tests/test_show.py::TestParseCardFields` — new test: a prefix-less filename (e.g. `ENH-5200-thing.md`) with frontmatter `priority: P1`, asserting `fields["priority"] == "P1"` instead of today's `None` [Agent 1/3 finding]
- `scripts/tests/test_ll_issues_format_check.py` (~line 349, the `--format json` baseline-shape dict alongside the existing `"malformed_dep_id": []` entry) — **will hard-fail** the moment the new drift gap kind is added to `FormatGaps` unless a matching `"<gap_key>": []` entry (with a `# BUG-3286: ...` comment, following the `malformed_dep_id`/BUG-3059 precedent) is inserted here [Agent 3 finding]
- `scripts/tests/test_issue_parser.py` — new `TestCheckFormatGapsPriorityDrift`-style class mirroring `TestCheckFormatGapsMalformedDepId` (:4369-4458), plus a paired `TestCorpusHasNoPriorityDrift`-style class mirroring `TestCorpusHasNoMalformedDepIds` (:4461-4477) asserting the four reconciled `.issues/` files (step 8) and the rest of the corpus report zero drift [Agent 3 finding]
- `scripts/tests/test_issue_parser.py::TestIssueParser::test_parse_file_without_priority_prefix` (:423-441) — re-verify under the new fallback; this file has no frontmatter `priority:` so its `P3`/last-priority assertion should hold unchanged, but it's the existing regression anchor for the code path being modified [Agent 3 finding]
- `scripts/tests/test_issue_parser_fuzz.py` — optional: the `"no_priority"` filename-structure generator (~lines 93-107) and the frontmatter `priority:` draw (~line 69) currently live in separate generators; composing them into one property test would cover the fallback path under fuzzing [Agent 3 finding]
- **Completeness verification (de-risks Criterion D / Change Surface).** _Rewritten by pre-implementation review 2026-08-21 — the previously specified grep was wrong in both directions and, wired into an "expect empty" test as instructed, would have shipped a guard that guards nothing._ The defects, each confirmed by running it against the working tree:

  - **It missed `skip.py:47`** — `re.sub(r"^P\d-", ...)` has no capture group, and the pattern required `\)-`. That is the literal site change C must fix, so the guard gave zero protection exactly where it mattered most.
  - It likewise missed `normalize.py:129`, `hooks/post_tool_use.py:97,107`, and `issues/prose_deps.py:21`.
  - **It matched `cli/issues/search.py:109`** — `re.match(r"^(P\d)-(P\d)$", val)`, the `--priority P1-P3` *range argument* parser, which is not a filename regex and never goes away. An "expect empty" test would have failed permanently.
  - Its whole-file `grep -v issue_parser.py` exclusion also hid `issue_parser.py:272`, the `resolve_issue_path` tiebreaker (now named under Out of scope).

  Widening the pattern to make the paren optional is **still not enough** — `issue_history/parsing.py:58`, `:744` and `session_store/writers.py:2433` all use the bare `re.match(r"^(P\d)", filename)` form with *no trailing hyphen*, and those three are priority readers. Since false negatives are the failure mode that broke the original, use the maximally inclusive pattern and absorb the cost in the allowlist:

  ```bash
  grep -rn -E "P\[0-5\]|P\\\\d" scripts/little_loops --include='*.py'
  ```

  This returns **32 hits across 16 files** today — small enough to enumerate, and it cannot miss a filename-priority regex by shape.

  **"Expect empty" is the wrong assertion shape**, since most hits are legitimate and permanent. Wire this as an **allowlist test** instead: a frozen set of `path:line` entries, each with a one-line reason, asserted equal to the grep's output. It mirrors the corpus-self-check spirit of `TestCorpusHasNoMalformedDepIds` but compares against a known set rather than the empty set, so it fails loudly when a *new* raw priority regex appears — the thing actually worth guarding. Categories of legitimate survivor, to be enumerated concretely at implementation time (re-derive the line numbers; do not trust these):

  | Site(s) | Why it legitimately survives |
  |---|---|
  | `cli/issues/search.py:109,114`, `mcp_server/tools.py:588,683` | priority-*argument* parsing / JSON-schema `pattern`; operates on a CLI or MCP value, never a filename |
  | `cli/issues/normalize.py:129` | `_slug_for` *strips* the prefix to build a slug; a text operation, not a priority read |
  | `cli/migrate.py:16`, `issues/prose_deps.py:21`, `issue_parser.py:58,155,1578`, `issue_lifecycle.py:1400` | optional `(?:P\d-)?` prefix inside an **issue-ID** regex; the priority group is discarded |
  | `issue_parser.py:50,329`, `cli/issues/refine_status.py:533` | normalized-filename convention check and its `--help`/docstring text |
  | `cli/issues/clusters.py:68` | `[P3]`-style priority tag inside cluster body text |
  | `cli/issues/prioritize.py:61`, `sync.py:292`, `session_store/writers.py:2494`, `issue_history/parsing.py:52`, `issue_parser.py:3091` | comments and docstrings |
  | `hooks/post_tool_use.py:97,107` | gates "is this an issue file" and extracts ID+slug; does not read priority as a value. **Known limitation, not fixed here:** it skips prefix-less files entirely, so a prefix-less repo gets no post-tool-use issue handling at all |
  | `issue_history/parsing.py:58,744` | the deliberately out-of-scope analytics reader (defaults to `"P5"`) |

  Two notes on exclusions. First, `issue_parser.py` and `issue_history/parsing.py` are **no longer excluded wholesale** via `grep -v` — their entries sit in the allowlist like any other, so the deliberate exclusions stay visible instead of hidden. Second, and importantly: **`issue_parser.py:272` does not appear in this grep at all**, because it uses `p.name.upper().startswith(f"{priority}-")` rather than a regex — as does `resolve_priority`'s own implementation. The grep is a regex-shape guard, not a complete census of filename-priority reads; `:272` is caught by reading, and is recorded under Proposed Solution § Out of scope so it is not rediscovered as a defect later.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:2065` — the `ll-issues format-check` docstring paragraph hand-enumerates all `FormatGaps` gap-kind names and states "reports gaps in twenty-five classes"; needs the new drift gap-kind name added to the list and the count incremented [Agent 2 finding]
- `docs/reference/CLI.md:2254` — the `--format json` example output is a literal dict of every gap key; needs the new gap-kind key inserted or the example understates the real payload [Agent 2 finding]
- `docs/reference/API.md:895-920` — an independently-maintained copy of the same "twenty-five gap classes" count and enumerated name list in `check_format_gaps`'s docstring reference, plus one prose bullet per gap kind; needs a matching count/list update and a new bullet following the `malformed_dep_id`/`stale_symbol_ref` precedent of naming the originating issue ID inline [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- **Prefer-source-A-fall-back-to-source-B resolution is an established shape in this module**, with the precedence documented inline rather than left implicit — evidence: `resolve_issue_path()`'s nested `_frontmatter_identity()` helper (`scripts/little_loops/issue_parser.py:213-234`, used at :236-249), where a missing/unparseable frontmatter value is treated as "no opinion" and falls through to the other source unchanged. `_gate_program_design()` (`scripts/little_loops/issue_parser.py:356-372`) is a smaller instance of the same "value present unless overridden" shape.
- **Duplicate independent readers of the same field get consolidated into one shared resolver, not reconciled after the fact** — evidence: `resolve_issue_path()`'s docstring (`scripts/little_loops/issue_parser.py:92-98`) states it is "the single shared ID->path resolver for filename-based lookups (BUG-3229)" specifically because `cli/issues/show.py` and `sprint.py:_find_issue_path` had drifted by computing the same thing independently. This is the same shape BUG-3286 describes between `IssueParser._parse_priority` and `show.py`'s own filename regex (`scripts/little_loops/cli/issues/show.py:80-81`).
- **Filename-vs-frontmatter drift has two prior resolutions in this codebase, not one** — (a) pick a winner via documented precedence (BUG-2806, `_frontmatter_identity`, frontmatter wins when present and non-contradictory, filename otherwise), or (b) leave both sources standing and report disagreement as a `FormatGaps` entry without picking a winner (BUG-2769's `malformed_id` gap, `scripts/little_loops/issue_parser.py:941-948`, which computes a canonical value from the filename and reports `f"{key}: {raw} (expected {canonical})"` when the frontmatter value disagrees). Both are live conventions; this issue's own Decision Rules already commits to option (a) for resolution and a `FormatGaps`-shaped rule for drift reporting, matching (b)'s output shape.
- **`update_frontmatter` + rewrite has three established call idioms**, distinguished by whether a rename is also happening:
  - Rename + frontmatter write as one filesystem operation: `content` is mutated via `update_frontmatter` before the rename, then threaded into `git_mv_with_fallback`'s optional `content=` parameter — evidence: `apply_normalize()` (`scripts/little_loops/cli/issues/normalize.py:432-464`), and `git_mv_with_fallback`'s own docstring (`scripts/little_loops/issue_lifecycle.py:1314-1332`) which documents "the write happens before the git-mv-failure fallback rename, or after a successful `git mv`." `apply_priorities()` (`scripts/little_loops/cli/issues/prioritize.py:100-148`) currently calls `git_mv_with_fallback(path, new_path)` with no `content=` argument and never touches frontmatter.
  - No rename, `update_frontmatter` + `atomic_write` as two calls: evidence — `scripts/little_loops/cli/issues/normalize.py:403-428` (`_rewrite_referencing_edges`), `scripts/little_loops/cli/issues/link.py:205,220`.
  - No rename, `update_frontmatter` + `Path.write_text` inside try/except with a warning log on failure: evidence — `scripts/little_loops/issue_lifecycle.py:594-605`.
  - The `update_frontmatter(content, updates)` immediately followed by a write is otherwise the standard two-line idiom across this codebase — evidence: `scripts/little_loops/cli/issues/set_status.py:137`, `scripts/little_loops/cli/issues/set_scores.py:54`, `scripts/little_loops/cli/issues/size.py:154`, `scripts/little_loops/cli/sprint/run.py:445`.
- **Adding a new `FormatGaps` gap kind touches nine fixed locations**, all present for every existing gap class (e.g. `malformed_dep_id`): the dataclass field (`scripts/little_loops/issue_parser.py:490-522`), the `has_gaps` OR-in (`:524-553`), the advisory-vs-blocking classification (`:483-487, 555-565`), `to_dict()` (`:567-595`), a documented paragraph in `check_format_gaps()`'s "Gap classes:" docstring block (`:654-824`) citing the originating issue ID, the inline detection loop itself, the `--help` text and docstring enumeration in `scripts/little_loops/cli/issues/format_check.py` (lines 63-70, 479-485) plus a matching print loop in `_print_gaps`, a dedicated test class following the `TestCheckFormatGapsMalformedDepId` template (`scripts/tests/test_issue_parser.py:4369-4458`) with a paired corpus self-check test (`TestCorpusHasNoMalformedDepIds`, `:4461-4477`) asserting the new gap kind fires zero times against this repo's own `.issues/` tree, and a baseline-shape entry in `scripts/tests/test_ll_issues_format_check.py` (~lines 339-360).

## Program Design

### Deviations

_2026-08-21, `/ll:manage-issue` implementation of step 7._ The Decision Rules
§ Precedence divergence section says `_derive_type_priority` should "call
`resolve_priority(..., default=None)`". Implemented instead: the priority
branch's precedence was reversed in place (filename-first, frontmatter
fallback) using the existing `_FILENAME_PRIORITY_RE` regex, without calling
the shared `resolve_priority()` function. Reason: `resolve_priority` requires
a `BRConfig` for `config.issue_priorities`, and `_derive_type_priority`'s
call chain (`_backfill_issues_and_snapshots` → `session_store/lifecycle.py`'s
`populate()`/`backfill()`) has no `BRConfig` in scope anywhere — threading one
through would touch call sites well beyond the single function this step
named, none of which are enumerated in the Integration Map. The `type` half
of the tuple is untouched, matching hazard 1; the filename fallback is
preserved, matching hazard 2. Both are pinned by
`test_v2_priority_prefers_filename_over_disagreeing_frontmatter` and
`test_v2_type_still_prefers_frontmatter_over_filename` in
`scripts/tests/test_session_store_lifecycle.py`.

### Types

No new types. `IssueInfo.priority` (`str`) and `IssueInfo.priority_int` (`int`) keep their current shapes and semantics.

### Signatures

- `resolve_priority(filename: str, frontmatter: dict[str, Any], config: BRConfig, *, default: str | None = None) -> str | None` — **new module-level function** in `issue_parser.py` (not a private method — three CLI modules outside the parser call it). Filename prefix first, frontmatter `priority:` second, caller-supplied `default` last.
- `IssueParser._parse_priority(self, filename: str, frontmatter: dict[str, Any]) -> str` — retained as a thin wrapper over `resolve_priority` with `default=self.config.issue_priorities[-1]`; gains the `frontmatter` parameter.
- `_priority_and_defaulted(filename: str, frontmatter: dict[str, Any], config: BRConfig) -> tuple[str, bool]` (`normalize.py`) — gains **both** the `frontmatter` and `config` parameters; `defaulted` is `True` only when *neither* source specifies a priority. **Corrected during pre-implementation review**: the earlier two-parameter form could not call `resolve_priority`, which requires a `BRConfig`. `config` is in scope at all three call sites (`normalize.py:290`, `:317`, `:338` — the middle one, in the duplicate-number branch, was previously unlisted).
- `apply_priorities(config: BRConfig, mapping: dict[str, str]) -> list[RenameResult]` — unchanged signature; body reads content, updates frontmatter, and threads it through the rename.
- `update_frontmatter(content: str, updates: dict[str, Any]) -> str` — existing helper (`scripts/little_loops/frontmatter.py:439`). Note it is a **pure content transform that returns new content**; it does not take a path and does not write. The caller performs the write.
- `git_mv_with_fallback(original_path: Path, new_path: Path, content: str | None = None) -> None` — existing helper (`scripts/little_loops/issue_lifecycle.py:1314`); its optional `content=` parameter is what makes rename+frontmatter-write a single filesystem operation.
- `skip_issue(original_path, new_path, reason=None, event_bus=None) -> None` — existing (`issue_lifecycle.py:1365`); unchanged signature. Already reads `raw_content` and passes `content=` to `git_mv_with_fallback` at `:1397`, so the frontmatter sync folds into the existing content assignment at `:1395`.

### Call Path

- `IssueParser.parse_file` → `_read_content` → `parse_frontmatter` → `IssueParser._parse_priority` → `resolve_priority` → `IssueInfo`
- `_parse_card_fields` (`show.py`) → `parse_frontmatter` → `resolve_priority`
- `_priority_and_defaulted` (`normalize.py`) → `resolve_priority`
- `apply_priorities` → `update_frontmatter(content, ...)` → `git_mv_with_fallback(path, new_path, content=updated)` — one operation, not a write after the rename
- `apply_priorities` (no-op branch) → `update_frontmatter(content, ...)` → `atomic_write` — no rename, so the two-call idiom applies
- `find_issues` → `IssueParser.parse_file` (unchanged; picks up the corrected priority transitively)

### Decision Rules

**Precedence rule.** When both a filename `P<n>-` prefix and a frontmatter `priority:` are present and they disagree, the **filename prefix wins**.

- Inputs: the issue filename and the parsed frontmatter dict.
- Rationale. `apply_priorities` writes the filename and leaves the frontmatter untouched, so for all four existing mismatches in this repo the filename is by construction the fresher signal. Filename-wins also preserves byte-identical behavior for every currently-prefixed repo. **This runs against the codebase's other precedent**, which the original capture missed: BUG-2806's `_frontmatter_identity` (frontmatter wins for `id`) and `session_store/writers.py:_derive_type_priority` (frontmatter wins for `priority`) both prefer frontmatter. The choice is still right, but for a narrower reason than "this is how the codebase does it" — it is right *because* it happens to name the correct value for the four drifts that exist today, and because step 5 makes the precedence nearly unobservable going forward. Once the two copies are kept in sync, precedence only decides legacy files written before this fix.
- Frontmatter is consulted only when the filename anchor yields no priority.
- A frontmatter value outside `config.issue_priorities` (malformed, e.g. `priority: high`) is ignored, falling through to the caller's `default` rather than raising.
- Escape hatch: none needed — the rule is total and has a defined result for every input.

**Default-sentinel rule.** `resolve_priority` returns the caller's `default` rather than hardcoding one, because the three live callers legitimately disagree about the no-priority-anywhere case and changing any of them is out of scope here: `IssueParser` returns `issue_priorities[-1]` (P5), `show.py` returns `None` (renders as an empty card field), `normalize.py` returns `"P3"` **with `defaulted=True`**, which drives a user-visible "priority was defaulted" warning. Unifying those sentinels is a separate change; this issue only stops them disagreeing when a source of truth *does* exist.

**Prefix-rewrite sync rule.** Any code path that writes an issue's `P<n>-` filename prefix must write the matching frontmatter `priority:` in the same operation. This binds `apply_priorities`, `skip_issue`, and `normalize`'s rename path.

- **The already-at-target early return is in scope, not excluded.** `apply_priorities:134-141` and `skip.py:49-56` both `return`/`continue` when `new_path == path`. That branch is precisely the state of all four existing mismatches (filename correct, frontmatter stale), so treating it as a pure no-op would leave the tool unable to repair the drift it is being taught to prevent — and would make Implementation Step 8 impossible to perform with `ll-issues prioritize` itself.
- Consequence for existing tests: `test_already_at_target_priority_is_noop` and `test_apply_is_idempotent` (`test_ll_issues_prioritize.py`, ~lines 188-209) are no longer asserting a *filesystem* no-op. They must be restated as "no rename occurs, frontmatter is reconciled" — idempotence still holds at the content level (a second run is a true no-op), which is what those tests should assert.
- `RenameResult` reporting is unchanged; a frontmatter-only reconciliation is still reported as a no-op rename with `old_priority == priority`.

**Precedence divergence rule (decided 2026-08-21).** `session_store/writers.py:_derive_type_priority` (`:2490-2510`) resolves priority frontmatter-first — the inverse of the rule above — and feeds the history DB. Two contradictory precedences must not coexist unexamined.

**Decision: convert `_derive_type_priority` to call `resolve_priority(..., default=None)`.** It is a two-source resolver already; the only change is which source wins, and post-change-C the sources agree anyway. This changes recorded history-DB priority for pre-fix drifted files ingested after the change — acceptable, since the filename value is the correct one for all four current mismatches.

**Two hazards in that conversion, added by pre-implementation review 2026-08-21:**

1. **`_derive_type_priority` resolves `type` *and* `priority` together**, both frontmatter-first (`writers.py:2496-2509`), and returns them as a tuple. Only the **priority** half changes. A naive "convert the function to `resolve_priority`" reading would silently invert the `type` precedence too, which nothing in this issue justifies and no test covers. Change the priority branch (`:2506-2509`) only; leave the `_FILENAME_TYPE_RE` branch (`:2502-2505`) exactly as-is.
2. **Do not delete the filename fallback.** Per Consequence 5, `_derive_type_priority` is the *only* frontmatter-reading site that is correct for the 1,105 absent-frontmatter files, precisely because it falls back to `_FILENAME_PRIORITY_RE`. Converting it to `resolve_priority(..., default=None)` preserves that (the resolver checks the filename first and frontmatter second, so both sources remain consulted) — but an implementer who instead "simplifies" it to a bare `fm.get("priority")` would regress a third of history-DB ingest. Pin the absent-frontmatter case with a test.

**Rejected: leave it inverted with an inline comment citing BUG-3286.** Only defensible if history-DB ingest should record what the file claimed at write time rather than what the planner resolved — nobody has made that argument, and a codebase with one resolver and one precedence is simpler to reason about than two coexisting rules that happen to agree today. Not adopted.

**Drift rule (new format-check gap kind).** Report a gap when a file has both a filename prefix and a frontmatter `priority:` whose values differ. Scoped to the file's own name and frontmatter — no cross-file comparison. Dismissal follows the existing format-check dismissal mechanism; no new opt-out key.

**Fix-order rule (new).** `_fix_template_placeholders` (`format_check.py:302-350`) fills `Status: [P0-P5]` / `Impact: [P0-P5]` from `fm.get("priority")`. If it runs while a file is in drift, it copies the stale value into prose, where no lint inspects it and the drift rule cannot see it. Within a single `--fix` pass, either reconcile priority before placeholder substitution, or have the placeholder fixer source its value from `resolve_priority` rather than raw frontmatter. The latter is simpler and self-consistent. Cover with a test: a drifted file run through `--fix` must not emit the frontmatter value into the body.

## Implementation Steps

1. Add the module-level `resolve_priority()` with the frontmatter fallback and caller-supplied `default`; reduce `IssueParser._parse_priority` to a wrapper and move the call in `parse_file` below `parse_frontmatter`. Cover with tests for fallback, prefix-wins precedence, malformed frontmatter, and the no-priority-anywhere default.
2. Convert `show.py:80-81` to `resolve_priority(..., default=None)` so `ll-issues show` and `IssueParser` agree; add a test asserting agreement on a prefix-less file.
3. Convert `normalize.py:_priority_and_defaulted` to consult frontmatter before defaulting to `P3`, preserving `defaulted=True` only when neither source specifies one. Test that `normalize --auto` on a prefix-less file with `priority: P1` proposes `P1-…`, not `P3-…`. **This must land with or before step 1** — step 1's filename-wins precedence makes normalize's invented prefix authoritative, so shipping 1 without 3 converts a read bug into data loss.
4. Convert `sync.py:320` to the shared resolver so pushed GitHub priority labels match the resolved priority.
5. Extend `apply_priorities` (rename branch **and** the `new_path == path` branch) and `skip_issue`/`skip.py` to keep frontmatter in sync; restate the two affected no-op/idempotence tests per the Decision Rules. Test that a re-prioritized and a skipped file both end with matching filename and frontmatter.
6. Add the format-check drift rule with tests for the matching and mismatching cases (nine touch points — see Codebase Research Findings). In the same change, apply the Fix-order rule to `_fix_template_placeholders` so `--fix` cannot bake a stale priority into the body.
7. Convert `session_store/writers.py:_derive_type_priority` to call `resolve_priority(..., default=None)` per the Precedence divergence rule. Not optional; it is the one site where the new rule actively contradicts existing behavior.
8. Reconcile the four existing `.issues/` mismatches — with step 5 landed, `ll-issues prioritize --apply` can do this itself; confirm the new rule reports clean afterwards.
9. Update `docs/reference/ISSUE_TEMPLATE.md` to document the field and precedence, including that frontmatter is the source consumed by `rn-implement` and the history DB.
10. Wire the completeness grep as an **allowlist test**, not an "expect empty" assertion — see Tests § Completeness verification for the corrected pattern, the reason the original was wrong in both directions, and the survivor table. Confirm no un-allowlisted raw priority regex remains.
11. **(New — change E.)** Fix `loops/rn-implement.yaml:363` to resolve the filename prefix from `issue_idx[issue_id].name` before falling back to `fm.get("priority")` and then `"P3"`. Test that an issue with a `P0-`/`P1-` prefix and no frontmatter `priority:` outranks a `P2-` issue that has the key — the exact inversion happening today for 1,105 issues (Consequence 5). **This is not covered by step 5** and was previously mislabelled "transitively fixed."
12. **(New — change F.)** Backfill the absent frontmatter `priority:` across `.issues/`: add `"priority": priority` to `sync.py`'s `_create_local_issue` frontmatter dict (`:713-719`) so no new ones are minted (Consequence 5a), then run a one-time pass writing the filename-derived priority into the ~1,105 prefixed files lacking the key. Land **after** steps 1-5 so the value written is the resolved one. Re-derive the count first; assert afterwards that the prefixed-but-key-less population is zero, and that step 6's drift rule still reports only the reconciled set.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Extend `scripts/tests/test_ll_issues_prioritize.py::TestApplyPriorities` — assert the frontmatter `priority:` key matches the renamed filename prefix after `apply_priorities` runs, **and** restate `test_already_at_target_priority_is_noop` / `test_apply_is_idempotent` (~lines 188-209) as "no rename, frontmatter reconciled" per the Decision Rules
- Add coverage for `ll-issues skip` in `scripts/tests/` — a skipped issue's frontmatter `priority:` must match its new prefix, including the already-at-target path
- Add a `normalize` test — prefix-less file with frontmatter `priority: P1` proposes `P1-…`, not `P3-…`, and reports `defaulted=False`
- Add a `sync.py` test — priority label derived for a prefix-less file uses the frontmatter value
- Add a `TestParseCardFields` case in `scripts/tests/test_show.py` — prefix-less filename with frontmatter `priority:` present, asserting the fallback value is returned
- Add the new gap-kind's `"<gap_key>": []` baseline entry to `scripts/tests/test_ll_issues_format_check.py` (~line 349) — the existing shape-assertion test fails without it
- Add `TestCheckFormatGaps<PriorityDrift>` and `TestCorpusHasNo<PriorityDrift>` classes in `scripts/tests/test_issue_parser.py`, mirroring `TestCheckFormatGapsMalformedDepId`/`TestCorpusHasNoMalformedDepIds` (:4369-4478)
- Update `docs/reference/CLI.md` (:2065, :2254) and `docs/reference/API.md` (:895-920) — increment the gap-class count, add the new gap-kind name to both enumerated lists and the JSON example, and add a documented bullet in API.md

_Added by pre-implementation review 2026-08-21:_

- Convert `session_store/writers.py:_derive_type_priority` (`:2490-2510`) to call `resolve_priority(..., default=None)` per Decision Rules § Precedence divergence (decided: adopt the shared resolver). Add a test pinning this precedence, so the next reader cannot mistake it for an oversight
- Apply the Fix-order rule to `format_check.py:_fix_template_placeholders` (`:302-350`) and test that `--fix` on a drifted file does not copy the stale frontmatter priority into the body's `Status:`/`Impact:` lines
- Add a transitivity test asserting that after `prioritize --apply` the frontmatter-only readers see the new value — specifically `rn-implement`'s `composite_score` input and the `issue_events`/`issue_snapshots` priority column — so the "fixed transitively by step 5" claim is asserted rather than assumed
- ~~Confirm `BRConfig.issue_priorities` and `config.issues.priorities` are the same list~~ — **resolved 2026-08-21, no work required.** `config/core.py:714-716` is a property returning `self._issues.priorities`; they are the same object, not merely equal. No reconciliation and no divergence test needed.

_Added by second pre-implementation review 2026-08-21 (Consequence 5 and the grep correction):_

- Fix `loops/rn-implement.yaml:363` (step 11) and test that a prefix-`P0`/no-frontmatter-key issue outranks a prefix-`P2`/has-key issue in `composite_score` ordering
- Add `"priority": priority` to `sync.py:_create_local_issue`'s frontmatter dict (`:713-719`) and test that a pulled issue's frontmatter priority matches its filename prefix
- Backfill the ~1,105 absent-frontmatter files (step 12) and add a corpus assertion that the prefixed-but-key-less population is zero
- Pin `_derive_type_priority`'s **filename fallback** with a test for the absent-frontmatter case — the conversion in step 7 must not regress it (Decision Rules § Precedence divergence, hazard 2) — and assert the `type` half of its precedence is *unchanged* (hazard 1)
- Plumb `config` **and** `frontmatter` into `_priority_and_defaulted` at all **three** call sites (`normalize.py:290`, `:317`, `:338`); the duplicate-number branch at `:317` was previously unlisted
- Replace step 10's "expect empty" grep with an allowlist test (Tests § Completeness verification) — as originally specified it missed `skip.py:47` and would have failed permanently on `search.py:109`
- Check `scripts/tests/test_mcp_*` for card-priority assertions that pin today's prefix-less `None`, since `mcp_server/tools.py:141` and `resources.py:234` inherit the `show.py` change

## Impact

<!-- ll-private-ok: external planning hub impact assessment -->
**Priority: P2.** Silent corruption of the core planning signal, no crash and no data loss. It fully disables priority ordering for any prefix-less repo (ll-product: 125 open issues all reading P5) and leaves an *active* two-sources-of-truth defect in every repo including this one.

Correction from the original capture, which called the four drifts "cosmetic today": they are not. Because seven sites read frontmatter directly (see Current Behavior), each drifted issue is currently mis-ordered by `rn-implement`'s queue scoring, mis-recorded in `issue_events`/`issue_snapshots`, and one `format-check --fix` away from having the stale value written into its body prose.

**Second correction, from pre-implementation review 2026-08-21: "the blast radius is four issues" was wrong** — that was the earlier revision's stated reason for holding at P2, and it counted only the files where the two sources *disagree*. The real internal blast radius is **1,105 files** whose frontmatter `priority:` is absent entirely (Consequence 5), every one of which `rn-implement` currently scores as P3 regardless of a `P0-`/`P1-` prefix. That is an ordering defect roughly 275× wider than the drift the issue was originally written around, and it is live in this repo right now.

**Priority held at P2 anyway**, on different reasoning than before: the failure is still silent mis-ordering rather than breakage or loss, every affected file's true priority remains recoverable from its filename, and the one reader that feeds durable state (`_derive_type_priority` → history DB) already falls back to the filename correctly. A P1 argument is available if the implement queue's ordering is considered load-bearing for autonomous runs — flag it if `rn-implement` is in active use.

**Effort: 3 (medium-high).** Revised up from 2 after refinement, held at 3 after the first pre-implementation review, and held at 3 again after the second: twelve source files plus docs, tests, and a one-time corpus backfill. The shared-resolver conversion is mechanical, but three of the added sites (`normalize`, `skip`, the two already-at-target branches) are *write* paths rather than read paths, two existing tests change meaning rather than just gaining assertions, and the review added `_derive_type_priority` plus the `_fix_template_placeholders` fix-order change. The format-check rule and its nine touch points remain the single largest chunk.

**Risk: medium.** The precedence choice makes the read change byte-identical for every prefixed file, so existing repos see no read behavior change. Three real risks:

1. **Ordering hazard.** Landing the parser fallback (step 1) without the `normalize` fix (step 3) makes normalize's invented `P3` authoritative on prefix-less repos, because filename-wins promotes it over the declared value. These must land together. (Corrected: the original text called this "irreversible data loss." It isn't — `apply_normalize` never rewrites `priority:`, so the declared value survives on disk and step 6's lint will flag the disagreement. The risk is a silently wrong resolved priority, not destruction.)
2. **New write surface.** `apply_priorities` currently never opens files; adding a content write makes it heavier and more failure-prone. Use the `git_mv_with_fallback(content=...)` single-operation idiom rather than a post-rename write, and check staging behavior.
3. **Test semantics change.** `test_already_at_target_priority_is_noop` / `test_apply_is_idempotent` stop being filesystem no-ops. Restating them is intended, not a regression — but it removes the guard that would have caught an accidental rename, so the replacement must still assert no rename occurred.
4. **Two precedence rules in one codebase.** Until step 7 lands, `resolve_priority` (filename-wins) and `_derive_type_priority` (frontmatter-wins) give different answers for the same drifted file — the planner and the history DB would disagree by construction. Step 7 is what keeps this a transition state rather than a permanent inconsistency.
5. **Config-driven regex widening.** Converting `show.py`/`skip.py`/`sync.py`/`normalize.py` from hardcoded `P\d`/`P[0-5]` to `config.issue_priorities` changes behavior for projects that customize `issues.priorities`. No effect on this repo; worth a release note if any consumer customizes the list.
6. **Corpus backfill touches ~1,105 files in one commit** (step 12). It is a mechanical frontmatter insert derived from each filename, so it is reviewable in aggregate rather than per-file, but it will dominate the diff and should land as its own commit — separate from the code changes — so a bisect can isolate it. Verify `update_frontmatter` round-trips cleanly on a sample first; a formatting regression across 1,105 issue files is the one genuinely expensive mistake available in this issue.
7. **Step 11 edits a loop YAML with an embedded Python heredoc.** `rn-implement.yaml:363` sits inside a `PYEOF` block, so `${...}` escaping rules apply to the surrounding FSM action and `ll-loop validate` must pass afterwards. Keep the change inside the Python, not the shell wrapper.

<!-- ll-private-ok: external planning hub scope documentation -->
**Verification claim.** The reproduction above and the mismatch scan were both executed against this checkout at capture time and re-executed during pre-implementation review (2026-08-21); the P5 result and the four named mismatches reproduce exactly. Re-derived counts: **2,089** files carry a frontmatter `priority:` (capture said 2,083 — re-derive rather than trusting either) and **0** files lack a filename prefix, so Consequence 1 cannot be reproduced in-repo. The capture's characterization of those 2,083 fields as "write-only" was **wrong** and is corrected in Current Behavior. Every line anchor in Location, the `git_mv_with_fallback(content=)` parameter, `_parse_card_fields(path, config)`, and the 25-field `FormatGaps` count were verified against the working tree. The ll-product figures cited in the originating report (`{P5: 125}`, the `P3:118, P2:109, P4:38, P1:20, P0:13, P5:4` frontmatter spread, the ll-mcp summary cards) are from an external repo and were **not** independently verified here; they match the predicted symptom of the confirmed mechanism.

## Steps to Reproduce

```bash
mkdir -p /tmp/pritest/.issues/enhancements && cd /tmp/pritest
printf -- '---\nid: ENH-279\npriority: P1\nstatus: open\n---\n\n# Test\n' \
  > .issues/enhancements/ENH-279-foo.md
python -c "
from pathlib import Path
from little_loops.issue_parser import IssueParser
from little_loops.config import BRConfig
p = IssueParser(BRConfig(Path('.')))
i = p.parse_file(Path('.issues/enhancements/ENH-279-foo.md'))
print(i.priority, i.priority_int)
"
# actual:   P5 5
# expected: P1 1
```

For the drift half, from this repo's root:

```bash
python3 - <<'EOF'
import re, pathlib
for p in pathlib.Path('.issues').rglob('*.md'):
    m = re.search(r'^priority:\s*(P[0-5])', p.read_text(errors='ignore'), re.M)
    fm = re.match(r'^(P[0-5])-', p.name)
    if m and fm and fm.group(1) != m.group(1):
        print('MISMATCH', p.name, '-> frontmatter', m.group(1))
EOF
```

## Root Cause

`IssueParser.parse_file` (`scripts/little_loops/issue_parser.py`) treats the filename as the sole priority source. `_parse_priority` has no access to the file's frontmatter — it takes a `filename: str`, not a path or parsed content — so the fallback to `issue_priorities[-1]` fires for any file whose name lacks the prefix, regardless of what the frontmatter says.

The drift half has a separate proximate cause: `apply_priorities` in `scripts/little_loops/cli/issues/prioritize.py` performs a pure path operation (`git_mv_with_fallback`) and never reads or rewrites file content, so the frontmatter copy written at creation is never updated on re-prioritization. `ll-issues skip` (`skip.py:47`) has the identical shape.

Both share a root: priority is stored twice with no designated authority and no invariant enforcing agreement. Two further consequences follow from the same root — because no reader is canonical, (a) five modules each rolled their own filename regex with three different no-priority defaults (`P5`, `None`, `P3`), one of which is written back to disk, and (b) a parallel set of seven sites reads the frontmatter copy instead, one of them (`_derive_type_priority`) having independently invented a two-source resolver with the opposite precedence. The system already contains both halves of the fix, disagreeing with each other.

## Location

_Line numbers re-anchored 2026-08-21 against the current working tree; prefer the named symbols, which are stable._

- `scripts/little_loops/issue_parser.py:58` — `_ANCHORED_FILENAME_RE`, optional priority group
- `scripts/little_loops/issue_parser.py:2883` — `parse_file` call site (`priority = self._parse_priority(filename)`), sole priority source; sits **above** the `parse_frontmatter` call at `:2892`
- `scripts/little_loops/issue_parser.py:3043-3056` — `_parse_priority` and the `issue_priorities[-1]` (P5) fallback
- `scripts/little_loops/cli/issues/create.py:311` — writes frontmatter `priority` (in sync with the filename only at creation)
- `scripts/little_loops/cli/issues/prioritize.py:99-148` — `apply_priorities`; `:134-141` is the already-at-target early return, `:142` the rename without frontmatter
- `scripts/little_loops/cli/issues/show.py:80-81` — independent filename regex, yields `None` not P5
- `scripts/little_loops/cli/issues/normalize.py:118-121` — `_priority_and_defaulted`, defaults to `P3`; consumed at **`:290`, `:317`, and `:338`** to build the rename target (re-anchored by pre-implementation review; the earlier `:292`/`:339` pair was off by two and omitted the duplicate-number branch at `:317`)
- `scripts/little_loops/cli/issues/normalize.py:129` — `_slug_for`'s `re.sub(r"^P[0-5]-", "", stem)`; a slug operation, not a priority read — allowlisted, not converted
- `scripts/little_loops/cli/issues/skip.py:47-56` — prefix rewrite via bare `re.sub`, plus its own already-at-target early return at `:49`
- `scripts/little_loops/issue_lifecycle.py:1393-1397` — `skip_issue` reads content and threads it through `git_mv_with_fallback(content=...)`; the natural insertion point for the skip-path sync
- `scripts/little_loops/sync.py:320` — filename-only priority regex feeding GitHub label push
- `scripts/little_loops/frontmatter.py:439` — `update_frontmatter(content, updates) -> str`, a pure content transform (does **not** take a path or write)

_Frontmatter-priority readers, added by pre-implementation review 2026-08-21:_

- `scripts/little_loops/session_store/writers.py:2490-2510` — `_derive_type_priority`, an existing frontmatter-first/filename-fallback resolver (used at `:2622`); the precedence conflict, see step 7
- `scripts/little_loops/loops/rn-implement.yaml:363` — `fm.get("priority", "P3")` feeding `composite_score` (`:348-353`) and the next-issue choice (`:355-371`)
- `scripts/little_loops/cli/issues/format_check.py:329` and `:284-289` — `_fix_template_placeholders` / `_TEMPLATE_PLACEHOLDER_FIXABLE`, writes frontmatter priority into the body
- `scripts/little_loops/cli/issues/set_status.py:173` — `record_issue_event(..., priority=fm.get("priority"))`
- `scripts/little_loops/session_store/writers.py:383`, `:2542`, `:2666` — `issue_snapshots.priority` on ingest and backfill
- `scripts/little_loops/config/core.py:714-716` — `BRConfig.issue_priorities`, a property returning `self._issues.priorities`; **the same object** `cli/issues/prioritize.py:119` uses (confirmed 2026-08-21)

_Consequence 5 anchors, added by second pre-implementation review 2026-08-21:_

- `scripts/little_loops/sync.py:660-745` — `_create_local_issue`; priority derived from GitHub labels at `:669-674`, written to the filename at `:682`, the `Impact` body at `:727`, and the `Status` line at `:732`, but **absent from the frontmatter dict at `:713-719`**
- `scripts/little_loops/loops/rn-implement.yaml:300-310` — `get_frontmatter`; `issue_idx.get(issue_id)` at `:301` yields the `Path`, so `p.name` is available for the filename-first fix at `:363`
- `scripts/little_loops/session_store/writers.py:2496-2509` — `_derive_type_priority`'s two branches: `_FILENAME_TYPE_RE` (`:2502-2505`, unchanged) and `_FILENAME_PRIORITY_RE` (`:2506-2509`, the only half step 7 touches)
- `scripts/little_loops/cli/issues/format_check.py:303, 327-329` — `_fix_template_placeholders` already holds `config`, `path`, `content`, and `fm`, so the Fix-order rule is a one-line substitution
- `scripts/little_loops/mcp_server/tools.py:141`, `scripts/little_loops/mcp_server/resources.py:234` — `_parse_card_fields` callers; inherit step 2 transitively
- `scripts/little_loops/issue_parser.py:272` — `resolve_issue_path`'s `startswith(f"{priority}-")` duplicate-path tiebreaker; deliberately out of scope, and invisible to step 10's regex grep

## Related Key Documentation

- `docs/reference/ISSUE_TEMPLATE.md` — issue frontmatter reference; does not currently document `priority:`
- `.claude/CLAUDE.md` § Issue File Format — filename convention `P[0-5]-[TYPE]-[NNN]-description.md`

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-21; outcome de-risking edits applied same day (precedence divergence resolved to a decision, completeness verification grep added)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 70/100 → MODERATE

### Outcome Risk Factors
- Wide file fanout: ~9 production files (`issue_parser.py`, `show.py`, `normalize.py`, `sync.py`, `prioritize.py`, `skip.py`, `format_check*.py`, `writers.py`, docs) plus ~5 test files span parser core, CLI issues layer, sync, session_store, and docs — broad enumeration across sites raises the chance one is missed under time pressure. Mitigated in part by the new completeness verification grep in the Tests section, but the write-path breadth itself is inherent to the bug's scope.
- Two existing tests change *meaning*, not just gain assertions (`test_already_at_target_priority_is_noop`, `test_apply_is_idempotent` in `test_ll_issues_prioritize.py`) — restating them incorrectly would silently remove the regression guard against an accidental rename.
- The new format-check gap kind touches 9 fixed locations (dataclass field, `has_gaps` OR-in, docstring, CLI help text, print loop, two test classes, baseline-shape dict) — each is individually mechanical and precedented, but omitting one is easy to miss without deliberately checking off the list in Codebase Research Findings.

_Resolved: the precedence-divergence call (`session_store/writers.py:_derive_type_priority`) is now a committed decision — convert to `resolve_priority(..., default=None)` — rather than a Preferred/Alternative choice left to the implementer (Decision Rules § Precedence divergence)._

## Session Log
- `/ll:manage-issue` - 2026-08-21T21:47:53 - `f6b03c29-ff65-4857-8be4-439d590930d1.jsonl`
- `/ll:ready-issue` - 2026-08-21T21:08:05 - `d9d4eb83-811f-4c1a-b740-f9e18c05bc97.jsonl`
- `/ll:confidence-check` - 2026-08-21T21:05:23 - `259e8978-8652-4d82-a932-fd2ef9f4c5e4.jsonl`
- `/ll:confidence-check` - 2026-08-21T20:23:41 - `4547e3e2-99ed-4578-a5e3-5c34241406e2.jsonl`
- `/ll:confidence-check` - 2026-08-21T19:01:50 - `45eaa854-fea1-43c3-8981-1d72e357bd5f.jsonl`
- `/ll:confidence-check` - 2026-08-21T18:58:41 - `eff768cf-ea73-4732-9715-12285ca3175d.jsonl`
- `/ll:wire-issue` - 2026-08-21T18:29:26 - `8dfb1ac4-9c46-4e39-8612-aa72663c1c57.jsonl`
- `/ll:refine-issue` - 2026-08-21T17:42:10 - `c401e0f5-28d0-4d01-95f3-309f5a7b95c5.jsonl`
- `/ll:capture-issue` - 2026-08-21T17:37:13 - `0c91fc4e-e09c-41b9-a77b-d05fa80fd5b1.jsonl`
