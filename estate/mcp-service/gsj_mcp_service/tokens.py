"""Token verification — stateless, per request (ADR-0040(g)).

JWT, HMAC-SHA256 (PyJWT), claims ``{case_id, timestep, episode_id, exp}``.
The token arrives as the last URL path segment (``/mcp/<token>``) because
that is the one channel the pi-mcp-extension config guarantees; the agent
may read its own token — accepted and documented: every call it can make is
already scoped to its own timestep, and any mutation breaks the signature.

The verifier holds the secret; nothing here ever logs or echoes it.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

import jwt


class TokenError(Exception):
    """Verification failure; ``reason`` is a short stable slug, ``detail``
    the human-readable message (safe to return — never contains the secret)."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class TokenClaims:
    case_id: str
    timestep: int
    episode_id: str
    exp: int


class TokenVerifier:
    def __init__(self, secret: str, leeway_s: int = 0) -> None:
        self._secret = secret
        self._leeway_s = leeway_s

    def verify_admin(self, token: str) -> None:
        """Verify a reindex-trigger token (CP-33, ADR-0047(d)): same secret,
        same HS256, but the claim set is ``{admin: "reindex", exp}`` — an
        episode token (case-scoped, no admin claim) never authorizes admin,
        and an admin token (no case_id) never authorizes tool calls."""
        try:
            payload = jwt.decode(
                token, self._secret, algorithms=["HS256"],
                leeway=self._leeway_s,
                options={"require": ["exp"]})
        except jwt.ExpiredSignatureError:
            raise TokenError("expired", "admin token expired") from None
        except jwt.InvalidTokenError as error:
            raise TokenError("invalid", f"admin token invalid: {error}") from None
        if payload.get("admin") != "reindex":
            raise TokenError(
                "claims", "not an admin token: claim admin='reindex' required")

    def verify(self, token: str) -> TokenClaims:
        try:
            payload = jwt.decode(
                token, self._secret, algorithms=["HS256"],
                leeway=self._leeway_s,
                options={"require": ["exp"]})
        except jwt.ExpiredSignatureError:
            raise TokenError("expired", "token expired") from None
        except jwt.InvalidTokenError as error:
            # covers tampered payloads, wrong-key signatures, malformed JWTs,
            # alg confusion (only HS256 accepted) — PyJWT's message is safe
            raise TokenError("invalid", f"token invalid: {error}") from None
        case_id = payload.get("case_id")
        timestep = payload.get("timestep")
        episode_id = payload.get("episode_id")
        if not isinstance(case_id, str) or not case_id:
            raise TokenError("claims", "token claims: case_id missing or not a string")
        if not isinstance(timestep, int) or isinstance(timestep, bool):
            raise TokenError("claims", "token claims: timestep missing or not an integer")
        if not isinstance(episode_id, str) or not episode_id:
            raise TokenError("claims", "token claims: episode_id missing or not a string")
        return TokenClaims(case_id=case_id, timestep=timestep,
                           episode_id=episode_id, exp=int(payload["exp"]))


# The per-request claims, set by the ASGI wrapper after verification and read
# by the tool bodies. contextvars propagate into the SDK's tool worker
# threads (anyio.to_thread copies the caller's context), which the
# concurrency tests assert end-to-end.
current_claims: ContextVar[TokenClaims | None] = ContextVar(
    "gsj_mcp_current_claims", default=None)


def require_claims() -> TokenClaims:
    claims = current_claims.get()
    if claims is None:  # unreachable behind the wrapper; belt for direct use
        raise TokenError("missing", "no verified token claims in request context")
    return claims
