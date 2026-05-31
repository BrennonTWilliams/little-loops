"""ll-issues fingerprint: extract structured fingerprint from an issue file."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_fingerprint(config: BRConfig, args: argparse.Namespace) -> int:
    """Extract structured fingerprint (id, files_to_modify, key_terms) from an issue file.

    Reads the issue file and outputs JSON with:
    - id: issue ID from frontmatter (falls back to filename parsing)
    - files_to_modify: sorted list of file paths from the Integration Map section
    - key_terms: sorted list of significant words after stop-word filtering

    Args:
        config: Project configuration.
        args: Parsed arguments with .issue_path.

    Returns:
        0 on success, 1 on error.
    """
    from little_loops.parallel.file_hints import extract_file_hints
    from little_loops.text_utils import extract_words

    issue_path = Path(args.issue_path)
    if not issue_path.is_absolute():
        issue_path = config.project_root / issue_path

    if not issue_path.is_file():
        print(f"Error: issue file not found: {issue_path}", file=sys.stderr)
        return 1

    content = issue_path.read_text()

    # Extract issue ID from frontmatter
    issue_id = ""
    fm_match = re.search(r"^---\n(.*?)^---", content, re.MULTILINE | re.DOTALL)
    if fm_match:
        id_match = re.search(r"^id:\s*(\S+)", fm_match.group(1), re.MULTILINE)
        if id_match:
            issue_id = id_match.group(1)
    if not issue_id:
        # Fallback: parse from filename (P3-ENH-1801-title -> ENH-1801)
        stem = issue_path.stem
        parts = stem.split("-")
        issue_id = "-".join(parts[1:3]) if len(parts) >= 3 else stem

    hints = extract_file_hints(content, issue_id=issue_id)
    key_terms = extract_words(content)

    result = {
        "id": issue_id,
        "files_to_modify": sorted(hints.files),
        "key_terms": sorted(key_terms),
    }

    print(json.dumps(result, indent=2))
    return 0
