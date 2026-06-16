"""GitHub utility functions for feature-branch PR state checks."""

from __future__ import annotations

import json
import subprocess


def is_pr_merged(branch: str, pr_url: str | None = None) -> bool:
    """Check whether a PR for the given branch or URL has been merged.

    Args:
        branch: Branch name to look up (used when pr_url is None)
        pr_url: PR URL to check directly (preferred over branch name)

    Returns:
        True if the PR exists and state is MERGED, False otherwise (including
        errors, missing gh CLI, timeouts, and unauthenticated states).
    """
    ref = pr_url or branch
    if not ref:
        return False
    try:
        result = subprocess.run(
            ["gh", "pr", "view", ref, "--json", "state,mergedAt"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return False
        data = json.loads(result.stdout)
        return data.get("state") == "MERGED"
    except FileNotFoundError:
        return False
    except subprocess.TimeoutExpired:
        return False
    except json.JSONDecodeError:
        return False
