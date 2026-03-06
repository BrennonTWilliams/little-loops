---
url: https://docs.boundaryml.com/ref/llm-client-providers/litellm.mdx
scraped_at: 2026-03-06T01:00:47.512678
filepath: docs-docs-boundaryml-com/ref/llm-client-providers/litellmmdx.md
---


***

## title: litellm

[LiteLLM](https://www.litellm.ai/) supports the OpenAI client, allowing you to use the
[`openai-generic`](/ref/llm-client-providers/openai-generic) provider with an
overridden `base_url`.

See [OpenAI Generic](/ref/llm-client-providers/openai-generic) for more details about parameters.

## Set up

1. Set up [LiteLLM Proxy server](https://docs.litellm.ai/docs/proxy/docker_quick_start#21-start-proxy)

2. Set up LiteLLM Client in BAML files

3. Use it in a BAML function!

```baml BAML
clientMyClient {
  provider "openai-generic"
  options {
    base_url "http://0.0.0.0:4000"
    api_key env.LITELLM_API_KEY
    model "gpt-5"
  }
}
```
