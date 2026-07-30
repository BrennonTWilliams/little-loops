"""Link checker for markdown documentation.

Provides automated verification that links in markdown files are valid.
Supports HTTP/HTTPS URL checking and internal file reference validation.
"""

from __future__ import annotations

import json
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal

# Retry-with-backoff before classifying a transient network failure as
# unreachable (a chunk of "broken" results can be one slow host hit serially).
_RETRY_BACKOFF_SECONDS = 0.2

# Cap on how long a 429 Retry-After (or fallback delay) is allowed to stall a
# single check, so a large/adversarial header value can't stall the run.
_MAX_RETRY_AFTER_SECONDS = 30.0

# Total number of 429 retries allowed across one check_markdown_links() run,
# so a page that 429s on every link can't multiply the run's wall-clock cost.
_DEFAULT_429_RETRY_BUDGET = 50

# Directory names that can never contribute markdown files, regardless of
# scope (default glob or an explicit wider base_dir/files override).
_DENYLISTED_DIR_NAMES = {"node_modules", ".pytest_cache", ".venv", ".git", ".loops", ".ll"}

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


class LinkOutcome(Enum):
    """Classification of an external link check result.

    BROKEN means the host authoritatively said the resource is gone
    (404/410). UNREACHABLE means no usable answer came back (timeout, DNS
    failure, connection reset/refused) - ambient network noise, not a repo
    defect. INDETERMINATE means the host answered but the status reflects
    checker aggressiveness or missing credentials (429/401/403/5xx), not
    evidence the link is dead.
    """

    VALID = "valid"
    BROKEN = "broken"
    UNREACHABLE = "unreachable"
    INDETERMINATE = "indeterminate"
    IGNORED = "ignored"


# Status codes that authoritatively assert the resource is gone.
_BROKEN_STATUS_CODES = {404, 410}

# Status codes that reflect checker aggressiveness or missing credentials,
# not evidence about the link itself.
_INDETERMINATE_STATUS_CODES = {401, 403, 429}


def _classify_http_status(code: int) -> LinkOutcome:
    """Classify a non-2xx/3xx HTTP status into a LinkOutcome tier.

    404/410 -> BROKEN (fatal). 429/401/403/5xx -> INDETERMINATE (reported,
    non-fatal). Any other status defaults to BROKEN.
    """
    if code in _INDETERMINATE_STATUS_CODES or 500 <= code < 600:
        return LinkOutcome.INDETERMINATE
    return LinkOutcome.BROKEN


@dataclass
class LinkResult:
    """Result of checking a single link.

    Attributes:
        url: The URL that was checked
        file: File containing the link
        line: Line number where link appears
        status: Status of the link ("valid", "broken", "unreachable", "ignored", "internal")
        error: Error message if link is broken
        link_text: The link text from markdown [text](url)
        action_severity: Closed-vocabulary action-severity, mirroring
            `doc_counts.CountResult.action_severity`. `auto` means no action is
            needed (valid/internal/ignored links); `mention` means a human
            should review (broken/unreachable links — `ll-check-links` has no
            `--fix` path, so these are surfaced but never silently rewritten);
            `route` means another command owns the repair (named in
            `route_owner`).
        route_owner: Name of the command that owns the repair, set only when
            `action_severity` is `route`.
    """

    url: str
    file: str
    line: int
    status: str
    error: str | None = None
    link_text: str | None = None
    action_severity: Literal["auto", "mention", "route"] = "auto"
    route_owner: str | None = None


@dataclass
class LinkCheckResult:
    """Overall results from link checking.

    Attributes:
        total_links: Total number of links found
        valid_links: Number of valid links
        broken_links: Number of broken links (host answered, said no)
        unreachable_links: Number of unreachable links (timeout, DNS, connection reset -
            ambient network noise, not a repo defect)
        indeterminate_links: Number of links whose status reflects checker
            aggressiveness or missing credentials (429/401/403/5xx) rather
            than evidence the link is dead - reported, not gating
        ignored_links: Number of ignored links
        internal_links: Number of internal file references
        results: List of individual link results
    """

    total_links: int = 0
    valid_links: int = 0
    broken_links: int = 0
    unreachable_links: int = 0
    indeterminate_links: int = 0
    ignored_links: int = 0
    internal_links: int = 0
    results: list[LinkResult] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Check if any broken links were found (unreachable links don't count)."""
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
    # Internal references start with # or ./ or ../
    if url.startswith("#") or url.startswith("./") or url.startswith("../"):
        return True
    # Ends with .md (plain file reference)
    if url.endswith(".md"):
        return True
    # Relative markdown links with anchors (e.g. TROUBLESHOOTING.md#getting-help)
    if ".md#" in url:
        return True
    return False


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


_UNREACHABLE_REASON_TYPES = (TimeoutError, socket.timeout, socket.gaierror, ConnectionError)


def _classify_url_error(reason: object) -> bool:
    """Return True if a urllib.error.URLError reason indicates unreachable (not broken)."""
    return isinstance(reason, _UNREACHABLE_REASON_TYPES)


def _parse_retry_after(headers: object) -> float | None:
    """Parse a numeric-seconds Retry-After header value, if present.

    HTTP-date Retry-After values are not parsed (rare in practice for the
    hosts this checker hits) and fall through to the caller's fallback delay.
    """
    if headers is None:
        return None
    value = headers.get("Retry-After") if hasattr(headers, "get") else None
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _check_url_once(url: str, timeout: int) -> tuple[LinkOutcome, str | None, float | None]:
    """Single-attempt URL check, no retry.

    Returns (outcome, error_message, retry_after_seconds). retry_after_seconds
    is only ever non-None for an INDETERMINATE 429 outcome.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "little-loops-link-checker/1.0"})
        req.get_method = lambda: "HEAD"  # type: ignore[method-assign]

        with urllib.request.urlopen(req, timeout=timeout) as response:
            if 200 <= response.status < 400:
                return LinkOutcome.VALID, None, None
            outcome = _classify_http_status(response.status)
            retry_after = (
                _parse_retry_after(getattr(response, "headers", None))
                if outcome is LinkOutcome.INDETERMINATE
                else None
            )
            return outcome, f"HTTP {response.status}", retry_after

    except urllib.error.HTTPError as e:
        outcome = _classify_http_status(e.code)
        retry_after = (
            _parse_retry_after(getattr(e, "headers", None))
            if outcome is LinkOutcome.INDETERMINATE
            else None
        )
        return outcome, f"HTTP {e.code}", retry_after
    except urllib.error.URLError as e:
        if _classify_url_error(e.reason):
            return LinkOutcome.UNREACHABLE, f"Connection error: {e.reason}", None
        return LinkOutcome.BROKEN, f"Connection error: {e.reason}", None
    except TimeoutError:
        return LinkOutcome.UNREACHABLE, "Timeout", None
    except Exception as e:
        return LinkOutcome.BROKEN, str(e), None


class Retry429Budget:
    """Thread-safe cap on total 429 retries across one check run."""

    def __init__(self, limit: int = _DEFAULT_429_RETRY_BUDGET) -> None:
        self._limit = limit
        self._lock = threading.Lock()
        self._used = 0

    def try_consume(self) -> bool:
        with self._lock:
            if self._used >= self._limit:
                return False
            self._used += 1
            return True


def check_url(url: str, timeout: int = 10) -> tuple[bool, str | None]:
    """Check if a URL is reachable.

    Retries once (with a short backoff) before classifying a transient
    network failure as unreachable, to smooth over one slow host rather than
    reporting every link to it as unreachable.

    Args:
        url: URL to check
        timeout: Request timeout in seconds

    Returns:
        Tuple of (is_valid, error_message). `is_valid` is True only for a
        confirmed-reachable URL; both broken and unreachable outcomes return
        False. Use `check_url_outcome()` to distinguish the two.
    """
    outcome, error = check_url_outcome(url, timeout)
    return outcome is LinkOutcome.VALID, error


def check_url_outcome(
    url: str,
    timeout: int = 10,
    retry_budget: Retry429Budget | None = None,
    retry_on_429: bool = True,
    fallback_retry_delay: float = 5.0,
) -> tuple[LinkOutcome, str | None]:
    """Check a URL and classify the result as VALID, BROKEN, UNREACHABLE, or INDETERMINATE.

    An UNREACHABLE outcome is always retried once. An INDETERMINATE 429 is
    retried once too, honoring the Retry-After header (capped at
    `_MAX_RETRY_AFTER_SECONDS`) or `fallback_retry_delay` when absent, gated
    on `retry_on_429` and on `retry_budget` (a per-run cap; unbounded when
    no budget object is supplied).

    Args:
        url: URL to check
        timeout: Request timeout in seconds
        retry_budget: Optional shared per-run cap on 429 retries
        retry_on_429: Whether to retry a 429 at all (from .mlc.config.json)
        fallback_retry_delay: Delay to use when no Retry-After header is present

    Returns:
        Tuple of (outcome, error_message)
    """
    outcome, error, retry_after = _check_url_once(url, timeout)
    if outcome is LinkOutcome.UNREACHABLE:
        time.sleep(_RETRY_BACKOFF_SECONDS)
        outcome, error, retry_after = _check_url_once(url, timeout)
    elif (
        outcome is LinkOutcome.INDETERMINATE
        and error is not None
        and error.startswith("HTTP 429")
        and retry_on_429
        and (retry_budget is None or retry_budget.try_consume())
    ):
        delay = retry_after if retry_after is not None else fallback_retry_delay
        delay = min(delay, _MAX_RETRY_AFTER_SECONDS)
        time.sleep(delay)
        outcome, error, retry_after = _check_url_once(url, timeout)
    return outcome, error


def _is_denylisted(path: Path, base_dir: Path) -> bool:
    """True if any path component names a directory that can never contribute
    markdown files (vendored deps, tool caches, run artifacts), regardless of
    scope - applies to both the default glob and an explicit files override.
    """
    try:
        rel = path.relative_to(base_dir)
    except ValueError:
        rel = path
    return any(part in _DENYLISTED_DIR_NAMES for part in rel.parts)


def check_markdown_links(
    base_dir: Path,
    ignore_patterns: list[str] | None = None,
    timeout: int = 10,
    verbose: bool = False,
    max_workers: int = 10,
    files: list[Path] | None = None,
) -> LinkCheckResult:
    """Check all markdown files for broken links.

    Args:
        base_dir: Base directory to search
        ignore_patterns: List of regex patterns to ignore
        timeout: Request timeout in seconds
        verbose: Whether to show progress
        max_workers: Maximum concurrent HTTP requests
        files: Explicit file list to check instead of the default doc-scope
            glob (`DEFAULT_DOC_FILES`). Still subject to the directory
            denylist.

    Returns:
        LinkCheckResult with all findings
    """
    if ignore_patterns is None:
        ignore_patterns = DEFAULT_IGNORE_PATTERNS.copy()

    result = LinkCheckResult()
    retry_config = load_retry_config(base_dir)
    retry_budget = Retry429Budget()

    # Find markdown files within the declared documentation scope, never the
    # whole tree - DEFAULT_DOC_FILES globs plus a hard directory denylist so
    # an explicit wider base_dir/files override still can't drag in vendored
    # or generated markdown.
    if files is not None:
        md_files = list(files)
    else:
        md_files = []
        for pattern in DEFAULT_DOC_FILES:
            md_files.extend(base_dir.glob(pattern))
    md_files = [f for f in md_files if not _is_denylisted(f, base_dir)]

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

                # Only check HTTP/HTTPS URLs; treat everything else as internal
                if not url.startswith(("http://", "https://")):
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
                    action_severity="mention",
                )
            )

    # Pass 2: Check HTTP URLs concurrently
    if http_checks:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_meta = {
                executor.submit(
                    check_url_outcome,
                    url,
                    timeout,
                    retry_budget,
                    bool(retry_config["retry_on_429"]),
                    float(retry_config["fallback_retry_delay"]),
                ): (
                    url,
                    link_text,
                    line_num,
                    file_str,
                )
                for url, link_text, line_num, file_str in http_checks
            }

            for future in as_completed(future_to_meta):
                url, link_text, line_num, file_str = future_to_meta[future]
                outcome, error = future.result()

                if outcome is LinkOutcome.VALID:
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
                elif outcome is LinkOutcome.UNREACHABLE:
                    result.unreachable_links += 1
                    result.results.append(
                        LinkResult(
                            url=url,
                            file=file_str,
                            line=line_num,
                            status="unreachable",
                            error=error,
                            link_text=link_text,
                            action_severity="mention",
                        )
                    )
                elif outcome is LinkOutcome.INDETERMINATE:
                    result.indeterminate_links += 1
                    result.results.append(
                        LinkResult(
                            url=url,
                            file=file_str,
                            line=line_num,
                            status="indeterminate",
                            error=error,
                            link_text=link_text,
                            action_severity="mention",
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
                            action_severity="mention",
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


def _parse_delay_string(value: str, default: float) -> float:
    """Parse a duration like "5s" or "500ms" into seconds; `default` on no match."""
    match = re.match(r"^(\d+(?:\.\d+)?)(ms|s)?$", value.strip())
    if not match:
        return default
    amount = float(match.group(1))
    unit = match.group(2) or "s"
    return amount / 1000 if unit == "ms" else amount


def load_retry_config(base_dir: Path) -> dict[str, bool | float]:
    """Load 429 retry tuning from .mlc.config.json's already-declared but
    previously-unread `retryOn429`/`fallbackRetryDelay` keys.

    Args:
        base_dir: Base directory path

    Returns:
        Dict with "retry_on_429" (bool) and "fallback_retry_delay" (float, seconds)
    """
    config: dict[str, bool | float] = {"retry_on_429": True, "fallback_retry_delay": 5.0}

    config_file = base_dir / ".mlc.config.json"
    if not config_file.exists():
        return config

    try:
        with open(config_file) as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return config

    if "retryOn429" in raw:
        config["retry_on_429"] = bool(raw["retryOn429"])
    fallback = raw.get("fallbackRetryDelay")
    if isinstance(fallback, str):
        config["fallback_retry_delay"] = _parse_delay_string(
            fallback, float(config["fallback_retry_delay"])
        )

    return config


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

    elif result.unreachable_links > 0 or result.indeterminate_links > 0:
        if result.unreachable_links > 0:
            lines.append(
                f"⚠ {result.unreachable_links} link(s) unreachable (network - not a broken link):"
            )
            lines.append("")

            for r in result.results:
                if r.status == "unreachable":
                    text_part = f"[{r.link_text}]" if r.link_text else ""
                    lines.append(f"  {text_part}({r.url})")
                    lines.append(f"    at {r.file}:{r.line}")
                    if r.error:
                        lines.append(f"    Error: {r.error}")
                    lines.append("")

        if result.indeterminate_links > 0:
            lines.append(
                f"⚠ {result.indeterminate_links} link(s) indeterminate "
                "(rate-limited/auth-walled/server error - not a confirmed broken link):"
            )
            lines.append("")

            for r in result.results:
                if r.status == "indeterminate":
                    text_part = f"[{r.link_text}]" if r.link_text else ""
                    lines.append(f"  {text_part}({r.url})")
                    lines.append(f"    at {r.file}:{r.line}")
                    if r.error:
                        lines.append(f"    Error: {r.error}")
                    lines.append("")

    else:
        lines.append(
            f"✓ All {result.total_links} link(s) valid! "
            f"({result.internal_links} internal, {result.ignored_links} ignored)"
        )

    if result.has_errors or result.unreachable_links > 0 or result.indeterminate_links > 0:
        lines.append("Summary:")
        lines.append(f"  Total links: {result.total_links}")
        lines.append(f"  Valid: {result.valid_links}")
        lines.append(f"  Broken: {result.broken_links}")
        lines.append(f"  Unreachable: {result.unreachable_links}")
        lines.append(f"  Indeterminate: {result.indeterminate_links}")
        lines.append(f"  Internal refs: {result.internal_links}")
        lines.append(f"  Ignored: {result.ignored_links}")

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
        "unreachable_links": result.unreachable_links,
        "indeterminate_links": result.indeterminate_links,
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
                "action_severity": r.action_severity,
                "route_owner": r.route_owner,
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
    lines.append(f"- **Unreachable**: {result.unreachable_links}")
    lines.append(f"- **Indeterminate**: {result.indeterminate_links}")
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
        lines.append("")

    if result.unreachable_links > 0:
        lines.append("## ⚠️ Unreachable Links (network - not a broken link)")
        lines.append("")
        lines.append("| URL | File | Line | Error |")
        lines.append("|-----|------|------|-------|")

        for r in result.results:
            if r.status == "unreachable":
                url_display = r.url[:60] + "..." if len(r.url) > 60 else r.url
                error_display = r.error or "Unknown"
                lines.append(f"| `{url_display}` | `{r.file}` | {r.line} | {error_display} |")
        lines.append("")

    if result.indeterminate_links > 0:
        lines.append(
            "## ⚠️ Indeterminate Links (rate-limited/auth-walled/server error "
            "- not a confirmed broken link)"
        )
        lines.append("")
        lines.append("| URL | File | Line | Error |")
        lines.append("|-----|------|------|-------|")

        for r in result.results:
            if r.status == "indeterminate":
                url_display = r.url[:60] + "..." if len(r.url) > 60 else r.url
                error_display = r.error or "Unknown"
                lines.append(f"| `{url_display}` | `{r.file}` | {r.line} | {error_display} |")
        lines.append("")

    if not result.has_errors and result.unreachable_links == 0 and result.indeterminate_links == 0:
        lines.append("## ✅ All Links Valid")
        lines.append("")
        lines.append(
            f"All {result.total_links} links are valid "
            f"({result.internal_links} internal references, "
            f"{result.ignored_links} ignored)."
        )

    return "\n".join(lines)
