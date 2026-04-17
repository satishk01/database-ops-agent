"""AgentCore Stack: Bedrock AgentCore Runtime deployment.

This stack creates the AgentCore runtime and endpoint for the
DataOps Supervisor Agent. AgentCore provides a managed, serverless
runtime for AI agents with built-in scaling and monitoring.

The agent container is deployed to AgentCore which handles:
- Auto-scaling based on invocation load
- Health monitoring and restart
- VPC networking to reach Aurora
- IAM-based invocation security
"""

from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_ecr_assets as ecr_assets,
    aws_ec2 as ec2,
    aws_secretsmanager as sm,
    CustomResource,
    custom_resources as cr,
    aws_lambda as _lambda,
    Duration,
    aws_logs as logs,
)


class AgentCoreStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        db_secret_name: str,
        aurora_cluster_id: str,
        aurora_instance_id: str,
        bedrock_model_id: str,
        aurora_security_group_id: str,
        vpc_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Container Image ─────────────────────────────────────────────
        image_asset = ecr_assets.DockerImageAsset(
            self, "AgentImage",
            directory="../backend",
            file="Dockerfile.agentcore",
        )

        # ── IAM Role for AgentCore Runtime ──────────────────────────────
        agentcore_role = iam.Role(
            self,
            "AgentCoreRole",
            role_name="dataops-agentcore-runtime-role",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("bedrock.amazonaws.com"),
                iam.ServicePrincipal("agentcore.bedrock.amazonaws.com"),
            ),
        )

        # Bedrock model invocation
        agentcore_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:ApplyGuardrail",
            ],
            resources=["*"],
        ))

        # Secrets Manager
        db_secret = sm.Secret.from_secret_name_v2(self, "DbSecret", db_secret_name)
        db_secret.grant_read(agentcore_role)

        # RDS describe
        agentcore_role.add_to_policy(iam.PolicyStatement(
            actions=["rds:DescribeDBClusters", "rds:DescribeDBInstances"],
            resources=["*"],
        ))

        # CloudWatch metrics
        agentcore_role.add_to_policy(iam.PolicyStatement(
            actions=["cloudwatch:GetMetricStatistics"],
            resources=["*"],
        ))

        # ECR pull
        agentcore_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "ecr:GetDownloadUrlForLayer",
                "ecr:BatchGetImage",
                "ecr:GetAuthorizationToken",
            ],
            resources=["*"],
        ))

        # CloudWatch Logs for AgentCore
        agentcore_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
            ],
            resources=["*"],
        ))

        # ── Outputs ─────────────────────────────────────────────────────
        # AgentCore doesn't have L2 CDK constructs yet, so we output
        # the values needed for the CLI/SDK deployment script.
        cdk.CfnOutput(
            self, "AgentCoreRoleArn",
            value=agentcore_role.role_arn,
            description="IAM Role ARN for AgentCore runtime",
        )
        cdk.CfnOutput(
            self, "ContainerImageUri",
            value=image_asset.image_uri,
            description="ECR image URI for AgentCore container",
        )
        cdk.CfnOutput(
            self, "DeployCommand",
            value=(
                f"python deploy_agentcore.py "
                f"--image-uri {image_asset.image_uri} "
                f"--role-arn {agentcore_role.role_arn} "
                f"--region {self.region}"
            ),
            description="Run this command to register the agent with AgentCore",
        )
