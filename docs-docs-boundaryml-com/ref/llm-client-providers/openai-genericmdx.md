---
url: https://docs.boundaryml.com/ref/llm-client-providers/openai-generic.mdx
scraped_at: 2026-03-06T01:00:48.959723
filepath: docs-docs-boundaryml-com/ref/llm-client-providers/openai-genericmdx.md
---


***

## title: openai-generic

The `openai-generic` provider supports all APIs that use OpenAI's request and
response formats, such as Groq, HuggingFace, Ollama, OpenRouter, and Together AI.

Example:

```baml BAML
clientMyClient {
  provider "openai-generic"
  options {
    base_url "https://api.provider.com"
    model ""
  }
}
```

A non-exhaustive list of providers you can use with `openai-generic`:

| Inference Provider | Docs                                                             |
| ------------------ | ---------------------------------------------------------------- |
| Azure AI Foundry   | [Azure AI Foundry](/ref/llm-client-providers/azure-ai-foundary)  |
| Cerebras           | [Cerebras](/ref/llm-client-providers/cerebras)                   |
| Groq               | [Groq](/ref/llm-client-providers/groq)                           |
| Hugging Face       | [Hugging Face](/ref/llm-client-providers/huggingface)            |
| Keywords AI        | [Keywords AI](/ref/llm-client-providers/keywordsai)              |
| Llama API          | [Llama API](/ref/llm-client-providers/llama-api)                 |
| Litellm            | [Litellm](/ref/llm-client-providers/litellm)                     |
| LM Studio          | [LM Studio](/ref/llm-client-providers/lmstudio)                  |
| Ollama             | [Ollama](/ref/llm-client-providers/ollama)                       |
| OpenRouter         | [OpenRouter](/ref/llm-client-providers/openrouter)               |
| Vercel AI Gateway  | [Vercel AI Gateway](/ref/llm-client-providers/vercel-ai-gateway) |
| Tinfoil            | [Tinfoil](/ref/llm-client-providers/tinfoil)                     |
| TogetherAI         | [TogetherAI](/ref/llm-client-providers/together)                 |
| Unify AI           | [Unify AI](/ref/llm-client-providers/unify)                      |
| vLLM               | [vLLM](/ref/llm-client-providers/vllm)                           |

## BAML-specific request `options`

These unique parameters (aka `options`)  modify the API request sent to the provider.

You can use this to modify the `headers` and `base_url` for example.The base URL for the API.

  **Default: `https://api.openai.com/v1`**Will be used to build the `Authorization` header, like so: `Authorization: Bearer $api_key`
  If `api_key` is not set, or is set to an empty string, the `Authorization` header will not be sent.

  **Default: ``**Additional headers to send with the request.

  Example:

  ```baml BAML
  clientMyClient {
    provider "openai-generic"
    options {
      base_url "https://api.provider.com"
      model ""
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
  ```Which finish reasons are allowed? **Default: `null`**version 0.73.0 onwards: This is case insensitive.Will raise a `BamlClientFinishReasonError` if the finish reason is not in the allow list. See [Exceptions](/guide/baml-basics/error-handling#bamlclientfinishreasonerror) for more details.

  Note, only one of `finish_reason_allow_list` or `finish_reason_deny_list` can be set.

  For example you can set this to `["stop"]` to only allow the stop finish reason, all other finish reasons (e.g. `length`) will treated as failures that PREVENT fallbacks and retries (similar to parsing errors).

  Then in your code you can use something like:

  ```baml
  clientMyClient {
    provider "openai"
    options {
      model "gpt-5-mini"
      api_key env.OPENAI_API_KEY
      // Finish reason allow list will only allow the stop finish reason
      finish_reason_allow_list ["stop"]
    }
  }
  ```Which finish reasons are denied? **Default: `null`**version 0.73.0 onwards: This is case insensitive.Will raise a `BamlClientFinishReasonError` if the finish reason is in the deny list. See [Exceptions](/guide/baml-basics/error-handling#bamlclientfinishreasonerror) for more details.

  Note, only one of `finish_reason_allow_list` or `finish_reason_deny_list` can be set.

  For example you can set this to `["length"]` to stop the function from continuing if the finish reason is `length`. (e.g. LLM was cut off because it was too long).

  Then in your code you can use something like:

  ```baml
  clientMyClient {
    provider "openai"
    options {
      model "gpt-5-mini"
      api_key env.OPENAI_API_KEY
      // Finish reason deny list will allow all finish reasons except length
      finish_reason_deny_list ["length"]
    }
  }
  ```Please let [us know on Discord](https://www.boundaryml.com/discord) if you have this use case! This is in alpha and we'd like to make sure we continue to cover your use cases.The type of response to return from the client.

  Sometimes you may expect a different response format than the provider default.
  For example, using Azure you may be proxying to an endpoint that returns a different format than the OpenAI default.

  **Default: `openai`**### `media_url_handler`

Controls how media URLs are processed before sending to the provider. This allows you to override the default behavior for handling images, audio, PDFs, and videos.

```baml
clientMyClient {
  provider openai
  options {
    media_url_handler {
      image "send_base64"                    // Options: send_base64 | send_url | send_url_add_mime_type | send_base64_unless_google_url
      audio "send_url"
      pdf "send_url_add_mime_type"
      video "send_url"
    }
  }
}
```

#### Options

Each media type can be configured with one of these modes:

* **`send_base64`** - Always download URLs and convert to base64 data URIs
* **`send_url`** - Pass URLs through unchanged to the provider
* **`send_url_add_mime_type`** - Ensure MIME type is present (may require downloading to detect)
* **`send_base64_unless_google_url`** - Only process non-gs\:// URLs (keep Google Cloud Storage URLs as-is)

#### Provider Defaults

If not specified, each provider uses these defaults:

| Provider     | Image                           | Audio                    | PDF           | Video      |
| ------------ | ------------------------------- | ------------------------ | ------------- | ---------- |
| OpenAI       | `send_url`                      | `send_base64`            | `send_url`    | `send_url` |
| Anthropic    | `send_url`                      | `send_url`               | `send_base64` | `send_url` |
| Google AI    | `send_base64_unless_google_url` | `send_url`               | `send_url`    | `send_url` |
| Vertex AI    | `send_url_add_mime_type`        | `send_url_add_mime_type` | `send_url`    | `send_url` |
| AWS Bedrock  | `send_base64`                   | `send_base64`            | `send_base64` | `send_url` |
| Azure OpenAI | `send_url`                      | `send_base64`            | `send_url`    | `send_url` |

#### When to Use

* **Use `send_base64`** when your provider doesn't support external URLs and you need to embed media content
* **Use `send_url`** when your provider handles URL fetching and you want to avoid the overhead of base64 conversion
* **Use `send_url_add_mime_type`** when your provider requires MIME type information (e.g., Vertex AI)
* **Use `send_base64_unless_google_url`** when working with Google Cloud Storage and want to preserve gs\:// URLsURL fetching happens at request time and may add latency. Consider caching or pre-converting frequently used media when using `send_base64` mode.## Provider request parameters

These are other parameters that are passed through to the provider, without modification by BAML. For example if the request has a `temperature` field, you can define it in the client here so every call has that set.For reasoning models (like `o1` or `o1-mini`), you must use `max_completion_tokens` instead of `max_tokens`.
  Please set `max_tokens` to `null` in order to get this to work.

  See the [OpenAI API documentation](https://platform.openai.com/docs/api-reference/chat/create#chat-create-max_completion_tokens) and [OpenAI Reasoning Docs](https://platform.openai.com/docs/guides/reasoning#controlling-costs) for more details about token handling.

  Example:

  ```baml BAML
  clientOpenAIo1 {
    provider "openai-generic"
    options {
      model "o4-mini"
      max_tokens null
    }
  }
  ```Consult the specific provider's documentation for more information.BAML will auto construct this field for you from the promptBAML will auto construct this field for you based on how you call the client in your codeThe model to use.

  For OpenAI, this might be `"gpt-5-mini"`; for Ollama, this might be `"llama2"`. The exact
  syntax will depend on your API provider's documentation: we'll just forward it to them as-is.For all other options, see the [official OpenAI API documentation](https://platform.openai.com/docs/api-reference/chat/create).
