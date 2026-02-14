"""Link checker for markdown documentation.

Provides automated verification that links in markdown files are valid.
Supports HTTP/HTTPS URL checking and internal file reference validation.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

# Markdown link patterns
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
BARE_URL_PATTERN = re.compile(r'(?:^|[\s\'"<\(])((?:https?://)[^\s\'"<>)]+)', re.MULTILINE)

# Default ignore patterns
DEFAULT_IGNORE_PATTERNS = [
    r"^http://localhost",
    r"^https://localhost",
    r"^http://127\.0\.0\.1",
    r"^https://127\.0\.0\.1",
    r"^http://0\.0\.0\.0",
    r"^https://0\.0\.0\.0",
]

# Files to check by default (relative to base directory)
DEFAULT_DOC_FILES = [
    "README.md",
    "CONTRIBUTING.md",
    "docs/**/*.md",
]


@dataclass
class LinkResult:
    """Result of checking a single link.

    Attributes:
        url: The URL that was checked
        file: File containing the link
        line: Line number where link appears
        status: Status of the link ("valid", "broken", "timeout", "ignored", "internal")
        error: Error message if link is broken
        link_text: The link text from markdown [text](url)
    """

    url: str
    file: str
    line: int
    status: str
    error: str | None = None
    link_text: str | None = None


@dataclass
class LinkCheckResult:
    """Overall results from link checking.

    Attributes:
        total_links: Total number of links found
        valid_links: Number of valid links
        broken_links: Number of broken links
        ignored_links: Number of ignored links
        internal_links: Number of internal file references
        results: List of individual link results
    """

    total_links: int = 0
    valid_links: int = 0
    broken_links: int = 0
    ignored_links: int = 0
    internal_links: int = 0
    results: list[LinkResult] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Check if any broken links were found."""
        return self.broken_links > 0


def extract_links_from_markdown(content: str, file_path: str) -> list[tuple[str, str | None, int]]:
    """Extract links from markdown content.

    Args:
        content: Markdown file content
        file_path: Path to the file (for context)

    Returns:
        List of (url, link_text, line_number) tuples
    """
    links: list[tuple[str, str | None, int]] = []
    lines = content.splitlines()

    for line_num, line in enumerate(lines, start=1):
        # Extract markdown links [text](url)
        for match in MARKDOWN_LINK_PATTERN.finditer(line):
            url = match.group(2).strip()
            link_text = match.group(1)
            links.append((url, link_text, line_num))

        # Extract bare URLs, excluding those already captured in markdown links
        # First, remove markdown link URLs from the line
        line_without_md_links = MARKDOWN_LINK_PATTERN.sub("", line)
        for match in BARE_URL_PATTERN.finditer(line_without_md_links):
            url = match.group(1).strip()
            # Clean up trailing punctuation
            url = re.sub(r"[.,;:!?)\]]+$", "", url)
            links.append((url, None, line_num))

    return links


def is_internal_reference(url: str) -> bool:
    """Check if URL is an internal file reference.

    Args:
        url: URL to check

    Returns:
        True if internal reference, False otherwise
    """
    # Internal references start with # or ./ or ../ or just .md
    return (
        url.startswith("#") or url.startswith("./") or url.startswith("../") or url.endswith(".md")
    )


def should_ignore_url(url: str, ignore_patterns: list[str]) -> bool:
    """Check if URL should be ignored based on patterns.

    Args:
        url: URL to check
        ignore_patterns: List of regex patterns to match

    Returns:
        True if URL should be ignored
    """
    for pattern in ignore_patterns:
        if re.search(pattern, url):
            return True
    return False


def check_url(url: str, timeout: int = 10) -> tuple[bool, str | None]:
    """Check if a URL is reachable.

    Args:
        url: URL to check
        timeout: Request timeout in seconds

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Create request with user agent
        req = urllib.request.Request(url, headers={"User-Agent": "little-loops-link-checker/1.0"})
        # Use HEAD request for efficiency
        req.get_method = lambda: "HEAD"  # type: ignore[method-assign]

        with urllib.request.urlopen(req, timeout=timeout) as response:
            # Accept 2xx and 3xx status codes
            if 200 <= response.status < 400:
                return True, None
            return False, f"HTTP {response.status}"

    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"Connection error: {e.reason}"
    except TimeoutError:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)


def check_markdown_links(
    base_dir: Path,
    ignore_patterns: list[str] | None = None,
    timeout: int = 10,
    verbose: bool = False,
    max_workers: int = 10,
) -> LinkCheckResult:
    """Check all markdown files for broken links.

    Args:
        base_dir: Base directory to search
        ignore_patterns: List of regex patterns to ignore
        timeout: Request timeout in seconds
        verbose: Whether to show progress
        max_workers: Maximum concurrent HTTP requests

    Returns:
        LinkCheckResult with all findings
    """
    if ignore_patterns is None:
        ignore_patterns = DEFAULT_IGNORE_PATTERNS.copy()

    result = LinkCheckResult()

    # Find all markdown files
    md_files = list(base_dir.rglob("*.md"))

    # Pass 1: Classify links, collect HTTP URLs for concurrent checking
    http_checks: list[tuple[str, str | None, int, str]] = []  # (url, link_text, line, file)

    for md_file in md_files:
        try:
            content = md_file.read_text()
            relative_path = md_file.relative_to(base_dir)
            file_str = str(relative_path)

            links = extract_links_from_markdown(content, file_str)

            for url, link_text, line_num in links:
                result.total_links += 1

                # Check if should ignore
                if should_ignore_url(url, ignore_patterns):
                    result.ignored_links += 1
                    result.results.append(
                        LinkResult(
                            url=url,
                            file=file_str,
                            line=line_num,
                            status="ignored",
                        )
                    )
                    continue

                # Check if internal reference
                if is_internal_reference(url):
                    result.internal_links += 1
                    result.results.append(
                        LinkResult(
                            url=url,
                            file=file_str,
                            line=line_num,
                            status="internal",
                            link_text=link_text,
                        )
                    )
                    continue

                # Collect HTTP/HTTPS URLs for concurrent checking
                http_checks.append((url, link_text, line_num, file_str))

        except Exception as e:
            # File read error - log as broken entry for this file
            result.results.append(
                LinkResult(
                    url="",
                    file=str(md_file.relative_to(base_dir)),
                    line=0,
                    status="broken",
                    error=f"File read error: {e}",
                )
            )

    # Pass 2: Check HTTP URLs concurrently
    if http_checks:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_meta = {
                executor.submit(check_url, url, timeout): (url, link_text, line_num, file_str)
                for url, link_text, line_num, file_str in http_checks
            }

            for future in as_completed(future_to_meta):
                url, link_text, line_num, file_str = future_to_meta[future]
                is_valid, error = future.result()

                if is_valid:
                    result.valid_links += 1
                    result.results.append(
                        LinkResult(
                            url=url,
                            file=file_str,
                            line=line_num,
                            status="valid",
                            link_text=link_text,
                        )
                    )
                else:
                    result.broken_links += 1
                    result.results.append(
                        LinkResult(
                            url=url,
                            file=file_str,
                            line=line_num,
                            status="broken",
                            error=error,
                            link_text=link_text,
                        )
                    )

    return result


def load_ignore_patterns(base_dir: Path) -> list[str]:
    """Load ignore patterns from .mlc.config.json.

    Args:
        base_dir: Base directory path

    Returns:
        List of ignore patterns
    """
    patterns = DEFAULT_IGNORE_PATTERNS.copy()

    config_file = base_dir / ".mlc.config.json"
    if not config_file.exists():
        return patterns

    try:
        with open(config_file) as f:
            config = json.load(f)

        # Extract ignore patterns
        ignore_list = config.get("ignorePatterns", [])
        for item in ignore_list:
            if isinstance(item, dict):
                pattern = item.get("pattern", "")
            elif isinstance(item, str):
                pattern = item
            else:
                continue

            if pattern:
                patterns.append(pattern)

    except (OSError, json.JSONDecodeError):
        # If config is invalid, use defaults
        pass

    return patterns


def format_result_text(result: LinkCheckResult) -> str:
    """Format link check result as text.

    Args:
        result: Link check result

    Returns:
        Formatted text output
    """
    lines = ["Documentation Link Check", "=" * 40]

    if result.has_errors:
        lines.append(f"✗ Found {result.broken_links} broken link(s):")
        lines.append("")

        for r in result.results:
            if r.status == "broken":
                text_part = f"[{r.link_text}]" if r.link_text else ""
                lines.append(f"  {text_part}({r.url})")
                lines.append(f"    at {r.file}:{r.line}")
                if r.error:
                    lines.append(f"    Error: {r.error}")
                lines.append("")

        # Summary
        lines.append("Summary:")
        lines.append(f"  Total links: {result.total_links}")
        lines.append(f"  Valid: {result.valid_links}")
        lines.append(f"  Broken: {result.broken_links}")
        lines.append(f"  Internal refs: {result.internal_links}")
        lines.append(f"  Ignored: {result.ignored_links}")

    else:
        lines.append(
            f"✓ All {result.total_links} link(s) valid! "
            f"({result.internal_links} internal, {result.ignored_links} ignored)"
        )

    return "\n".join(lines)


def format_result_json(result: LinkCheckResult) -> str:
    """Format link check result as JSON.

    Args:
        result: Link check result

    Returns:
        JSON string
    """
    data = {
        "total_links": result.total_links,
        "valid_links": result.valid_links,
        "broken_links": result.broken_links,
        "ignored_links": result.ignored_links,
        "internal_links": result.internal_links,
        "has_errors": result.has_errors,
        "results": [
            {
                "url": r.url,
                "file": r.file,
                "line": r.line,
                "status": r.status,
                "error": r.error,
                "link_text": r.link_text,
            }
            for r in result.results
        ],
    }

    return json.dumps(data, indent=2)


def format_result_markdown(result: LinkCheckResult) -> str:
    """Format link check result as Markdown.

    Args:
        result: Link check result

    Returns:
        Markdown formatted string
    """
    lines = ["# Documentation Link Check", ""]
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total links**: {result.total_links}")
    lines.append(f"- **Valid**: {result.valid_links}")
    lines.append(f"- **Broken**: {result.broken_links}")
    lines.append(f"- **Internal references**: {result.internal_links}")
    lines.append(f"- **Ignored**: {result.ignored_links}")
    lines.append("")

    if result.has_errors:
        lines.append("## ❌ Broken Links")
        lines.append("")
        lines.append("| URL | File | Line | Error |")
        lines.append("|-----|------|------|-------|")

        for r in result.results:
            if r.status == "broken":
                url_display = r.url[:60] + "..." if len(r.url) > 60 else r.url
                error_display = r.error or "Unknown"
                lines.append(f"| `{url_display}` | `{r.file}` | {r.line} | {error_display} |")
    else:
        lines.append("## ✅ All Links Valid")
        lines.append("")
        lines.append(
            f"All {result.total_links} links are valid "
            f"({result.internal_links} internal references, "
            f"{result.ignored_links} ignored)."
        )

    return "\n".join(lines)
