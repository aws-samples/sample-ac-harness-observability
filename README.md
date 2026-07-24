# AgentCore Harness Observability Sample

End-to-end example showing how to propagate OpenTelemetry (OTel) trace context and baggage from a client application (AWS Lambda) through Amazon Bedrock AgentCore Harness to a Strands agent, with traces exported to CloudWatch and third-party observability tools.

## Architecture

```
+---------------------+        +-------------------------------+        +---------------------------+
|   AWS Lambda        |        |  AgentCore Harness            |        |  Observability Backend    |
|   (Client App)      |        |  (Managed Agent Loop)         |        |                           |
|                     |        |                               |        |                           |
|  +--------------+   |  OTel  |  +-------------------------+  |  OTLP  |  +---------------------+  |
|  | ADOT Layer   |---+------->|  | Strands Agent           |--+------->|  | CloudWatch / X-Ray  |  |
|  | (auto-instr) |   |  hdrs  |  | (Claude Sonnet 4.6)     |  | spans  |  +---------------------+  |
|  +--------------+   |        |  +-------------------------+  |        |                           |
|        |            |        |        |                      |        |  +---------------------+  |
|  +--------------+   |        |  +-----------+                |        |  | 3P OTel Collector   |  |
|  | Custom Span  |   |        |  | Tools     |                |        |  | (Datadog, Grafana,  |  |
|  | (call_harness)|  |        |  | Browser   |                |        |  |  New Relic, etc.)   |  |
|  +--------------+   |        |  | Code Intr.|                |        |  +---------------------+  |
|        |            |        |  +-----------+                |        |                           |
|  +--------------+   |        +-------------------------------+        +---------------------------+
|  | Baggage      |   |
|  | tenant.id    |   |
|  | session.id   |   |
|  +--------------+   |
+---------------------+
```

## Request Flow: Trace and Baggage Propagation

The following sequence shows how W3C `traceparent`, `tracestate`, `baggage`, and AWS X-Ray headers propagate across service boundaries:

```
1. Lambda Invocation
   |
   |  [X-Ray active tracing creates root span]
   |  [ADOT layer initializes TracerProvider + X-Ray propagator]
   |
   v
2. handler.py: lambda_handler()
   |
   |  - Attaches baggage: tenant.id, session.id
   |  - Creates custom span: "call_harness"
   |
   v
3. boto3: invoke_harness() API call
   |
   |  [inject_otel_headers() intercepts the request]
   |  [Injects headers into HTTP request:]
   |     traceparent:     00-<trace_id>-<span_id>-01
   |     tracestate:      ...
   |     baggage:         tenant.id=customer_xyz,session.id=harness_demo_...
   |     X-Amzn-Trace-Id: Root=1-...;Parent=...;Sampled=1
   |
   v
4. AgentCore Harness (receives propagated context)
   |
   |  - Extracts trace context from incoming headers
   |  - Creates child spans under the same trace
   |  - Copies baggage keys to span attributes
   |    (via OTEL_BAGGAGE_SPAN_ATTRIBUTE_KEYS allow-list)
   |
   v
5. Strands Agent (orchestrated by Harness)
   |
   |  - Executes agent loop (model calls, tool use)
   |  - Each iteration produces spans linked to the same trace
   |  - Baggage attributes (tenant.id, session.id) attached to all spans
   |
   v
6. OTLP Export
   |
   +---> CloudWatch / X-Ray (native integration)
   +---> 3P Collector (if configured via OTLP endpoint)
```

All spans across Lambda, Harness, and the Strands agent share the same trace ID, enabling end-to-end distributed tracing from client invocation through agent reasoning and tool execution.

## Best Practices

This sample demonstrates several patterns for observability in agent-based systems.

### Custom spans for client-side tracking

Add a custom OTel span (`call_harness`) around the `invoke_harness` call. This provides a clear boundary in the trace between your application logic and the agent execution, with duration and error tracking.

### Baggage for dynamic context propagation

Values like `tenant.id` and `session.id` are best known by the client application, not the agent. Attach them as W3C baggage at the call site so they propagate automatically to all downstream spans without modifying the agent code.

### Explicit OTel header injection

The `invoke_harness` API does not auto-propagate trace headers through the boto3 SDK. Use a boto3 event hook (`before-send`) with `opentelemetry.propagate.inject()` to add `traceparent`, `baggage`, and `X-Amzn-Trace-Id` headers to every outbound request.

### Baggage attribute allow-listing

OTel instrumentation does not copy baggage to span attributes by default (security concern). Set `OTEL_BAGGAGE_SPAN_ATTRIBUTE_KEYS` on both the Lambda and the Harness to explicitly allow-list which baggage keys become span attributes.

### ADOT Lambda layer for auto-instrumentation

Use the AWS Distro for OpenTelemetry (ADOT) Lambda layer with the `INSTRUMENT_HANDLER` exec wrapper. It configures the `TracerProvider`, X-Ray ID generator, propagators, and OTLP exporter automatically. Custom spans created via `trace.get_tracer()` at invocation time integrate seamlessly.

In addition to the ADOT Lambda layer, bundle the latest ADOT [≥v0.18.0] alongside the Lambda handler and set the following environment variables to activate the latest OTel instrumentation improvements:

```
AGENT_OBSERVABILITY_ENABLED=true
AWS_GENAI_CONTENT_EXTRACTION_OPT_OUT=true
OTEL_AWS_APPLICATION_SIGNALS_ENABLED=false
OTEL_PROPAGATORS=tracecontext,baggage,xray-lambda,xray
OTEL_PYTHON_DISTRO=aws_distro
OTEL_PYTHON_CONFIGURATOR=aws_configurator
OTEL_LOGS_EXPORTER=none
OTEL_METRICS_EXPORTER=none
OTEL_TRACES_EXPORTER=otlp
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
```

### Harness OTel configuration: reducing span noise and enabling semantic conventions

By default, the Harness runtime auto-instruments all outbound HTTP libraries (urllib3, requests, botocore, httpx, etc.). This creates excessive low-level spans that add noise to traces and, critically, can interfere with baggage propagation by creating intermediate spans that don't carry baggage context forward.

Disable instrumentations that produce noisy internal spans and exclude health-check URLs:

```
OTEL_PYTHON_EXCLUDED_URLS=169.254.169.254,/ping,/health
OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=urllib3,requests,botocore,aiohttp-client,httpx
```

To future-proof your traces for the evolving GenAI semantic conventions, opt in to the latest experimental attributes. This ensures your spans include standardized GenAI fields (model ID, token counts, etc.) as the OTel specification stabilizes:

```
AWS_GENAI_CONTENT_EXTRACTION_OPT_OUT=true
OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental,gen_ai_span_attributes_only
```

- `AWS_GENAI_CONTENT_EXTRACTION_OPT_OUT` prevents prompt/response content from being captured in spans and moved to logs (privacy/cost concern). Requires ADOT [≥v0.17.1].
- `OTEL_SEMCONV_STABILITY_OPT_IN` enables the latest GenAI semantic convention attributes so your traces align with the emerging OTel standard as it matures. Strands [≥v1.48.0] will use latest Gen AI semantic convention and use attributes instead of now deprecated events to capture LLM input, output, prompts, and tool call.

### Sending Harness telemetry to a third-party collector

To export Harness agent telemetry to a third-party observability platform (Langfuse, Datadog, Grafana, New Relic, etc.), configure the OTLP endpoint and authentication headers as Harness environment variables:

```
OTEL_EXPORTER_OTLP_ENDPOINT=https://otel-collector.example.com:4318
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer <your-api-key>,X-Custom-Header=value
```

- `OTEL_EXPORTER_OTLP_ENDPOINT` — the URL of your third-party OTel collector's OTLP receiver (HTTP/protobuf).
- `OTEL_EXPORTER_OTLP_HEADERS` — comma-separated key=value pairs for authentication or routing headers required by your collector.

> **Note:** Configuring a third-party OTLP endpoint on the Harness sends agent telemetry (spans from the Strands agent loop, model calls, and tool executions) to your collector. Lambda telemetry and AgentCore platform telemetry continue to be sent to CloudWatch / X-Ray regardless of this setting.


## Project Structure

```
.
├── app/lambda/invoke_harness/    # Lambda function code
│   ├── handler.py                # Entry point: baggage setup, agent invocation
│   ├── custom_span.py            # OTel span decorator + header injection
│   └── requirements.txt          # Python dependencies
├── cdk/                          # CDK infrastructure
│   ├── app.py                    # CDK app entry point
│   ├── modules/
│   │   ├── harness.py            # AgentCore Harness construct
│   │   └── lambda_client.py      # Lambda + ADOT layer construct
│   └── stacks/
│       └── ac_harness_demo_stack.py
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.13+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Node.js 24.x or later (for CDK CLI)
- AWS credentials configured (`aws configure` or environment variables)
- Docker (required for Lambda dependency bundling)

### Setup

1. Clone and install dependencies:

```bash
git clone <repository-url>
cd <repository-directory>
uv sync --refresh --reinstall
```

2. Configure environment variables:

```bash
cp cdk/.env.cdk.sample cdk/.env
# Edit cdk/.env with your values
```

3. Deploy the stack:

```bash
cd cdk
uv run --env-file .env cdk deploy --yes
```

4. Invoke the agent:

Navigate to the `invoke_harness` Lambda function in the AWS Console and use the **Test** button to trigger an invocation. Traces appear in CloudWatch X-Ray within a few seconds.

## License

This project is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file for details.
