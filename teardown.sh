#!/bin/bash
set -euo pipefail

# ============================================================
# DataOps Agent — Teardown / Cleanup
# ============================================================
#
# Destroys all CDK stacks and cleans up residual resources.
#
# Usage:
#   chmod +x teardown.sh
#   ./teardown.sh --region us-east-1
#
# Add --keep-secret to preserve the Secrets Manager secret.
# Add --keep-ecr to preserve ECR images.
# ============================================================

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
KEEP_SECRET=false
KEEP_ECR=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --region) REGION="$2"; shift 2 ;;
    --keep-secret) KEEP_SECRET=true; shift ;;
    --keep-ecr) KEEP_ECR=true; shift ;;
    --help)
      echo "Usage: ./teardown.sh [--region us-east-1] [--keep-secret] [--keep-ecr]"
      exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export CDK_DEFAULT_ACCOUNT=$ACCOUNT_ID
export CDK_DEFAULT_REGION=$REGION

echo "============================================================"
echo " DataOps Agent — Teardown"
echo "============================================================"
echo " Account: $ACCOUNT_ID"
echo " Region:  $REGION"
echo "============================================================"
echo ""

# ── Step 1: Disable CloudFront before deleting ──────────────
echo ">> Step 1/5: Checking for CloudFront distribution..."
CF_DIST_ID=$(aws cloudformation describe-stacks \
  --stack-name DataOpsAgentFrontend \
  --query 'Stacks[0].Outputs[?contains(OutputKey,`Distribution`)].OutputValue' \
  --output text --region "$REGION" 2>/dev/null || echo "")

if [[ -n "$CF_DIST_ID" && "$CF_DIST_ID" != "None" ]]; then
  echo "   CloudFront distribution found. CDK will handle disabling it."
else
  echo "   No CloudFront distribution found (stack may not exist). Skipping."
fi
echo ""

# ── Step 2: Destroy CDK stacks (reverse order) ─────────────
echo ">> Step 2/5: Destroying CDK stacks..."
pushd infra > /dev/null

# Destroy in reverse dependency order
for STACK in DataOpsAgentCore DataOpsAgentFrontend DataOpsAgentApi; do
  echo "   Destroying $STACK..."
  if aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" &>/dev/null; then
    cdk destroy "$STACK" --force --region "$REGION" 2>&1 || {
      echo "   WARNING: CDK destroy failed for $STACK. Trying CloudFormation directly..."
      aws cloudformation delete-stack --stack-name "$STACK" --region "$REGION"
      echo "   Waiting for $STACK deletion..."
      aws cloudformation wait stack-delete-complete --stack-name "$STACK" --region "$REGION" 2>/dev/null || true
    }
    echo "   $STACK destroyed."
  else
    echo "   $STACK does not exist. Skipping."
  fi
done

popd > /dev/null
echo ""

# ── Step 3: Clean up ECR repository ────────────────────────
echo ">> Step 3/5: Cleaning up ECR images..."
if [[ "$KEEP_ECR" == false ]]; then
  # CDK creates repos with names like cdk-hnb659fds-container-assets-*
  ECR_REPOS=$(aws ecr describe-repositories \
    --query 'repositories[?contains(repositoryName,`dataops`) || contains(repositoryName,`cdk-hnb659fds-container`)].repositoryName' \
    --output text --region "$REGION" 2>/dev/null || echo "")

  for REPO in $ECR_REPOS; do
    echo "   Deleting ECR repository: $REPO"
    aws ecr delete-repository --repository-name "$REPO" --force --region "$REGION" 2>/dev/null || true
  done
  if [[ -z "$ECR_REPOS" ]]; then
    echo "   No ECR repositories found."
  fi
else
  echo "   Skipping ECR cleanup (--keep-ecr)."
fi
echo ""

# ── Step 4: Clean up CloudWatch log groups ──────────────────
echo ">> Step 4/5: Cleaning up CloudWatch log groups..."
LOG_GROUPS=$(aws logs describe-log-groups \
  --log-group-name-prefix "/aws/lambda/dataops-agent" \
  --query 'logGroups[].logGroupName' \
  --output text --region "$REGION" 2>/dev/null || echo "")

for LG in $LOG_GROUPS; do
  echo "   Deleting log group: $LG"
  aws logs delete-log-group --log-group-name "$LG" --region "$REGION" 2>/dev/null || true
done
if [[ -z "$LOG_GROUPS" ]]; then
  echo "   No log groups found."
fi
echo ""

# ── Step 5: Optionally remove Secrets Manager secret ───────
echo ">> Step 5/5: Secrets Manager..."
if [[ "$KEEP_SECRET" == false ]]; then
  echo "   NOTE: The DB secret was NOT created by CDK, so we don't delete it."
  echo "   To delete it manually:"
  echo "   aws secretsmanager delete-secret --secret-id dataops-agent/aurora-credentials --force-delete-without-recovery --region $REGION"
else
  echo "   Skipping (--keep-secret)."
fi
echo ""

echo "============================================================"
echo " Teardown complete!"
echo ""
echo " Remaining resources you may want to clean up manually:"
echo "   - CDK bootstrap stack: CDKToolkit (shared, don't delete if other apps use it)"
echo "   - CDK bootstrap bucket: cdk-hnb659fds-assets-$ACCOUNT_ID-$REGION"
echo "   - Secrets Manager secret: dataops-agent/aurora-credentials"
echo "   - Bedrock AgentCore runtime (if registered): delete via AWS console"
echo "============================================================"
