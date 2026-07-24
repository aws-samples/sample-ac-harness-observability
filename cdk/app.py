#!/usr/bin/env python3
"""Build and deploy CDK application stack"""

import os

import aws_cdk as cdk

from stacks.ac_harness_demo_stack import ACHarnessDemoStack

# CDK context keys that can be set via environment variables
# (e.g. from .env.cdk.mon when using `uv run --env-file .env.cdk.mon cdk deploy`)
_ENV_CONTEXT_KEYS = [
    "OTEL_BAGGAGE_SPAN_ATTRIBUTE_KEYS",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_HEADERS",
    "HARNESS_ARN",
]

app = cdk.App()

# Merge environment variables into CDK context (CLI -c flags take precedence)
for key in _ENV_CONTEXT_KEYS:
    if app.node.try_get_context(key) is None and os.environ.get(key):
        app.node.set_context(key, os.environ[key])

ACHarnessDemoStack(
    app, "ac-harness-demo",
)

app.synth()
