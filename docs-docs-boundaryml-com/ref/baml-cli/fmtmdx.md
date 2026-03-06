---
url: https://docs.boundaryml.com/ref/baml-cli/fmt.mdx
scraped_at: 2026-03-06T01:00:36.239800
filepath: docs-docs-boundaryml-com/ref/baml-cli/fmtmdx.md
---


The `fmt` command will format your BAML files.**Warning: Beta Feature**

  This feature is still in-progress, and does not yet support all BAML syntax.## Usage

```
baml-cli fmt [OPTIONS] [file.baml] [file2.baml] [file3.baml] ...
```

## Details

To disable the formatter in a file, you can add

```baml
// baml-format: ignore
```

anywhere in the file.

Formatting is done in-place and non-configurable.
