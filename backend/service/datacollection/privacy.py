"""
Privacy and PII Sanitization Module.

Provides functions to sanitize sensitive information from collected data
before uploading to the Hub server.

Redacts:
- Email addresses
- Phone numbers
- Social Security Numbers
- Credit card numbers
- API keys and tokens
- Passwords
"""

import re
from typing import Dict, Any


# Patterns for sensitive data
PATTERNS = [
    # Email addresses
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]'),

    # Phone numbers (various formats)
    (r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', '[PHONE]'),
    (r'\b\(\d{3}\)\s*\d{3}[-.\s]?\d{4}\b', '[PHONE]'),
    (r'\+\d{1,3}[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', '[PHONE]'),

    # Social Security Numbers
    (r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b', '[SSN]'),

    # Credit card numbers
    (r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '[CARD]'),
    (r'\b\d{4}[-\s]?\d{6}[-\s]?\d{5}\b', '[CARD]'),  # Amex

    # API keys and tokens (common patterns)
    (r'(api[_-]?key|apikey)[:\s=]+["\']?[\w-]{20,}["\']?', 'api_key: [REDACTED]'),
    (r'(secret[_-]?key|secretkey)[:\s=]+["\']?[\w-]{20,}["\']?', 'secret_key: [REDACTED]'),
    (r'(access[_-]?token|accesstoken)[:\s=]+["\']?[\w-]{20,}["\']?', 'access_token: [REDACTED]'),
    (r'(auth[_-]?token|authtoken)[:\s=]+["\']?[\w-]{20,}["\']?', 'auth_token: [REDACTED]'),
    (r'\bsk-[a-zA-Z0-9]{40,}\b', '[OPENAI_KEY]'),  # OpenAI API key
    (r'\btskey-[a-zA-Z0-9-]+\b', '[TAILSCALE_KEY]'),  # Tailscale key

    # Passwords
    (r'(password|passwd|pwd)[:\s=]+["\']?\S+["\']?', 'password: [REDACTED]'),

    # Bearer tokens
    (r'Bearer\s+[A-Za-z0-9_-]+\.?[A-Za-z0-9_-]*\.?[A-Za-z0-9_-]*', 'Bearer [REDACTED]'),

    # IP addresses (optional - may want to keep for debugging)
    # (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP]'),
]


def sanitize_text(text: str) -> str:
    """
    Sanitize text by redacting potentially sensitive information.

    Args:
        text: Input text that may contain sensitive data

    Returns:
        Text with sensitive information redacted
    """
    if not text:
        return text

    sanitized = text

    for pattern, replacement in PATTERNS:
        try:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
        except re.error:
            continue

    return sanitized


def sanitize_dict(data: Dict[str, Any], keys_to_redact: set = None) -> Dict[str, Any]:
    """
    Recursively sanitize a dictionary.

    Args:
        data: Dictionary to sanitize
        keys_to_redact: Set of key names to fully redact

    Returns:
        Sanitized dictionary
    """
    if keys_to_redact is None:
        keys_to_redact = {
            'password', 'passwd', 'pwd',
            'api_key', 'apikey', 'api-key',
            'secret', 'secret_key', 'secretkey',
            'token', 'auth_token', 'access_token',
            'private_key', 'privatekey',
            'ssn', 'social_security',
            'credit_card', 'card_number',
        }

    result = {}

    for key, value in data.items():
        key_lower = key.lower()

        # Fully redact sensitive keys
        if key_lower in keys_to_redact:
            result[key] = '[REDACTED]'

        # Recursively process nested dicts
        elif isinstance(value, dict):
            result[key] = sanitize_dict(value, keys_to_redact)

        # Process lists
        elif isinstance(value, list):
            result[key] = [
                sanitize_dict(item, keys_to_redact) if isinstance(item, dict)
                else sanitize_text(item) if isinstance(item, str)
                else item
                for item in value
            ]

        # Sanitize string values
        elif isinstance(value, str):
            result[key] = sanitize_text(value)

        # Pass through other types
        else:
            result[key] = value

    return result


def should_collect_audio(config: Dict[str, Any]) -> bool:
    """
    Check if audio collection is enabled and user has consented.

    Args:
        config: Data collection configuration

    Returns:
        True if audio collection is allowed
    """
    return (
        config.get("enabled", False) and
        config.get("audio_collection", False) and
        config.get("user_consent", False)
    )


def should_collect_video(config: Dict[str, Any]) -> bool:
    """
    Check if video collection is enabled and user has consented.

    Args:
        config: Data collection configuration

    Returns:
        True if video collection is allowed
    """
    return (
        config.get("enabled", False) and
        config.get("video_collection", False) and
        config.get("user_consent", False)
    )
