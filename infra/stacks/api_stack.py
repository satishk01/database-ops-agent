"""API Stack: Lambda (container) + REST API Gateway with Response Streaming.

Uses API Gateway REST API with ResponseTransferMode=STREAM to support
long-running agent calls (up to 15 minutes) with chunked streaming responses.
This eliminates the 29-second timeout limitation of traditional API Gateway.
"""

from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_iam as iam,
    aws_logs as logs,
    aws_secretsmanager as sm,
    aws_ec2 as ec2,
)


class ApiStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        aurora_cluster_id: str,
        aurora_instance_id: str,
        db_secret_name: str,
        bedrock_model_id: str,
        bedrock_guardrail_id: str,
        aurora_security_group_id: str,
        vpc_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── VPC (lookup existing where Aurora lives) ────────────────────
        vpc = None
        security_group = None
        if vpc_id:
            vpc = ec2.Vpc.from_lookup(self, "Vpc", vpc_id=vpc_id)
        if aurora_security_group_id:
            security_group = ec2.SecurityGroup.from_security_group_id(
                self, "AuroraSg", aurora_security_group_id
            )

        # ── Secrets Manager reference ───────────────────────────────────
        db_secret = sm.Secret.from_secret_name_v2(
            self, "DbSecret", db_secret_name
        )

        # ── Lambda Function (container image) ──────────────────────────
        lambda_fn = _lambda.DockerImageFunction(
            self,
            "DataOpsAgentFn",
            function_name="dataops-agent-api",
            code=_lambda.DockerImageCode.from_image_asset(
                "../backend",
                file="Dockerfile",
            ),
            architecture=_lambda.Architecture.X86_64,
            memory_size=1024,
            timeout=Duration.minutes(15),
            environment={
                "AWS_REGION_NAME": self.region,
                "DB_SECRET_NAME": db_secret_name,
                "AURORA_CLUSTER_ID": aurora_cluster_id,
                "AURORA_INSTANCE_ID": aurora_instance_id,
                "BEDROCK_MODEL_ID": bedrock_model_id,
                "BEDROCK_GUARDRAIL_ID": bedrock_guardrail_id,
                "DB_SSLMODE": "verify-full",
                "DB_SSLROOTCERT": "/var/task/rds-global-bundle.pem",
                "CORS_ORIGINS": "*",
            },
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ) if vpc else None,
            security_groups=[security_group] if security_group else None,
            log_retention=logs.RetentionDays.TWO_WEEKS,
        )

        # ── IAM Permissions ─────────────────────────────────────────────
        lambda_fn.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:ApplyGuardrail",
            ],
            resources=["*"],
        ))
        db_secret.grant_read(lambda_fn)
        lambda_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["rds:DescribeDBClusters", "rds:DescribeDBInstances"],
            resources=["*"],
        ))
        lambda_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["cloudwatch:GetMetricStatistics"],
            resources=["*"],
        ))

        # ── REST API Gateway with Response Streaming ────────────────────
        rest_api = apigw.RestApi(
            self,
            "DataOpsAgentRestApi",
            rest_api_name="dataops-agent-api",
            description="DataOps Agent API with response streaming",
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=100,
                throttling_burst_limit=50,
            ),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["*"],
                max_age=Duration.hours(1),
            ),
        )

        # /api resource
        api_resource = rest_api.root.add_resource("api")

        # /api/chat — POST with streaming
        chat_resource = api_resource.add_resource("chat")

        # /api/health — GET (non-streaming, standard proxy)
        health_resource = api_resource.add_resource("health")
        health_resource.add_method(
            "GET",
            apigw.LambdaIntegration(lambda_fn, proxy=True),
        )

        # ── Streaming integration for /api/chat ────────────────────────
        # Use the response-streaming-invocations URI to enable streaming
        streaming_uri = (
            f"arn:aws:apigateway:{self.region}:lambda:path"
            f"/2021-11-15/functions/{lambda_fn.function_arn}"
            f"/response-streaming-invocations"
        )

        streaming_integration = apigw.Integration(
            type=apigw.IntegrationType.AWS_PROXY,
            integration_http_method="POST",
            uri=streaming_uri,
            options=apigw.IntegrationOptions(
                timeout=Duration.minutes(15),
            ),
        )

        # Use CfnMethod to set ResponseTransferMode: STREAM
        chat_method = chat_resource.add_method(
            "POST",
            streaming_integration,
        )

        # Override the CloudFormation to add ResponseTransferMode
        cfn_method = chat_method.node.default_child
        cfn_method.add_property_override(
            "Integration.ResponseTransferMode", "STREAM"
        )
        cfn_method.add_property_override(
            "Integration.TimeoutInMillis", 900000  # 15 minutes
        )

        # Grant API Gateway permission to invoke Lambda with streaming
        lambda_fn.add_permission(
            "ApiGwStreamingInvoke",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_arn=rest_api.arn_for_execute_api(),
        )

        # ── Outputs ─────────────────────────────────────────────────────
        self.api_url = rest_api.url

        cdk.CfnOutput(self, "ApiUrl", value=rest_api.url,
                       description="REST API Gateway endpoint URL (streaming)")
        cdk.CfnOutput(self, "LambdaFunctionName", value=lambda_fn.function_name)
