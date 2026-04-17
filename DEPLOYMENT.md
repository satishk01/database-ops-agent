# DataOps Agent — Deployment Guide (Amazon Linux 2023 EC2)

## Architecture

```
User → CloudFront → S3 (React UI)
                  → API Gateway → Lambda (Docker) → Bedrock Claude
                                                   → Aurora PostgreSQL (SSL)
                                                   → CloudWatch Metrics
                                                   → Secrets Manager
```

## Prerequisites on EC2

Run the automated setup script, or install manually:

```bash
chmod +x setup-ec2.sh
./setup-ec2.sh
```

### What gets installed

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12+ | Backend runtime, CDK |
| Node.js | 20 LTS | Frontend build, CDK CLI |
| Docker | Latest | Lambda container image build |
| AWS CLI | v2 | AWS API calls |
| AWS CDK | Latest | Infrastructure as Code |
| git | Latest | Source control |

### Manual install (if you prefer)

```bash
# Python 3.12
sudo dnf install -y python3.12 python3.12-pip python3.12-devel

# Node.js 20
curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
sudo dnf install -y nodejs

# Docker
sudo dnf install -y docker
sudo systemctl start docker && sudo systemctl enable docker
sudo usermod -aG docker $USER
newgrp docker   # or log out/in

# AWS CLI v2 (usually pre-installed on AL2023)
aws --version

# CDK CLI
sudo npm install -g aws-cdk
```

## IAM Permissions

Your EC2 instance role (or configured credentials) needs:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CDKBootstrapAndDeploy",
      "Effect": "Allow",
      "Action": [
        "cloudformation:*",
        "s3:*",
        "iam:*",
        "lambda:*",
        "apigateway:*",
        "execute-api:*",
        "cloudfront:*",
        "logs:*",
        "ecr:*",
        "ssm:GetParameter",
        "ssm:PutParameter",
        "sts:AssumeRole"
      ],
      "Resource": "*"
    },
    {
      "Sid": "BedrockAccess",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:ApplyGuardrail"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AuroraAccess",
      "Effect": "Allow",
      "Action": [
        "rds:DescribeDBClusters",
        "rds:DescribeDBInstances",
        "secretsmanager:GetSecretValue",
        "cloudwatch:GetMetricStatistics"
      ],
      "Resource": "*"
    }
  ]
}
```

## Pre-deployment: Aurora Setup

Before deploying, ensure you have:

1. An Aurora PostgreSQL cluster running
2. A Secrets Manager secret with the DB credentials in this format:
   ```json
   {
     "host": "your-cluster.cluster-xxxx.us-east-1.rds.amazonaws.com",
     "port": 5432,
     "dbname": "postgres",
     "username": "postgres",
     "password": "your-password"
   }
   ```
   Create it with:
   ```bash
   aws secretsmanager create-secret \
     --name dataops-agent/aurora-credentials \
     --secret-string '{"host":"YOUR_CLUSTER_ENDPOINT","port":5432,"dbname":"postgres","username":"postgres","password":"YOUR_PASSWORD"}'
   ```

3. Note down these values:
   - VPC ID (where Aurora lives)
   - Security Group ID (that allows access to Aurora on port 5432)
   - Aurora Cluster Identifier
   - Aurora Writer Instance Identifier

4. Bedrock model access enabled for Claude Sonnet in your region

## Deployment Steps

### Step 1: Clone and enter the project

```bash
git clone <your-repo-url> dataops-agent
cd dataops-agent
```

### Step 2: Configure AWS credentials

Either attach an IAM role to the EC2 instance, or:
```bash
aws configure
# Enter: Access Key, Secret Key, Region (us-east-1), Output (json)
```

Verify:
```bash
aws sts get-caller-identity
```

### Step 3: Seed the demo database (optional)

If you want demo data for the agent to analyze:
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create a .env with your Aurora connection
cat > .env << 'EOF'
DB_SECRET_NAME=dataops-agent/aurora-credentials
AWS_REGION=us-east-1
DB_SSLMODE=verify-full
EOF

python3 seed_demo_db.py
deactivate
cd ..
```

### Step 4: Deploy everything

```bash
chmod +x deploy.sh
./deploy.sh \
  --vpc-id vpc-0abc1234def56789 \
  --aurora-sg-id sg-0abc1234def56789 \
  --aurora-cluster-id my-aurora-cluster \
  --aurora-instance-id my-aurora-instance-1 \
  --db-secret-name dataops-agent/aurora-credentials \
  --region us-east-1
```

This will:
1. Build the React frontend (`npm run build`)
2. Install CDK Python dependencies
3. Bootstrap CDK in your account/region
4. Deploy the API stack (builds Docker image, creates Lambda + API Gateway)
5. Deploy the Frontend stack (S3 bucket + CloudFront distribution)
6. Deploy the AgentCore stack (IAM role + ECR image)

### Step 5: Get your URLs

After deployment, the stack outputs show:
- `DataOpsAgentApi.ApiUrl` — API Gateway endpoint
- `DataOpsAgentFrontend.CloudFrontUrl` — Your app URL

Or query them:
```bash
aws cloudformation describe-stacks \
  --stack-name DataOpsAgentFrontend \
  --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontUrl`].OutputValue' \
  --output text --region us-east-1
```

Open the CloudFront URL in your browser — that's your production app.

### Step 6: Register with AgentCore (optional)

The AgentCore stack outputs a deploy command. Run it:
```bash
cd infra
python3 deploy_agentcore.py \
  --image-uri <ECR_IMAGE_URI_FROM_OUTPUT> \
  --role-arn <ROLE_ARN_FROM_OUTPUT> \
  --region us-east-1
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `docker: permission denied` | Run `newgrp docker` or log out/in |
| CDK bootstrap fails | Check IAM permissions, ensure `sts:AssumeRole` is allowed |
| Lambda timeout | Agent calls can take 60-120s; Lambda timeout is 5min, should be fine |
| Aurora connection refused | Ensure Lambda's security group can reach Aurora on port 5432 |
| `ssl_is_used()` returns false | Check `DB_SSLMODE=verify-full` and RDS CA bundle is in the Docker image |
| Bedrock `AccessDeniedException` | Enable model access in Bedrock console for your region |
| CloudFront 403 on `/api/*` | Wait 5-10 min for distribution to propagate |

## Cleanup

```bash
cd infra
cdk destroy --all --force
```

This removes all 3 stacks. The S3 bucket has `auto_delete_objects=True` so it cleans up fully.
