---
url: https://docs.boundaryml.com/ref/editor-extension-settings/baml-cli-path.mdx
scraped_at: 2026-03-06T01:00:45.025532
filepath: docs-docs-boundaryml-com/ref/editor-extension-settings/baml-cli-pathmdx.md
---


| Type             | Value |
| ---------------- | ----- |
| `string \| null` | null  |

If set, all generated code will use this instead of the packaged generator shipped with the extension.We recommend this setting! This prevents mismatches between the VSCode Extension and the installed BAML package.## Usage

If you use unix, you can run `where baml-cli` in your project to figure out what the path is.

```json settings.json
{
  "baml.cliPath": "/path/to/baml-cli"
}
```
