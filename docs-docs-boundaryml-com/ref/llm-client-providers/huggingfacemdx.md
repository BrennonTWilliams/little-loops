---
url: https://docs.boundaryml.com/ref/llm-client-providers/huggingface.mdx
scraped_at: 2026-03-06T01:00:47.236973
filepath: docs-docs-boundaryml-com/ref/llm-client-providers/huggingfacemdx.md
---


***

## title: huggingface

[HuggingFace](https://huggingface.co/) supports the OpenAI client, allowing you to use the
[`openai-generic`](/docs/snippets/clients/providers/openai) provider with an
overridden `base_url`.

See [https://huggingface.co/docs/inference-endpoints/index](https://huggingface.co/docs/inference-endpoints/index) for more information on their Inference Endpoints.

```baml BAML
clientMyClient {
  provider openai-generic
  options {
    base_url "https://api-inference.huggingface.co/v1"
    api_key env.HUGGINGFACE_API_KEY
  }
}
```
