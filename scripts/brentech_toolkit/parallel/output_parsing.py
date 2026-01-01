"""Output parsing utilities for automation tools.

Provides parsing functions for Claude CLI command outputs, enabling both
sequential and parallel issue processors to interpret structured command
responses consistently.
"""

from __future__ import annotations

import re
from typing import Any

# Regex patterns for standardized output parsing
SECTION_PATTERN = re.compile(r"^## (\w+)$", re.MULTILINE)
TABLE_ROW_PATTERN = re.compile(r"\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*(.+?)\s*\|")
STATUS_PATTERN = re.compile(r"^- (\w+): (\w+)", re.MULTILINE)


def parse_sections(output: str) -> dict[str, str]:
    """Parse output into sections by ## SECTION_NAME headers.

    The standardized slash command output format uses ## SECTION_NAME
    headers (uppercase with underscores) to delimit sections.

    Args:
        output: The stdout from a slash command

    Returns:
        dict mapping section names to their content
    """
    sections: dict[str, str] = {}
    current_section = "PREAMBLE"
    current_content: list[str] = []

    for line in output.split("\n"):
        match = SECTION_PATTERN.match(line)
        if match:
            # Save previous section
            sections[current_section] = "\n".join(current_content).strip()
            current_section = match.group(1)
            current_content = []
        else:
            current_content.append(line)

    # Save final section
    sections[current_section] = "\n".join(current_content).strip()
    return sections


def parse_validation_table(section_content: str) -> dict[str, dict[str, str]]:
    """Parse a validation table from section content.

    Expects format:
    | Check | Status | Details |
    |-------|--------|---------|
    | Format | PASS | ... |

    Args:
        section_content: Content of the VALIDATION section

    Returns:
        dict mapping check names to {status, details}
    """
    results: dict[str, dict[str, str]] = {}
    for match in TABLE_ROW_PATTERN.finditer(section_content):
        check_name = match.group(1)
        # Skip header row indicators
        if check_name.lower() in ("check", "---", ""):
            continue
        results[check_name] = {
            "status": match.group(2).upper(),
            "details": match.group(3).strip(),
        }
    return results


def parse_status_lines(section_content: str) -> dict[str, str]:
    """Parse status lines from section content.

    Expects format:
    - tests: PASS
    - lint: PASS

    Args:
        section_content: Content of a section with status lines

    Returns:
        dict mapping item names to status values
    """
    results: dict[str, str] = {}
    for match in STATUS_PATTERN.finditer(section_content):
        results[match.group(1)] = match.group(2).upper()
    return results


def parse_ready_issue_output(output: str) -> dict[str, Any]:
    """Extract verdict and concerns from ready_issue output.

    The ready_issue command outputs structured sections with a VERDICT
    section containing READY, NOT_READY, or NEEDS_REVIEW.

    Supports both old format (VERDICT: READY) and new standardized format
    (## VERDICT\\nREADY) for backwards compatibility.

    Args:
        output: The stdout from the ready_issue command

    Returns:
        dict with keys:
        - verdict: str ("READY", "NOT_READY", "NEEDS_REVIEW", or "UNKNOWN")
        - concerns: list[str] of concern messages
        - is_ready: bool indicating if issue is ready for implementation
        - sections: dict of parsed sections (if standardized format)
        - validation: dict of validation results (if standardized format)
    """
    # Try new standardized format first
    sections = parse_sections(output)
    verdict = "UNKNOWN"
    concerns: list[str] = []
    validation: dict[str, dict[str, str]] = {}

    # Check for VERDICT section (new format)
    if "VERDICT" in sections:
        verdict_content = sections["VERDICT"].strip().upper()
        if verdict_content in ("READY", "NOT_READY", "NEEDS_REVIEW"):
            verdict = verdict_content

    # Fall back to old format (VERDICT: READY)
    if verdict == "UNKNOWN":
        verdict_match = re.search(
            r"VERDICT:\s*(READY|NOT[_\s]?READY|NEEDS[_\s]?REVIEW)",
            output,
            re.IGNORECASE,
        )
        if verdict_match:
            verdict = verdict_match.group(1).upper().replace(" ", "_")

    # Parse CONCERNS section (new format)
    if "CONCERNS" in sections:
        concern_content = sections["CONCERNS"]
        for line in concern_content.split("\n"):
            line = line.strip()
            if line.startswith("- ") and line != "- None":
                concerns.append(line[2:])  # Remove "- " prefix

    # Fall back to old concern detection
    if not concerns:
        for line in output.split("\n"):
            line_stripped = line.strip()
            if any(
                indicator in line_stripped
                for indicator in ["WARNING", "Concern:", "Issue:", "Missing:"]
            ):
                concerns.append(line_stripped)

    # Parse VALIDATION section if present
    if "VALIDATION" in sections:
        validation = parse_validation_table(sections["VALIDATION"])

    return {
        "verdict": verdict,
        "concerns": concerns,
        "is_ready": verdict == "READY",
        "sections": sections,
        "validation": validation,
    }


def parse_manage_issue_output(output: str) -> dict[str, Any]:
    """Extract structured data from manage_issue output.

    The manage_issue command outputs structured sections with metadata,
    files changed, commits, verification results, and final status.

    Args:
        output: The stdout from the manage_issue command

    Returns:
        dict with keys:
        - status: str ("COMPLETED", "FAILED", "BLOCKED", or "UNKNOWN")
        - files_changed: list[str] of modified files
        - files_created: list[str] of created files
        - commits: list[str] of commit hashes/messages
        - verification: dict of verification results
        - ooda_impact: dict of OODA impact status
        - sections: dict of all parsed sections
    """
    sections = parse_sections(output)
    status = "UNKNOWN"
    files_changed: list[str] = []
    files_created: list[str] = []
    commits: list[str] = []
    verification: dict[str, str] = {}
    ooda_impact: dict[str, str] = {}

    # Parse RESULT section for status
    if "RESULT" in sections:
        status_match = re.search(r"Status:\s*(\w+)", sections["RESULT"])
        if status_match:
            status = status_match.group(1).upper()

    # Parse FILES_CHANGED section
    if "FILES_CHANGED" in sections:
        for line in sections["FILES_CHANGED"].split("\n"):
            line = line.strip()
            if line.startswith("- ") and line != "- None":
                files_changed.append(line[2:])

    # Parse FILES_CREATED section
    if "FILES_CREATED" in sections:
        for line in sections["FILES_CREATED"].split("\n"):
            line = line.strip()
            if line.startswith("- ") and line != "- None":
                files_created.append(line[2:])

    # Parse COMMITS section
    if "COMMITS" in sections:
        for line in sections["COMMITS"].split("\n"):
            line = line.strip()
            if line.startswith("- ") and line != "- None":
                commits.append(line[2:])

    # Parse VERIFICATION section
    if "VERIFICATION" in sections:
        verification = parse_status_lines(sections["VERIFICATION"])

    # Parse OODA_IMPACT section
    if "OODA_IMPACT" in sections:
        for line in sections["OODA_IMPACT"].split("\n"):
            line = line.strip()
            if line.startswith("- "):
                parts = line[2:].split(":", 1)
                if len(parts) == 2:
                    ooda_impact[parts[0].strip()] = parts[1].strip().upper()

    return {
        "status": status,
        "files_changed": files_changed,
        "files_created": files_created,
        "commits": commits,
        "verification": verification,
        "ooda_impact": ooda_impact,
        "sections": sections,
    }
