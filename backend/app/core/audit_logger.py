import json
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone

security_logger = logging.getLogger("enterprise_ai.security")

SENSITIVE_KEYS = {
    "password",
    "hashed_password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "jwt_secret",
    "authorization",
    "api_key",
    "credentials",
}


def sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redact sensitive keys from dictionary payloads."""
    sanitized: Dict[str, Any] = {}
    for k, v in payload.items():
        if k.lower() in SENSITIVE_KEYS:
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, dict):
            sanitized[k] = sanitize_payload(v)
        elif isinstance(v, list):
            sanitized[k] = [
                sanitize_payload(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            sanitized[k] = v
    return sanitized


def log_security_event(
    event_type: str,
    details: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    severity: str = "WARNING",
):
    """Record an audit trail log entry for a security-relevant event."""
    details = details or {}
    safe_details = sanitize_payload(details)

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "severity": severity.upper(),
        "user_id": user_id,
        "organization_id": organization_id,
        "details": safe_details,
    }

    msg = f"SECURITY_AUDIT: {json.dumps(log_entry)}"
    level = getattr(logging, severity.upper(), logging.WARNING)
    security_logger.log(level, msg)
