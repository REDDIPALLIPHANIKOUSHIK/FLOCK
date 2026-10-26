from typing import Optional
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from app.client import UrjaPortalClient
from app.config import Settings, get_settings

_portal_client: Optional[UrjaPortalClient] = None
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def init_portal_client(settings: Settings) -> UrjaPortalClient:
    """Initialize portal client singleton on application startup."""
    global _portal_client
    if _portal_client is None:
        _portal_client = UrjaPortalClient(settings)
        await _portal_client.start()
    return _portal_client


async def close_portal_client() -> None:
    """Close portal client on application shutdown."""
    global _portal_client
    if _portal_client is not None:
        await _portal_client.close()
        _portal_client = None


def get_portal_client(settings: Settings = Depends(get_settings)) -> UrjaPortalClient:
    """Dependency provider returning the active UrjaPortalClient."""
    global _portal_client
    if _portal_client is None:
        _portal_client = UrjaPortalClient(settings)
    return _portal_client


async def verify_api_key(
    api_key: Optional[str] = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Enforce API Key authentication if configured in settings.
    Permits unrestricted access when api_key is None (local dev workflow).
    """
    if settings.api_key:
        if not api_key or api_key != settings.api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API Key. Provide a valid 'X-API-Key' header."
            )
