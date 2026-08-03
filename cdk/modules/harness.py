"""Deploys harness agent"""

from aws_cdk import (
    Stack,
    CfnOutput,
    aws_iam as iam,
    aws_bedrockagentcore as bedrockagentcore,
)
from constructs import Construct


class HarnessAgent(Construct):
    """CDK construct for AgentCore Harness deployment"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        stack = Stack.of(self)

        env_vars = {
            # [recommended] Reduce span noise
            "OTEL_PYTHON_EXCLUDED_URLS": "169.254.169.254,/ping,/health",
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": (
                "urllib3,requests,botocore,aiohttp-client,httpx"
            ),

            # [recommended] GenAI semantic convention stability
            "AWS_GENAI_CONTENT_EXTRACTION_OPT_OUT": "true",
            "OTEL_SEMCONV_STABILITY_OPT_IN": (
                "gen_ai_latest_experimental,gen_ai_span_attributes_only"
            ),
        }

        # [required] Allow-list baggage attributes
        env_baggage_keys = self.node.try_get_context(
            "OTEL_BAGGAGE_SPAN_ATTRIBUTE_KEYS"
        )
        if env_baggage_keys:
            env_vars["OTEL_BAGGAGE_SPAN_ATTRIBUTE_KEYS"] = env_baggage_keys
        else:
            env_vars["OTEL_BAGGAGE_SPAN_ATTRIBUTE_KEYS"] = (
                "harness.id,harness.endpoint.qualifier,session.id"
            )

        # Enable third-party observability
        env_otlp_endpoint = self.node.try_get_context(
            "OTEL_EXPORTER_OTLP_ENDPOINT"
        )
        env_otlp_headers = self.node.try_get_context(
            "OTEL_EXPORTER_OTLP_HEADERS"
        )
        if env_otlp_endpoint and env_otlp_headers:
            env_vars["OTEL_EXPORTER_OTLP_ENDPOINT"] = env_otlp_endpoint
            env_vars["OTEL_EXPORTER_OTLP_HEADERS"] = env_otlp_headers

        # Execution role for the harness
        self.execution_role = iam.Role(
            self, "HarnessExecutionRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            inline_policies={
                "BedrockModelAccess": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "bedrock:InvokeModel",
                                "bedrock:InvokeModelWithResponseStream"
                            ],
                            resources=[
                                "arn:aws:bedrock:*::foundation-model/*",
                                f"arn:aws:bedrock:{stack.region}:{stack.account}:*"
                            ],
                        )
                    ]
                ),
                "EcrPublicTokenAccess": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["ecr-public:GetAuthorizationToken"],
                            resources=["*"],
                        )
                    ]
                ),
                "StsForEcrPublicPull": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["sts:GetServiceBearerToken"],
                            resources=["*"],
                        )
                    ]
                ),
                "XRayTracingAccess": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "xray:PutTraceSegments",
                                "xray:PutTelemetryRecords",
                                "xray:GetSamplingRules",
                                "xray:GetSamplingTargets"
                            ],
                            resources=["*"],
                        )
                    ]
                ),
                "CloudWatchLogsGroup": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "logs:CreateLogGroup",
                                "logs:DescribeLogStreams"
                            ],
                            resources=[
                                f"arn:aws:logs:{stack.region}:{stack.account}:log-group:/aws/bedrock-agentcore/runtimes/*"
                            ],
                        )
                    ]
                ),
                "CloudWatchLogsDescribeGroups": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["logs:DescribeLogGroups"],
                            resources=[
                                f"arn:aws:logs:{stack.region}:{stack.account}:log-group:*"
                            ],
                        )
                    ]
                ),
                "CloudWatchLogsStream": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "logs:CreateLogStream",
                                "logs:PutLogEvents"
                            ],
                            resources=[
                                f"arn:aws:logs:{stack.region}:{stack.account}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
                            ],
                        )
                    ]
                ),
                "CloudWatchMetricsPublish": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["cloudwatch:PutMetricData"],
                            resources=["*"],
                            conditions={
                                "StringEquals": {
                                    "cloudwatch:namespace": "bedrock-agentcore"
                                }
                            }
                        )
                    ]
                ),
                "AgentCoreWorkloadIdentity": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "bedrock-agentcore:GetWorkloadAccessToken",
                                "bedrock-agentcore:GetWorkloadAccessTokenForJWT"
                            ],
                            resources=[
                                f"arn:aws:bedrock-agentcore:{stack.region}:{stack.account}:workload-identity-directory/default",
                                f"arn:aws:bedrock-agentcore:{stack.region}:{stack.account}:workload-identity-directory/default/workload-identity/harness_*"
                            ],
                        )
                    ]
                ),
                "AgentCoreBrowserDefault": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "bedrock-agentcore:StartBrowserSession",
                                "bedrock-agentcore:StopBrowserSession",
                                "bedrock-agentcore:GetBrowserSession",
                                "bedrock-agentcore:ListBrowserSessions",
                                "bedrock-agentcore:UpdateBrowserStream",
                                "bedrock-agentcore:ConnectBrowserAutomationStream",
                                "bedrock-agentcore:ConnectBrowserLiveViewStream"
                            ],
                            resources=[
                                f"arn:aws:bedrock-agentcore:{stack.region}:aws:browser/*",
                            ],
                        )
                    ]
                ),
                "AgentCoreCodeInterpreterDefault": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "bedrock-agentcore:StartCodeInterpreterSession",
                                "bedrock-agentcore:StopCodeInterpreterSession",
                                "bedrock-agentcore:GetCodeInterpreterSession",
                                "bedrock-agentcore:ListCodeInterpreterSessions",
                                "bedrock-agentcore:InvokeCodeInterpreter"
                            ],
                            resources=[
                                f"arn:aws:bedrock-agentcore:{stack.region}:aws:code-interpreter/*"
                            ],
                        )
                    ]
                )
            },
        )

        # Create the AgentCore Harness
        self.harness = bedrockagentcore.CfnHarness(
            self, "Harness",
            harness_name="ac_harness_demo",
            execution_role_arn=self.execution_role.role_arn,
            model=bedrockagentcore.CfnHarness.HarnessModelConfigurationProperty(
                bedrock_model_config=bedrockagentcore.CfnHarness.HarnessBedrockModelConfigProperty(
                    model_id="global.anthropic.claude-sonnet-4-6",
                ),
            ),
            system_prompt=[
                bedrockagentcore.CfnHarness.HarnessSystemContentBlockProperty(
                    text="You are a helpful AI assistant."
                )
            ],
            environment_variables=env_vars,
            memory=bedrockagentcore.CfnHarness.HarnessMemoryConfigurationProperty(disabled={})
        )

        CfnOutput(
            self, "HarnessArn",
            description="AgentCore Harness ARN",
            value=self.harness.attr_arn,
        )
