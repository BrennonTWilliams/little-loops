---
url: https://docs.boundaryml.com/ref/llm-client-providers/ollama.mdx
scraped_at: 2026-03-06T01:00:48.233544
filepath: docs-docs-boundaryml-com/ref/llm-client-providers/ollamamdx.md
---


***

## title: ollama

[Ollama](https://ollama.com/) supports the OpenAI client, allowing you to use the
[`openai-generic`](/docs/snippets/clients/providers/openai) provider with an
overridden `base_url`.Note that to call Ollama, you must use its OpenAI-compatible
  `/v1` endpoint. See [Ollama's OpenAI compatibility
  documentation](https://ollama.com/blog/openai-compatibility).You can try out BAML with Ollama at promptfiddle.com, by running 

  `OLLAMA_ORIGINS='*' ollama serve`

  . Learn more in 

  [here](https://www.boundaryml.com/blog/ollama-structured-output)```baml BAML
clientMyClient {
  provider "openai-generic"
  options {
    base_url "http://localhost:11434/v1"
    model llama3
  }
}
```

## BAML-specific request `options`

These unique parameters (aka `options`)  modify the API request sent to the provider.

You can use this to modify the `headers` and `base_url` for example.The base URL for the API. **Default: `http://localhost:11434/v1`**Note the `/v1` at the end of the URL. See [Ollama's OpenAI compatability](https://ollama.com/blog/openai-compatibility)Additional headers to send with the request.

  Example:

  ```baml BAML
  clientMyClient {
    provider ollama
    options {
      model "llama3"
      headers {
        "X-My-Header" "my-value"
      }
    }
  }
  ```The role to use if the role is not in the allowed\_roles. **Default: `"user"` usually, but some models like OpenAI's `gpt-5` will use `"system"`**

  Picked the first role in `allowed_roles` if not "user", otherwise "user".Which roles should we forward to the API? **Default: `["system", "user", "assistant"]` usually, but some models like OpenAI's `o1-mini` will use `["user", "assistant"]`**

  When building prompts, any role not in this list will be set to the `default_role`.A mapping to transform role names before sending to the API. **Default: `{}`** (no remapping)

  For google-ai provider, the default is: `{ "assistant": "model" }`

  This allows you to use standard role names in your prompts (like "user", "assistant", "system") but send different role names to the API. The remapping happens after role validation and default role assignment.

  **Example:**

  ```json
  {
    "user": "human",
    "assistant": "ai",
  }
  ```

  With this configuration, `{{ _.role("user") }}` in your prompt will result in a message with role "human" being sent to the API.Which role metadata should we forward to the API? **Default: `[]`**

  For example you can set this to `["foo", "bar"]` to forward the cache policy to the API.

  If you do not set `allowed_role_metadata`, we will not forward any role metadata to the API even if it is set in the prompt.

  Then in your prompt you can use something like:

  ```baml
  clientFoo {
    provider openai
    options {
      allowed_role_metadata: ["foo", "bar"]
    }
  }

  clientFooWithout {
    provider openai
    options {
    }
  }
  template_string Foo() #"
    {{ _.role('user', foo={"type": "ephemeral"}, bar="1", cat=True) }}
    This will be have foo and bar, but not cat metadata. But only for Foo, not FooWithout.
    {{ _.role('user') }}
    This will have none of the role metadata for Foo or FooWithout.
  "#
  ```

  You can use the playground to see the raw curl request to see what is being sent to the API.Whether the internal LLM client should use the streaming API. **Default: `true`**

  Then in your prompt you can use something like:

  ```baml
  clientMyClientWithoutStreaming {
    provider anthropic
    options {
      model claude-3-5-haiku-20241022
      api_key env.ANTHROPIC_API_KEY
      max_tokens 1000
      supports_streaming false
    }
  }

  function MyFunction() -> string {
    client MyClientWithoutStreaming
    prompt #"Write a short story"#
  }
  ```

  ```python
  # This will be streamed from your python code perspective, 
  # but under the hood it will call the non-streaming HTTP API
  # and then return a streamable response with a single event
  b.stream.MyFunction()

  # This will work exactly the same as before
  b.MyFunction()
  ```## Provider request parameters

These are other parameters that are passed through to the provider, without modification by BAML. For example if the request has a `temperature` field, you can define it in the client here so every call has that set.

Consult the specific provider's documentation for more information.BAML will auto construct this field for you from the promptBAML will auto construct this field for you based on how you call the client in your codeThe model to use.

  | Model      | Description                                                                                                     |
  | ---------- | --------------------------------------------------------------------------------------------------------------- |
  | `llama4`   | Meta Llama 4: Latest generation with enhanced reasoning capabilities                                            |
  | `llama3.3` | Meta Llama 3.3: Enhanced version with improved performance                                                      |
  | `llama3`   | Meta Llama 3: The most capable openly available LLM to date                                                     |
  | `qwen2`    | Qwen2 is a new series of large language models from Alibaba group                                               |
  | `phi3`     | Phi-3 is a family of lightweight 3B (Mini) and 14B (Medium) state-of-the-art open models by Microsoft           |
  | `aya`      | Aya 23, released by Cohere, is a new family of state-of-the-art, multilingual models that support 23 languages. |
  | `mistral`  | The 7B model released by Mistral AI, updated to version 0.3.                                                    |
  | `gemma`    | Gemma is a family of lightweight, state-of-the-art open models built by Google DeepMind. Updated to version 1.1 |
  | `mixtral`  | A set of Mixture of Experts (MoE) model with open weights by Mistral AI in 8x7b and 8x22b parameter sizes.      |

  For the most up-to-date list of models supported by Ollama, see their [Model Library](https://ollama.com/library).To use a specific version you would do: 

    `"mixtral:8x22b"`
