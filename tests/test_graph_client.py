"""Tests for app/graph_client.py — Phase 5.

Covers:
- GraphClient.__init__: validates required config fields.
- GraphClient.get_access_token: success, MSAL exception, missing access_token.
- GraphClient._request: success, network error, non-200 response, invalid JSON.
- GraphClient.get_organization: delegates to _request correctly.
- GraphClient.get_users: delegates to _request with correct params.

No real network calls, no real tokens. Uses unittest.mock throughout.
"""

from unittest.mock import MagicMock, patch, PropertyMock
import pytest

from app.graph_client import GraphClient, GraphClientError, GRAPH_BASE_URL, GRAPH_SCOPE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_CONFIG = {
    "azure_tenant_id": "tenant-123",
    "azure_client_id": "client-456",
    "azure_client_secret": "secret-789",
    "openai_api_key": "key",
    "azure_openai_endpoint": "",
    "azure_openai_api_version": "2024-02-15-preview",
    "azure_openai_deployment": "gpt-4o-mini",
}


def _make_config(**overrides):
    """Return a MagicMock mimicking AppConfig with optional field overrides."""
    cfg = MagicMock()
    data = {**VALID_CONFIG, **overrides}
    for k, v in data.items():
        setattr(cfg, k, v)
    return cfg


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestGraphClientInit:
    def test_init_success(self):
        with patch("app.graph_client.get_config", return_value=_make_config()):
            client = GraphClient()
        assert client._tenant_id == "tenant-123"
        assert client._client_id == "client-456"
        assert client._client_secret == "secret-789"
        assert client._base_url == GRAPH_BASE_URL
        assert client._app is None  # lazy, not created yet

    @pytest.mark.parametrize(
        "missing_field",
        ["azure_tenant_id", "azure_client_id", "azure_client_secret"],
    )
    def test_init_raises_when_field_missing(self, missing_field):
        with patch(
            "app.graph_client.get_config",
            return_value=_make_config(**{missing_field: ""}),
        ):
            with pytest.raises(GraphClientError, match="AZURE_TENANT_ID"):
                GraphClient()


# ---------------------------------------------------------------------------
# get_access_token
# ---------------------------------------------------------------------------


class TestGetAccessToken:
    def _client(self):
        with patch("app.graph_client.get_config", return_value=_make_config()):
            return GraphClient()

    def test_returns_token_on_success(self):
        client = self._client()
        mock_app = MagicMock()
        mock_app.acquire_token_for_client.return_value = {"access_token": "tok-abc"}

        with patch("app.graph_client.msal.ConfidentialClientApplication", return_value=mock_app):
            token = client.get_access_token()

        assert token == "tok-abc"
        mock_app.acquire_token_for_client.assert_called_once_with(scopes=[GRAPH_SCOPE])

    def test_raises_on_msal_exception(self):
        client = self._client()
        mock_app = MagicMock()
        mock_app.acquire_token_for_client.side_effect = RuntimeError("boom")

        with patch("app.graph_client.msal.ConfidentialClientApplication", return_value=mock_app):
            with pytest.raises(GraphClientError, match="Failed to acquire"):
                client.get_access_token()

    def test_raises_when_no_access_token_in_result(self):
        client = self._client()
        mock_app = MagicMock()
        mock_app.acquire_token_for_client.return_value = {
            "error": "invalid_client",
            "error_description": "Bad credentials",
        }

        with patch("app.graph_client.msal.ConfidentialClientApplication", return_value=mock_app):
            with pytest.raises(GraphClientError, match="invalid_client"):
                client.get_access_token()

    def test_error_description_excluded_when_contains_secret(self):
        client = self._client()
        mock_app = MagicMock()
        mock_app.acquire_token_for_client.return_value = {
            "error": "invalid_client",
            "error_description": "The secret provided is wrong.",
        }

        with patch("app.graph_client.msal.ConfidentialClientApplication", return_value=mock_app):
            with pytest.raises(GraphClientError) as exc_info:
                client.get_access_token()
        # secret-containing description must not leak into message
        assert "secret provided" not in str(exc_info.value).lower()

    def test_msal_app_is_reused(self):
        """_get_app must be called only once across multiple token requests."""
        client = self._client()
        mock_app = MagicMock()
        mock_app.acquire_token_for_client.return_value = {"access_token": "tok"}

        with patch("app.graph_client.msal.ConfidentialClientApplication", return_value=mock_app) as mock_cls:
            client.get_access_token()
            client.get_access_token()

        mock_cls.assert_called_once()  # MSAL app created only once


# ---------------------------------------------------------------------------
# _request
# ---------------------------------------------------------------------------


class TestRequest:
    def _client_with_token(self, token="test-token"):
        with patch("app.graph_client.get_config", return_value=_make_config()):
            client = GraphClient()
        client.get_access_token = MagicMock(return_value=token)
        return client

    def _mock_response(self, status_code=200, json_data=None, raise_json=False):
        resp = MagicMock()
        resp.status_code = status_code
        if raise_json:
            resp.json.side_effect = ValueError("bad json")
        else:
            resp.json.return_value = json_data or {}
        return resp

    def test_success_returns_json(self):
        client = self._client_with_token()
        payload = {"value": [{"id": "org-1"}]}

        with patch("app.graph_client.requests.request", return_value=self._mock_response(200, payload)) as mock_req:
            result = client._request("GET", "organization")

        assert result == payload
        mock_req.assert_called_once()
        call_kwargs = mock_req.call_args
        assert call_kwargs.args[0] == "GET"
        assert "organization" in call_kwargs.args[1]
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer test-token"
        assert call_kwargs.kwargs["timeout"] == 30

    def test_raises_on_network_error(self):
        import requests as req_lib
        client = self._client_with_token()

        with patch("app.graph_client.requests.request", side_effect=req_lib.RequestException("timeout")):
            with pytest.raises(GraphClientError, match="network or timeout"):
                client._request("GET", "organization")

    def test_raises_on_non_200_response(self):
        client = self._client_with_token()

        with patch("app.graph_client.requests.request", return_value=self._mock_response(403)):
            with pytest.raises(GraphClientError, match="HTTP 403"):
                client._request("GET", "organization")

    def test_raises_on_invalid_json(self):
        client = self._client_with_token()

        with patch("app.graph_client.requests.request", return_value=self._mock_response(200, raise_json=True)):
            with pytest.raises(GraphClientError, match="invalid JSON"):
                client._request("GET", "organization")

    def test_raises_when_token_acquisition_fails(self):
        with patch("app.graph_client.get_config", return_value=_make_config()):
            client = GraphClient()
        client.get_access_token = MagicMock(side_effect=GraphClientError("no token"))

        with pytest.raises(GraphClientError, match="no token"):
            client._request("GET", "organization")

    def test_url_built_correctly(self):
        client = self._client_with_token()

        with patch("app.graph_client.requests.request", return_value=self._mock_response(200, {})) as mock_req:
            client._request("GET", "/users")

        url = mock_req.call_args.args[1]
        assert url == "https://graph.microsoft.com/v1.0/users"

    def test_params_forwarded(self):
        client = self._client_with_token()

        with patch("app.graph_client.requests.request", return_value=self._mock_response(200, {})) as mock_req:
            client._request("GET", "users", params={"$top": 5})

        assert mock_req.call_args.kwargs["params"] == {"$top": 5}


# ---------------------------------------------------------------------------
# get_organization
# ---------------------------------------------------------------------------


class TestGetOrganization:
    def test_returns_dict(self):
        with patch("app.graph_client.get_config", return_value=_make_config()):
            client = GraphClient()
        client._request = MagicMock(return_value={"id": "org-1", "displayName": "Contoso"})

        result = client.get_organization()

        client._request.assert_called_once_with("GET", "organization")
        assert result == {"id": "org-1", "displayName": "Contoso"}

    def test_returns_empty_dict_on_non_dict_response(self):
        with patch("app.graph_client.get_config", return_value=_make_config()):
            client = GraphClient()
        client._request = MagicMock(return_value=[1, 2, 3])  # unexpected list

        result = client.get_organization()
        assert result == {}


# ---------------------------------------------------------------------------
# get_users
# ---------------------------------------------------------------------------


class TestGetUsers:
    def test_returns_dict_with_default_top(self):
        with patch("app.graph_client.get_config", return_value=_make_config()):
            client = GraphClient()
        payload = {"value": [{"id": "u1"}, {"id": "u2"}]}
        client._request = MagicMock(return_value=payload)

        result = client.get_users()

        client._request.assert_called_once_with("GET", "users", params={"$top": 10})
        assert result == payload

    def test_returns_dict_with_custom_top(self):
        with patch("app.graph_client.get_config", return_value=_make_config()):
            client = GraphClient()
        client._request = MagicMock(return_value={"value": []})

        client.get_users(top=25)

        client._request.assert_called_once_with("GET", "users", params={"$top": 25})

    def test_returns_empty_dict_on_non_dict_response(self):
        with patch("app.graph_client.get_config", return_value=_make_config()):
            client = GraphClient()
        client._request = MagicMock(return_value="unexpected string")

        result = client.get_users()
        assert result == {}
