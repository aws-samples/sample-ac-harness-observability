"""CDK application stack to deploy all relevant resources"""

from aws_cdk import (
    Stack,
)
from constructs import Construct
from modules.lambda_fn import LambdaFn
from modules.harness import HarnessAgent


class ACHarnessDemoStack(Stack):
    """deploys complete application stack"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        env_harness_arn = self.node.try_get_context(
            "HARNESS_ARN"
        )
        if not env_harness_arn:
            # Harness ARN not configured. Create harness agent
            harness = HarnessAgent(self, "harness_demo")
            env_harness_arn = harness.harness.attr_arn
        LambdaFn(self, "lambda_fn", harness_arn=env_harness_arn)
