---
url: https://docs.boundaryml.com/guide/development/environment-variables.mdx
scraped_at: 2026-03-06T01:00:28.190922
filepath: docs-docs-boundaryml-com/guide/development/environment-variablesmdx.md
---


***

title: Set Environment Variables
slug: /guide/development/environment-variables
----------------------------------------------

## Environment Variables in BAML

Sometimes you'll see environment variables used in BAML, like in clients:

```baml

clientGPT4o {
  provider baml-openai-chat
  options {
    model gpt-5-mini
    api_key env.OPENAI_API_KEY
  }
}
```

## Setting Environment Variables

### In the VSCode Playground

Once you open a `.baml` file in VSCode, you should see a small button over every BAML function: `Open Playground`. Then you should be able to set environment variables in the settings tab.Or type `BAML Playground` in the VSCode Command Bar (`CMD + Shift + P` or `CTRL + Shift + P`) to open the playground.

### For Boundary Studio Integration

To send logs and traces to Boundary Studio, you need to set the `BOUNDARY_API_KEY` environment variable. This key is provided when you create an API key in your Boundary Studio dashboard.```bash
    # .env.local
    BOUNDARY_API_KEY=your_api_key_here
    ``````bash
    # .env
    BOUNDARY_API_KEY=your_api_key_here
    ``````bash
    # .env
    BOUNDARY_API_KEY=your_api_key_here
    ``````yaml
    # config/application.yml
    BOUNDARY_API_KEY: your_api_key_here
    ```### For Your App (Default)

BAML will do its best to load environment variables from your program. Any of the following strategies for setting env vars are compatible with BAML:

* Setting them in your shell before running your program
* In your `Dockerfile`
* In your `next.config.js`
* In your Kubernetes manifest
* From `secrets-store.csi.k8s.io`
* From a secrets provider such as [Infisical](https://infisical.com/) / [Doppler](https://www.doppler.com/)
* From a `.env` file (using `dotenv` CLI)
* Using account credentials for ephemeral token generation (e.g., Vertex AI Auth Tokens)
* `python-dotenv` package in Python or `dotenv` package in Node.js

```bash
export MY_SUPER_SECRET_API_KEY="..."
python my_program_using_baml.py
``````python
    from dotenv import load_dotenv
    from baml_client import b

    load_dotenv()
    ``````typescript
    import dotenv from 'dotenv'
    import { b } from './baml_client'

    dotenv.config()
    ``````ruby
    require 'dotenv/load'
    require 'baml_client'
    ```## Boundary Studio Integration

When you use BAML in your application, logs and traces are automatically sent to Boundary Studio for monitoring and debugging. To enable this integration, you need to set the `BOUNDARY_API_KEY` environment variable with an API key from your Boundary Studio dashboard.

The API key is used to:

* Authenticate your application with Boundary Studio
* Associate logs and traces with your specific project and environment
* Control access permissions for different operations

## Setting Environment Variables

### In the VSCode Playground

Once you open a `.baml` file in VSCode, you should see a small button over every BAML function: `Open Playground`. Then you should be able to set environment variables in the settings tab.Or type `BAML Playground` in the VSCode Command Bar (`CMD + Shift + P` or `CTRL + Shift + P`) to open the playground.

### For Boundary Studio Integration

To send logs and traces to Boundary Studio, you need to set the `BOUNDARY_API_KEY` environment variable. This key is provided when you create an API key in your Boundary Studio dashboard.```bash
    # .env.local
    BOUNDARY_API_KEY=your_api_key_here
    ``````bash
    # .env
    BOUNDARY_API_KEY=your_api_key_here
    ``````bash
    # .env
    BOUNDARY_API_KEY=your_api_key_here
    ``````yaml
    # config/application.yml
    BOUNDARY_API_KEY: your_api_key_here
    ```### For Your App (Default)

BAML will do its best to load environment variables from your program. Any of the following strategies for setting env vars are compatible with BAML:

* Setting them in your shell before running your program
* In your `Dockerfile`
* In your `next.config.js`
* In your Kubernetes manifest
* From `secrets-store.csi.k8s.io`
* From a secrets provider such as [Infisical](https://infisical.com/) / [Doppler](https://www.doppler.com/)
* From a `.env` file (using `dotenv` CLI)
* Using account credentials for ephemeral token generation (e.g., Vertex AI Auth Tokens)
* `python-dotenv` package in Python or `dotenv` package in Node.js

```bash
export MY_SUPER_SECRET_API_KEY="..."
python my_program_using_baml.py
``````python
    from dotenv import load_dotenv
    from baml_client import b

    load_dotenv()
    ``````typescript
    import dotenv from 'dotenv'
    import { b } from './baml_client'

    dotenv.config()
    ``````ruby
    require 'dotenv/load'
    require 'baml_client'
    ```## Setting LLM API Keys per Request

You can set the API key for an LLM dynamically by passing in the key as a header or as a parameter (depending on the provider), using the [ClientRegistry](/guide/baml-advanced/llm-client-registry).
