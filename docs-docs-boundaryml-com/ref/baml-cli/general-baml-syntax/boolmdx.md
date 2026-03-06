---
url: https://docs.boundaryml.com/ref/baml/general-baml-syntax/bool.mdx
scraped_at: 2026-03-06T01:00:38.172227
filepath: docs-docs-boundaryml-com/ref/baml-cli/general-baml-syntax/boolmdx.md
---


`true` or `false`

## Usage

```baml
function CreateStory(long: bool) -> string {
    client "openai/gpt-5-mini"
    prompt #"
        Write a story that is {{ "10 paragraphs" if long else "1 paragraph" }} long.
    "#
}

test LongStory {
    functions [CreateStory]
    args { long true }
}

test ShortStory {
    functions [CreateStory]
    args { long false }
}
```
