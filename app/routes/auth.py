"""Authentication management route."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from app.client import UrjaPortalClient
from app.config import Settings, get_settings
from app.dependencies import get_portal_client
from app.models import AuthResponse, LoginRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Establish or test upstream portal session",
    description=(
        "Authenticates against the legacy Urja Meter Ops portal using configured server credentials "
        "and maintains the upstream session cookie. Custom credential overrides are restricted to development mode."
    )
)
async def login(
    body: LoginRequest = LoginRequest(),
    client: UrjaPortalClient = Depends(get_portal_client),
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    """Validate or establish an active session with the legacy portal."""
    # Deliberate safeguard: do not allow open credential proxying in non-development environments
    if (body.email or body.password) and settings.app_env.lower() not in ("development", "test"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Custom credential overrides are forbidden in non-development environments."
        )

    # Use configured portal credentials by default
    target_email = body.email if body.email else settings.urja_username
    target_password = body.password if body.password else settings.urja_password

    if not target_email or not target_password:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Portal credentials are not configured on the server."
        )

    logger.info("Initiating portal authentication handshake for user: %s", target_email)
    await client.authenticate(email=target_email, password=target_password)

    return AuthResponse(
        authenticated=True,
        message="Authenticated successfully with upstream portal.",
        session_active=client.is_authenticated,
    )
