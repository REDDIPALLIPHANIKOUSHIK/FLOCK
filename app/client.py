"""Urja Meter Ops Portal HTTP Client Adapter.

Handles session establishment, cookie persistence, CSRF requirements,
automatic re-authentication, error mapping, and raw upstream communication.
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional
import httpx

from app.config import Settings
from app.exceptions import (
    PortalAuthenticationError,
    PortalNotFoundError,
    PortalParseError,
    PortalRateLimitError,
    PortalSessionExpiredError,
    PortalTimeoutError,
    PortalUpstreamError,
)

logger = logging.getLogger(__name__)


class UrjaPortalClient:
    """Asynchronous HTTP adapter for the legacy Urja Meter Ops portal."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.urja_base_url.rstrip("/")
        self.timeout = settings.upstream_timeout_seconds
        self.max_retries = settings.upstream_max_retries
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()
        self._is_authenticated = False

    async def start(self) -> None:
        """Initialize the persistent HTTP connection pool."""
        if self._client is None or self._client.is_closed:
            headers = {
                "User-Agent": "Urja-Ops-API-Adapter/1.0 (+https://github.com/REDDIPALLIPHANIKOUSHIK/FLOCK)",
                "Accept": "application/json, text/html, */*",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/",
            }
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(self.timeout, connect=5.0),
                follow_redirects=True,
            )
            self._is_authenticated = False

    async def close(self) -> None:
        """Close HTTP connections on application shutdown."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            self._is_authenticated = False

    @property
    def is_authenticated(self) -> bool:
        """Return whether an active session cookie is present."""
        if not self._client or not self._is_authenticated:
            return False
        # Verify session token cookie exists in client cookie jar
        for cookie in self._client.cookies.jar:
            if "__Secure-better-auth.session_token" in cookie.name:
                return True
        return False

    async def authenticate(self, email: Optional[str] = None, password: Optional[str] = None) -> bool:
        """
        Authenticate against legacy portal login endpoint (/login).
        
        Requires application/x-www-form-urlencoded payload with email & password,
        and Origin header matching base URL to satisfy CSRF protection.
        """
        if self._client is None or self._client.is_closed:
            await self.start()

        target_email = email or self.settings.urja_username
        target_password = password or self.settings.urja_password

        if not target_email or not target_password:
            raise PortalAuthenticationError("Missing upstream credentials in configuration or request.")

        login_url = f"{self.base_url}/login"
        payload = {
            "email": target_email,
            "password": target_password,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": self.base_url,
            "Referer": login_url,
            "Accept": "application/json, */*",
        }

        try:
            assert self._client is not None
            response = await self._client.post("/login", data=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise PortalTimeoutError("Timed out while connecting to portal login endpoint.") from exc
        except httpx.RequestError as exc:
            raise PortalUpstreamError(f"Network error during portal authentication: {exc.__class__.__name__}") from exc

        # The portal returns HTTP 200 with JSON redirect or error structure
        if response.status_code != 200:
            if response.status_code == 403:
                raise PortalAuthenticationError("Portal rejected login submission (CSRF or Origin forbidden).")
            raise PortalAuthenticationError(f"Portal login returned unexpected status {response.status_code}.")

        try:
            data = response.json()
        except Exception:
            data = {}

        # Check for failure signature in body: {"type":"failure","status":401,...}
        if data.get("type") == "failure":
            raise PortalAuthenticationError("Invalid upstream credentials provided.")

        # Check for successful session cookie
        has_session = any("__Secure-better-auth.session_token" in c.name for c in self._client.cookies.jar)
        if not has_session and data.get("type") != "redirect":
            raise PortalAuthenticationError("Portal did not issue a valid session cookie upon login.")

        self._is_authenticated = True
        logger.info("Successfully established authenticated session with Urja legacy portal.")
        return True

    async def ensure_authenticated(self) -> None:
        """Ensure client has an active session, authenticating under lock if needed."""
        if self.is_authenticated:
            return

        async with self._lock:
            if not self.is_authenticated:
                await self.authenticate()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        is_retry: bool = False,
    ) -> httpx.Response:
        """
        Execute an HTTP request against upstream portal with session recovery.
        Detects session expiry, redirects to login, and re-authenticates once.
        """
        if self._client is None or self._client.is_closed:
            await self.start()

        # If not already authenticated and not calling login, ensure session
        if not self.is_authenticated and not path.startswith("/login"):
            await self.ensure_authenticated()

        req_headers = headers or {}
        try:
            assert self._client is not None
            response = await self._client.request(
                method,
                path,
                params=params,
                headers=req_headers,
            )
        except httpx.TimeoutException as exc:
            raise PortalTimeoutError(f"Upstream request timed out: {path}") from exc
        except httpx.RequestError as exc:
            raise PortalUpstreamError(f"Upstream communication failure: {exc.__class__.__name__}") from exc

        # Detect session expiration / unauthenticated responses
        is_expired = False
        if response.status_code == 401:
            is_expired = True
        elif response.status_code == 200:
            # SvelteKit redirect payload: {"type":"redirect","location":"/login"}
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    payload = response.json()
                    if payload.get("type") == "redirect" and "/login" in payload.get("location", ""):
                        is_expired = True
                except Exception:
                    pass
            elif "text/html" in content_type:
                # Returned login page HTML unexpectedly on protected route
                if "Urja Meter Ops • Sign in" in response.text or "<form method=\"POST\"" in response.text:
                    is_expired = True

        if is_expired:
            self._is_authenticated = False
            if not is_retry:
                logger.warning("Upstream session expired while accessing %s. Re-authenticating and retrying...", path)
                async with self._lock:
                    await self.authenticate()
                return await self._request(method, path, params=params, headers=headers, is_retry=True)
            raise PortalSessionExpiredError("Upstream portal session expired and re-authentication failed.")

        # Map HTTP errors
        if response.status_code == 404:
            raise PortalNotFoundError(f"Upstream resource not found: {path}")
        if response.status_code == 429:
            retry_after_val = response.headers.get("Retry-After")
            retry_after = int(retry_after_val) if retry_after_val and retry_after_val.isdigit() else None
            raise PortalRateLimitError("Upstream portal rate limit exceeded.", retry_after=retry_after)
        if response.status_code >= 500:
            raise PortalUpstreamError(f"Upstream portal returned server error {response.status_code}.", status_code=502)
        if response.status_code >= 400:
            raise PortalUpstreamError(f"Upstream portal returned error {response.status_code}.", status_code=502)

        return response

    async def search_meters(self, query: str = "", page: int = 1) -> Dict[str, Any]:
        """
        Call upstream /portal/meters/search?q={query}&page={page}.
        Returns raw JSON: {"data": [...], "total": int}
        """
        response = await self._request("GET", "/portal/meters/search", params={"q": query, "page": page})
        try:
            return response.json()
        except Exception as exc:
            raise PortalParseError("Failed to decode meters search JSON response.") from exc

    async def get_meter_deval_data(self, meter_id: str) -> Dict[str, Any]:
        """
        Call upstream /meters/{meter_id}/__data.json for SvelteKit deval data.
        """
        headers = {"x-sveltekit-load": "true"}
        response = await self._request("GET", f"/meters/{meter_id}/__data.json", headers=headers)
        try:
            data = response.json()
            # Check if SvelteKit returned an error node for 404
            nodes = data.get("nodes", [])
            for node in nodes:
                if node and node.get("type") == "error":
                    status = node.get("status", 404)
                    if status == 404:
                        raise PortalNotFoundError(f"Meter {meter_id} not found.")
                    raise PortalUpstreamError(node.get("error", {}).get("message", "Upstream meter error"))
            return data
        except PortalNotFoundError:
            raise
        except Exception as exc:
            raise PortalParseError(f"Failed to parse deval data for meter {meter_id}: {exc}") from exc

    async def get_meter_html(self, meter_id: str) -> str:
        """Call upstream /meters/{meter_id} for server-rendered HTML."""
        response = await self._request("GET", f"/meters/{meter_id}")
        return response.text

    async def get_meter_geo(self, meter_id: str) -> Dict[str, Any]:
        """
        Call upstream /portal/meters/{meter_id}/geo.
        Returns: {"data": {"latitude": "...", "longitude": "..."}}
        """
        try:
            response = await self._request("GET", f"/portal/meters/{meter_id}/geo")
            return response.json().get("data", {})
        except PortalNotFoundError:
            return {}
        except Exception:
            return {}

    async def get_meter_energy(
        self,
        meter_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Call upstream /portal/meters/{meter_id}/energy?from=YYYY-MM-DD&to=YYYY-MM-DD.
        Returns list of reading dicts.
        """
        params: Dict[str, Any] = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        response = await self._request("GET", f"/portal/meters/{meter_id}/energy", params=params)
        try:
            payload = response.json()
            return payload.get("data", [])
        except Exception as exc:
            raise PortalParseError(f"Failed to parse consumption response for meter {meter_id}.") from exc

    async def get_distribution_transformers(self, page: int = 1) -> Dict[str, Any]:
        """
        Call upstream /portal/dts?page={page}.
        Returns: {"data": [...], "total": int}
        """
        response = await self._request("GET", "/portal/dts", params={"page": page})
        try:
            return response.json()
        except Exception as exc:
            raise PortalParseError("Failed to parse distribution transformers response.") from exc

    async def check_health(self) -> Dict[str, Any]:
        """
        Probe upstream portal connectivity and authentication state.
        Lightweight check against root endpoint.
        """
        if self._client is None or self._client.is_closed:
            await self.start()

        try:
            assert self._client is not None
            resp = await self._client.get("/", timeout=5.0)
            reachable = resp.status_code in (200, 302, 303)
            return {
                "reachable": reachable,
                "status_code": resp.status_code,
                "authenticated": self.is_authenticated,
                "base_url": self.base_url,
            }
        except Exception as exc:
            return {
                "reachable": False,
                "error": exc.__class__.__name__,
                "authenticated": False,
                "base_url": self.base_url,
            }
