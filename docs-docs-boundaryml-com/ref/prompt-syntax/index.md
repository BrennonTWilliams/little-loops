---
url: https://docs.boundaryml.com/ref/prompt-syntax/
scraped_at: 2026-03-06T01:00:51.619319
filepath: docs-docs-boundaryml-com/ref/prompt-syntax/index.md
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

Jinja CookbookBasic SyntaxLoops / Iterating Over ListsConditional StatementsSetting VariablesIncluding other TemplatesString FormattingBuilt-in filters

[Jinja Cookbook](#jinja-cookbook)
[Basic Syntax](#basic-syntax)
[Loops / Iterating Over Lists](#loops--iterating-over-lists)
[Conditional Statements](#conditional-statements)
[Setting Variables](#setting-variables)
[Including other Templates](#including-other-templates)
[String Formatting](#string-formatting)
[Built-in filters](#built-in-filters)

BAML Prompt strings are essentiallyMinijinjatemplates, which offer the ability to express logic and data manipulation within strings. Jinja is a very popular and mature templating language amongst Python developers, so Github Copilot or another LLM can already help you write most of the logic you want.

[Minijinja](https://docs.rs/minijinja/latest/minijinja/filters/index.html#functions)

## Jinja Cookbook


When in doubt — use the BAML VSCode Playground preview. It will show you the fully rendered prompt, even when it has complex logic.


### Basic Syntax


{% ... %}: Use for executing statements such as for-loops or conditionals.{{ ... }}: Use for outputting expressions or variables.{# ... #}: Use for comments within the template, which will not be rendered.

`{% ... %}`
`{{ ... }}`
`{# ... #}`

### Loops / Iterating Over Lists


Here’s how you can iterate over a list of items, accessing each item’s attributes:


```
1function MyFunc(messages: Message[]) -> string {2prompt #"3{% for message in messages %}4{{ message.user_name }}: {{ message.content }}5{% endfor %}6"#7}
```


### Conditional Statements


Use conditional statements to control the flow and output of your templates based on conditions:


```
1function MyFunc(user: User) -> string {2prompt #"3{% if user.is_active %}4Welcome back, {{ user.name }}!5{% else %}6Please activate your account.7{% endif %}8"#9}
```


### Setting Variables


You can define and use variables within your templates to simplify expressions or manage data:


```
1function MyFunc(items: Item[]) -> string {2prompt #"3{% set total_price = 0 %}4{% for item in items %}5{% set total_price = total_price + item.price %}6{% endfor %}7Total price: {{ total_price }}8"#9}
```


### Including other Templates


To promote reusability, you can include other templates within a template. Seetemplate strings:

[template strings](/ref/baml/template-string)

```
1template_string PrintUserInfo(arg1: string, arg2: User) #"2{{ arg1 }}3The user's name is: {{ arg2.name }}4"#56function MyFunc(arg1: string, user: User) -> string {7prompt #"8Here is the user info:9{{ PrintUserInfo(arg1, user) }}10"#11}
```


### String Formatting


BAML supports Python’s new-style string formatting via the.format()method on strings. This uses{}placeholders (not%s-style).

`.format()`
`{}`
`%s`

```
1{# Basic substitution #}2{{ "{}, {}!".format("Hello", "World") }}3{# Output: Hello, World! #}45{# Number formatting with commas #}6{{ "{:,}".format(1234567) }}7{# Output: 1,234,567 #}89{# Fixed decimal places #}10{{ "{:.2f}".format(3.14159) }}11{# Output: 3.14 #}1213{# Padding and alignment #}14{{ "{:<10}".format("left") }}15{{ "{:>10}".format("right") }}16{{ "{:^10}".format("center") }}
```


Only new-style{}formatting is supported. Old-style%sformatting via the|formatfilter isnotavailable because BAML uses the|formatfilter forserializing objects(e.g.value|format(type="yaml")).

`{}`
`%s`
`|format`
`|format`
[serializing objects](/ref/prompt-syntax/jinja-filters#format)
`value|format(type="yaml")`

For a full reference of what’s possible with Python’s format specification, seepyformat.info.

[pyformat.info](https://pyformat.info/)

### Built-in filters


Seejinja docs

[jinja docs](https://jinja.palletsprojects.com/en/3.1.x/templates/#list-of-builtin-filters)