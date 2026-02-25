# ENH-498: Observation Masking / Scratch Pad Pattern

## Plan

### Phase 1: CLAUDE.md Instructions
Add `## Automation: Scratch Pad` section at end of `.claude/CLAUDE.md` (after line 118) with:
- File size check before reading (wc -l; if >200 lines, redirect to scratch)
- Test/lint output piping to scratch with tail summary
- Scratch path reference pattern

### Phase 2: Config Schema
Insert `scratch_pad` block in `config-schema.json` after `context_monitor` (line 447), before `documents` (line 448):
- `enabled`: boolean, default false
- `threshold_lines`: integer, default 200, min 50, max 1000

### Phase 3: Default Config
Add `"scratch_pad": { "enabled": false }` to `.claude/ll-config.json` after `context_monitor`.

### Phase 4: Session Cleanup
Add `rm -rf "/tmp/ll-scratch" 2>/dev/null || true` to `hooks/scripts/session-cleanup.sh` cleanup() after line 14.

## Success Criteria
- [x] CLAUDE.md has scratch pad instructions
- [x] config-schema.json has scratch_pad block
- [x] ll-config.json has scratch_pad default
- [x] session-cleanup.sh cleans /tmp/ll-scratch
- [x] All tests pass
- [x] Lint passes
- [x] Type check passes
