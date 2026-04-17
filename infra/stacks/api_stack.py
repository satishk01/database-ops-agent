"""API Stack: Lambda (container) + API Gateway HTTP API."""

from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as integrations,
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
            timeout=Duration.minutes(5),
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
                "POWERTOOLS_SERVICE_NAME": "dataops-agent",
            },
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ) if vpc else None,
            security_groups=[security_group] if security_group else None,
            log_retention=logs.RetentionDays.TWO_WEEKS,
        )

        # ── IAM Permissions ─────────────────────────────────────────────
        # Bedrock invoke
        lambda_fn.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:ApplyGuardrail",
            ],
            resources=["*"],
        ))

        # Secrets Manager read
        db_secret.grant_read(lambda_fn)

        # RDS describe (for list_aurora_clusters, instance details)
        lambda_fn.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "rds:DescribeDBClusters",
                "rds:DescribeDBInstances",
            ],
            resources=["*"],
        ))

        # CloudWatch metrics read (for CPU, connections, storage, replica lag)
        lambda_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["cloudwatch:GetMetricStatistics"],
            resources=["*"],
        ))

        # ── API Gateway HTTP API ────────────────────────────────────────
        http_api = apigwv2.HttpApi(
            self,
            "DataOpsAgentHttpApi",
            api_name="dataops-agent-api",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[apigwv2.CorsHttpMethod.ANY],
                allow_headers=["*"],
                max_age=Duration.hours(1),
            ),
        )

        lambda_integration = integrations.HttpLambdaIntegration(
            "LambdaIntegration", lambda_fn
        )

        http_api.add_routes(
            path="/api/{proxy+}",
            methods=[apigwv2.HttpMethod.ANY],
            integration=lambda_integration,
        )

        # ── Outputs ─────────────────────────────────────────────────────
        self.api_url = http_api.url

        cdk.CfnOutput(self, "ApiUrl", value=http_api.url or "",
                       description="API Gateway endpoint URL")
        cdk.CfnOutput(self, "LambdaFunctionName", value=lambda_fn.function_name,
                       description="Lambda function name")
