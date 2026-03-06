---
url: https://docs.boundaryml.com/guide/development/deploying/docker-rest-api.mdx
scraped_at: 2026-03-06T01:00:27.207565
filepath: docs-docs-boundaryml-com/guide/development/deploying/docker-rest-apimdx.md
---


***

## title: OpenAPIThis feature was added in: v0.55.0.This page assumes you've gone through the [OpenAPI quickstart].[OpenAPI quickstart]: /docs/get-started/quickstart/openapi

To deploy BAML as a RESTful API, you'll need to do three things:

* host your BAML functions in a Docker container
* update your app to call it
* run BAML and your app side-by-side using `docker-compose`

Read on to learn how to do this with `docker-compose`.You can also run `baml-cli` in a subprocess from your app directly, and we
  may recommend this approach in the future. Please let us know if you'd
  like to see instructions for doing so, and in what language, by asking in
  [Discord][discord] or [on the GitHub issue][openapi-feedback-github-issue].## Host your BAML functions in a Docker container

In the directory containing your `baml_src/` directory, create a
`baml.Dockerfile` to host your BAML functions in a Docker container:BAML-over-HTTP is currently a preview feature. Please provide feedback either
  in [Discord][discord] or on [GitHub][openapi-feedback-github-issue] so that
  we can stabilize the feature and keep you updated!```docker title="baml.Dockerfile"
FROM node:20

WORKDIR /app
COPY baml_src/ .

# If you want to pin to a specific version (which we recommend):
# RUN npm install -g @boundaryml/baml@VERSION
RUN npm install -g @boundaryml/baml

CMD baml-cli serve --preview --port 2024
```Assuming you intend to run your own application in a container, we recommend
    using `docker-compose` to run your app and BAML-over-HTTP side-by-side:

    ```bash
    docker compose up --build --force-recreate
    ```

    ```yaml title="docker-compose.yaml"
    services:
      baml-over-http:
        build:
          # This will build baml.Dockerfile when you run docker-compose up
          context: .
          dockerfile: baml.Dockerfile
        healthcheck:
          test: [ "CMD", "curl", "-f", "http://localhost:2024/_debug/ping" ]
          interval: 1s
          timeout: 100ms
          retries: 3
        # This allows you to 'curl localhost:2024/_debug/ping' from your machine,
        # i.e. the Docker host
        ports:
          - "2024:2024"

      debug-container:
        image: amazonlinux:latest
        depends_on:
          # Wait until the baml-over-http healthcheck passes to start this container
          baml-over-http:
            condition: service_healthy
        command: "curl -v http://baml-over-http:2024/_debug/ping"
    ```To call the BAML server from your laptop (i.e. the host machine), you must use
      `localhost:2024`. You may only reach it as `baml-over-http:2024` from within
      another Docker container.If you don't care about using `docker-compose`, you can just run:

    ```bash
    docker build -t baml-over-http -f baml.Dockerfile .
    docker run -p 2024:2024 baml-over-http
    ```To verify for yourself that BAML-over-HTTP is up and running, you can run:

```bash
curl http://localhost:2024/_debug/ping
```

## Update your app to call it

Update your code to use `BOUNDARY_ENDPOINT`, if set, as the endpoint for your BAML functions.```go
    import (
        "os"
        baml "my-golang-app/baml_client"
    )

    func main() {
        cfg := baml.NewConfiguration()
        if boundaryEndpoint := os.Getenv("BOUNDARY_ENDPOINT"); boundaryEndpoint != "" {
            cfg.BasePath = boundaryEndpoint
        }
        if boundaryApiKey := os.Getenv("BOUNDARY_API_KEY"); boundaryApiKey != "" {
            cfg.DefaultHeader["Authorization"] = "Bearer " + boundaryApiKey
        }
        b := baml.NewAPIClient(cfg).DefaultAPI
        // Use `b` to make API calls
    }
    ``````java
    import com.boundaryml.baml_client.ApiClient;
    import com.boundaryml.baml_client.ApiException;
    import com.boundaryml.baml_client.Configuration;
    import com.boundaryml.baml_client.api.DefaultApi;
    import com.boundaryml.baml_client.auth.*;

    public class ApiExample {
        public static void main(String[] args) {
            ApiClient apiClient = Configuration.getDefaultApiClient();

            String boundaryEndpoint = System.getenv("BOUNDARY_ENDPOINT");
            if (boundaryEndpoint != null && !boundaryEndpoint.isEmpty()) {
                apiClient.setBasePath(boundaryEndpoint);
            }

            String boundaryApiKey = System.getenv("BOUNDARY_API_KEY");
            if (boundaryApiKey != null && !boundaryApiKey.isEmpty()) {
                apiClient.addDefaultHeader("Authorization", "Bearer " + boundaryApiKey);
            }

            DefaultApi apiInstance = new DefaultApi(apiClient);
            // Use `apiInstance` to make API calls
        }
    }
    ``````php
    require_once(__DIR__ . '/vendor/autoload.php');

    $config = BamlClient\Configuration::getDefaultConfiguration();

    $boundaryEndpoint = getenv('BOUNDARY_ENDPOINT');
    $boundaryApiKey = getenv('BOUNDARY_API_KEY');

    if ($boundaryEndpoint) {
        $config->setHost($boundaryEndpoint);
    }

    if ($boundaryApiKey) {
        $config->setAccessToken($boundaryApiKey);
    }

    $apiInstance = new OpenAPI\Client\Api\DefaultApi(
        new GuzzleHttp\Client(),
        $config
    );

    // Use `$apiInstance` to make API calls
    ``````ruby
    require 'baml_client'

    api_client = BamlClient::ApiClient.new

    boundary_endpoint = ENV['BOUNDARY_ENDPOINT']
    if boundary_endpoint
      api_client.host = boundary_endpoint
    end

    boundary_api_key = ENV['BOUNDARY_API_KEY']
    if boundary_api_key
      api_client.default_headers['Authorization'] = "Bearer #{boundary_api_key}"
    end
    b = BamlClient::DefaultApi.new(api_client)
    # Use `b` to make API calls
    ``````rust
    let mut config = baml_client::apis::configuration::Configuration::default();
    if let Some(base_path) = std::env::var("BOUNDARY_ENDPOINT").ok() {
        config.base_path = base_path;
    }
    if let Some(api_key) = std::env::var("BOUNDARY_API_KEY").ok() {
        config.bearer_access_token = Some(api_key);
    }
    // Use `config` to make API calls
    ```## Run your app with docker-compose

Replace `debug-container` with the Dockerfile for your app in the
`docker-compose.yaml` file:

```yaml
services:
  baml-over-http:
    build:
      context: .
      dockerfile: baml.Dockerfile
    networks:
      - my-app-network
    healthcheck:
      test: [ "CMD", "curl", "-f", "http://localhost:2024/_debug/ping" ]
      interval: 1s
      timeout: 100ms
      retries: 3
    ports:
      - "2024:2024"

  my-app:
    build:
      context: .
      dockerfile: my-app.Dockerfile
    depends_on:
      baml-over-http:
        condition: service_healthy
    environment:
      - BAML_ENDPOINT=http://baml-over-http:2024

  debug-container:
    image: amazonlinux:latest
    depends_on:
      baml-over-http:
        condition: service_healthy
    command: sh -c 'curl -v "$${BAML_ENDPOINT}/_debug/ping"'
    environment:
      - BAML_ENDPOINT=http://baml-over-http:2024
```

Additionally, you'll want to make sure that you generate the BAML client at
image build time, because `baml_client/` should not be checked into your repo.

This means that in the CI workflow you use to push your Docker images, you'll
want to do something like this:

```yaml .github/workflows/build-image.yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Build the BAML client
        run: |
          set -eux
          npx @boundaryml/baml generate
          docker build -t my-app .
```

## (Optional) Secure your BAML functions

To secure your BAML server, you can also set a password on it using the
`BAML_PASSWORD` environment variable:```bash
    BAML_PASSWORD=sk-baml-your-secret-password \
      baml-cli serve --preview --port 2024
    ``````docker
    FROM node:20

    WORKDIR /app
    RUN npm install -g @boundaryml/baml
    COPY baml_src/ .

    ENV BAML_PASSWORD=sk-baml-your-secret-password
    CMD baml-cli serve --preview --port 2024
    ```This will require incoming requests to attach your specified password as
authorization metadata. You can verify this by confirming that this returns `403
Forbidden`:

```bash
curl -v "http://localhost:2024/_debug/status"
```

If you attach your password to the request, you'll see that it now returns `200 OK`:```bash
    export BAML_PASSWORD=sk-baml-your-secret-password
    curl "http://baml:${BAML_PASSWORD}@localhost:2024/_debug/status"
    ``````bash
    export BAML_PASSWORD=sk-baml-your-secret-password
    curl "http://localhost:2024/_debug/status" -H "X-BAML-API-KEY: ${BAML_PASSWORD}"
    ````BAML_PASSWORD` will secure all endpoints *except* `/_debug/ping`, so that you
  can always debug the reachability of your BAML server.[discord]: https://discord.gg/BTNBeXGuaS

[openapi-feedback-github-issue]: https://github.com/BoundaryML/baml/issues/892
