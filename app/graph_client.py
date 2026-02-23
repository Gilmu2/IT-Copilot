"""Microsoft Graph API client (client credentials flow). No CLI, no printing."""

from typing import Any, Optional

import msal
import requests

from app.config import get_config


def _is_403(e: "GraphClientError") -> bool:
    """True if the error indicates HTTP 403 (permission denied)."""
    return getattr(e, "status_code", None) == 403 or "403" in str(e)


def _safe_graph(
    thunk,
    default: Optional[dict] = None,
    limitations: Optional[list] = None,
):
    """
    Run a Graph call (no-arg thunk). Single consistent pattern for all Graph calls.
    - 403 → append to limitations, return default, do NOT raise
    - 404 → append 'Not found (404)', return default
    - Other HTTP → append with status code, return default
    - Network/auth errors → append error type, return default
    Never prints; callers handle display.
    """
    default = default if default is not None else {}
    limitations = limitations if limitations is not None else []
    try:
        return thunk()
    except GraphClientError as e:
        code = getattr(e, "status_code", None)
        if code == 403:
            limitations.append("Permission-limited: request returned 403")
        elif code == 404:
            limitations.append("Not found (404)")
        elif code is not None:
            limitations.append(f"Error: HTTP {code}")
        else:
            limitations.append("Error: network or auth failure")
        return default


class GraphClientError(Exception):
    """Raised when Graph auth or API request fails. No secrets in message."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
REQUEST_TIMEOUT = 30

# Single source of truth for all Graph endpoints used or probed. Adding a new endpoint = add one dict here.
ENDPOINT_REGISTRY: list[dict[str, Any]] = [
    {"area": "Managed Devices", "endpoint": "deviceManagement/managedDevices", "method": "GET", "params": {"$top": 1}, "currently_granted": True},
    {"area": "Mobile Apps", "endpoint": "deviceAppManagement/mobileApps", "method": "GET", "params": {"$top": 1}, "currently_granted": True},
    {"area": "Device Configurations", "endpoint": "deviceManagement/deviceConfigurations", "method": "GET", "params": {"$top": 1}, "currently_granted": True},
    {"area": "Service Config", "endpoint": "deviceManagement/deviceEnrollmentConfigurations", "method": "GET", "params": {"$top": 1}, "currently_granted": True},
    {"area": "Reports", "endpoint": "deviceManagement/reports/getConfigurationPolicyNonComplianceSummaryReport", "method": "POST", "params": None, "json_body": {}, "currently_granted": True},
    {"area": "Users", "endpoint": "users", "method": "GET", "params": {"$top": 1}, "currently_granted": False},
    {"area": "Groups", "endpoint": "groups", "method": "GET", "params": {"$top": 1}, "currently_granted": False},
    {"area": "Conditional Access", "endpoint": "identity/conditionalAccess/policies", "method": "GET", "params": {"$top": 1}, "currently_granted": False},
    {"area": "Security Alerts", "endpoint": "security/alerts_v2", "method": "GET", "params": {"$top": 1}, "currently_granted": False},
    {"area": "Licenses", "endpoint": "subscribedSkus", "method": "GET", "params": {"$top": 1}, "currently_granted": False},
]


class GraphClient:
    """Minimal HTTP wrapper for Microsoft Graph with app-only auth. Extensible for Phase 6."""

    def __init__(self) -> None:
        """Validate Graph config from get_config(); raise GraphClientError if any value missing."""
        config = get_config()
        if not config.azure_tenant_id or not config.azure_client_id or not config.azure_client_secret:
            raise GraphClientError(
                "Microsoft Graph requires AZURE_TENANT_ID, AZURE_CLIENT_ID, and "
                "AZURE_CLIENT_SECRET in .env. See .env.example."
            )
        self._tenant_id = config.azure_tenant_id
        self._client_id = config.azure_client_id
        self._client_secret = config.azure_client_secret
        self._base_url = GRAPH_BASE_URL
        self._app: Optional[msal.ConfidentialClientApplication] = None
        self._last_snapshot_status: dict[str, str] = {}

    def _get_app(self) -> msal.ConfidentialClientApplication:
        """Lazy MSAL app (in-memory only)."""
        if self._app is None:
            authority = f"https://login.microsoftonline.com/{self._tenant_id}"
            self._app = msal.ConfidentialClientApplication(
                self._client_id,
                authority=authority,
                client_credential=self._client_secret,
            )
        return self._app

    def get_access_token(self) -> str:
        """Acquire token for client credentials flow. Raise GraphClientError on failure."""
        try:
            app = self._get_app()
            result = app.acquire_token_for_client(scopes=[GRAPH_SCOPE])
        except Exception as e:
            raise GraphClientError("Failed to acquire Microsoft Graph token.") from e

        if "access_token" not in result:
            error = result.get("error", "unknown")
            desc = result.get("error_description", "")
            msg = f"Microsoft Graph token failed: {error}."
            if desc and "secret" not in desc.lower() and "key" not in desc.lower():
                msg += f" {desc[:200]}"
            raise GraphClientError(msg)

        return result["access_token"]

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Internal: send request with Bearer token, timeout; return JSON. Raise GraphClientError on failure."""
        try:
            token = self.get_access_token()
        except GraphClientError:
            raise

        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            url = endpoint
        else:
            url = f"{self._base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = {"Authorization": f"Bearer {token}"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        try:
            resp = requests.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_body,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as e:
            raise GraphClientError("Microsoft Graph request failed (network or timeout).", status_code=None) from e

        if not (200 <= resp.status_code < 300):
            raise GraphClientError(
                f"Microsoft Graph request failed (HTTP {resp.status_code}).",
                status_code=resp.status_code,
            )

        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            raise GraphClientError("Microsoft Graph returned invalid JSON.")

    def get_organization(self) -> dict[str, Any]:
        """GET /organization. Proof-of-integration method (app-only)."""
        data = self._request("GET", "organization")
        return data if isinstance(data, dict) else {}

    def get_users(self, top: int = 10) -> dict[str, Any]:
        """GET /users with $top. Proof-of-integration method (app-only). Returns Graph response dict."""
        data = self._request("GET", "users", params={"$top": top})
        return data if isinstance(data, dict) else {}

    def _get_paginated(
        self,
        endpoint: str,
        max_items: int,
        page_size: int = 999,
    ) -> dict[str, Any]:
        """
        GET a collection endpoint with pagination; follow @odata.nextLink until we have max_items or no more pages.
        Returns {"value": list}. Uses page_size per request (Graph supports up to 999).
        """
        params = {"$top": min(page_size, max_items)}
        data = self._request("GET", endpoint, params=params)
        values = list(data.get("value") or [])
        while len(values) < max_items and data.get("@odata.nextLink"):
            next_link = data["@odata.nextLink"]
            data = self._request("GET", next_link)
            chunk = data.get("value") or []
            values.extend(chunk)
            if not chunk:
                break
        return {"value": values[:max_items]}

    def get_managed_devices(self, top: int = 10) -> dict[str, Any]:
        """GET /deviceManagement/managedDevices (Intune) with pagination. Returns Graph response dict with full 'value' list."""
        if top <= 999:
            data = self._request("GET", "deviceManagement/managedDevices", params={"$top": top})
            return data if isinstance(data, dict) else {}
        return self._get_paginated("deviceManagement/managedDevices", max_items=top)

    def get_groups(self, top: int = 10) -> dict[str, Any]:
        """GET /groups with $top. Returns Graph response dict."""
        data = self._request("GET", "groups", params={"$top": top})
        return data if isinstance(data, dict) else {}

    def get_managed_device(self, device_id: str) -> dict[str, Any]:
        """GET /deviceManagement/managedDevices/{id}. Single device (Intune)."""
        data = self._request("GET", f"deviceManagement/managedDevices/{device_id}")
        return data if isinstance(data, dict) else {}

    def get_mobile_apps(self, top: int = 100) -> dict[str, Any]:
        """GET /deviceAppManagement/mobileApps with pagination. Requires DeviceManagementApps.ReadWrite.All."""
        if top <= 999:
            data = self._request("GET", "deviceAppManagement/mobileApps", params={"$top": top})
            return data if isinstance(data, dict) else {}
        return self._get_paginated("deviceAppManagement/mobileApps", max_items=top)

    def get_device_configurations(self, top: int = 100) -> dict[str, Any]:
        """GET /deviceManagement/deviceConfigurations with pagination. Requires DeviceManagementConfiguration.ReadWrite.All."""
        if top <= 999:
            data = self._request("GET", "deviceManagement/deviceConfigurations", params={"$top": top})
            return data if isinstance(data, dict) else {}
        return self._get_paginated("deviceManagement/deviceConfigurations", max_items=top)

    def probe_endpoint(self, entry: dict[str, Any]) -> tuple[str, str]:
        """
        Probe one endpoint from ENDPOINT_REGISTRY. Uses real API call; captures 403/404/other.
        Returns (status, notes): status is 'Available' | 'Denied' | 'Error'; notes is short text.
        """
        method = entry.get("method", "GET")
        endpoint = entry.get("endpoint", "")
        params = entry.get("params")
        json_body = entry.get("json_body") if method == "POST" else None
        currently_granted = entry.get("currently_granted", True)
        try:
            self._request(method, endpoint, params=params, json_body=json_body)
            return ("Available", "Granted")
        except GraphClientError as e:
            code = getattr(e, "status_code", None)
            if code == 403:
                return ("Denied", "Future scope" if not currently_granted else "Not granted (403)")
            if code == 404:
                return ("Available", "No data")
            msg = str(e)
            if len(msg) > 50:
                msg = msg[:47] + "..."
            return ("Error", f"Error: {msg}")

    def get_permission_status(self) -> dict[str, str]:
        """
        Return a cached snapshot of which endpoints are available/denied,
        built from the last _build_intune_snapshot() call. Keys are area names, values 'available' or 'denied'.
        """
        return dict(self._last_snapshot_status)

    def _build_intune_snapshot(
        self,
        limitations: Optional[list] = None,
        top: int = 10000,
    ) -> Optional[dict[str, Any]]:
        """
        Fetch devices, apps, and configs via _safe_graph with pagination and return a structured snapshot.
        Returns None if all three Graph calls fail (e.g. 403). Used by suggest-fixes, trend-summary, and copilot.
        Default top=10000 to capture large tenants (3k+ devices); pagination follows @odata.nextLink.
        """
        limitations = limitations if limitations is not None else []
        devices_data = _safe_graph(
            lambda: self.get_managed_devices(top=top),
            default=None,
            limitations=limitations,
        )
        apps_data = _safe_graph(
            lambda: self.get_mobile_apps(top=top),
            default=None,
            limitations=limitations,
        )
        configs_data = _safe_graph(
            lambda: self.get_device_configurations(top=top),
            default=None,
            limitations=limitations,
        )
        if devices_data is None and apps_data is None and configs_data is None:
            return None

        self._last_snapshot_status = {
            "Managed Devices": "available" if devices_data else "denied",
            "Mobile Apps": "available" if apps_data else "denied",
            "Device Configurations": "available" if configs_data else "denied",
        }

        devices = (devices_data or {}).get("value") or []
        apps = (apps_data or {}).get("value") or []
        configs = (configs_data or {}).get("value") or []

        compliant = non_compliant = unknown = 0
        os_breakdown: dict[str, int] = {}
        non_compliant_by_os: dict[str, int] = {}
        for d in devices:
            comp = (d.get("complianceState") or "unknown").lower()
            os_name = d.get("operatingSystem") or "Unknown"
            os_breakdown[os_name] = os_breakdown.get(os_name, 0) + 1
            if comp == "compliant":
                compliant += 1
            elif comp == "noncompliant":
                non_compliant += 1
                non_compliant_by_os[os_name] = non_compliant_by_os.get(os_name, 0) + 1
            else:
                unknown += 1

        app_type_breakdown: dict[str, int] = {}
        for a in apps:
            t = (a.get("@odata.type") or "unknown").replace("#microsoft.graph.", "")
            app_type_breakdown[t] = app_type_breakdown.get(t, 0) + 1

        config_policy_names = [c.get("displayName") or "" for c in configs if c.get("displayName")]

        top_non_compliant_os = sorted(
            non_compliant_by_os.items(), key=lambda x: -x[1]
        )[:3]

        return {
            "total_devices": len(devices),
            "compliant": compliant,
            "non_compliant": non_compliant,
            "unknown": unknown,
            "os_breakdown": os_breakdown,
            "top_non_compliant_os": [{"os": k, "count": v} for k, v in top_non_compliant_os],
            "config_count": len(configs),
            "config_policy_names": config_policy_names,
            "app_count": len(apps),
            "app_type_breakdown": app_type_breakdown,
        }
