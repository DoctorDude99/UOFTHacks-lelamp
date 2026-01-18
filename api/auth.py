"""
Authentication module for LeLamp API.

Provides Clerk JWT validation with local network bypass.
"""

import logging
import os
from typing import Optional
from functools import lru_cache
import ipaddress
from pathlib import Path

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import httpx
import jwt
from jwt import PyJWKClient
from dotenv import load_dotenv

from api.deps import get_config

# Load .env from ~/.lelamp/.env
_env_path = Path.home() / ".lelamp" / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

logger = logging.getLogger(__name__)

# HTTP Bearer token security scheme
security = HTTPBearer(auto_error=False)


# =============================================================================
# Local Network Detection
# =============================================================================

# Private network ranges (RFC 1918 + localhost + link-local)
PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),       # Localhost
    ipaddress.ip_network("169.254.0.0/16"),    # Link-local
    ipaddress.ip_network("::1/128"),           # IPv6 localhost
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
    ipaddress.ip_network("fc00::/7"),          # IPv6 unique local
]


def is_local_network(ip_str: str) -> bool:
    """
    Check if an IP address is on a local/private network.

    Args:
        ip_str: IP address string (IPv4 or IPv6)

    Returns:
        True if the IP is on a private/local network
    """
    try:
        # Handle IPv4-mapped IPv6 addresses like "::ffff:192.168.1.1"
        if ip_str.startswith("::ffff:"):
            ip_str = ip_str[7:]

        ip = ipaddress.ip_address(ip_str)

        for network in PRIVATE_NETWORKS:
            if ip in network:
                return True
        return False
    except ValueError:
        # Invalid IP address - be safe and require auth
        logger.warning(f"Invalid IP address format: {ip_str}")
        return False


def get_client_ip(request: Request) -> str:
    """
    Get the real client IP from a request.

    Handles X-Forwarded-For header for reverse proxy setups.
    """
    # Check for proxy headers first
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP (original client)
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fall back to direct client
    if request.client:
        return request.client.host

    return "unknown"


# =============================================================================
# Clerk JWT Validation
# =============================================================================

class ClerkAuth:
    """Clerk authentication handler."""

    def __init__(self, secret_key: Optional[str] = None, publishable_key: Optional[str] = None):
        self.secret_key = secret_key
        self.publishable_key = publishable_key
        self._jwks_client: Optional[PyJWKClient] = None
        self._jwks_url: Optional[str] = None

        # Extract Clerk frontend API domain from publishable key
        # Format: pk_test_<base64_encoded_domain>$ or pk_live_<base64_encoded_domain>$
        if publishable_key:
            try:
                import base64
                # Remove pk_test_ or pk_live_ prefix
                encoded = publishable_key.split('_', 2)[-1]
                # Add padding if needed
                padding = 4 - len(encoded) % 4
                if padding != 4:
                    encoded += '=' * padding
                # Decode and strip any trailing $ or whitespace
                domain = base64.b64decode(encoded).decode('utf-8').rstrip('$').strip()
                self._jwks_url = f"https://{domain}/.well-known/jwks.json"
                logger.info(f"Clerk JWKS URL: {self._jwks_url}")
            except Exception as e:
                logger.warning(f"Could not extract Clerk domain from publishable key: {e}")

    @property
    def jwks_client(self) -> Optional[PyJWKClient]:
        """Lazy-load JWKS client."""
        if self._jwks_client is None and self._jwks_url:
            try:
                self._jwks_client = PyJWKClient(self._jwks_url)
            except Exception as e:
                logger.warning(f"Failed to create JWKS client: {e}")
        return self._jwks_client

    def validate_token(self, token: str) -> Optional[dict]:
        """
        Validate a Clerk JWT token using JWKS (RS256).

        Args:
            token: JWT token string

        Returns:
            Decoded token payload if valid, None otherwise
        """
        if not self.jwks_client:
            logger.warning("Clerk JWKS client not configured")
            return None

        try:
            # Get the signing key from JWKS
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)

            # Decode and verify the token with the public key
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={"verify_aud": False}  # Clerk doesn't always set audience
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Clerk token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid Clerk token: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error validating Clerk token: {e}")
            return None


# Global auth instance (initialized from config)
_clerk_auth: Optional[ClerkAuth] = None


def get_clerk_auth() -> Optional[ClerkAuth]:
    """Get or create the Clerk auth instance."""
    global _clerk_auth

    if _clerk_auth is None:
        config = get_config()
        auth_config = config.get("auth", {})

        if auth_config.get("enabled", False):
            # Secret key from env var (preferred) or config (fallback)
            secret_key = os.environ.get("CLERK_SECRET_KEY") or auth_config.get("clerk_secret_key")
            publishable_key = auth_config.get("clerk_publishable_key")

            _clerk_auth = ClerkAuth(
                secret_key=secret_key,
                publishable_key=publishable_key,
            )

    return _clerk_auth


# =============================================================================
# FastAPI Dependencies
# =============================================================================

class AuthResult:
    """Result of authentication check."""

    def __init__(
        self,
        authenticated: bool,
        user_id: Optional[str] = None,
        bypass_reason: Optional[str] = None,
        error: Optional[str] = None
    ):
        self.authenticated = authenticated
        self.user_id = user_id
        self.bypass_reason = bypass_reason
        self.error = error

    @property
    def is_local_bypass(self) -> bool:
        return self.bypass_reason == "local_network"


async def check_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> AuthResult:
    """
    Check authentication for a request.

    This dependency checks:
    1. If auth is disabled in config -> allow
    2. If request is from local network -> allow (bypass)
    3. If valid Clerk token provided -> allow
    4. Otherwise -> deny

    Usage:
        @router.get("/protected")
        async def protected_route(auth: AuthResult = Depends(require_auth)):
            return {"user_id": auth.user_id}
    """
    config = get_config()
    auth_config = config.get("auth", {})
    setup_config = config.get("setup", {})

    # Check if auth is enabled
    if not auth_config.get("enabled", False):
        return AuthResult(
            authenticated=True,
            bypass_reason="auth_disabled"
        )

    # Allow first boot access - if setup isn't complete, allow access to finish setup
    # This prevents chicken-and-egg problem with configuring auth
    if not setup_config.get("setup_complete", False):
        return AuthResult(
            authenticated=True,
            bypass_reason="first_boot"
        )

    # Check for local network bypass (no logging - too noisy)
    # Default to False - require explicit opt-in for local bypass
    if auth_config.get("local_bypass", False):
        client_ip = get_client_ip(request)
        if is_local_network(client_ip):
            return AuthResult(
                authenticated=True,
                bypass_reason="local_network"
            )

    # Require token for remote access
    if not credentials:
        return AuthResult(
            authenticated=False,
            error="No authentication token provided"
        )

    # Validate Clerk token
    clerk = get_clerk_auth()
    if not clerk:
        return AuthResult(
            authenticated=False,
            error="Authentication not configured"
        )

    payload = clerk.validate_token(credentials.credentials)
    if not payload:
        return AuthResult(
            authenticated=False,
            error="Invalid or expired token"
        )

    # Extract user ID from Clerk token
    user_id = payload.get("sub") or payload.get("user_id")

    return AuthResult(
        authenticated=True,
        user_id=user_id
    )


async def require_auth(
    auth: AuthResult = Depends(check_auth)
) -> AuthResult:
    """
    Require authentication for a route.

    Raises HTTPException if not authenticated.

    Usage:
        @router.get("/protected")
        async def protected_route(auth: AuthResult = Depends(require_auth)):
            return {"user_id": auth.user_id}
    """
    if not auth.authenticated:
        raise HTTPException(
            status_code=401,
            detail=auth.error or "Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return auth


async def optional_auth(
    auth: AuthResult = Depends(check_auth)
) -> AuthResult:
    """
    Optional authentication - doesn't raise error if not authenticated.

    Useful for routes that behave differently for authenticated users.

    Usage:
        @router.get("/info")
        async def info_route(auth: AuthResult = Depends(optional_auth)):
            if auth.authenticated:
                return {"user_id": auth.user_id, "premium": True}
            return {"premium": False}
    """
    return auth


# =============================================================================
# Utility Functions
# =============================================================================

def is_auth_enabled() -> bool:
    """Check if authentication is enabled in config."""
    config = get_config()
    return config.get("auth", {}).get("enabled", False)


def get_auth_config() -> dict:
    """Get the auth configuration."""
    config = get_config()
    return config.get("auth", {})
