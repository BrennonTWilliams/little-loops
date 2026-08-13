# Behavior Parity & Capability-Search Doctrine (ENH-3045)

Full procedure for Phase 3's `REPLACED_ARTIFACTS` extraction, Phase 4's
capability-search requirement, and Phase 8a's `### Behavior Parity` emission.

## Phase 3 addition: REPLACED_ARTIFACTS extraction

Alongside `EXISTING_WIRING`, scan `## Summary`, `## Proposed Solution`, and
`### Files to Modify` for a file reference that shares a line with a
replacement keyword: `delete`, `deletes`, `deleted`, `remove`, `removes`,
`removed`, `replace`, `replaces`, `replaced`, `rewrite`, `rewrites`,
`rewritten`, `supersede`, `supersedes`, `superseded`, `delegate`, `delegates`,
`delegated`. Only a reference that **resolves** to a real tracked file counts.

```
REPLACED_ARTIFACTS: [list of paths this issue rewrites/deletes/delegates away]
```

If empty, skip the Behavior Parity work in Phases 4 and 8a entirely — an
issue that only adds new code has nothing to preserve.

## Phase 4 addition: capability-search requirement (Agent 1 & Agent 3)

Before either agent's prompt concludes "no existing implementation exists,"
it must search by **capability** — the input/output shape of what the new
code needs, and the callers of the shared primitive that shape suggests —
not by the algorithm's name. A grep for a term like "union-find" or
"disjoint-set" finds nothing if the codebase never names the algorithm, even
when a function with the exact same input/output contract already exists
under an unrelated name. The resulting claim must name what was searched
(the capability shape and the caller-search performed), not just assert the
negative.

The same grounding applies to **positive** claims: an assertion that an
existing symbol is reusable, unchanged, or behaves a certain way must quote
the specific line that makes it true, not merely name the symbol — naming a
symbol proves it resolves, not that the claim about it holds.

For each file in `REPLACED_ARTIFACTS`, Agent 1 additionally locates every
behavior of that file (as named in its docstrings, comments, or observed
logic) so Phase 8a can enumerate a disposition for each.

## Phase 8a addition: `### Behavior Parity` subsection

Emit exactly one `### Behavior Parity` subsection per issue under
`## Integration Map` — bare heading, the replaced artifact carried as a
table column, never as heading text (`_heading_bodies()` matches the heading
anchored and exact, so a per-artifact heading would never be detected):

```markdown
### Behavior Parity

_Wiring pass added by `/ll:wire-issue`:_
| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `path/to/old_file.py` | [behavior 1] | PRESERVED / CHANGED / DROPPED | [why] |
| `path/to/old_file.py` | [behavior 2] | PRESERVED / CHANGED / DROPPED | [why] |
```

Skip emission (and this whole file's other steps) when `REPLACED_ARTIFACTS`
is empty, or when the issue sets `behavior_parity_not_applicable: true` in
frontmatter — a human decision; wire must never set this flag itself. Phase
8c's Preservation Rule and contradiction carve-out govern this subsection
identically to the other Integration Map subsections.
