#!/bin/bash
set -euo pipefail

# ============================================================
# DataOps Agent — Full Production Deployment (CDK)
# ============================================================
#
# Deploys 3 stacks:
#   1. DataOpsAgentApi      — Lambda (Docker) + API Gateway
#   2. DataOpsAgentFrontend — S3 + CloudFront
#   3. DataOpsAgentCore     — IAM role + ECR image for AgentCore
#
# Prerequisites (run setup-ec2.sh first):
#   - Python 3.12, Node.js 20, Docker, AWS CLI, CDK CLI
#   - AWS credentials configured
#
# Usage:
#   ./deploy.sh \
#     --vpc-id vpc-xxxxxxxx \
#     --aurora-sg-id sg-xxxxxxxx \
#     --aurora-cluster-id my-aurora-cluster \
#     --aurora-instance-id my-aurora-instance-1 \
#     --db-secret-name dataops-agent/aurora-credentials \
#     --region us-east-1
#
# ============================================================

show_help() {
  echo "Usage: ./deploy.sh [OPTIONS]"
  echo ""
  echo "Required:"
  echo "  --vpc-id              VPC ID where Aurora lives"
  echo "  --aurora-sg-id        Security group ID that can reach Aurora"
  echo "  --aurora-cluster-id   Aurora cluster identifier"
  echo "  --aurora-instance-id  Aurora writer instance identifier"
  echo "  --db-secret-name      Secrets Manager secret name for Aurora creds"
  echo ""
  echo "Optional:"
  echo "  --region              AWS region (default: us-east-1)"
  echo "  --bedrock-model-id    Bedrock model (default: Claude Sonnet)"
  echo "  --bedrock-guardrail-id  Bedrock guardrail ID"
  echo "  --skip-frontend       Skip frontend build & deploy"
  echo "  --skip-agentcore      Skip AgentCore stack"
  echo "  --help                Show this help"
}

# Defaults
VPC_ID=""
AURORA_SG_ID=""
AURORA_CLUSTER_ID=""
AURORA_INSTANCE_ID=""
DB_SECRET_NAME="dataops-agent/aurora-credentials"
BEDROCK_MODEL_ID="us.anthropic.claude-sonnet-4-20250514-v1:0"
BEDROCK_GUARDRAIL_ID=""
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
SKIP_FRONTEND=false
SKIP_AGENTCORE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --vpc-id) VPC_ID="$2"; shift 2 ;;
    --aurora-sg-id) AURORA_SG_ID="$2"; shift 2 ;;
    --aurora-cluster-id) AURORA_CLUSTER_ID="$2"; shift 2 ;;
    --aurora-instance-id) AURORA_INSTANCE_ID="$2"; shift 2 ;;
    --db-secret-name) DB_SECRET_NAME="$2"; shift 2 ;;
    --bedrock-model-id) BEDROCK_MODEL_ID="$2"; shift 2 ;;
    --bedrock-guardrail-id) BEDROCK_GUARDRAIL_ID="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --skip-frontend) SKIP_FRONTEND=true; shift ;;
    --skip-agentcore) SKIP_AGENTCORE=true; shift ;;
    --help) show_help; exit 0 ;;
    *) echo "Unknown option: $1"; show_help; exit 1 ;;
  esac
done

# Validate required args
if [[ -z "$VPC_ID" || -z "$AURORA_SG_ID" || -z "$AURORA_CLUSTER_ID" || -z "$AURORA_INSTANCE_ID" ]]; then
  echo "ERROR: Missing required arguments."
  echo ""
  show_help
  exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export CDK_DEFAULT_ACCOUNT=$ACCOUNT_ID
export CDK_DEFAULT_REGION=$REGION

# CDK context args (reused across all deploys)
CDK_CONTEXT=(
  --context vpcId="$VPC_ID"
  --context auroraSgId="$AURORA_SG_ID"
  --context auroraClusterId="$AURORA_CLUSTER_ID"
  --context auroraInstanceId="$AURORA_INSTANCE_ID"
  --context dbSecretName="$DB_SECRET_NAME"
  --context bedrockModelId="$BEDROCK_MODEL_ID"
  --context bedrockGuardrailId="$BEDROCK_GUARDRAIL_ID"
)

echo "============================================================"
echo " DataOps Agent — Production Deployment"
echo "============================================================"
echo " Account:          $ACCOUNT_ID"
echo " Region:           $REGION"
echo " VPC:              $VPC_ID"
echo " Aurora SG:        $AURORA_SG_ID"
echo " Aurora Cluster:   $AURORA_CLUSTER_ID"
echo " Aurora Instance:  $AURORA_INSTANCE_ID"
echo " DB Secret:        $DB_SECRET_NAME"
echo " Bedrock Model:    $BEDROCK_MODEL_ID"
echo " Guardrail:        ${BEDROCK_GUARDRAIL_ID:-'(none)'}"
echo "============================================================"
echo ""

# ── Step 1: Build Frontend ──────────────────────────────────
if [[ "$SKIP_FRONTEND" == false ]]; then
  echo ">> Step 1/5: Building frontend..."
  pushd frontend > /dev/null
  npm install --silent
  npm run build
  popd > /dev/null
  echo "   Built to frontend/dist/"
  echo ""
else
  echo ">> Step 1/5: Skipping frontend build (--skip-frontend)"
  echo ""
fi

# ── Step 2: Install CDK Python deps ────────────────────────
echo ">> Step 2/5: Installing CDK Python dependencies..."
pip3 install -r infra/requirements.txt -q
echo "   Done."
echo ""

# ── Step 3: CDK Bootstrap ──────────────────────────────────
echo ">> Step 3/5: CDK bootstrap..."
pushd infra > /dev/null
cdk bootstrap aws://$ACCOUNT_ID/$REGION "${CDK_CONTEXT[@]}"
echo "   Done."
echo ""

# ── Step 4: Deploy API + Frontend stacks ───────────────────
echo ">> Step 4/5: Deploying API stack (Lambda + API Gateway)..."
cdk deploy DataOpsAgentApi \
  --require-approval never \
  "${CDK_CONTEXT[@]}"
echo ""

if [[ "$SKIP_FRONTEND" == false ]]; then
  echo "   Deploying Frontend stack (S3 + CloudFront)..."
  cdk deploy DataOpsAgentFrontend \
    --require-approval never \
    "${CDK_CONTEXT[@]}"
  echo ""
fi

# ── Step 5: Deploy AgentCore stack ─────────────────────────
if [[ "$SKIP_AGENTCORE" == false ]]; then
  echo ">> Step 5/5: Deploying AgentCore stack (IAM + ECR image)..."
  cdk deploy DataOpsAgentCore \
    --require-approval never \
    "${CDK_CONTEXT[@]}"
  echo ""
  echo "   To register with AgentCore, run the command from the stack output:"
  echo "   python3 deploy_agentcore.py --image-uri <URI> --role-arn <ARN> --region $REGION"
  echo ""
else
  echo ">> Step 5/5: Skipping AgentCore (--skip-agentcore)"
  echo ""
fi

popd > /dev/null

# ── Done ────────────────────────────────────────────────────
echo "============================================================"
echo " Deployment complete!"
echo ""
echo " Stack outputs (API URL, CloudFront URL) are printed above."
echo " You can also view them with:"
echo "   aws cloudformation describe-stacks --stack-name DataOpsAgentApi --query 'Stacks[0].Outputs' --region $REGION"
echo "   aws cloudformation describe-stacks --stack-name DataOpsAgentFrontend --query 'Stacks[0].Outputs' --region $REGION"
echo "============================================================"
