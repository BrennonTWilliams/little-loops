"""Output parsing utilities for automation tools.

Provides parsing functions for Claude CLI command outputs, enabling both
sequential and parallel issue processors to interpret structured command
responses consistently.
"""

from __future__ import annotations

import re
from typing import Any

# Regex patterns for standardized output parsing
# Support #, ##, and ### headers with flexible spacing and optional formatting
# Handles: ## VERDICT, ###VERDICT, ## **VERDICT**, ##  VERDICT
SECTION_PATTERN = re.compile(
    r"^#{1,3}\s*\**(\w+)\**\s*$",
    re.MULTILINE,
)
TABLE_ROW_PATTERN = re.compile(r"\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*(.+?)\s*\|")
STATUS_PATTERN = re.compile(r"^- (\w+): (\w+)", re.MULTILINE)

# Valid verdicts for ready_issue
VALID_VERDICTS = ("READY", "CORRECTED", "NOT_READY", "NEEDS_REVIEW", "CLOSE")


def _clean_verdict_content(content: str) -> str:
    """Clean verdict content by removing common formatting artifacts.

    Handles:
    - Code block markers (``` and `)
    - Markdown bold/italic (** and *)
    - Template brackets ([])
    - Leading/trailing whitespace
    - Colons after verdict

    Args:
        content: Raw verdict content from output

    Returns:
        Cleaned content ready for verdict extraction
    """
    # Remove code fence markers (``` or ```)
    content = re.sub(r"^```\w*\s*", "", content)
    content = re.sub(r"\s*```$", "", content)
    # Remove inline code backticks
    content = content.replace("`", "")
    # Remove markdown bold/italic
    content = content.replace("**", "").replace("*", "")
    # Remove template brackets
    content = content.strip("[]")
    return content.strip()


def _extract_verdict_from_text(text: str) -> str | None:
    """Extract a valid verdict from arbitrary text.

    Searches for valid verdict keywords in the text, handling various
    formats like "READY", "The verdict is READY", "NOT_READY", etc.

    Args:
        text: Text that may contain a verdict

    Returns:
        Valid verdict string or None if not found
    """
    text_upper = text.upper()

    # Check each valid verdict (check NOT_READY before READY to avoid partial match)
    # Order matters: check longer/compound verdicts first
    for verdict in ("NOT_READY", "NEEDS_REVIEW", "CORRECTED", "READY", "CLOSE"):
        # Match verdict as a word boundary (not part of another word)
        # Handle both underscore and space variants
        patterns = [
            rf"\b{verdict}\b",
            rf"\b{verdict.replace('_', ' ')}\b",  # NOT READY, NEEDS REVIEW
            rf"\b{verdict.replace('_', '-')}\b",  # NOT-READY, NEEDS-REVIEW
        ]
        for pattern in patterns:
            if re.search(pattern, text_upper):
                # Normalize to underscore format
                return verdict

    # Try common Claude phrasings that map to verdicts
    # Note: Using re.IGNORECASE since patterns are lowercase
    phrasing_map = [
        # Patterns for READY
        (r"\bissue\s+is\s+ready\b", "READY"),
        (r"\bready\s+for\s+implementation\b", "READY"),
        (r"\bimplementation[\s-]ready\b", "READY"),
        (r"\bapproved\s+for\s+implementation\b", "READY"),
        # Patterns for CLOSE
        (r"\bshould\s+be\s+closed\b", "CLOSE"),
        (r"\bclose\s+this\s+issue\b", "CLOSE"),
        (r"\bmark\s+as\s+closed\b", "CLOSE"),
        (r"\balready\s+fixed\b", "CLOSE"),
        (r"\binvalid\s+reference\b", "CLOSE"),
        # Patterns for NOT_READY
        (r"\bnot\s+ready\b", "NOT_READY"),  # General "not ready" pattern
        (r"\bneeds?\s+more\s+work\b", "NOT_READY"),
        (r"\brequires?\s+clarification\b", "NOT_READY"),
        (r"\bmissing\s+information\b", "NOT_READY"),
        # Patterns for CORRECTED
        (r"\bcorrections?\s+made\b", "CORRECTED"),
        (r"\bupdated?\s+and\s+ready\b", "CORRECTED"),
        (r"\bfixed?\s+and\s+ready\b", "CORRECTED"),
    ]

    for pattern, verdict in phrasing_map:
        if re.search(pattern, text, re.IGNORECASE):
            return verdict

    return None


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
    section containing READY, CORRECTED, NOT_READY, NEEDS_REVIEW, or CLOSE.

    Supports both old format (VERDICT: READY) and new standardized format
    (## VERDICT\\nREADY) for backwards compatibility.

    Args:
        output: The stdout from the ready_issue command

    Returns:
        dict with keys:
        - verdict: str ("READY", "CORRECTED", "NOT_READY", "NEEDS_REVIEW",
                        "CLOSE", or "UNKNOWN")
        - concerns: list[str] of concern messages
        - is_ready: bool indicating if issue is ready for implementation
        - was_corrected: bool indicating if corrections were made
        - should_close: bool indicating if issue should be closed
        - close_reason: str|None (e.g., "already_fixed", "invalid_ref")
        - close_status: str|None (e.g., "Closed - Already Fixed")
        - corrections: list[str] of corrections made
        - validated_file_path: str|None path to the file that was validated
        - sections: dict of parsed sections (if standardized format)
        - validation: dict of validation results (if standardized format)
    """
    # Try new standardized format first
    sections = parse_sections(output)
    verdict = "UNKNOWN"
    concerns: list[str] = []
    corrections: list[str] = []
    validation: dict[str, dict[str, str]] = {}
    close_reason: str | None = None
    close_status: str | None = None
    validated_file_path: str | None = None

    # Strategy 1: Check for VERDICT section (new format with # or ## header)
    if "VERDICT" in sections:
        verdict_section = sections["VERDICT"].strip()

        # Try each non-empty line until we find a verdict
        for line in verdict_section.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Clean the line of formatting artifacts
            cleaned = _clean_verdict_content(line)
            if not cleaned:
                continue

            # Try to extract verdict from cleaned line
            extracted = _extract_verdict_from_text(cleaned)
            if extracted:
                verdict = extracted
                break

    # Strategy 2: Old format (VERDICT: READY) anywhere in output
    if verdict == "UNKNOWN":
        verdict_match = re.search(
            r"VERDICT:\s*(READY|CORRECTED|NOT[_\s-]?READY|NEEDS[_\s-]?REVIEW|CLOSE)",
            output,
            re.IGNORECASE,
        )
        if verdict_match:
            verdict = verdict_match.group(1).upper().replace(" ", "_").replace("-", "_")

    # Strategy 3: Look for verdict keywords near "verdict" mentions
    if verdict == "UNKNOWN":
        # Find lines containing "verdict" and check for verdict keywords
        for line in output.split("\n"):
            if "verdict" in line.lower():
                extracted = _extract_verdict_from_text(line)
                if extracted:
                    verdict = extracted
                    break

    # Strategy 4: Scan entire output for standalone verdict keywords
    # (last resort - may have false positives but better than UNKNOWN)
    if verdict == "UNKNOWN":
        extracted = _extract_verdict_from_text(output)
        if extracted:
            verdict = extracted

    # Strategy 5: Clean the entire output and retry extraction
    # Handles cases where formatting artifacts (bold, backticks) break word boundaries
    if verdict == "UNKNOWN":
        cleaned_output = _clean_verdict_content(output)
        extracted = _extract_verdict_from_text(cleaned_output)
        if extracted:
            verdict = extracted

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

    # Parse CORRECTIONS_MADE section if present
    if "CORRECTIONS_MADE" in sections:
        corrections_content = sections["CORRECTIONS_MADE"]
        for line in corrections_content.split("\n"):
            line = line.strip()
            if line.startswith("- ") and line != "- None":
                corrections.append(line[2:])

    # Parse CLOSE_REASON section if present (for CLOSE verdict)
    if "CLOSE_REASON" in sections:
        close_reason_content = sections["CLOSE_REASON"]
        # Look for "- Reason: <value>" line
        for line in close_reason_content.split("\n"):
            # Strip whitespace and bold markers (**) that Claude sometimes adds
            line = line.strip().replace("**", "")
            if line.lower().startswith("- reason:"):
                reason_value = line.split(":", 1)[1].strip().lower()
                # Also strip backticks that may wrap the value
                close_reason = reason_value.strip("`").strip()
                break
            # Also handle "Reason: <value>" without dash
            if line.lower().startswith("reason:"):
                reason_value = line.split(":", 1)[1].strip().lower()
                close_reason = reason_value.strip("`").strip()
                break

    # Parse CLOSE_STATUS section if present
    if "CLOSE_STATUS" in sections:
        close_status_content = sections["CLOSE_STATUS"].strip()
        # Take first non-empty line as the status
        for line in close_status_content.split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                close_status = line
                break

    # Parse VALIDATED_FILE section if present (for path validation)
    if "VALIDATED_FILE" in sections:
        validated_file_content = sections["VALIDATED_FILE"].strip()
        # Take first non-empty line as the file path
        for line in validated_file_content.split("\n"):
            line = line.strip()
            # Skip empty lines, comments, and template placeholders
            if line and not line.startswith("#") and not line.startswith("["):
                validated_file_path = line
                break

    # Parse VALIDATION section if present
    if "VALIDATION" in sections:
        validation = parse_validation_table(sections["VALIDATION"])

    # Determine flags based on verdict
    is_ready = verdict in ("READY", "CORRECTED")
    was_corrected = verdict == "CORRECTED" or len(corrections) > 0
    should_close = verdict == "CLOSE"

    return {
        "verdict": verdict,
        "concerns": concerns,
        "is_ready": is_ready,
        "was_corrected": was_corrected,
        "should_close": should_close,
        "close_reason": close_reason,
        "close_status": close_status,
        "corrections": corrections,
        "validated_file_path": validated_file_path,
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
