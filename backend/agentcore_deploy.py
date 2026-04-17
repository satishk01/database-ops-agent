"""
Bedrock AgentCore Deployment Script.

This script demonstrates how to deploy the DataOps Supervisor Agent
to AWS Bedrock AgentCore Runtime for production use.

Prerequisites:
  - AWS CLI configured with appropriate permissions
  - Bedrock AgentCore access enabled in your account
  - pip install boto3

Usage:
  python agentcore_deploy.py
"""

import json
import boto3
from app.config import settings


def deploy_to_agentcore():
    """Deploy the supervisor agent to Bedrock AgentCore Runtime."""
    client = boto3.client("bedrock-agentcore", region_name=settings.AWS_REGION)

    # Step 1: Create the AgentCore runtime
    print("Creating AgentCore runtime...")
    runtime_response = client.create_agent_runtime(
        agentRuntimeName="dataops-supervisor-agent",
        description="Autonomous Database Operations Supervisor Agent",
        agentRuntimeArtifact={
            "containerConfiguration": {
                "containerUri": "YOUR_ECR_IMAGE_URI",  # Build and push Docker image first
            }
        },
        roleArn="YOUR_AGENTCORE_ROLE_ARN",
        networkConfiguration={
            "networkMode": "PUBLIC",
        },
    )
    runtime_id = runtime_response["agentRuntimeId"]
    print(f"AgentCore runtime created: {runtime_id}")

    # Step 2: Create an endpoint for invocation
    print("Creating AgentCore endpoint...")
    endpoint_response = client.create_agent_runtime_endpoint(
        agentRuntimeId=runtime_id,
        name="dataops-supervisor-endpoint",
        description="Endpoint for DataOps Supervisor Agent",
    )
    endpoint_id = endpoint_response["agentRuntimeEndpointId"]
    print(f"Endpoint created: {endpoint_id}")

    return {
        "runtime_id": runtime_id,
        "endpoint_id": endpoint_id,
    }


def invoke_agentcore(endpoint_id: str, message: str):
    """Invoke the deployed agent via AgentCore endpoint."""
    client = boto3.client("bedrock-agentcore", region_name=settings.AWS_REGION)

    response = client.invoke_agent_runtime(
        agentRuntimeEndpointId=endpoint_id,
        payload=json.dumps({"message": message}),
    )
    return json.loads(response["body"].read())


# Dockerfile template for AgentCore deployment
DOCKERFILE_TEMPLATE = """
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

# AgentCore expects the agent to listen on port 8080
ENV PORT=8080
EXPOSE 8080

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
"""


if __name__ == "__main__":
    print("=" * 60)
    print("DataOps Agent — Bedrock AgentCore Deployment")
    print("=" * 60)
    print()
    print("Before deploying, ensure you have:")
    print("  1. Built and pushed a Docker image to ECR")
    print("  2. Created an IAM role for AgentCore with Bedrock + RDS access")
    print("  3. Updated the ECR URI and Role ARN in this script")
    print()
    print("Dockerfile template:")
    print(DOCKERFILE_TEMPLATE)
    print()
    print("To deploy, uncomment the deploy call below:")
    print("  result = deploy_to_agentcore()")
    print("  print(result)")
