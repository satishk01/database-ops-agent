#!/usr/bin/env python3
"""
Deploy the DataOps Agent to Bedrock AgentCore Runtime.

Run after CDK deploy to register the container with AgentCore:
  python deploy_agentcore.py \
    --image-uri <ECR_IMAGE_URI> \
    --role-arn <AGENTCORE_ROLE_ARN> \
    --region us-east-1

The CDK stack outputs the exact command to run.
"""

import argparse
import json
import time
import boto3


def create_runtime(client, image_uri: str, role_arn: str) -> str:
    """Create an AgentCore runtime for the DataOps agent."""
    print("Creating AgentCore runtime...")
    response = client.create_agent_runtime(
        agentRuntimeName="dataops-supervisor-agent",
        description="Autonomous Database Operations Supervisor Agent — "
                    "diagnoses Aurora PostgreSQL issues and implements safe fixes",
        agentRuntimeArtifact={
            "containerConfiguration": {
                "containerUri": image_uri,
            }
        },
        roleArn=role_arn,
        networkConfiguration={
            "networkMode": "PUBLIC",
        },
    )
    runtime_id = response["agentRuntimeId"]
    print(f"  Runtime ID: {runtime_id}")
    return runtime_id


def wait_for_runtime(client, runtime_id: str, timeout: int = 300):
    """Wait for the AgentCore runtime to become ACTIVE."""
    print("Waiting for runtime to become ACTIVE...")
    start = time.time()
    while time.time() - start < timeout:
        response = client.get_agent_runtime(agentRuntimeId=runtime_id)
        status = response.get("status", "UNKNOWN")
        print(f"  Status: {status}")
        if status == "ACTIVE":
            return True
        if status in ("FAILED", "DELETING"):
            print(f"  Runtime failed with status: {status}")
            return False
        time.sleep(10)
    print("  Timed out waiting for runtime.")
    return False


def create_endpoint(client, runtime_id: str) -> str:
    """Create an invocation endpoint for the AgentCore runtime."""
    print("Creating AgentCore endpoint...")
    response = client.create_agent_runtime_endpoint(
        agentRuntimeId=runtime_id,
        name="dataops-supervisor-endpoint",
        description="Production endpoint for DataOps Supervisor Agent",
    )
    endpoint_id = response["agentRuntimeEndpointId"]
    print(f"  Endpoint ID: {endpoint_id}")
    return endpoint_id


def wait_for_endpoint(client, endpoint_id: str, timeout: int = 300):
    """Wait for the endpoint to become READY."""
    print("Waiting for endpoint to become READY...")
    start = time.time()
    while time.time() - start < timeout:
        response = client.get_agent_runtime_endpoint(
            agentRuntimeEndpointId=endpoint_id
        )
        status = response.get("status", "UNKNOWN")
        print(f"  Status: {status}")
        if status == "READY":
            return True
        if status in ("FAILED", "DELETING"):
            print(f"  Endpoint failed with status: {status}")
            return False
        time.sleep(10)
    print("  Timed out waiting for endpoint.")
    return False


def main():
    parser = argparse.ArgumentParser(description="Deploy DataOps Agent to AgentCore")
    parser.add_argument("--image-uri", required=True, help="ECR container image URI")
    parser.add_argument("--role-arn", required=True, help="IAM role ARN for AgentCore")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    args = parser.parse_args()

    client = boto3.client("bedrock-agentcore", region_name=args.region)

    print("=" * 60)
    print("DataOps Agent — AgentCore Deployment")
    print("=" * 60)
    print(f"  Image:  {args.image_uri}")
    print(f"  Role:   {args.role_arn}")
    print(f"  Region: {args.region}")
    print()

    runtime_id = create_runtime(client, args.image_uri, args.role_arn)
    if not wait_for_runtime(client, runtime_id):
        print("FAILED: Runtime did not become active.")
        return

    endpoint_id = create_endpoint(client, runtime_id)
    if not wait_for_endpoint(client, endpoint_id):
        print("FAILED: Endpoint did not become ready.")
        return

    print()
    print("=" * 60)
    print("Deployment complete!")
    print(f"  Runtime ID:  {runtime_id}")
    print(f"  Endpoint ID: {endpoint_id}")
    print()
    print("Test with:")
    print(f'  aws bedrock-agentcore invoke-agent-runtime \\')
    print(f'    --agent-runtime-endpoint-id {endpoint_id} \\')
    print(f'    --payload \'{{"message": "Run a health check"}}\'')
    print("=" * 60)


if __name__ == "__main__":
    main()
