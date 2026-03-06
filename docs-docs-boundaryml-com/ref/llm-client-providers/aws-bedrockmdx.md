---
url: https://docs.boundaryml.com/ref/llm-client-providers/aws-bedrock.mdx
scraped_at: 2026-03-06T01:00:46.509535
filepath: docs-docs-boundaryml-com/ref/llm-client-providers/aws-bedrockmdx.md
---


***

title: aws-bedrock
subtitle: AWS Bedrock provider for BAML
---------------------------------------

The `aws-bedrock` provider supports all text-output models available via the [Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html).

## Quick Start

```baml BAML
clientMyClient {
  provider aws-bedrock
  options {
    model "anthropic.claude-3-sonnet-20240229-v1:0"
    inference_configuration {
      max_tokens 100
      temperature 0.7
    }
    // Pass any other parameters that are model specific, 
    // like with claude thinking models.
    additional_model_request_fields {
      thinking {
        type "enabled"
        budget_tokens 1030
      }
    }
  }
}
```

## Authentication

AWS Bedrock uses standard AWS authentication methods. We recommend using AWS profiles in development and AWS services' IAM roles in production, but all of the following are supported:When developing locally, you can use the AWS CLI in combination with profiles to manage your credentials.

    For example, if you run `aws sso login` with a default profile, BAML will automatically pick up those credentials:

    ```ini ~/.aws/config
    [default]
    sso_start_url = https://your-sso-start-url.awsapps.com/start
    sso_region = us-west-2
    sso_account_id = 123456789012
    sso_role_name = YourSSORole
    region = us-west-2
    output = json
    ```

    You can also choose a specific profile by setting the `AWS_PROFILE` environment variable.

    In the BAML playground, you can set this by clicking the "API Keys" button in
    the top right (you'll also need to set `AWS_REGION` to the same region as your
    profile).

    The BAML-generated clients will also respect `AWS_PROFILE` if it is set:

    ```bash
    export AWS_PROFILE=staging-profile
    ```

    Alternatively, you can also explicitly specify the profile directly in the BAML config itself
    (this will take precedence over the environment variable):

    ```bash
    # First, login with SSO
    aws sso login --profile staging-profile

    # Then use the profile in your BAML config
    clientMyClient {
      provider aws-bedrock
      options {
        profile "staging-profile"
        model "anthropic.claude-3-sonnet-20240229-v1:0"
      }
    }
    ```In AWS Lambda, EC2, ECS, etc., BAML will automatically use the service's IAM role, by reading the relevant environment variables. To override this behavior, see the section on [Explicit Credentials](#explicit-credentials).\`\`\`

    ```baml BAML
    clientMyClient {
      provider aws-bedrock
      options {
        region "us-east-1"  // Only region is required
        model "anthropic.claude-3-sonnet-20240229-v1:0"
      }
    }
    ```

    **Best Practices:**

    * Use execution roles in Lambda
    * Use task roles in ECS
    * Use instance profiles in EC2
    * Never hardcode credentials in AWS environments
    * See [IAM Permissions](#iam-permissions) section for required permissionsThe simplest way to authenticate. Set these environment variables:

    ```bash
    export AWS_ACCESS_KEY_ID="your_key"
    export AWS_SECRET_ACCESS_KEY="your_secret"
    export AWS_REGION="us-east-1"
    ```

    ```baml BAML
    clientMyClient {
      provider aws-bedrock
      options {
        // No need to specify credentials - they'll be picked up from environment
        model "anthropic.claude-3-sonnet-20240229-v1:0"
      }
    }
    ```You can specify credentials directly in your BAML configuration:

    ```baml BAML
    clientMyClient {
      provider aws-bedrock
      options {
        access_key_id env.AWS_ACCESS_KEY_ID
        secret_access_key env.AWS_SECRET_ACCESS_KEY
        region "us-east-1"
        model "anthropic.claude-3-sonnet-20240229-v1:0"
      }
    }
    ```

    **Important Notes:**

    * Explicit credentials take precedence over environment variables
    * If specifying any credential, you must provide all required ones
    * For temporary credentials, include `session_token`
    * Not recommended for production AWS environments (use IAM roles instead)## Credential Resolution

BAML follows a specific order when resolving AWS credentials:

1. **Explicit BAML Configuration**
   ```baml BAML
   clientMyClient {
     provider aws-bedrock
     options {
       access_key_id env.MY_ACCESS_KEY      // Highest precedence
       secret_access_key env.MY_SECRET_KEY
       region "us-east-1"
     }
   }
   ```

2. **Environment Variables**
   ```bash
   AWS_ACCESS_KEY_ID
   AWS_SECRET_ACCESS_KEY
   AWS_SESSION_TOKEN    # Optional
   AWS_REGION
   AWS_PROFILE
   ```

3. **AWS Configuration Files**
   ```ini
   # ~/.aws/credentials
   [default]
   aws_access_key_id = ...
   aws_secret_access_key = ...

   # ~/.aws/config
   [default]
   region = us-east-1
   ```

4. **Instance Metadata** (EC2/ECS only)
   * IAM Role credentials
   * Instance profile credentials

### Important Rules

1. **All or Nothing**
   * If you provide any credential explicitly, you must provide all required credentials
   * This won't work:
     ```baml BAML
     clientMyClient {
       provider aws-bedrock
       options {
         access_key_id env.AWS_ACCESS_KEY_ID
         // Error: secret_access_key is required when access_key_id is provided
         model "anthropic.claude-3-sonnet-20240229-v1:0"
       }
     }
     ```

2. **Session Token Requirements**
   * When using `session_token`, you must provide all three:
     * `access_key_id`
     * `secret_access_key`
     * `session_token`

3. **Profile Exclusivity**
   * When using `profile`, you cannot specify other credentials:
     ```baml BAML
     clientMyClient {
       provider aws-bedrock
       options {
         profile "my-profile"
         access_key_id env.AWS_ACCESS_KEY_ID  // Error: Cannot mix profile with explicit credentials
         model "anthropic.claude-3-sonnet-20240229-v1:0"
       }
     }
     ```

4. **Environment Variable Override**
   * Explicit values in BAML always override environment variables:
     ```baml BAML
     clientMyClient {
       provider aws-bedrock
       options {
         access_key_id "AKIAXXXXXXXX"  // This will be used even if AWS_ACCESS_KEY_ID exists
         secret_access_key env.AWS_SECRET_ACCESS_KEY
         model "anthropic.claude-3-sonnet-20240229-v1:0"
       }
     }
     ```

5. **AWS Lambda/ECS/EC2**
   * In AWS services, credentials are automatically provided by the runtime
   * Explicitly provided credentials will override the automatic ones
   * Best practice: Don't specify credentials in AWS environments, use IAM roles instead

### Using Custom Environment Variables

You can map your own environment variable names:```baml BAML
    clientMyClient {
      provider aws-bedrock
      options {
        access_key_id env.MY_CUSTOM_AWS_KEY_ID
        secret_access_key env.MY_CUSTOM_AWS_SECRET
        session_token env.MY_CUSTOM_AWS_SESSION  // Optional
        region env.MY_CUSTOM_AWS_REGION
        model "anthropic.claude-3-sonnet-20240229-v1:0"
      }
    }
    ``````bash
    # Your custom environment variables
    export MY_CUSTOM_AWS_KEY_ID="your_key"
    export MY_CUSTOM_AWS_SECRET="your_secret"
    export MY_CUSTOM_AWS_REGION="us-east-1"
    export MY_CUSTOM_AWS_SESSION="optional_session_token"
    ```## Cross-Account Access

To use Bedrock from a different AWS account:

1. **Set up the target account role** (where Bedrock is):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::SOURCE_ACCOUNT_ID:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "YOUR_EXTERNAL_ID"
        }
      }
    }
  ]
}
```

2. **Configure the source account** (where your application runs):```ini
    # ~/.aws/config
    [profile target-role]
    role_arn = arn:aws:iam::TARGET_ACCOUNT_ID:role/ROLE_NAME
    source_profile = default
    region = us-east-1
    ```

    ```baml BAML
    clientMyClient {
      provider aws-bedrock
      options {
        profile "target-role"
        model "anthropic.claude-3-sonnet-20240229-v1:0"
      }
    }
    ``````bash
    # Assume role and export credentials
    aws sts assume-role \
      --role-arn arn:aws:iam::TARGET_ACCOUNT_ID:role/ROLE_NAME \
      --role-session-name "BamlSession" \
      --external-id "YOUR_EXTERNAL_ID"

    export AWS_ACCESS_KEY_ID="from-sts-output"
    export AWS_SECRET_ACCESS_KEY="from-sts-output"
    export AWS_SESSION_TOKEN="from-sts-output"
    ``````typescript
    import { ClientRegistry } from '@baml/core';
    import { STSClient, AssumeRoleCommand } from '@aws-sdk/client-sts';

    const sts = new STSClient({ region: 'us-east-1' });
    const response = await sts.send(new AssumeRoleCommand({
        RoleArn: 'arn:aws:iam::TARGET_ACCOUNT_ID:role/ROLE_NAME',
        RoleSessionName: 'BamlSession',
        ExternalId: 'YOUR_EXTERNAL_ID'
    }));

    const registry = new ClientRegistry();
    registry.addLlmClient('MyClient', 'aws-bedrock', {
        accessKeyId: response.Credentials!.AccessKeyId,
        secretAccessKey: response.Credentials!.SecretAccessKey,
        sessionToken: response.Credentials!.SessionToken,
        region: 'us-east-1'
    });
    ```## IAM Permissions

### Basic Permissions

The following IAM permissions are required for basic Bedrock access:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "arn:aws:bedrock:*:*:model/*"
    }
  ]
}
```

### Additional Permissions

Depending on your setup, you might need additional permissions:See [Cross-Account Access](#cross-account-access) section for the required trust relationships and permissions.If using VPC endpoints:

    ```json
    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": [
            "bedrock:InvokeModel",
            "bedrock:InvokeModelWithResponseStream"
          ],
          "Resource": "arn:aws:bedrock:*:*:model/*",
          "Condition": {
            "StringEquals": {
              "aws:SourceVpc": "vpc-xxxxxxxx"
            }
          }
        }
      ]
    }
    ```To restrict access to specific models:

    ```json
    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": [
            "bedrock:InvokeModel",
            "bedrock:InvokeModelWithResponseStream"
          ],
          "Resource": [
            "arn:aws:bedrock:*:*:model/anthropic.claude-*",
            "arn:aws:bedrock:*:*:model/meta.llama2-*"
          ]
        }
      ]
    }
    ```### Best Practices

* Follow the principle of least privilege
* Use resource-based policies when possible
* Consider using AWS Organizations SCPs for enterprise-wide controls
* Regularly audit IAM permissions using AWS IAM Access Analyzer

## Configuration Options

### BAML-specific request `options`

These unique parameters (aka `options`) are modify the API request sent to the provider.

You can use this to modify the `region`, `access_key_id`, `secret_access_key`, and `session_token` sent to the provider.The AWS region to use. **Default: `AWS_REGION` environment variable**AWS access key ID. **Default: `AWS_ACCESS_KEY_ID` environment variable**AWS secret access key. **Default: `AWS_SECRET_ACCESS_KEY` environment variable**Temporary session token. Required if using temporary credentials. **Default: `AWS_SESSION_TOKEN` environment variable**AWS profile name from credentials file. **Default: `AWS_PROFILE` environment variable**AWS endpoint URL. Useful for using a VPC endpoint.The role to use if the role is not in the allowed\_roles. **Default: `"user"` usually, but some models like OpenAI's `gpt-5` will use `"system"`**

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
  ```## Modular API

* `b.request` returns a fully signed SigV4 `HTTPRequest` pointing at the
  Converse API.
* Forward the request as-is. Do not mutate the headers; they already include
  `Authorization`, `X-Amz-Date`, and (if needed) `X-Amz-Security-Token`.
* Send the request immediately after building it. The signature is computed at
  request time, so rebuilding gives you a fresh signature.
* Streaming modular calls are not yet supported for Bedrock.

```typescript TypeScript
import { SignatureV4 } from "@aws-sdk/signature-v4"
import { defaultProvider } from "@aws-sdk/credential-provider-node"
import { HttpRequest } from "@aws-sdk/protocol-http"
import { b } from 'baml_client'

async function callBedrock() {
  const req = await b.request.ExtractResume("John Doe | Software Engineer | BSc in CS")

  const body = req.body.json() as any
  const bodyString = JSON.stringify(body)
  const url = new URL(req.url)
  const region = (req.client_details.options?.region as string) ?? process.env.AWS_REGION ?? "us-east-1"

  const signer = new SignatureV4({
    service: "bedrock",
    region,
    credentials: defaultProvider(),
  })

  const unsigned = new HttpRequest({
    protocol: url.protocol,
    hostname: url.hostname,
    path: url.pathname,
    method: req.method,
    headers: {
      ...req.headers,
      host: url.host,
      "content-type": "application/json",
    },
    body: bodyString,
  })

  const signed = await signer.sign(unsigned)

  const res = await fetch(req.url, {
    method: req.method,
    headers: signed.headers as Record,
    body: bodyString,
  })

  if (!res.ok) {
    throw new Error(`Bedrock request failed: ${res.status}`)
  }

  const payload = await res.json()
  const message = payload.output.message.content.find((block: any) => block.text)?.text ?? ''

  return b.parse.ExtractResume(message)
}
```

```python Python
import json
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import boto3
from baml_client import b

def call_bedrock():
  req = b.request.ExtractResume("John Doe | Software Engineer | BSc in CS")

  body = req.body.json()
  body_bytes = json.dumps(body).encode("utf-8")

  session = boto3.Session()
  credentials = session.get_credentials().get_frozen_credentials()
  region = req.client_details.options.get("region") or session.region_name or "us-east-1"

  aws_request = AWSRequest(
    method=req.method,
    url=req.url,
    data=body_bytes,
    headers=dict(req.headers),
  )
  SigV4Auth(credentials, "bedrock", region).add_auth(aws_request)

  response = requests.post(
    req.url,
    headers=dict(aws_request.headers.items()),
    data=body_bytes,
  )
  response.raise_for_status()

  payload = response.json()
  message = payload["output"]["message"]["content"][0]["text"]
  return b.parse.ExtractResume(message)
```

### `media_url_handler`

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
* **Use `send_base64_unless_google_url`** when working with Google Cloud Storage and want to preserve gs\:// URLsURL fetching happens at request time and may add latency. Consider caching or pre-converting frequently used media when using `send_base64` mode.AWS Bedrock converts most media to base64 by default (`send_base64` for images, audio, and PDFs). Consider using S3 presigned URLs with `send_url` mode for large files to avoid base64 overhead.## Provider request parameters

These are other `options` that are passed through to the provider, without modification by BAML. For example if the request has a `temperature` field, you can define it in the client here so every call has that set.

Consult the specific provider's documentation for more information.The model to use.

  | Model | Description |
  | ----- | ----------- |

  #### Anthropic Claude (Latest Generation)

  * `anthropic.claude-opus-4-1-20250805-v1:0` - Most powerful coding
  * `anthropic.claude-sonnet-4-20250514-v1:0` - Best default, 1M context available
  * `anthropic.claude-3-5-haiku-20241022-v1:0` - Fast and efficient

  #### Meta Llama (Latest Generation)

  * `meta.llama4-maverick-17b-instruct-v1:0` - Latest Llama 4
  * `meta.llama3-3-70b-instruct-v1:0` - Enhanced Llama 3.3

  Run `aws bedrock list-foundation-models | jq '.modelSummaries.[].modelId'` to see available models.

  Note: You must [request model access](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html) before use.Model-specific inference parameters. See [AWS Bedrock documentation](https://docs.rs/aws-sdk-bedrockruntime/latest/aws_sdk_bedrockruntime/types/struct.InferenceConfiguration.html).

  ```baml BAML
  clientMyClient {
    provider aws-bedrock
    options {
      inference_configuration {
        max_tokens 1000
        temperature 1.0
        top_p 0.8
      }
    }
  }
  ```## Troubleshooting

### Common Errors```json
  {
    "Error": "AccessDeniedException",
    "Message": "User is not authorized to perform: bedrock:InvokeModel"
  }
  ```

  **Solution:**

  * Check IAM permissions
  * Verify execution role permissions in Lambda/ECS
  * Ensure credentials have Bedrock access```json
  {
    "Error": "UnrecognizedClientException",
    "Message": "The security token included in the request is invalid"
  }
  ```

  **Solution:**

  * Verify credentials are set correctly
  * Check if session token is required and provided
  * Ensure credentials haven't expired```json
  {
    "Error": "ValidationException",
    "Message": "Model is not supported in this Region"
  }
  ```

  **Solution:**

  * Check model availability in your region
  * Request model access if needed
  * Consider using a different region```json
  {
    "Error": "ValidationException",
    "Message": "Account is not authorized to use model"
  }
  ```

  **Solution:**

  * Request model access through AWS Console
  * Wait for approval (1-2 business days)
  * Verify model ID is correct### Environment-Specific Setup* Set appropriate memory and timeout
  * Configure execution role with Bedrock permissions
  * Consider VPC endpoints for private subnets* Use task roles (ECS) or instance profiles (EC2)
  * Configure VPC endpoints if needed
  * Check security group outbound rules* Set AWS credentials in environment or config files
  * Use `AWS_PROFILE` to manage multiple profiles
  * Run `aws configure list` to verify configuration
