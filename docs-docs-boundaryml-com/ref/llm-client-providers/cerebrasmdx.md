---
url: https://docs.boundaryml.com/ref/llm-client-providers/cerebras.mdx
scraped_at: 2026-03-06T01:00:46.462011
filepath: docs-docs-boundaryml-com/ref/llm-client-providers/cerebrasmdx.md
---


***

## title: Cerebras

[Cerebras](https://inference-docs.cerebras.ai/resources/openai) supports the OpenAI client, allowing you to use the
[`openai-generic`](/ref/llm-client-providers/openai-generic) provider with an
overridden `base_url`.

See [OpenAI Generic](/ref/llm-client-providers/openai-generic) for more details about parameters.

**Example:**

```baml BAML
clientCerebrasLlama {
  provider "openai-generic"
  options {
    base_url "https://api.cerebras.ai/v1"
    api_key env.CEREBRAS_API_KEY
    model "llama-3.3-70b"
  }
}
```
