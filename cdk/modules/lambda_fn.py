"""Deploys invoke harness Lambda client"""

from pathlib import Path
from aws_cdk import (
    Stack,
    BundlingOptions,
    CfnOutput,
    aws_lambda as _lambda,
    aws_iam as iam,
    Duration,
)
from aws_cdk.aws_lambda import (
    AdotLambdaExecWrapper,
    AdotLayerVersion,
    AdotLambdaLayerPythonSdkVersion
)
from constructs import Construct

_TOOLS_DIR = str(
    Path(__file__).resolve().parent / ".." / ".." / "app" / "lambda" / "invoke_harness"
)


class LambdaFn(Construct):
    """CDK construct for invoke harness Lambda client deployment"""

    def __init__(self, scope: Construct, construct_id: str, harness_arn: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        stack = Stack.of(self)

        env_vars = {
            # Application configurations [user configured]
            "HARNESS_ARN": harness_arn,
            "POWERTOOLS_LOG_LEVEL": "INFO",

            # Lambda OTEL configurations [do not modify]
            "AWS_LAMBDA_EXEC_WRAPPER": "/opt/otel-instrument",
            "AGENT_OBSERVABILITY_ENABLED": "true",
            "AWS_GENAI_CONTENT_EXTRACTION_OPT_OUT": "true",
            "OTEL_AWS_APPLICATION_SIGNALS_ENABLED": "false",
            "OTEL_PROPAGATORS": "tracecontext,baggage,xray-lambda,xray",
            "OTEL_LOGS_EXPORTER": "none",
            "OTEL_METRICS_EXPORTER": "none",
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",

            "OTEL_PYTHON_DISTRO": "aws_distro",
            "OTEL_PYTHON_CONFIGURATOR": "aws_configurator",
        }

        # [required] Allow-list baggage attributes
        env_baggage_keys = self.node.try_get_context(
            "OTEL_BAGGAGE_SPAN_ATTRIBUTE_KEYS"
        )
        if env_baggage_keys:
            env_vars["OTEL_BAGGAGE_SPAN_ATTRIBUTE_KEYS"] = env_baggage_keys
        else:
            env_vars["OTEL_BAGGAGE_SPAN_ATTRIBUTE_KEYS"] = (
                "harness.id,harness.endpoint.qualifier,session.id,tenant.id"
            )

        # tracing = _lambda.Tracing.ACTIVE
        tracing = _lambda.Tracing.DISABLED
        # AWS-managed Lambda layers
        otel_layer = _lambda.LayerVersion.from_layer_version_arn(
            self, "AWSOpenTelemetryDistroPython",
            f"arn:aws:lambda:{stack.region}:901920570463:layer:AWSOpenTelemetryDistroPython:29"
        )
        powertools_layer = _lambda.LayerVersion.from_layer_version_arn(
            self, "AWSLambdaPowertoolsPythonV3",
            f"arn:aws:lambda:{stack.region}:017000801446:layer:AWSLambdaPowertoolsPythonV3-python313-arm64:33"
        )
        # adot_layer = _lambda.AdotInstrumentationConfig(
        #     layer_version=AdotLayerVersion.from_python_sdk_layer_version(
        #         AdotLambdaLayerPythonSdkVersion.LATEST
        #     ),
        #     exec_wrapper=AdotLambdaExecWrapper.INSTRUMENT_HANDLER
        # )

        self.lambda_fn = _lambda.Function(
            self, 'invoke_harness',
            runtime=_lambda.Runtime.PYTHON_3_13,
            code=_lambda.Code.from_asset(
                _TOOLS_DIR,
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_13.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output"
                    ],
                ),
            ),
            handler='handler.lambda_handler',
            timeout=Duration.minutes(5),
            memory_size=128,
            environment=env_vars,
            tracing=tracing,
            layers=[otel_layer, powertools_layer],
        )
        self.lambda_fn.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "CloudWatchLambdaApplicationSignalsExecutionRolePolicy"
            )
        )
        self.lambda_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:InvokeHarness",
                    "bedrock-agentcore:InvokeAgentRuntime",
                    "bedrock-agentcore:InvokeAgentRuntimeForUser",
                    "bedrock-agentcore:InvokeAgentRuntimeCommand",
                ],
                # resources=[env_harness_arn],
                resources=["*"],
            )
        )
        CfnOutput(
            self, "lambda_invoke_harness_arn",
            description="Lambda based MCP tool for Orders",
            value=self.lambda_fn.function_arn
        )
