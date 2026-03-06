---
url: https://docs.boundaryml.com/ref/llm-client-providers/vllm.mdx
scraped_at: 2026-03-06T01:00:49.799546
filepath: docs-docs-boundaryml-com/ref/llm-client-providers/vllmmdx.md
---


***

## title: vLLM

[vLLM](https://docs.vllm.ai/) supports the OpenAI client, allowing you
to use the [`openai-generic`](/docs/snippets/clients/providers/openai) provider
with an overridden `base_url`.

See [https://docs.vllm.ai/en/latest/serving/openai\_compatible\_server.html](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html) for more information.

```baml BAML
clientMyClient {
  provider "openai-generic"
  options {
    base_url "http://localhost:8000/v1"
    api_key "token-abc123"
    model "NousResearch/Meta-Llama-3-8B-Instruct"
    default_role "user" // Required for using VLLM
  }
}
```
