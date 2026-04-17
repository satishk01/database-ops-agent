import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


def _load_secret(secret_name: str, region: str) -> dict:
    """Load database credentials from AWS Secrets Manager."""
    try:
        import boto3
        client = boto3.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        return json.loads(response["SecretString"])
    except Exception as e:
        logger.warning(f"Could not load secret '{secret_name}': {e}. Falling back to env vars.")
        return {}


class Settings:
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    BEDROCK_MODEL_ID: str = os.getenv(
        "BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"
    )

    # Bedrock Guardrail for PII filtering and prompt attack prevention
    BEDROCK_GUARDRAIL_ID: str = os.getenv("BEDROCK_GUARDRAIL_ID", "")
    BEDROCK_GUARDRAIL_VERSION: str = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")

    # DB credentials — prefer Secrets Manager, fall back to env vars
    DB_SECRET_NAME: str = os.getenv("DB_SECRET_NAME", "")

    # Aurora cluster/instance identifiers for CloudWatch and RDS API
    AURORA_CLUSTER_ID: str = os.getenv("AURORA_CLUSTER_ID", "")
    AURORA_INSTANCE_ID: str = os.getenv("AURORA_INSTANCE_ID", "")

    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173"
    ).split(",")

    def __init__(self):
        secret = {}
        if self.DB_SECRET_NAME:
            secret = _load_secret(self.DB_SECRET_NAME, self.AWS_REGION)

        self.DB_HOST: str = secret.get("host", os.getenv("DB_HOST", ""))
        self.DB_PORT: int = int(secret.get("port", os.getenv("DB_PORT", "5432")))
        self.DB_NAME: str = secret.get("dbname", os.getenv("DB_NAME", "postgres"))
        self.DB_USER: str = secret.get("username", os.getenv("DB_USER", "postgres"))
        self.DB_PASSWORD: str = secret.get("password", os.getenv("DB_PASSWORD", ""))
        # verify-full is the recommended mode for Aurora PostgreSQL
        self.DB_SSLMODE: str = os.getenv("DB_SSLMODE", "verify-full")
        self.DB_SSLROOTCERT: str = os.getenv("DB_SSLROOTCERT", "rds-global-bundle.pem")


settings = Settings()
