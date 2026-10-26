"""Authentication management route."""

from fastapi import APIRouter, Depends
from app.client import UrjaPortalClient
from app.dependencies import get_portal_client
from app.models import AuthResponse, LoginRequest

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Establish or test upstream portal session",
    description="Authenticates against the legacy Urja Meter Ops portal using configured or provided credentials and stores the session cookie."
)
async def login(
    body: LoginRequest = LoginRequest(),
    client: UrjaPortalClient = Depends(get_portal_client),
) -> AuthResponse:
    """Validate or establish an active session with the legacy portal."""
    await client.authenticate(email=body.email, password=body.password)
    return AuthResponse(
        authenticated=True,
        message="Authenticated successfully with upstream portal.",
        session_active=client.is_authenticated,
    )
