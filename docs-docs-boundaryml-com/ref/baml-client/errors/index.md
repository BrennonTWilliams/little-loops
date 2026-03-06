---
url: https://docs.boundaryml.com/ref/baml_client/errors/
scraped_at: 2026-03-06T01:00:42.033872
filepath: docs-docs-boundaryml-com/ref/baml-client/errors/index.md
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

Error Class HierarchyError TypesBamlValidationErrorBamlClientFinishReasonErrorBamlAbortErrorFallback Error AggregationType GuardsCommon Properties

[Error Class Hierarchy](#error-class-hierarchy)
[Error Types](#error-types)
[BamlValidationError](#bamlvalidationerror)
[BamlClientFinishReasonError](#bamlclientfinishreasonerror)
[BamlAbortError](#bamlaborterror)
[Fallback Error Aggregation](#fallback-error-aggregation)
[Type Guards](#type-guards)
[Common Properties](#common-properties)

BAML provides a set of error classes for handling different error scenarios when working with LLMs. Each error type is designed to handle specific failure cases in the BAML runtime.


## Error Class Hierarchy


All BAML errors extend the base JavaScriptErrorclass and include a literaltypefield for type identification.

`Error`
`type`

```
1// Base JavaScript Error class2class Error {3message: string4name: string5stack?: string6}78// BAML-specific error classes9class BamlValidationError extends Error {10type: 'BamlValidationError'11message: string12prompt: string13raw_output: string14detailed_message: string15}1617class BamlClientFinishReasonError extends Error {18type: 'BamlClientFinishReasonError'19message: string20prompt: string21raw_output: string22detailed_message: string23}2425class BamlAbortError extends Error {26type: 'BamlAbortError'27message: string28reason?: any29detailed_message: string30}
```


## Error Types


### BamlValidationError

[BamlValidationError](/ref/baml_client/errors/baml-validation-error)

Thrown when BAML fails to parse or validate LLM output. Contains the original prompt and raw output for debugging.


### BamlClientFinishReasonError

[BamlClientFinishReasonError](/ref/baml_client/errors/baml-client-finish-reason-error)

Thrown when an LLM terminates with a disallowed finish reason. Includes the original prompt and partial output received before termination.


### BamlAbortError

[BamlAbortError](/ref/baml_client/errors/baml-abort-error)

Thrown when a BAML operation is cancelled via an abort controller. Contains an optional reason for the cancellation.


## Fallback Error Aggregation


When usingfallback clientsor clients withretry policies, BAML attempts multiple client calls before finally failing. In these cases:

[fallback clients](/ref/llm-client-strategies/fallback)
[retry policies](/ref/llm-client-strategies/retry-policy)

The errortypecorresponds to the final (last) failed attemptThemessagefield contains the error message from the final attemptThedetailed_messagefield contains thecomplete historyof all failed attempts

`message`
`detailed_message`

This allows you to debug the entire fallback chain while still getting a specific error type for the final failure.


## Type Guards


All BAML errors can be identified using TypeScript’sinstanceofoperator:

`instanceof`

```
1try {2// BAML operation3} catch (error) {4if (error instanceof BamlAbortError) {5// Handle cancellation6} else if (error instanceof BamlValidationError) {7// Handle validation error8} else if (error instanceof BamlClientFinishReasonError) {9// Handle finish reason error10}11}
```


## Common Properties


All BAML error classes include:


Literal type identifier specific to each error class.


Human-readable error message describing the failure.


Comprehensive error information that includes the complete history of all failed attempts when using fallback clients or retry policies. For single attempts, this typically contains the same information asmessagebut may include additional debugging details.

`message`

For detailed information about each error type, refer to their individual reference pages.
