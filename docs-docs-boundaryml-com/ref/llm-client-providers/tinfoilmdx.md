---
url: https://docs.boundaryml.com/ref/llm-client-providers/tinfoil.mdx
scraped_at: 2026-03-06T01:00:49.258627
filepath: docs-docs-boundaryml-com/ref/llm-client-providers/tinfoilmdx.md
---


***

## title: Tinfoil

[Tinfoil](https://tinfoil.sh/) is verifiably private AI inference.

Tinfoil supports the OpenAI client, allowing you
to use the [`openai-generic`](/docs/snippets/clients/providers/openai) provider
with an overridden `base_url`.

```baml
clientTinfoilDeepSeek {
  provider openai-generic
  retry_policy Exponential
  options {
    base_url "https://deepseek-r1-70b-p.model.tinfoil.sh/v1"
    model "deepseek-r1-70b"
    api_key env.TINFOIL_API_KEY
  }
}
```
