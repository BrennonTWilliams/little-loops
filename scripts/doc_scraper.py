#!/usr/bin/env python3
"""
Documentation Scraper

A Python script that scrapes documentation sites, discovers all pages,
converts them to Markdown, and organizes them into a mirrored folder structure.

Usage:
    python doc_scraper.py <url> [options]

Example:
    python doc_scraper.py https://manual.raycast.com/mac --verbose
"""

import argparse
import asyncio
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class SitemapNode:
    """Represents a node in the documentation sitemap tree."""

    url: str
    title: str
    children: list["SitemapNode"] = field(default_factory=list)
    depth: int = 0
    is_leaf: bool = True

    def __repr__(self) -> str:
        return f"SitemapNode(title={self.title!r}, url={self.url!r}, children={len(self.children)})"


@dataclass
class ScrapedPage:
    """Represents a scraped page with its content and metadata."""

    url: str
    title: str
    markdown_content: str
    filepath: Path
    depth: int = 0


# =============================================================================
# Error Handler
# =============================================================================


class ScraperErrorHandler:
    """Handles errors during the scraping process."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.errors: list[dict[str, Any]] = []
        self.skipped: list[str] = []
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Set up logging configuration."""
        logger = logging.getLogger("doc_scraper")
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)

        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

    def log_error(self, url: str, error: Exception, context: str = ""):
        """Log an error with context."""
        error_info = {
            "url": url,
            "error": str(error),
            "type": type(error).__name__,
            "context": context,
            "timestamp": datetime.now().isoformat(),
        }
        self.errors.append(error_info)
        self.logger.error(f"{context}: {url} - {error}")

    def log_skipped(self, url: str, reason: str):
        """Log a skipped URL."""
        self.skipped.append(url)
        self.logger.debug(f"Skipped: {url} - {reason}")

    def print_summary(self):
        """Print error summary if verbose mode is enabled."""
        if not self.verbose:
            return

        print("\n" + "=" * 60)
        print("SCRAPER SUMMARY")
        print("=" * 60)

        if self.errors:
            print(f"\n❌ Errors encountered: {len(self.errors)}")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error['url']}")
                print(f"     {error['type']}: {error['error']}")
                if error["context"]:
                    print(f"     Context: {error['context']}")

        if self.skipped:
            print(f"\n⏭️  Skipped URLs: {len(self.skipped)}")
            for url in self.skipped[:10]:  # Show first 10
                print(f"  - {url}")
            if len(self.skipped) > 10:
                print(f"  ... and {len(self.skipped) - 10} more")

        if not self.errors and not self.skipped:
            print("\n✅ No errors or skips!")

        print("=" * 60 + "\n")


# =============================================================================
# Sitemap Discovery
# =============================================================================


class SitemapDiscovery:
    """Discovers the documentation site structure using multiple strategies."""

    def __init__(self, base_url: str, error_handler: ScraperErrorHandler, max_depth: int = 3):
        self.base_url = base_url
        self.base_domain = urlparse(base_url).netloc
        self.error_handler = error_handler
        self.max_depth = max_depth
        self.visited_urls: set[str] = set()
        self.seen_titles: set[str] = set()

    async def discover(self) -> SitemapNode:
        """
        Discover sitemap using multiple strategies.
        Returns root SitemapNode.
        """
        self.error_handler.logger.info(f"Discovering sitemap for {self.base_url}")

        # Strategy 1: Try sitemap.xml
        sitemap = await self._try_sitemap_xml()
        if sitemap:
            return sitemap

        # Strategy 2: Parse HTML navigation
        sitemap = await self._try_html_navigation()
        if sitemap:
            return sitemap

        # Strategy 3: Recursive crawling (fallback)
        self.error_handler.logger.warning(
            "Could not find sitemap.xml or parse navigation. Falling back to recursive crawling."
        )
        return await self._recursive_crawl()

    async def _try_sitemap_xml(self) -> SitemapNode | None:
        """Attempt to parse sitemap.xml from the site."""
        sitemap_urls = [
            urljoin(self.base_url, "/sitemap.xml"),
            urljoin(self.base_url, "/sitemap_index.xml"),
        ]

        for sitemap_url in sitemap_urls:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        sitemap_url, timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        if response.status == 200:
                            content = await response.text()
                            return await self._process_sitemap_content(content, sitemap_url)
            except Exception as e:
                self.error_handler.logger.debug(f"No sitemap.xml found at {sitemap_url}: {e}")

        return None

    async def _process_sitemap_content(self, content: str, sitemap_url: str) -> SitemapNode | None:
        """Process sitemap XML content, following sitemap indexes if needed."""
        try:
            kind, urls = self._parse_sitemap_xml(content)

            if kind == "index":
                self.error_handler.logger.info(
                    f"Found sitemap index with {len(urls)} child sitemaps, fetching all"
                )
                all_page_urls: list[str] = []
                async with aiohttp.ClientSession() as session:
                    for child_url in urls:
                        try:
                            async with session.get(
                                child_url, timeout=aiohttp.ClientTimeout(total=10)
                            ) as resp:
                                if resp.status == 200:
                                    child_content = await resp.text()
                                    child_kind, child_urls = self._parse_sitemap_xml(child_content)
                                    if child_kind == "urlset":
                                        all_page_urls.extend(child_urls)
                        except Exception as e:
                            self.error_handler.logger.debug(
                                f"Failed to fetch child sitemap {child_url}: {e}"
                            )
                if all_page_urls:
                    self.error_handler.logger.info(
                        f"Collected {len(all_page_urls)} URLs from sitemap index"
                    )
                    return self._build_tree_from_urls(all_page_urls)
                return None

            if urls:
                return self._build_tree_from_urls(urls)

        except Exception as e:
            self.error_handler.logger.debug(f"Failed to parse sitemap {sitemap_url}: {e}")

        return None

    def _parse_sitemap_xml(self, content: str) -> tuple[str, list[str]]:
        """
        Parse sitemap XML content.
        Returns (kind, urls) where kind is 'index' or 'urlset'.
        For 'index', urls are child sitemap URLs.
        For 'urlset', urls are page URLs.
        """
        from lxml import etree

        root = etree.fromstring(content.encode())
        ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        if etree.QName(root.tag).localname == "sitemapindex":
            child_urls = [
                loc.text for loc in root.xpath("//ns:sitemap/ns:loc", namespaces=ns) if loc.text
            ]
            return "index", child_urls

        urls = [
            loc[0].text
            for url_elem in root.xpath("//ns:url", namespaces=ns)
            for loc in [url_elem.xpath("ns:loc", namespaces=ns)]
            if loc and loc[0].text
        ]
        return "urlset", urls

    def _build_tree_from_urls(self, urls: list[str]) -> SitemapNode:
        """Build a tree structure from a flat list of URLs."""
        root = SitemapNode(url=self.base_url, title="Root")

        for url in sorted(urls):
            parsed = urlparse(url)
            path_parts = [p for p in parsed.path.split("/") if p]

            # Build title from path
            title = (
                path_parts[-1].replace("-", " ").replace("_", " ").title()
                if path_parts
                else "Index"
            )

            current = root
            current_depth = 0

            for i, part in enumerate(path_parts[:-1]):
                # Find matching child or create new
                found = False
                for child in current.children:
                    if part in child.url:
                        current = child
                        found = True
                        break

                if not found:
                    section_title = part.replace("-", " ").replace("_", " ").title()
                    section_url = urljoin(self.base_url, "/".join(path_parts[: i + 1]) + "/")
                    new_node = SitemapNode(
                        url=section_url, title=section_title, depth=i + 1, is_leaf=False
                    )
                    current.children.append(new_node)
                    current = new_node

                current_depth += 1

            # Add leaf node
            leaf = SitemapNode(url=url, title=title, depth=current_depth + 1, is_leaf=True)
            current.children.append(leaf)

        return root

    async def _try_html_navigation(self) -> SitemapNode | None:
        """Attempt to parse HTML navigation elements."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.base_url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        return None

                    html = await response.text()
                    soup = BeautifulSoup(html, "lxml")

                    # Try common navigation selectors
                    selectors = [
                        "nav",
                        "[role='navigation']",
                        ".sidebar",
                        ".navigation",
                        "#sidebar",
                        "aside",
                        ".menu",
                        "[class*='nav']",
                        "[id*='nav']",
                    ]

                    links: list[Any] = []
                    for selector in selectors:
                        nav = soup.select_one(selector)
                        if nav:
                            links.extend(nav.find_all("a", href=True))
                            if len(links) > 5:  # Found a decent navigation
                                break
                            links = []

                    if links:
                        return self._build_tree_from_html_links(links)

        except Exception as e:
            self.error_handler.logger.debug(f"Failed to parse HTML navigation: {e}")

        return None

    def _build_tree_from_html_links(self, links) -> SitemapNode:
        """Build a tree from HTML navigation links."""
        urls = set()
        for link in links:
            href = link.get("href")
            if not href:
                continue

            full_url = urljoin(self.base_url, href)

            # Only include same-domain links
            if urlparse(full_url).netloc != self.base_domain:
                continue

            # Skip common non-content links
            if any(
                pattern in full_url.lower()
                for pattern in [
                    "api",
                    "auth",
                    "login",
                    "logout",
                    "account",
                    "search",
                    "feed",
                    "rss",
                    "tag",
                    "category",
                    ".pdf",
                    ".zip",
                    "github",
                    "twitter",
                    "discord",
                    "slack",
                ]
            ):
                continue

            urls.add(full_url)

        # Add base URL
        urls.add(self.base_url)

        return self._build_tree_from_urls(sorted(urls))

    async def _recursive_crawl(self) -> SitemapNode:
        """Recursively crawl the site to discover pages."""
        root = SitemapNode(url=self.base_url, title="Root")

        async with aiohttp.ClientSession() as session:
            await self._crawl_page(self.base_url, root, session, depth=0)

        return root

    async def _crawl_page(
        self, url: str, parent: SitemapNode, session: aiohttp.ClientSession, depth: int
    ):
        """Recursively crawl a page and its links."""
        if url in self.visited_urls or depth >= self.max_depth:
            return

        self.visited_urls.add(url)

        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return

                html = await response.text()
                soup = BeautifulSoup(html, "lxml")

                # Get page title
                title_tag = soup.find("title")
                title = (
                    title_tag.get_text() if title_tag else Path(urlparse(url).path).name or "Index"
                )

                # Create node
                node = SitemapNode(url=url, title=title.strip(), depth=depth)
                parent.children.append(node)

                # Find links
                for link in soup.find_all("a", href=True):
                    href = link.get("href")
                    if not isinstance(href, str):
                        continue

                    full_url = urljoin(url, href)

                    # Only crawl same-domain links
                    if urlparse(full_url).netloc != self.base_domain:
                        continue

                    # Skip anchors and non-content
                    if full_url.startswith("#") or any(
                        ext in full_url for ext in [".pdf", ".zip", ".jpg", ".png"]
                    ):
                        continue

                    await self._crawl_page(full_url, node, session, depth + 1)

        except Exception as e:
            self.error_handler.log_error(url, e, "during recursive crawl")


# =============================================================================
# Folder Structure Builder
# =============================================================================


class FolderStructureBuilder:
    """Builds the mirrored folder structure from the sitemap."""

    def __init__(self, base_url: str, output_dir: Path, error_handler: ScraperErrorHandler):
        self.base_url = base_url
        self.output_dir = output_dir
        self.error_handler = error_handler
        self.url_to_filepath: dict[str, Path] = {}

    def build(self, sitemap: SitemapNode) -> Path:
        """Build folder structure from sitemap. Returns root directory path."""
        # Extract subject name from URL
        subject_name = self._extract_subject_name()
        root_dir = self.output_dir / subject_name

        self.error_handler.logger.info(f"Creating output directory: {root_dir}")

        # Build structure
        self._build_node(sitemap, root_dir)

        return root_dir

    def _extract_subject_name(self) -> str:
        """Extract a subject name from the base URL."""
        parsed = urlparse(self.base_url)
        domain = parsed.netloc

        # Convert domain to folder name
        name = domain.replace(".", "-")
        name = re.sub(r"[^a-z0-9-]", "", name.lower())

        return f"docs-{name}"

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string for use as a filename."""
        # Remove special characters, replace spaces with hyphens
        name = name.lower()
        name = re.sub(r"[^\w\s-]", "", name)
        name = re.sub(r"[\s_]+", "-", name)
        name = name.strip("-")

        # Limit length
        if len(name) > 100:
            name = name[:97] + "..."

        return name or "index"

    def _build_node(self, node: SitemapNode, parent_dir: Path, is_root: bool = False):
        """Recursively build directory structure for a node."""
        if is_root:
            # Root node becomes index.md in the root directory
            filepath = parent_dir / "index.md"
            self.url_to_filepath[node.url] = filepath
        elif node.is_leaf or not node.children:
            # Leaf node becomes a .md file
            filename = self._sanitize_filename(node.title) + ".md"
            filepath = parent_dir / filename
            self.url_to_filepath[node.url] = filepath
        else:
            # Non-leaf node becomes a subdirectory with index.md
            dir_name = self._sanitize_filename(node.title)
            child_dir = parent_dir / dir_name
            filepath = child_dir / "index.md"
            self.url_to_filepath[node.url] = filepath
            parent_dir = child_dir

        # Create directory if needed
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Process children
        for child in node.children:
            self._build_node(child, parent_dir, is_root=False)


# =============================================================================
# Page Processor
# =============================================================================


class PageProcessor:
    """Processes pages: scrapes, converts to Markdown, and writes files."""

    def __init__(self, error_handler: ScraperErrorHandler, concurrent: int = 3, timeout: int = 30):
        self.error_handler = error_handler
        self.concurrent = concurrent
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(concurrent)
        self.markitdown = self._init_markitdown()
        self.crawler = None

    def _init_markitdown(self):
        """Initialize MarkItDown converter."""
        try:
            from markitdown import MarkItDown

            return MarkItDown()
        except ImportError:
            self.error_handler.logger.warning(
                "MarkItDown not available. Using simple HTML conversion."
            )
            return None

    async def process_pages(self, url_to_filepath: dict[str, Path]) -> list[ScrapedPage]:
        """Process all pages concurrently."""
        self.error_handler.logger.info(
            f"Processing {len(url_to_filepath)} pages with {self.concurrent} workers"
        )

        # Initialize shared crawler instance for all pages
        try:
            from crawl4ai import AsyncWebCrawler

            crawler = AsyncWebCrawler(verbose=False)
            await crawler.start()
            self.crawler = crawler
        except ImportError:
            self.error_handler.logger.debug("crawl4ai not available, using simple HTTP")
            self.crawler = None

        tasks = [
            self._process_single_page(url, filepath) for url, filepath in url_to_filepath.items()
        ]

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            # Ensure crawler is properly closed
            if self.crawler:
                try:
                    await self.crawler.close()
                except Exception as e:
                    self.error_handler.logger.warning(f"Error closing crawler: {e}")

        # Filter out exceptions
        pages = []
        for result in results:
            if isinstance(result, Exception):
                self.error_handler.logger.error(f"Task failed: {result}")
            elif isinstance(result, ScrapedPage):
                pages.append(result)

        return pages

    async def _process_single_page(self, url: str, filepath: Path) -> ScrapedPage | None:
        """Process a single page."""
        async with self.semaphore:
            try:
                self.error_handler.logger.debug(f"Processing: {url}")

                # Scrape page
                html = await self._scrape_page(url)

                if not html:
                    self.error_handler.log_skipped(url, "No content retrieved")
                    return None

                # Convert to Markdown
                markdown = self._convert_to_markdown(html, url)

                # Add frontmatter
                markdown = self._add_frontmatter(markdown, url, filepath)

                # Write file
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(markdown, encoding="utf-8")

                self.error_handler.logger.debug(f"✓ Wrote: {filepath}")

                # Extract title from first heading or filename
                title = self._extract_title(markdown, filepath)

                return ScrapedPage(
                    url=url, title=title, markdown_content=markdown, filepath=filepath
                )

            except Exception as e:
                self.error_handler.log_error(url, e, "during page processing")
                return None

    async def _scrape_page(self, url: str) -> str | None:
        """Scrape a page using the shared crawler instance."""
        if self.crawler:
            try:
                result = await self.crawler.arun(
                    url=url,
                    timeout=self.timeout * 1000,
                    bypass_cache=True,
                )

                if result.success:
                    return result.html
                else:
                    self.error_handler.logger.warning(
                        f"Crawl failed for {url}: {result.error_message}"
                    )
                    return await self._simple_fetch(url)

            except Exception as e:
                self.error_handler.logger.debug(f"crawl4ai failed, using fallback: {e}")
                return await self._simple_fetch(url)

        # Fallback to simple HTTP request
        return await self._simple_fetch(url)

    async def _simple_fetch(self, url: str) -> str | None:
        """Simple HTTP fetch as fallback."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        return await response.text()
        except Exception as e:
            self.error_handler.logger.error(f"HTTP fetch failed for {url}: {e}")

        return None

    def _convert_to_markdown(self, html: str, url: str) -> str:
        """Convert HTML to Markdown using MarkItDown."""
        if self.markitdown:
            try:
                result = self.markitdown.convert_string(html)
                return result.text_content
            except Exception as e:
                self.error_handler.logger.debug(f"MarkItDown conversion failed: {e}")

        # Fallback: simple HTML to Markdown conversion
        return self._simple_html_to_markdown(html)

    def _simple_html_to_markdown(self, html: str) -> str:
        """Simple HTML to Markdown conversion as fallback."""
        soup = BeautifulSoup(html, "lxml")

        # Remove scripts and styles
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        # Convert elements
        lines = []

        for element in soup.find_all(True):
            text = element.get_text(strip=True)
            if not text:
                continue

            tag_name = element.name

            if tag_name == "h1":
                lines.append(f"\n# {text}\n")
            elif tag_name == "h2":
                lines.append(f"\n## {text}\n")
            elif tag_name == "h3":
                lines.append(f"\n### {text}\n")
            elif tag_name == "h4":
                lines.append(f"\n#### {text}\n")
            elif tag_name == "p":
                lines.append(f"\n{text}\n")
            elif tag_name in ("ul", "ol"):
                lines.append(f"\n{text}\n")
            elif tag_name == "code":
                lines.append(f"`{text}`")
            elif tag_name == "pre":
                lines.append(f"\n```\n{text}\n```\n")
            elif tag_name == "a":
                href = element.get("href", "")
                lines.append(f"[{text}]({href})")

        return "\n".join(lines)

    def _add_frontmatter(self, markdown: str, url: str, filepath: Path) -> str:
        """Add YAML frontmatter to the markdown."""
        frontmatter = f"""---
url: {url}
scraped_at: {datetime.now().isoformat()}
filepath: {filepath.relative_to(filepath.anchor)}
---

"""
        return frontmatter + markdown

    def _extract_title(self, markdown: str, filepath: Path) -> str:
        """Extract title from markdown or use filename."""
        # Try to find first heading
        match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
        if match:
            return match.group(1).strip()

        # Fall back to filename
        return filepath.stem.replace("-", " ").replace("_", " ").title()


# =============================================================================
# Main Scraper Class
# =============================================================================


class DocumentationScraper:
    """Main coordinator for the documentation scraping process."""

    def __init__(
        self,
        base_url: str,
        output_dir: Path = Path("./"),
        verbose: bool = False,
        max_depth: int = 3,
        concurrent: int = 5,
        timeout: int = 30,
        sitemap_only: bool = False,
    ):
        self.base_url = base_url
        self.output_dir = Path(output_dir)
        self.verbose = verbose
        self.max_depth = max_depth
        self.concurrent = concurrent
        self.timeout = timeout
        self.sitemap_only = sitemap_only

        self.error_handler = ScraperErrorHandler(verbose=verbose)

    async def run(self) -> int:
        """Run the scraper. Returns exit code."""
        try:
            # Validate URL
            parsed = urlparse(self.base_url)
            if not parsed.scheme or not parsed.netloc:
                self.error_handler.logger.error(f"Invalid URL: {self.base_url}")
                return 1

            self.error_handler.logger.info(f"Starting documentation scraper for: {self.base_url}")

            # Step 1: Discover sitemap
            discovery = SitemapDiscovery(self.base_url, self.error_handler, self.max_depth)
            sitemap = await discovery.discover()

            if self.verbose:
                self._print_sitemap(sitemap)

            if self.sitemap_only:
                self.error_handler.logger.info("Sitemap discovery only. Exiting.")
                return 0

            # Step 2: Build folder structure
            builder = FolderStructureBuilder(self.base_url, self.output_dir, self.error_handler)
            root_dir = builder.build(sitemap)

            self.error_handler.logger.info(f"Output directory: {root_dir}")
            self.error_handler.logger.info(f"Discovered {len(builder.url_to_filepath)} pages")

            # Step 3: Process pages
            processor = PageProcessor(self.error_handler, self.concurrent, self.timeout)
            pages = await processor.process_pages(builder.url_to_filepath)

            self.error_handler.logger.info(f"Successfully processed {len(pages)} pages")

            # Print summary
            self.error_handler.print_summary()

            return 0

        except KeyboardInterrupt:
            self.error_handler.logger.info("\nInterrupted by user")
            return 130
        except Exception as e:
            self.error_handler.logger.error(f"Fatal error: {e}")
            return 1

    def _print_sitemap(self, node: SitemapNode, prefix: str = "", is_last: bool = True):
        """Print the sitemap as a tree structure."""
        connector = "└── " if is_last else "├── "
        print(f"{prefix}{connector}{node.title} ({node.url})")

        children = node.children
        for i, child in enumerate(children):
            is_last_child = i == len(children) - 1
            extension = "    " if is_last else "│   "
            self._print_sitemap(child, prefix + extension, is_last_child)


# =============================================================================
# CLI Interface
# =============================================================================


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Scrape documentation sites and convert to Markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://manual.raycast.com/mac
  %(prog)s https://docs.python.org/3 --verbose --output ./python-docs
  %(prog)s https://manual.raycast.com/mac --sitemap-only
        """,
    )

    parser.add_argument("url", help="Documentation site URL to scrape")

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show sitemap and detailed progress"
    )

    parser.add_argument(
        "-o", "--output", type=Path, default=Path("./"), help="Output directory (default: ./)"
    )

    parser.add_argument("--max-depth", type=int, default=3, help="Maximum crawl depth (default: 3)")

    parser.add_argument(
        "--concurrent",
        type=int,
        default=3,
        help="Number of concurrent page processors (default: 3)",
    )

    parser.add_argument(
        "--timeout", type=int, default=30, help="Page load timeout in seconds (default: 30)"
    )

    parser.add_argument(
        "--sitemap-only",
        action="store_true",
        help="Only discover and display sitemap, don't scrape",
    )

    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()

    scraper = DocumentationScraper(
        base_url=args.url,
        output_dir=args.output,
        verbose=args.verbose,
        max_depth=args.max_depth,
        concurrent=args.concurrent,
        timeout=args.timeout,
        sitemap_only=args.sitemap_only,
    )

    exit_code = await scraper.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
