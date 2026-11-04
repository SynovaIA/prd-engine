from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from prd_engine.api.dependencies import auth


@pytest.fixture
def configured_token(monkeypatch):
    token = "t" * 40
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(api_access_token=token))
    return token


@pytest.mark.asyncio
async def test_valid_bearer_token_is_accepted(configured_token):
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=configured_token)

    assert await auth.require_api_token(credentials) is None


@pytest.mark.asyncio
async def test_missing_credentials_are_rejected(configured_token):
    with pytest.raises(HTTPException) as exc:
        await auth.require_api_token(None)

    assert exc.value.status_code == 401
    assert exc.value.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_invalid_token_is_rejected(configured_token):
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid-token")

    with pytest.raises(HTTPException) as exc:
        await auth.require_api_token(credentials)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid bearer token"


@pytest.mark.asyncio
async def test_non_bearer_scheme_is_rejected(configured_token):
    credentials = HTTPAuthorizationCredentials(scheme="Basic", credentials=configured_token)

    with pytest.raises(HTTPException) as exc:
        await auth.require_api_token(credentials)

    assert exc.value.status_code == 401
