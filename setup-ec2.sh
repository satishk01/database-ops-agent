#!/bin/bash
set -euo pipefail

# ============================================================
# DataOps Agent — EC2 Prerequisites Setup (Amazon Linux 2023)
# ============================================================
# Run this ONCE on a fresh AL2023 EC2 instance to install
# all dependencies needed to build and deploy the app.
#
# Usage:
#   chmod +x setup-ec2.sh
#   ./setup-ec2.sh
#
# After this script completes, run deploy.sh to deploy.
# ============================================================

echo "============================================================"
echo " Installing prerequisites on Amazon Linux 2023"
echo "============================================================"
echo ""

# ── 1. System packages ─────────────────────────────────────
echo ">> 1/7  System packages (git, gcc, curl, unzip)..."
sudo dnf update -y -q
sudo dnf install -y -q git gcc gcc-c++ make openssl-devel bzip2-devel \
    libffi-devel zlib-devel readline-devel sqlite-devel curl unzip tar gzip
echo "   Done."
echo ""

# ── 2. Python 3.12 ─────────────────────────────────────────
echo ">> 2/7  Python 3.12..."
if command -v python3.12 &>/dev/null; then
    echo "   Python 3.12 already installed: $(python3.12 --version)"
else
    sudo dnf install -y -q python3.12 python3.12-pip python3.12-devel
fi
# Set as default python3 if not already
sudo alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 2>/dev/null || true
python3 --version
pip3 install --upgrade pip -q
echo "   Done."
echo ""

# ── 3. Node.js 20 LTS ──────────────────────────────────────
echo ">> 3/7  Node.js 20 LTS..."
if command -v node &>/dev/null; then
    echo "   Node.js already installed: $(node --version)"
else
    curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
    sudo dnf install -y -q nodejs
fi
node --version
npm --version
echo "   Done."
echo ""

# ── 4. Docker ───────────────────────────────────────────────
echo ">> 4/7  Docker..."
if command -v docker &>/dev/null; then
    echo "   Docker already installed: $(docker --version)"
else
    sudo dnf install -y -q docker
    sudo systemctl start docker
    sudo systemctl enable docker
    sudo usermod -aG docker $USER
    echo "   NOTE: Log out and back in for docker group to take effect,"
    echo "   or run: newgrp docker"
fi
docker --version
echo "   Done."
echo ""

# ── 5. AWS CLI v2 ──────────────────────────────────────────
echo ">> 5/7  AWS CLI v2..."
if command -v aws &>/dev/null; then
    echo "   AWS CLI already installed: $(aws --version)"
else
    curl -sS "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
    unzip -q /tmp/awscliv2.zip -d /tmp
    sudo /tmp/aws/install
    rm -rf /tmp/aws /tmp/awscliv2.zip
fi
aws --version
echo "   Done."
echo ""

# ── 6. AWS CDK CLI ──────────────────────────────────────────
echo ">> 6/7  AWS CDK CLI..."
if command -v cdk &>/dev/null; then
    echo "   CDK already installed: $(cdk --version)"
else
    sudo npm install -g aws-cdk
fi
cdk --version
echo "   Done."
echo ""

# ── 7. Python CDK dependencies ─────────────────────────────
echo ">> 7/7  Python CDK + project dependencies..."
pip3 install aws-cdk-lib constructs -q
echo "   Done."
echo ""

# ── Summary ─────────────────────────────────────────────────
echo "============================================================"
echo " All prerequisites installed!"
echo ""
echo " Versions:"
echo "   Python:   $(python3 --version)"
echo "   Node.js:  $(node --version)"
echo "   npm:      $(npm --version)"
echo "   Docker:   $(docker --version 2>/dev/null || echo 'restart shell for docker')"
echo "   AWS CLI:  $(aws --version)"
echo "   CDK:      $(cdk --version)"
echo ""
echo " Next steps:"
echo "   1. Configure AWS credentials:"
echo "      aws configure"
echo "      (or attach an IAM role to this EC2 instance)"
echo ""
echo "   2. Make sure your IAM identity has permissions for:"
echo "      - CloudFormation (full)"
echo "      - S3, CloudFront, Lambda, API Gateway, IAM"
echo "      - ECR (for Docker image push)"
echo "      - Bedrock (InvokeModel, ApplyGuardrail)"
echo "      - Secrets Manager (read)"
echo "      - RDS (describe), CloudWatch (GetMetricStatistics)"
echo "      - SSM (CDK bootstrap uses it)"
echo ""
echo "   3. If you just installed Docker, run:"
echo "      newgrp docker"
echo "      (or log out and back in)"
echo ""
echo "   4. Deploy:"
echo "      cd dataops-agent"
echo "      chmod +x deploy.sh"
echo "      ./deploy.sh --help"
echo "============================================================"
