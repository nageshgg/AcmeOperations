"""JWT bearer-token validation against Keycloak, and RBAC dependencies."""

import os
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

KEYCLOAK_INTERNAL_URL = os.environ["KEYCLOAK_INTERNAL_URL"]
KEYCLOAK_REALM = os.environ["KEYCLOAK_REALM"]
KEYCLOAK_ISSUER = os.environ["KEYCLOAK_ISSUER"]
KEYCLOAK_CLIENT_ID = os.environ["KEYCLOAK_CLIENT_ID"]

JWKS_URL = f"{KEYCLOAK_INTERNAL_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"

# auto_error=False so a *missing* Authorization header goes through our own
# code path below and comes back as 401 (RFC 7235: 401 = not authenticated,
# 403 = authenticated but not authorized). FastAPI's HTTPBearer default
# (auto_error=True) would instead raise 403 for a missing header, which
# conflates "you never logged in" with "you're logged in but not allowed" —
# the wrong status code for a client trying to distinguish those two cases.
_bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def _get_jwks_client() -> PyJWKClient:
    """Built once per process and reused. PyJWKClient caches signing keys
    internally and automatically refetches the JWKS if it encounters a
    `kid` it hasn't seen before (e.g. after a Keycloak key rotation), so we
    don't need to hand-roll a refresh/TTL loop here.
    """
    return PyJWKClient(JWKS_URL)


def decode_token(token: str) -> dict:
    """Verify a Keycloak-issued JWT's signature, issuer, audience, and
    expiry, returning its claims.

    Raises HTTPException(401) on any validation failure (bad signature,
    wrong issuer/audience, expired token, malformed token, etc.) rather
    than leaking the underlying jwt library's exception type to callers.
    """
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=KEYCLOAK_ISSUER,
            audience=KEYCLOAK_CLIENT_ID,
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return claims


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    """FastAPI dependency: verifies the bearer token and returns its claims
    (username, realm roles, etc.) for use by the route or by nested
    dependencies such as `require_role`.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = decode_token(credentials.credentials)
    claims["_roles"] = set(claims.get("realm_access", {}).get("roles", []))
    return claims


def require_role(*allowed_roles: str):
    """Dependency factory for RBAC.

    Usage:
        @app.get("/admin-only")
        def route(user: dict = Depends(require_role("admin"))): ...

    Raises HTTPException(403) if the token's realm roles don't intersect
    `allowed_roles`. This is the single enforcement point every tool
    (Step 4) and route in this app relies on for authorization.
    """

    def _dependency(user: dict = Depends(get_current_user)) -> dict:
        if not user["_roles"] & set(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(allowed_roles)}",
            )
        return user

    return _dependency
