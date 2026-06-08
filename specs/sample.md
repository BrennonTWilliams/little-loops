# mdcheck — Markdown Link Checker

## Overview

`mdcheck` is a command-line tool that scans Markdown files for broken hyperlinks and
anchor references. It reports dead links with file paths and line numbers, produces
exit codes suitable for CI pipelines, and supports an ignore list to skip known-offline
or intentionally unreachable URLs.

## Core Features

- **Recursive file scan** — accept a directory path and walk all `.md` files recursively;
  also accept a single file path for targeted checks
- **HTTP link validation** — make HEAD requests (with GET fallback) and flag non-2xx or
  network-error responses as broken
- **Anchor reference check** — verify `[text](#anchor)` references resolve to a heading
  within the same file or across the scanned tree
- **Parallel validation** — validate links concurrently with a configurable worker pool
  (default: 8 workers) to keep runtimes short on large doc trees
- **CI-friendly exit codes** — exit 0 when all links are valid; exit 1 when any broken
  link is found, with a summary line count for easy shell gating
- **Ignore list** — support a `.mdcheck-ignore` file (one glob or URL pattern per line)
  so known-bad or intentionally offline links do not cause failures

## Non-Goals

- Does not rewrite or fix broken links automatically (a `--fix` mode is out of scope)
- Does not validate relative file paths (only URL and anchor references)
- Does not support non-Markdown file types

## Acceptance Criteria

- Running `mdcheck ./docs` on a directory containing a file with a broken HTTP link exits
  1 and prints the file path, line number, and URL for each broken link
- Running `mdcheck ./docs` on a directory where all links are valid exits 0 and prints
  "All links OK (N checked)"
- A link matched by a pattern in `.mdcheck-ignore` is skipped and does not cause a
  non-zero exit code or appear in the broken-link report
