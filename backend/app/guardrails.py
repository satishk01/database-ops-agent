"""
Bedrock Guardrails integration and prompt injection protection.

Provides:
1. AWS Bedrock Guardrails API — filters PII and blocks prompt attacks
2. Local prompt injection detection — catches common manipulation patterns
3. Response sanitization — strips PII patterns from agent output
"""

import re
import json
import logging
from app.config import settings

logger = logging.getLogger(__name__)

# ── Prompt Injection Detection ──────────────────────────────────────────────

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"ignore\s+(all\s+)?above\s+instructions",
    r"disregard\s+(all\s+)?prior",
    r"forget\s+(all\s+)?(your|previous)\s+(rules|instructions|constraints)",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"new\s+system\s+prompt",
    r"override\s+(system|safety)",
    r"pretend\s+you\s+(are|have)\s+no\s+(restrictions|rules|guardrails)",
    r"act\s+as\s+if\s+you\s+have\s+no\s+constraints",
    r"jailbreak",
    r"DAN\s+mode",
    r"\bsudo\s+mode\b",
]


def detect_prompt_injection(text: str) -> tuple[bool, str]:
    """Check user input for prompt injection attempts."""
    lower = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lower):
            return True, f"Blocked: prompt injection detected (pattern: {pattern})"
    return False, "OK"


# ── PII Sanitization ────────────────────────────────────────────────────────

PII_PATTERNS = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN_REDACTED]"),                          # SSN
    (r"\b\d{16}\b", "[CARD_REDACTED]"),                                      # Credit card (no spaces)
    (r"\b\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}\b", "[CARD_REDACTED]"),       # Credit card (spaced)
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL_REDACTED]"),
    (r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", "[PHONE_REDACTED]"),            # US phone
]


def sanitize_pii(text: str) -> str:
    """Remove common PII patterns from text."""
    result = text
    for pattern, replacement in PII_PATTERNS:
        result = re.sub(pattern, replacement, result)
    return result


# ── Bedrock Guardrails API ──────────────────────────────────────────────────

def apply_bedrock_guardrail(text: str, source: str = "INPUT") -> tuple[str, bool]:
    """
    Apply AWS Bedrock Guardrail to text content.

    Args:
        text: The text to check.
        source: "INPUT" for user messages, "OUTPUT" for agent responses.

    Returns:
        (processed_text, was_blocked) tuple.
    """
    if not settings.BEDROCK_GUARDRAIL_ID:
        # No guardrail configured — apply local PII sanitization only
        return sanitize_pii(text), False

    try:
        import boto3
        client = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION)

        response = client.apply_guardrail(
            guardrailIdentifier=settings.BEDROCK_GUARDRAIL_ID,
            guardrailVersion=settings.BEDROCK_GUARDRAIL_VERSION,
            source=source,
            content=[{"text": {"text": text}}],
        )

        action = response.get("action", "NONE")
        if action == "GUARDRAIL_INTERVENED":
            # Guardrail blocked the content
            outputs = response.get("outputs", [])
            blocked_text = outputs[0]["text"] if outputs else "Content blocked by guardrail."
            logger.warning(f"Guardrail intervened on {source}: {action}")
            return blocked_text, True

        return text, False

    except Exception as e:
        logger.error(f"Bedrock Guardrail error: {e}")
        # Fail open with local sanitization
        return sanitize_pii(text), False
