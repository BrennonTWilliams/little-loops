---
url: https://docs.boundaryml.com/guide/development/
scraped_at: 2026-03-06T01:00:27.824713
filepath: docs-docs-boundaryml-com/guide/development/index.md
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

Environment Variables in BAMLSetting Environment VariablesIn the VSCode PlaygroundFor Boundary Studio IntegrationFor Your App (Default)Boundary Studio IntegrationSetting Environment VariablesIn the VSCode PlaygroundFor Boundary Studio IntegrationFor Your App (Default)Setting LLM API Keys per Request

[Environment Variables in BAML](#environment-variables-in-baml)
[Setting Environment Variables](#setting-environment-variables)
[In the VSCode Playground](#in-the-vscode-playground)
[For Boundary Studio Integration](#for-boundary-studio-integration)
[For Your App (Default)](#for-your-app-default)
[Boundary Studio Integration](#boundary-studio-integration)
[Setting Environment Variables](#setting-environment-variables-1)
[In the VSCode Playground](#in-the-vscode-playground-1)
[For Boundary Studio Integration](#for-boundary-studio-integration-1)
[For Your App (Default)](#for-your-app-default-1)
[Setting LLM API Keys per Request](#setting-llm-api-keys-per-request)

## Environment Variables in BAML


Sometimes you’ll see environment variables used in BAML, like in clients:


```
1client<llm> GPT4o {2provider baml-openai-chat3options {4model gpt-5-mini5api_key env.OPENAI_API_KEY6}7}
```


## Setting Environment Variables


### In the VSCode Playground


Once you open a.bamlfile in VSCode, you should see a small button over every BAML function:Open Playground. Then you should be able to set environment variables in the settings tab.

`.baml`
`Open Playground`

Or typeBAML Playgroundin the VSCode Command Bar (CMD + Shift + PorCTRL + Shift + P) to open the playground.

`BAML Playground`
`CMD + Shift + P`
`CTRL + Shift + P`

### For Boundary Studio Integration


To send logs and traces to Boundary Studio, you need to set theBOUNDARY_API_KEYenvironment variable. This key is provided when you create an API key in your Boundary Studio dashboard.

`BOUNDARY_API_KEY`

```
$# .env.local$BOUNDARY_API_KEY=your_api_key_here
```


### For Your App (Default)


BAML will do its best to load environment variables from your program. Any of the following strategies for setting env vars are compatible with BAML:


Setting them in your shell before running your programIn yourDockerfileIn yournext.config.jsIn your Kubernetes manifestFromsecrets-store.csi.k8s.ioFrom a secrets provider such asInfisical/DopplerFrom a.envfile (usingdotenvCLI)Using account credentials for ephemeral token generation (e.g., Vertex AI Auth Tokens)python-dotenvpackage in Python ordotenvpackage in Node.js

`Dockerfile`
`next.config.js`
`secrets-store.csi.k8s.io`
[Infisical](https://infisical.com/)
[Doppler](https://www.doppler.com/)
`.env`
`dotenv`
`python-dotenv`
`dotenv`

```
$export MY_SUPER_SECRET_API_KEY="..."$python my_program_using_baml.py
```


```
1from dotenv import load_dotenv2from baml_client import b34load_dotenv()
```


## Boundary Studio Integration


When you use BAML in your application, logs and traces are automatically sent to Boundary Studio for monitoring and debugging. To enable this integration, you need to set theBOUNDARY_API_KEYenvironment variable with an API key from your Boundary Studio dashboard.

`BOUNDARY_API_KEY`

The API key is used to:


Authenticate your application with Boundary StudioAssociate logs and traces with your specific project and environmentControl access permissions for different operations


## Setting Environment Variables


### In the VSCode Playground


Once you open a.bamlfile in VSCode, you should see a small button over every BAML function:Open Playground. Then you should be able to set environment variables in the settings tab.

`.baml`
`Open Playground`

Or typeBAML Playgroundin the VSCode Command Bar (CMD + Shift + PorCTRL + Shift + P) to open the playground.

`BAML Playground`
`CMD + Shift + P`
`CTRL + Shift + P`

### For Boundary Studio Integration


To send logs and traces to Boundary Studio, you need to set theBOUNDARY_API_KEYenvironment variable. This key is provided when you create an API key in your Boundary Studio dashboard.

`BOUNDARY_API_KEY`

```
$# .env.local$BOUNDARY_API_KEY=your_api_key_here
```


### For Your App (Default)


BAML will do its best to load environment variables from your program. Any of the following strategies for setting env vars are compatible with BAML:


Setting them in your shell before running your programIn yourDockerfileIn yournext.config.jsIn your Kubernetes manifestFromsecrets-store.csi.k8s.ioFrom a secrets provider such asInfisical/DopplerFrom a.envfile (usingdotenvCLI)Using account credentials for ephemeral token generation (e.g., Vertex AI Auth Tokens)python-dotenvpackage in Python ordotenvpackage in Node.js

`Dockerfile`
`next.config.js`
`secrets-store.csi.k8s.io`
[Infisical](https://infisical.com/)
[Doppler](https://www.doppler.com/)
`.env`
`dotenv`
`python-dotenv`
`dotenv`

```
$export MY_SUPER_SECRET_API_KEY="..."$python my_program_using_baml.py
```


```
1from dotenv import load_dotenv2from baml_client import b34load_dotenv()
```


## Setting LLM API Keys per Request


You can set the API key for an LLM dynamically by passing in the key as a header or as a parameter (depending on the provider), using theClientRegistry.

[ClientRegistry](/guide/baml-advanced/llm-client-registry)