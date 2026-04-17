"""Frontend Stack: S3 + CloudFront with OAC."""

from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
)


class FrontendStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        api_url: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── S3 Bucket (private, CloudFront-only access) ────────────────
        site_bucket = s3.Bucket(
            self,
            "SiteBucket",
            bucket_name=f"dataops-agent-frontend-{self.account}-{self.region}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # ── CloudFront Distribution ─────────────────────────────────────
        # Origin Access Control for S3
        oac = cloudfront.S3OriginAccessControl(
            self, "OAC",
            signing=cloudfront.Signing.SIGV4_NO_OVERRIDE,
        )

        # API origin — REST API with /prod stage prefix
        # REST API URL: https://{id}.execute-api.{region}.amazonaws.com/prod/
        api_domain = cdk.Fn.select(2, cdk.Fn.split("/", api_url))

        api_origin = origins.HttpOrigin(
            api_domain,
            origin_path="/prod",
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
        )

        distribution = cloudfront.Distribution(
            self,
            "Distribution",
            comment="DataOps Agent Frontend",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    site_bucket,
                    origin_access_control=oac,
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            additional_behaviors={
                "/api/*": cloudfront.BehaviorOptions(
                    origin=api_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                ),
            },
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
            ],
        )

        # ── Deploy built frontend to S3 ────────────────────────────────
        s3deploy.BucketDeployment(
            self,
            "DeploySite",
            sources=[s3deploy.Source.asset("../frontend/dist")],
            destination_bucket=site_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )

        # ── Outputs ─────────────────────────────────────────────────────
        cdk.CfnOutput(
            self, "CloudFrontUrl",
            value=f"https://{distribution.distribution_domain_name}",
            description="CloudFront distribution URL",
        )
        cdk.CfnOutput(
            self, "S3BucketName",
            value=site_bucket.bucket_name,
            description="S3 bucket for frontend assets",
        )
