---
id: BUG-3070
priority: P2
type: BUG
status: done
discovered_commit: 9e313a96
discovered_branch: main
discovered_date: 2026-08-05
discovered_by: manage-release
completed_at: 2026-08-06T01:02:29Z
labels:
- release
- tooling
- commands
- changelog
testable: true
size: Small
---

# BUG-3070: `/ll:manage-release` creates the tag before the changelog commit, so every tag omits its own changelog entry

## Summary

`commands/manage-release.md` specified the execution order **bump → tag → changelog →
release** in five separate places. Followed literally, the annotated tag is created
*before* the `docs(release): add changelog for vX.Y.Z` commit exists, so `vX.Y.Z` points
at a tree whose `CHANGELOG.md` has no `X.Y.Z` section. The GitHub release notes are
derived from that same file, so the published release and the tagged tree disagree.

Discovered while executing the v1.154.0 release, where it was worked around manually by
running the changelog step ahead of the tag step.

## Current Behavior

Five ordering statements, all specifying tag-before-changelog:

| Line | Context |
|---|---|
| 98 | Interactive "Full release" option description |
| 124 | Multi-select execution order |
| 289 | The authoritative `5b. Execute Actions` ordering |
| 416 | `Action: full` sequence |
| 482 | Arguments reference for `full` |

The document body reinforced it: `##### Action: tag` (line 329) was laid out *before*
`##### Action: changelog` (line 343), so an implementer reading top-to-bottom tags first
even without consulting the ordering lines.

The `changelog` step itself commits (`commands/manage-release.md`, `Action: changelog`):

```bash
git add CHANGELOG.md
git commit -m "docs(release): add changelog for vX.Y.Z"
```

That commit lands *after* `git tag -a vX.Y.Z`, so it is unreachable from the tag.

Corroborating evidence that this path was already being taken: the baseline-detection
snippet at line 148 carries the comment `# If HEAD is exactly at a tag (e.g., changelog
run after tagging), use the tag before it` — machinery that exists specifically to
tolerate the broken order rather than prevent it.

## Steps to Reproduce

1. Run `/ll:manage-release full <version>` and follow the documented order literally.
2. `git show vX.Y.Z:CHANGELOG.md | grep 'X.Y.Z'` → no entry for the version being tagged.
3. `git log vX.Y.Z..HEAD --oneline` → the `docs(release): add changelog` commit sits
   after the tag.

## Expected Behavior

The tag points at a commit containing its own changelog entry. `git show
vX.Y.Z:CHANGELOG.md` includes the `## [X.Y.Z]` section, and the GitHub release notes
match the tagged tree.

## Resolution

Reordered to **bump → changelog → tag → release** across all five statements, and moved
the `##### Action: changelog` section body ahead of `##### Pre-Release: Learning Test
Audit` and `##### Action: tag` so document order matches execution order. Section
headings now read `bump → changelog → Pre-Release Audit → tag → release`, each appearing
exactly once.

Added a rationale note at the `5b. Execute Actions` ordering line so the sequence is not
"corrected" back later:

> The changelog is written and committed **before** the tag is created, so the tag points
> at a commit that contains its own `CHANGELOG.md` entry (and so the GitHub release, whose
> notes are derived from that entry, is consistent with the tagged tree).

The learning-test audit was left immediately before `tag`, unchanged in position.

Net diff: 44 insertions, 39 deletions in `commands/manage-release.md`.

## Program Design

No code changes; the "design" is the ordering contract the command spec encodes.

**Invariant.** For any released version `X.Y.Z`: `git show vX.Y.Z:CHANGELOG.md` contains
a `## [X.Y.Z]` heading. Equivalently, the `docs(release): add changelog for vX.Y.Z`
commit is an ancestor of `vX.Y.Z`.

**Decision Rules.**

| Condition | Order |
|---|---|
| `full`, or any multi-action selection | `bump` → `changelog` → audit → `tag` → `release` |
| `changelog` alone, HEAD already at a tag | Baseline is the tag *before* HEAD (existing line-148 detection); no reordering applies |
| `tag` alone | Caller is responsible for the invariant; command does not synthesize a changelog |

**Why the audit stays between `changelog` and `tag`.** It is a pre-tag gate — its stated
contract is "if the script exits 0, continue to tag creation". Moving it earlier would
change which artifacts exist when it aborts; that is deliberately out of scope here (see
Impact for the residual `block`-mode wrinkle).

### Signatures

**No signature is added, removed, or altered by this issue** — it changes a command
specification (`commands/manage-release.md`), not Python source. The one existing
signature the ordering contract depends on, unchanged here, is the gate the spec invokes
between `changelog` and `tag` (`scripts/little_loops/learning_tests/release_gate.py:36`):

```python
def run_release_gate(cwd: Path, *, base_dir: Path | None = None) -> int:
```

Its integer return is the branch point: `0` continues to tag creation, `1` aborts the
release. The rest of the enforced contract is the shell-level sequence below.

```bash
# The ordered effect the spec now prescribes for `full`:
git commit -m "chore(release): bump version to X.Y.Z"     # bump
git commit -m "docs(release): add changelog for vX.Y.Z"   # changelog  (MUST precede tag)
run_release_gate(pathlib.Path.cwd()) -> int               # audit gate, exit 0 continues
git tag -a vX.Y.Z -m "Release vX.Y.Z"                     # tag        (now contains changelog)
gh release create vX.Y.Z --notes-file <notes>             # release
```

### Call Path

Anchors are headings in `commands/manage-release.md`:

- `#### 5b. Execute Actions` — authoritative ordering statement (edited)
- `##### Action: bump` — unchanged, still first
- `##### Action: changelog` — **moved** to precede the audit and `tag`
- `##### Pre-Release: Learning Test Audit` → `little_loops.learning_tests.release_gate.run_release_gate`
- `##### Action: tag` — **moved** to follow `changelog`
- `##### Action: release` — unchanged, still last
- `##### Action: full` — sequence line (edited)
- `### 3. Interactive Mode (No Arguments)` — option description and multi-select order (edited)
- `## Arguments` — `full` reference (edited)

## Acceptance Criteria

- [x] No occurrence of `tag → changelog` or `tag + changelog` remains in
      `commands/manage-release.md`.
- [x] All five ordering statements read `changelog` before `tag`.
- [x] `##### Action: changelog` precedes `##### Action: tag` in document order.
- [x] Each `##### ` section heading appears exactly once (no duplicate left by the move).
- [x] The rationale for the ordering is stated inline at the authoritative ordering line.
- [x] v1.154.0 verified to satisfy the invariant: `git show v1.154.0:CHANGELOG.md`
      contains the `## [1.154.0]` section.

## Impact

Every release produced by following this command had a tag whose tree lacked its own
changelog. Consumers checking out a tag — the normal way to inspect "what shipped in
X.Y.Z" — saw a `CHANGELOG.md` whose newest entry was the *previous* release. Automated
runs would not notice, since nothing asserted the invariant.

Severity is bounded by the fact that the changelog commit does land on `main` immediately
after, so the content is never lost, only mis-anchored relative to the tag.

**Residual wrinkle introduced by this fix.** With `changelog` now ahead of `tag`, a
learning-test audit running in `block` mode aborts *after* the changelog has already been
committed, leaving a changelog commit with no corresponding tag. Under the old order it
aborted before any changelog work. Moving the audit to just after `bump` would restore the
cleaner abort, but that is a separate decision and was intentionally not taken here. The
default mode is `warn`, so this only bites projects that opt into `block`.

## Integration Map

- `commands/manage-release.md` — the only file changed.
- Interacts with `Pre-Release: Learning Test Audit`, which remains a pre-`tag` gate.
- No Python source, test, or schema changes; this is a command-spec defect.

## Related Key Documentation

- `commands/manage-release.md`
- `CHANGELOG.md` (Keep a Changelog format)

## Session Log
- `hook:posttooluse-status-done` - 2026-08-06T01:03:30 - `69e7163c-c409-4bc1-8f43-92b62dfb5e4b.jsonl`

- **2026-08-05** — Found during the v1.154.0 release. The release itself was completed
  with the corrected order applied manually: version bumped `1.153.0 → 1.154.0` across 6
  locations in 5 files, changelog written and committed, tag `v1.154.0` created and
  pushed, GitHub release published, and the package built with `hatch` and published to
  PyPI (`little-loops 1.154.0`), verified by installing from PyPI into a clean venv.
- **2026-08-05** — Fix applied to `commands/manage-release.md` and verified by grep that
  no stale ordering text or duplicated section survived the move.

## Status

Done. Fix applied to `commands/manage-release.md`; the v1.154.0 tag satisfies the
invariant.
