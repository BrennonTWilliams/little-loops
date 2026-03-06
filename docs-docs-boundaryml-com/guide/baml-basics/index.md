---
url: https://docs.boundaryml.com/guide/baml-basics/
scraped_at: 2026-03-06T01:00:22.674419
filepath: docs-docs-boundaryml-com/guide/baml-basics/index.md
---

[Home](/home)
[Guide](/guide/introduction/what-is-baml)
[Examples](/examples/interactive-examples)
[BAML Reference](/ref/overview)
[Playground](https://promptfiddle.com/)
[Agents.md](/agents-md/claude-code)
[Changelog](/changelog/changelog)

IntroductionWhat is BAML?Why BAML?What's the baml_src folderWhat's baml_clientInstallation: EditorsVSCode ExtensionCursor ExtensionJetBrains IDEsZedClaude CodeOthersInstallation: LanguagePythonTypescriptGoRubyRustREST API (other languages)ElixirFramework IntegrationReact/Next.jsDevelopmentEnvironment VariablesTerminal LogsUpgrade BAML versionsDeployingBAML BasicsPrompting with BAMLSwitching LLMsTesting functionsStreamingMulti-Modal (Images / Audio)Error HandlingConfiguring TimeoutsConcurrent CallsAbortSignal / CancellationBAML AdvancedCollector (track tokens)LLM Client RegistryDynamic TypesReusing Prompt SnippetsPrompt Caching / Message Role MetadataChecks and AssertsModular APIPrompt OptimizationBoundary CloudObservabilityComparisonsBAML vs LangchainBAML vs MarvinBAML vs Ai-SDKBAML vs OpenAI SDKBAML vs PydanticContact


What is BAML?Why BAML?What's the baml_src folderWhat's baml_client

[What is BAML?](/guide/introduction/what-is-baml)
[Why BAML?](/guide/introduction/why-baml)
[What's the baml_src folder](/guide/introduction/baml_src)
[What's baml_client](/guide/introduction/baml_client)

VSCode ExtensionCursor ExtensionJetBrains IDEsZedClaude CodeOthers

[VSCode Extension](/guide/installation-editors/vs-code-extension)
[Cursor Extension](/guide/installation-editors/cursor-extension)
[JetBrains IDEs](/guide/installation-editors/jetbrains)
[Zed](/guide/installation-editors/zed)
[Claude Code](/guide/installation-editors/claude-code)
[Others](/guide/installation-editors/others)

PythonTypescriptGoRubyRustREST API (other languages)Elixir

[Python](/guide/installation-language/python)
[Typescript](/guide/installation-language/typescript)
[Go](/guide/installation-language/go)
[Ruby](/guide/installation-language/ruby)
[Rust](/guide/installation-language/rust)
[REST API (other languages)](/guide/installation-language/rest-api-other-languages)
[Elixir](/guide/installation-language/elixir)

React/Next.js


Environment VariablesTerminal LogsUpgrade BAML versionsDeploying

[Environment Variables](/guide/development/environment-variables)
[Terminal Logs](/guide/development/terminal-logs)
[Upgrade BAML versions](/guide/development/upgrade-baml-versions)

Prompting with BAMLSwitching LLMsTesting functionsStreamingMulti-Modal (Images / Audio)Error HandlingConfiguring TimeoutsConcurrent CallsAbortSignal / Cancellation

[Prompting with BAML](/guide/baml-basics/prompting-with-baml)
[Switching LLMs](/guide/baml-basics/switching-llms)
[Testing functions](/guide/baml-basics/testing-functions)
[Streaming](/guide/baml-basics/streaming)
[Multi-Modal (Images / Audio)](/guide/baml-basics/multi-modal)
[Error Handling](/guide/baml-basics/error-handling)
[Configuring Timeouts](/guide/baml-basics/timeouts)
[Concurrent Calls](/guide/baml-basics/concurrent-calls)
[AbortSignal / Cancellation](/guide/baml-basics/abort-signal)

Collector (track tokens)LLM Client RegistryDynamic TypesReusing Prompt SnippetsPrompt Caching / Message Role MetadataChecks and AssertsModular APIPrompt Optimization

[Collector (track tokens)](/guide/baml-advanced/collector-track-tokens)
[LLM Client Registry](/guide/baml-advanced/llm-client-registry)
[Dynamic Types](/guide/baml-advanced/dynamic-types)
[Reusing Prompt Snippets](/guide/baml-advanced/reusing-prompt-snippets)
[Prompt Caching / Message Role Metadata](/guide/baml-advanced/prompt-caching-message-role-metadata)
[Checks and Asserts](/guide/baml-advanced/checks-and-asserts)
[Modular API](/guide/baml-advanced/modular-api)
[Prompt Optimization](/guide/baml-advanced/prompt-optimization)

Observability


BAML vs LangchainBAML vs MarvinBAML vs Ai-SDKBAML vs OpenAI SDKBAML vs Pydantic

[BAML vs Langchain](/guide/comparisons/baml-vs-langchain)
[BAML vs Marvin](/guide/comparisons/baml-vs-marvin)
[BAML vs Ai-SDK](/guide/comparisons/baml-vs-ai-sdk)
[BAML vs OpenAI SDK](/guide/comparisons/baml-vs-open-ai-sdk)
[BAML vs Pydantic](/guide/comparisons/baml-vs-pydantic)

Contact

[Contact](/guide/contact)
[Help on Discord](https://discord.gg/BTNBeXGuaS)

What BAML Functions Actually DoPrompt Preview + seeing the CURL requestCalling the functionNext steps

[What BAML Functions Actually Do](#what-baml-functions-actually-do)
[Prompt Preview + seeing the CURL request](#prompt-preview--seeing-the-curl-request)
[Calling the function](#calling-the-function)
[Next steps](#next-steps)

We recommend reading theinstallationinstructions first

[installation](/guide/installation-language/python)

BAML functions are special definitions that get converted into real code (Python, TS, etc) that calls LLMs. Think of them as a way to define AI-powered functions that are type-safe and easy to use in your application.


### What BAML Functions Actually Do


When you write a BAML function like this:


```
1function ExtractResume(resume_text: string) -> Resume {2client "openai-responses/gpt-5-mini"3// The prompt uses Jinja syntax.. more on this soon.4prompt #"5Extract info from this text.67{# special macro to print the output schema + instructions #}8{{ ctx.output_format }}910Resume:11---12{{ resume_text }}13---14"#15}
```


BAML converts it into code that:


Takes your input (resume_text)Sends a request to OpenAI’s GPT-4 API with your prompt.Parses the JSON response into yourResumetypeReturns a type-safe object you can use in your code

`resume_text`
`Resume`

### Prompt Preview + seeing the CURL request


For maximum transparency, you can see the API request BAML makes to the LLM provider using the VSCode extension.
Below you can see thePrompt Preview, where you see the full rendered prompt (once you add a test case):


Note how the{{ ctx.output_format }}macro is replaced with the output schema instructions.

`{{ ctx.output_format }}`

The Playground will also show you theRaw CURL request(switch from “Prompt Review” to “Raw cURL”):


Always include the{{ ctx.output_format }}macro in your prompt. This injects your output schema into the prompt, which helps the LLM output the right thing. You can alsocustomize what it prints.

`{{ ctx.output_format }}`
[customize what it prints](/ref/prompt-syntax/ctx-output-format)

One of our design philosophies is to never hide the prompt from you. You control and can always see the entire prompt.


## Calling the function


Recall that BAML will generate abaml_clientdirectory in the language of your choice using the parameters in yourgeneratorconfig. This contains the function and types you defined.

`baml_client`
[generator](/ref/baml/generator)
`generator`

Now we can call the function, which will make a request to the LLM and return theResumeobject:

`Resume`

```
1# Import the baml client (We call it `b` for short)2from baml_client import b3# Import the Resume type, which is now a Pydantic model!4from baml_client.types import Resume56def main():7resume_text = """Jason Doe\nPython, Rust\nUniversity of California, Berkeley, B.S.\nin Computer Science, 2020\nAlso an expert in Tableau, SQL, and C++\n"""89# this function comes from the autogenerated "baml_client".10# It calls the LLM you specified and handles the parsing.11resume = b.ExtractResume(resume_text)1213# Fully type-checked and validated!14assert isinstance(resume, Resume)
```


Do not modify any code insidebaml_client, as it’s autogenerated.

`baml_client`

## Next steps


CheckoutPromptFiddleto see various interactive BAML function examples or view theexample prompts

[PromptFiddle](https://promptfiddle.com/)
[example prompts](/examples)

Read the next guide to learn more about choosing different LLM providers and running tests in the VSCode extension.

[Switching LLMsUse any provider or open-source model](/guide/baml-basics/switching-llms)

Use any provider or open-source model

[Testing FunctionsTest your functions in the VSCode extension](/guide/baml-basics/testing-functions)

Test your functions in the VSCode extension

[Chat RolesDefine user or assistant roles in your prompts](/examples/prompt-engineering/chat)

Define user or assistant roles in your prompts

[Function Calling / ToolsUse function calling or tools in your prompts](/examples/prompt-engineering/tools-function-calling)

Use function calling or tools in your prompts
