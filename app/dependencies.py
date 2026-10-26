"""FastAPI dependency injection providers."""

from typing import Optional
from fastapi import Depends
from app.client import UrjaPortalClient
from app.config import Settings, get_settings

_portal_client: Optional[UrjaPortalClient] = None


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
