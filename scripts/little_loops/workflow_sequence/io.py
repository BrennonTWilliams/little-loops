"""File I/O helpers for workflow sequence analysis."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml


def _load_messages(messages_file: Path) -> list[dict[str, Any]]:
    """Load messages from JSONL file."""
    messages = []
    skipped = 0
    with open(messages_file, encoding="utf-8") as f:
        for line_num, raw_line in enumerate(f, 1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError as e:
                skipped += 1
                print(f"Warning: skipping malformed line {line_num}: {e}", file=sys.stderr)
    if skipped:
        print(f"Warning: skipped {skipped} malformed line(s) in {messages_file}", file=sys.stderr)
    return messages


def _load_patterns(patterns_file: Path) -> dict[str, Any]:
    """Load patterns from Step 1 YAML output."""
    with open(patterns_file, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
