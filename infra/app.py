#!/usr/bin/env python3
"""CDK App entry point for DataOps Agent infrastructure."""

import os
import aws_cdk as cdk
from stacks.frontend_stack import FrontendStack
from stacks.api_stack import ApiStack
from stacks.agentcore_stack import AgentCoreStack

app = cdk.App()

env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"),
)

# Configuration from context or defaults
aurora_cluster_id = app.node.try_get_context("auroraClusterId") or ""
aurora_instance_id = app.node.try_get_context("auroraInstanceId") or ""
db_secret_name = app.node.try_get_context("dbSecretName") or "dataops-agent/aurora-credentials"
bedrock_model_id = app.node.try_get_context("bedrockModelId") or "us.anthropic.claude-sonnet-4-20250514-v1:0"
bedrock_guardrail_id = app.node.try_get_context("bedrockGuardrailId") or ""
aurora_security_group_id = app.node.try_get_context("auroraSgId") or ""
vpc_id = app.node.try_get_context("vpcId") or ""

# Stack 1: API (Lambda + API Gateway)
api_stack = ApiStack(
    app, "DataOpsAgentApi",
    env=env,
    aurora_cluster_id=aurora_cluster_id,
    aurora_instance_id=aurora_instance_id,
    db_secret_name=db_secret_name,
    bedrock_model_id=bedrock_model_id,
    bedrock_guardrail_id=bedrock_guardrail_id,
    aurora_security_group_id=aurora_security_group_id,
    vpc_id=vpc_id,
)

# Stack 2: Frontend (S3 + CloudFront)
frontend_stack = FrontendStack(
    app, "DataOpsAgentFrontend",
    env=env,
    api_url=api_stack.api_url,
)

# Stack 3: AgentCore Runtime (optional production deployment)
agentcore_stack = AgentCoreStack(
    app, "DataOpsAgentCore",
    env=env,
    db_secret_name=db_secret_name,
    aurora_cluster_id=aurora_cluster_id,
    aurora_instance_id=aurora_instance_id,
    bedrock_model_id=bedrock_model_id,
    aurora_security_group_id=aurora_security_group_id,
    vpc_id=vpc_id,
)

app.synth()
