import os
import logging
import urllib.request
import psycopg2
from app.config import settings

logger = logging.getLogger(__name__)

RDS_CA_BUNDLE_URL = "https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem"


def _ensure_rds_ca_bundle(cert_path: str) -> str:
    """Download the RDS global CA bundle if it doesn't exist locally."""
    if os.path.isfile(cert_path):
        return cert_path
    try:
        logger.info(f"Downloading RDS CA bundle to {cert_path}...")
        urllib.request.urlretrieve(RDS_CA_BUNDLE_URL, cert_path)
        logger.info("RDS CA bundle downloaded successfully.")
        return cert_path
    except Exception as e:
        logger.warning(f"Could not download RDS CA bundle: {e}")
        return cert_path


def get_connection():
    """Get an Aurora PostgreSQL connection with SSL/TLS."""
    conn_params = dict(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        sslmode=settings.DB_SSLMODE,
        connect_timeout=10,
    )
    # Auto-resolve RDS CA bundle for verify-full / verify-ca
    if settings.DB_SSLMODE in ("verify-full", "verify-ca"):
        cert_path = _ensure_rds_ca_bundle(settings.DB_SSLROOTCERT)
        conn_params["sslrootcert"] = cert_path
    elif settings.DB_SSLROOTCERT:
        conn_params["sslrootcert"] = settings.DB_SSLROOTCERT

    return psycopg2.connect(**conn_params)


def execute_query(sql: str, params=None) -> list[dict]:
    """Execute a read query and return results as list of dicts."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def execute_command(sql: str) -> str:
    """Execute a write command (DDL/DML) and return status."""
    conn = get_connection()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return f"Success: {cur.statusmessage}"
    except Exception as e:
        return f"Error: {str(e)}"
    finally:
        conn.close()
