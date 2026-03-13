# ENH-676: Reduce column widths in ll-issues refine-status table

## Analysis

Current column widths after "source" are too wide, causing overflow in narrow terminals.

**Current widths (post-source columns):**
- `_CMD_WIDTH = 8` (each dynamic command column)
- `_SCORE_WIDTH = 7` ("ready" column)
- `_CONF_WIDTH = 10` ("confidence" column)
- `_TOTAL_WIDTH = 5` ("total" column)

**Width calculation with 4 dynamic command columns:**
- Non-title overhead: id(8) + pri(4) + source(7) + norm(4) + fmt(4) + 4*cmd(8) + ready(7) + conf(10) + total(5) + separators(24) = 105
- At 80 cols: title = -25 (doesn't fit)
- At 100 cols: title = -5 (doesn't fit)

## Changes

### 1. Reduce `_CMD_WIDTH` from 8 to 6
- "verify" (6) fits exactly
- "refine" (6) fits exactly
- "tradeoff" (8) truncates to "trade…" via existing `_truncate()`
- "map" (3) fits easily
- Savings: 2 chars × N command columns

### 2. Reduce `_CONF_WIDTH` from 10 to 5
- Header changes from "confidence" to "conf"
- Values are numeric (max 3 digits) or em-dash — fit easily in 5
- Savings: 5 chars

### 3. Reduce `_SCORE_WIDTH` from 7 to 5
- Header "ready" is exactly 5 chars — perfect fit
- Values are numeric (max 3 digits) or em-dash
- Savings: 2 chars

### 4. No change to `_TOTAL_WIDTH` (already 5)

**New overhead with 4 cmd columns:** 105 - 8 - 5 - 2 = 90
- At 100 cols: title = 10 (usable)
- At 120 cols: title = 30 (comfortable)

## Files Modified

1. `scripts/little_loops/cli/issues/refine_status.py` — width constants + header text
2. `scripts/tests/test_refine_status.py` — update expected widths in assertions

## Success Criteria

- [ ] Width constants updated
- [ ] Header text for "confidence" shortened to "conf"
- [ ] Tests pass
- [ ] Type checks pass
