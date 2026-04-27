"""Tests for ready-issue lint: file:line contamination detection — ENH-1300."""

from __future__ import annotations

CLEAN_ISSUE = """\
---
title: Clean issue
---

# ENH-001: Clean Issue

## Summary

This issue uses only anchor-style references.

## Proposed Solution

See `scripts/foo.py` (near function `process`) for the existing implementation.

```python
# file.py:42 — this is inside a code fence and should be ignored
x = 1
```
"""

CONTAMINATED_ISSUE = """\
---
title: Contaminated issue
---

# ENH-002: Contaminated Issue

## Summary

This issue has a file:line reference.

## Proposed Solution

See scripts/foo.py:42 for the existing implementation.
Also check bar.ts:100 for the interface.
"""


class TestReadyIssueLintRule:
    """Validate that the file:line lint rule detects contamination correctly."""

    def test_clean_issue_passes(self) -> None:
        """An issue with no bare file:line refs (only anchors) reports no matches."""
        from little_loops.issues.anchor_sweep import _CODE_FENCE, _FILE_LINE

        content = CLEAN_ISSUE
        fence_spans = [(m.start(), m.end()) for m in _CODE_FENCE.finditer(content)]

        def _in_fence(start: int, end: int) -> bool:
            return any(fs <= start and end <= fe for fs, fe in fence_spans)

        matches = [m for m in _FILE_LINE.finditer(content) if not _in_fence(m.start(), m.end())]
        assert matches == [], f"Expected no file:line matches, got: {matches}"

    def test_contaminated_issue_flagged(self) -> None:
        """An issue with bare file:line refs outside fences is correctly flagged."""
        from little_loops.issues.anchor_sweep import _CODE_FENCE, _FILE_LINE

        content = CONTAMINATED_ISSUE
        fence_spans = [(m.start(), m.end()) for m in _CODE_FENCE.finditer(content)]

        def _in_fence(start: int, end: int) -> bool:
            return any(fs <= start and end <= fe for fs, fe in fence_spans)

        matches = [m for m in _FILE_LINE.finditer(content) if not _in_fence(m.start(), m.end())]
        paths = [m.group(1) for m in matches]
        assert "scripts/foo.py" in paths
        assert "bar.ts" in paths

    def test_ref_inside_fence_not_flagged(self) -> None:
        """file:line references inside code fences are not flagged."""
        from little_loops.issues.anchor_sweep import _CODE_FENCE, _FILE_LINE

        content = "```\nfoo.py:99\n```\n"
        fence_spans = [(m.start(), m.end()) for m in _CODE_FENCE.finditer(content)]

        def _in_fence(start: int, end: int) -> bool:
            return any(fs <= start and end <= fe for fs, fe in fence_spans)

        matches = [m for m in _FILE_LINE.finditer(content) if not _in_fence(m.start(), m.end())]
        assert matches == []
