---
id: FEAT-1896
title: "Decisions Log — Skill Bridges"
type: FEAT
priority: P3
parent: FEAT-1892
discovered_date: 2026-06-03
depends_on:
- FEAT-1891
- FEAT-1894
decision_needed: false
---

# FEAT-1896: Decisions Log — Skill Bridges

## Summary

Wire three skills (`/ll:decide-issue`, `/ll:tradeoff-review-issues`, `/ll:go-no-go`) to append `decision` entries as a side effect, and optionally wire `/ll:capture-issue` for architectural choices at capture time. All integrations gracefully degrade when `decisions.yaml` is absent. Can run in parallel with FEAT-1895 once FEAT-1894 is merged.

## Parent Issue

Decomposed from FEAT-1892: Decisions Log — CLI Subcommand, Sync, and Skill Bridges

## Integration Map

### Files to Modify
- `skills/decide-issue/SKILL.md` — add `ll-issues decisions add` bash call after Phase 6 annotation; guard with `[ -f .ll/decisions.yaml ]`; add `Bash(ll-issues:*)` to `allowed-tools` in frontmatter if not present (already listed per refinement notes — verify)
- `commands/tradeoff-review-issues.md` — add `ll-issues decisions add` bash call after final output; guard with `[ -f .ll/decisions.yaml ]`
- `skills/go-no-go/SKILL.md` — add `ll-issues decisions add` bash call after verdict; guard with `[ -f .ll/decisions.yaml ]`; add `Bash(ll-issues:*)` to `allowed-tools` in frontmatter (currently missing per Step 20)
- `skills/capture-issue/SKILL.md` — optional: add `ll-issues decisions add` for notable architectural choices at capture time; guard with `[ -f .ll/decisions.yaml ]`

### Similar Patterns (Key Anchors)
- `skills/decide-issue/SKILL.md` — already has `Bash(ll-issues:*)` in `allowed-tools` as reference
- `capture-issue` and `go-no-go` skills use `2>/dev/null || true` graceful degradation pattern

## Proposed Solution

### decide-issue Bridge (Step 6)

After Phase 6 annotation in `skills/decide-issue/SKILL.md`, add:

```bash
if [ -f .ll/decisions.yaml ]; then
    ll-issues decisions add --type=decision --issue=$FILE \
      --rule="<chosen option title>" \
      --rationale="<Decision Rationale text>" \
      --alternatives-rejected="<other options + scores>"
fi
```

### tradeoff-review-issues Bridge (Step 6)

After final output in `commands/tradeoff-review-issues.md`, append `decision` entry:
- `--issue` = issue analyzed
- `--rule` = recommendation text
- `--rationale` = key tradeoff narrative
- `--alternatives-rejected` = losing options

```bash
if [ -f .ll/decisions.yaml ]; then
    ll-issues decisions add --type=decision \
      --issue="$ISSUE_ID" \
      --rule="$RECOMMENDATION" \
      --rationale="$KEY_TRADEOFF" \
      --alternatives-rejected="$LOSING_OPTIONS"
fi
```

### go-no-go Bridge (Step 6)

After verdict in `skills/go-no-go/SKILL.md`, append:
- `--issue` = issue evaluated
- `--rule` = "Go" or "No-Go"
- `--rationale` = blocking or approving criteria met
- `--enforcement=advisory`

Also add `Bash(ll-issues:*)` to `allowed-tools` frontmatter (Step 20).

### capture-issue Bridge (Step 7 — Optional)

Update `skills/capture-issue/SKILL.md` to optionally log a `decision` entry when the user makes a notable architectural choice at capture time. Gate on `[ -f .ll/decisions.yaml ]`.

### Graceful Degradation Pattern

All integrations must use one of:
```bash
# Option A: explicit file guard
if [ -f .ll/decisions.yaml ]; then
    ll-issues decisions add ...
fi

# Option B: silent fallthrough (matches existing pattern)
ll-issues decisions add ... 2>/dev/null || true
```

## Acceptance Criteria

- [ ] `/ll:decide-issue` appends `decision` entry after option selection; silently skipped if `decisions.yaml` absent
- [ ] `/ll:tradeoff-review-issues` appends `decision` entry after analysis; silently skipped if absent
- [ ] `/ll:go-no-go` appends `decision` entry after verdict; silently skipped if absent
- [ ] `skills/go-no-go/SKILL.md` frontmatter includes `Bash(ll-issues:*)` in `allowed-tools` (Step 20)
- [ ] Optional: `/ll:capture-issue` appends `decision` entry for notable architectural choices
- [ ] All bridges use consistent graceful degradation pattern

## Session Log
- `/ll:issue-size-review` - 2026-06-03T00:00:00Z - `3b396e18-8717-4088-9842-5574f1659959.jsonl`
