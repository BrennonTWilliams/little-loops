---
url: https://docs.boundaryml.com/ref/baml_client/react-next-js/
scraped_at: 2026-03-06T01:00:43.747921
filepath: docs-docs-boundaryml-com/ref/baml-client/react-next-js/index.md
---

[Home](/home)
[Guide](/guide/introduction/what-is-baml)
[Examples](/examples/interactive-examples)
[BAML Reference](/ref/overview)
[Playground](https://promptfiddle.com/)
[Agents.md](/agents-md/claude-code)
[Changelog](/changelog/changelog)

Overviewbaml-cliinitgeneratetestservedevfmtLanguage ReferenceGeneral BAML SyntaxTypesfunctiontesttemplate_stringclient<llm>classenumgeneratorGenerated baml_clientwith_options(..)AbortSignal / CancellationCollectorlogging / env varsAsyncClient / SyncClientTypeBuilderClientRegistryclient OptionOnTickMultimodalImageAudioPdfVideoErrorsReact/Next.jsAttributesWhat are attributes?@alias / @@alias@description / @@description@skip@assert@checkJinja in Attributes@@dynamicLLM Client ProvidersOverviewAWS BedrockAnthropicGoogle AI: GeminiGoogle: VertexOpenAIOpenAI Responses APIOpenAI from AzureOpenRouteropenai-genericMicrosoft Foundry (openai-generic)Cerebras (openai-generic)Groq (openai-generic)Hugging Face (openai-generic)Keywords AI (openai-generic)Llama API (openai-generic)Litellm (openai-generic)LM Studio (openai-generic)Ollama (openai-generic)Vercel AI Gateway (openai-generic)Tinfoil (openai-generic)TogetherAI (openai-generic)Unify AI (openai-generic)vLLM (openai-generic)LLM Client StrategiesTimeout ConfigurationRetry PolicyFallbackRound RobinPrompt SyntaxWhat is jinja?Jinja Filtersctx.output_formatctx.client_.roleVariablesConditionalsLoopsEditor Extension Settingsbaml.cliPathbaml.generateCodeOnSavebaml.enablePlaygroundProxybaml.syncExtensionToGeneratorVersion


Overview

[Overview](/ref/overview)

initgeneratetestservedevfmt

[init](/ref/baml-cli/init)
[generate](/ref/baml-cli/generate)
[test](/ref/baml-cli/test)
[serve](/ref/baml-cli/serve)
[dev](/ref/baml-cli/dev)
[fmt](/ref/baml-cli/fmt)

General BAML SyntaxTypesfunctiontesttemplate_stringclient<llm>classenumgenerator

[Types](/ref/baml/types)
[function](/ref/baml/function)
[test](/ref/baml/test)
[template_string](/ref/baml/template-string)
[client<llm>](/ref/baml/client-llm)
[class](/ref/baml/class)
[enum](/ref/baml/enum)
[generator](/ref/baml/generator)

with_options(..)AbortSignal / CancellationCollectorlogging / env varsAsyncClient / SyncClientTypeBuilderClientRegistryclient OptionOnTickMultimodalImageAudioPdfVideoErrorsReact/Next.js

[with_options(..)](/ref/baml_client/with-options)
[AbortSignal / Cancellation](/ref/baml_client/abort-signal)
[Collector](/ref/baml_client/collector)
[logging / env vars](/ref/baml_client/config)
[AsyncClient / SyncClient](/ref/baml_client/client)
[TypeBuilder](/ref/baml_client/type-builder)
[ClientRegistry](/ref/baml_client/client-registry)
[client Option](/ref/baml_client/client-option)
[OnTick](/ref/baml_client/on-tick)
[Multimodal](/ref/baml_client/media)
[Image](/ref/baml_client/image)
[Audio](/ref/baml_client/audio)
[Pdf](/ref/baml_client/pdf)
[Video](/ref/baml_client/video)

What are attributes?@alias / @@alias@description / @@description@skip@assert@checkJinja in Attributes@@dynamic

[What are attributes?](/ref/attributes/what-are-attributes)
[@alias / @@alias](/ref/attributes/alias)
[@description / @@description](/ref/attributes/description)
[@skip](/ref/attributes/skip)
[@assert](/ref/attributes/assert)
[@check](/ref/attributes/check)
[Jinja in Attributes](/ref/attributes/jinja-in-attributes)
[@@dynamic](/ref/attributes/dynamic)

OverviewAWS BedrockAnthropicGoogle AI: GeminiGoogle: VertexOpenAIOpenAI Responses APIOpenAI from AzureOpenRouteropenai-genericMicrosoft Foundry (openai-generic)Cerebras (openai-generic)Groq (openai-generic)Hugging Face (openai-generic)Keywords AI (openai-generic)Llama API (openai-generic)Litellm (openai-generic)LM Studio (openai-generic)Ollama (openai-generic)Vercel AI Gateway (openai-generic)Tinfoil (openai-generic)TogetherAI (openai-generic)Unify AI (openai-generic)vLLM (openai-generic)

[Overview](/ref/llm-client-providers/overview)
[AWS Bedrock](/ref/llm-client-providers/aws-bedrock)
[Anthropic](/ref/llm-client-providers/anthropic)
[Google AI: Gemini](/ref/llm-client-providers/google-ai-gemini)
[Google: Vertex](/ref/llm-client-providers/google-vertex)
[OpenAI](/ref/llm-client-providers/open-ai)
[OpenAI Responses API](/ref/llm-client-providers/open-ai-responses-api)
[OpenAI from Azure](/ref/llm-client-providers/open-ai-from-azure)
[OpenRouter](/ref/llm-client-providers/openrouter)
[openai-generic](/ref/llm-client-providers/openai-generic)
[Microsoft Foundry (openai-generic)](/ref/llm-client-providers/microsoft-foundry)
[Cerebras (openai-generic)](/ref/llm-client-providers/cerebras)
[Groq (openai-generic)](/ref/llm-client-providers/groq)
[Hugging Face (openai-generic)](/ref/llm-client-providers/huggingface)
[Keywords AI (openai-generic)](/ref/llm-client-providers/keywordsai)
[Llama API (openai-generic)](/ref/llm-client-providers/llama-api)
[Litellm (openai-generic)](/ref/llm-client-providers/litellm)
[LM Studio (openai-generic)](/ref/llm-client-providers/lmstudio)
[Ollama (openai-generic)](/ref/llm-client-providers/ollama)
[Vercel AI Gateway (openai-generic)](/ref/llm-client-providers/vercel-ai-gateway)
[Tinfoil (openai-generic)](/ref/llm-client-providers/tinfoil)
[TogetherAI (openai-generic)](/ref/llm-client-providers/together)
[Unify AI (openai-generic)](/ref/llm-client-providers/unify)
[vLLM (openai-generic)](/ref/llm-client-providers/vllm)

Timeout ConfigurationRetry PolicyFallbackRound Robin

[Timeout Configuration](/ref/llm-client-strategies/timeouts)
[Retry Policy](/ref/llm-client-strategies/retry-policy)
[Fallback](/ref/llm-client-strategies/fallback)
[Round Robin](/ref/llm-client-strategies/round-robin)

What is jinja?Jinja Filtersctx.output_formatctx.client_.roleVariablesConditionalsLoops

[What is jinja?](/ref/prompt-syntax/what-is-jinja)
[Jinja Filters](/ref/prompt-syntax/jinja-filters)
[ctx.output_format](/ref/prompt-syntax/ctx-output-format)
[ctx.client](/ref/prompt-syntax/ctx-client)
[_.role](/ref/prompt-syntax/role)
[Variables](/ref/prompt-syntax/variables)
[Conditionals](/ref/prompt-syntax/conditionals)
[Loops](/ref/prompt-syntax/loops)

baml.cliPathbaml.generateCodeOnSavebaml.enablePlaygroundProxybaml.syncExtensionToGeneratorVersion

[baml.cliPath](/ref/editor-extension-settings/baml-cli-path)
[baml.generateCodeOnSave](/ref/editor-extension-settings/baml-generate-code-on-save)
[baml.enablePlaygroundProxy](/ref/editor-extension-settings/baml-enable-playground-proxy)
[baml.syncExtensionToGeneratorVersion](/ref/editor-extension-settings/baml-sync-extension-to-generator-version)
[Help on Discord](https://discord.gg/BTNBeXGuaS)

HookInputHookOutput

[HookInput](#hookinput)
[HookOutput](#hookoutput)

BAML automatically generates a type-safe React hook for each BAML function. Each hook follows the naming patternuse{FunctionName}and supports both streaming and non-streaming modes.

`use{FunctionName}`

```
1import { useWriteMeAStory } from "@/baml_client/react/hooks";23// Basic usage with streaming enabled by default4const hook = useWriteMeAStory();56// Access streaming and final data7const { data, streamData, finalData } = hook;89// Track request state10const { isLoading, isStreaming, isPending, isSuccess, isError } = hook;1112// Execute the function13await hook.mutate("A story about a brave AI");1415// Reset state if needed16hook.reset();
```


## HookInput


The hook accepts an optional configuration object. SeeHook Inputfor complete details.

[Hook Input](/ref/baml_client/react-next-js/hook-input)

Enable streaming mode for real-time updates. Defaults to true.


Callback for streaming updates. Only available when streaming is enabled.


Callback when the request completes.


Unified callback for both streaming and final responses.


Callback when an error occurs. SeeError Types.

[Error Types](/ref/baml_client/errors/overview)

## HookOutput


The hook returns an object with the following properties. SeeHook Outputfor complete details.

[Hook Output](/ref/baml_client/react-next-js/hook-output)

The current response data. Contains either streaming or final data depending on the request state.


The final response data. Only available when the request completes.


Latest streaming update. Only available in streaming mode.


Error information if the request fails. SeeError Types.

[Error Types](/ref/baml_client/errors/overview)

True while the request is in progress (either pending or streaming).


True if the request is pending (not yet streaming or completed).


True if the request is currently streaming data. Only available in streaming mode.


True if the request completed successfully.


True if the request failed.


Current state of the request. For streaming hooks: ‘idle’ | ‘pending’ | ‘streaming’ | ‘success’ | ‘error’. For non-streaming hooks: ‘idle’ | ‘pending’ | ‘success’ | ‘error’.


Function to execute the BAML function. Returns a ReadableStream for streaming hooks, or a Promise of the final response for non-streaming hooks.


Function to reset the hook state back to its initial values.
