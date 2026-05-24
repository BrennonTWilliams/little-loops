---
id: ENH-1684
type: ENH
priority: P4
status: open
discovered_date: 2026-05-24
discovered_by: capture-issue
captured_at: '2026-05-24T18:14:01Z'
decision_needed: false
---

# ENH-1684: Add timestamp suffix to deep-research run directory to prevent silent overwrite

## Summary

The `deep-research` loop's `init` state uses `: >` to truncate artifact files whenever the same topic slug maps to an existing directory. Re-running research on the same topic silently destroys previous results. Append a `$(date +%Y-%m-%dT%H%M%S)` suffix to the run directory slug so every invocation lands in its own isolated directory.

## Current Behavior

The `init` state generates a slug from the topic and runs:

```bash
DIR="${context.output_dir}/$SLUG"
mkdir -p "$DIR"
: > "$DIR/report.md"
: > "$DIR/knowledge-base.md"
: > "$DIR/coverage.md"
: > "$DIR/query-log.md"
```

If `.loops/research/ai-safety/` already exists from a prior run, all four artifact files are silently emptied before the new run begins. The prior research is unrecoverable.

## Expected Behavior

Each invocation creates a new, uniquely named run directory:

```
.loops/research/ai-safety-20260524-143022/
  report.md
  knowledge-base.md
  coverage.md
  query-log.md
```

Re-running the same topic produces `ai-safety-20260524-150811/` alongside the original — no data loss.

## Motivation

Users iterate on research topics (refine the question, re-run after new events). Without per-run isolation, there is no way to compare an earlier and later synthesis or recover from a partial run gone wrong. This is the minimum-complexity fix for that loss-of-data bug.

## Implementation Steps

1. In `scripts/little_loops/loops/deep-research.yaml`, update the `init` state's `action` shell block:
   - Append `$(date +%Y-%m-%dT%H%M%S)` to the slug before building `DIR`.
   - Remove the `: > "$DIR/..."` truncation lines (the files are new, so `mkdir -p` alone is sufficient; the empty-file init can stay as `: > "$DIR/file"` since the dir is fresh).

2. The `SLUG` generation line becomes:

   ```bash
   SLUG=$(echo "${context.topic}" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/-\+/-/g; s/^-//; s/-$//')
   SLUG="$${SLUG:-deep-research-run}"
   TS=$(date +%Y-%m-%dT%H%M%S)
   DIR="${context.output_dir}/$${SLUG}-$${TS}"
   ```

3. No other states need changes — all downstream states reference `${captured.run_dir.output}` which remains stable within a single loop run.

4. Optionally add slug truncation (`${SLUG:0:40}`) before appending the timestamp to bound path length for very long topics.

## Out of Scope

- "Latest" symlink (Option B) — adds complexity not warranted for this fix.
- Date-scoped hierarchy (Option D) — topic browsing would require scanning subdirs.
- Metadata manifest file — useful but independent; can be a follow-on ENH.

## Acceptance Criteria

- [ ] Running `ll-loop run deep-research "AI safety"` twice produces two separate directories under `.loops/research/`.
- [ ] Neither run's artifact files are empty after the second invocation.
- [ ] The timestamp format is `YYYY-MM-DDTHHMMSS` (no colons, filesystem-safe).
- [ ] `ll-loop validate deep-research` still exits 0.

## Session Log
- `/ll:capture-issue` - 2026-05-24T18:14:01Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/63b24a19-04df-472a-86c8-b45901270f93.jsonl`
