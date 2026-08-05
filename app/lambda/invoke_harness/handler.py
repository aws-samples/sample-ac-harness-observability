"""Invoke harness"""
# pylint:disable=W1203,W0718

import os
import json
from typing import Any
from datetime import datetime
import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from opentelemetry import baggage, context as trace_context
from custom_span import otel_span_decorator, inject_otel_headers

HARNESS_ARN = os.getenv("HARNESS_ARN")
CONTEXT = "I live in NY"

logger = Logger(service="invoke_harness")
client = boto3.client("bedrock-agentcore", region_name="us-east-1")

# Register the event hook so every API call carries the trace context
client.meta.events.register("before-send.bedrock-agentcore.*", inject_otel_headers)


def _session_id() -> str:
    """Generate custom agent session id"""
    # Session ID must be ≥33 chars
    return f"harness_demo_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def _response(status_code: int, body: str) -> dict[str, Any]:
    """Build a standard Lambda response."""
    return {"statusCode": status_code, "body": body}


@otel_span_decorator(span_name="call_harness")
def call_agent(session_id, query) -> str:
    """Call harness agent and prints response"""
    logger.info(f"[SessionID={session_id}] {query}")

    response = client.invoke_harness(
        harnessArn=HARNESS_ARN,
        runtimeSessionId=session_id,
        messages=[
            {"role": "user", "content": [{"text": query}]},
            {"role": "user", "content": [{"text": CONTEXT}]}
        ]
    )

    # Stream the response
    response_str = ""
    for event in response["stream"]:
        if "contentBlockDelta" in event:
            delta = event["contentBlockDelta"].get("delta", {})
            if "text" in delta:
                response_str += delta["text"]
                # print(delta["text"], end="", flush=True)
                logger.debug(delta["text"])
        elif "runtimeClientError" in event:
            logger.error(f"\nError: {event['runtimeClientError']['message']}")

    return response_str


def lambda_handler(event: dict, context: LambdaContext) -> dict[str, Any]:
    """Invoke harness agent"""
    logger.debug("Boto3 version: %s", boto3.__version__)
    logger.debug("Event: %s", json.dumps(event, default=str))
    logger.debug("Context: %s", json.dumps(context.__dict__, default=str))

    # Extract prompt and tenant.id from event, falling back to defaults
    prompt = (event or {}).get("prompt", "what is the capital of my state?")
    tenant_id = (event or {}).get("tenant.id", "customer_xyz")

    session_id = _session_id()
    ctx = baggage.set_baggage("tenant.id", tenant_id)
    ctx = baggage.set_baggage("session.id", session_id, ctx)
    trace_context.attach(ctx)

    response_str = call_agent(session_id, prompt)
    return _response(200, response_str)


def main():
    """Main routine to make multi-turn query"""
    session_id = _session_id()
    call_agent(session_id, "what is the capital of my state?")


if __name__ == "__main__":
    main()
