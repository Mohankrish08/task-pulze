"""OAuth 2.1 authorization server that maps MCP tokens to per-user Todoist tokens."""

import secrets
import time
from urllib.parse import urlencode

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from task_pulze.auth.storage import Store
from task_pulze.config import Settings

SCOPE = "todoist"
PENDING_TTL = 600
CODE_TTL = 300


class TodoistAuthCode(AuthorizationCode):
    todoist_token: str


class TodoistRefreshToken(RefreshToken):
    grant_id: str
    todoist_token: str
    resource: str | None = None


class TodoistAccessToken(AccessToken):
    grant_id: str
    todoist_token: str


class TodoistAuthProvider(
    OAuthAuthorizationServerProvider[TodoistAuthCode, TodoistRefreshToken, TodoistAccessToken]
):
    def __init__(self, store: Store, settings: Settings) -> None:
        self._store = store
        self._settings = settings

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        data = await self._store.get_client(client_id)
        return OAuthClientInformationFull.model_validate_json(data) if data else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        assert client_info.client_id is not None
        await self._store.save_client(client_info.client_id, client_info.model_dump_json())

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        assert client.client_id is not None
        await self._store.purge_expired()
        request_id = secrets.token_urlsafe(32)
        await self._store.put_pending(
            request_id, client.client_id, params.model_dump_json(), time.time() + PENDING_TTL
        )
        return f"{self._settings.base_url}/login?{urlencode({'request': request_id})}"

    async def pending_client(self, request_id: str) -> OAuthClientInformationFull | None:
        pending = await self._store.get_pending(request_id)
        return await self.get_client(pending[0]) if pending else None

    async def approve(self, request_id: str, todoist_token: str) -> str | None:
        pending = await self._store.pop_pending(request_id)
        if pending is None:
            return None
        client_id, raw_params = pending
        params = AuthorizationParams.model_validate_json(raw_params)
        code = secrets.token_urlsafe(32)
        auth_code = AuthorizationCode(
            code=code,
            scopes=params.scopes or [SCOPE],
            expires_at=time.time() + CODE_TTL,
            client_id=client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
        )
        await self._store.put_code(
            code, auth_code.model_dump_json(exclude={"code"}), todoist_token, auth_code.expires_at
        )
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    async def deny(self, request_id: str) -> str | None:
        pending = await self._store.pop_pending(request_id)
        if pending is None:
            return None
        params = AuthorizationParams.model_validate_json(pending[1])
        return construct_redirect_uri(
            str(params.redirect_uri),
            error="access_denied",
            error_description="The user cancelled the connection.",
            state=params.state,
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> TodoistAuthCode | None:
        found = await self._store.get_code(authorization_code)
        if found is None:
            return None
        data, todoist_token = found
        code = TodoistAuthCode.model_validate(
            {**data, "code": authorization_code, "todoist_token": todoist_token}
        )
        return code if code.client_id == client.client_id else None

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: TodoistAuthCode
    ) -> OAuthToken:
        if not await self._store.consume_code(authorization_code.code):
            raise TokenError("invalid_grant", "Authorization code was already used.")
        return await self._issue(
            grant_id=secrets.token_urlsafe(16),
            client_id=authorization_code.client_id,
            scopes=authorization_code.scopes,
            resource=authorization_code.resource,
            todoist_token=authorization_code.todoist_token,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> TodoistRefreshToken | None:
        stored = await self._store.get_token(refresh_token, "refresh")
        if stored is None or stored.client_id != client.client_id:
            return None
        return TodoistRefreshToken(
            token=refresh_token,
            client_id=stored.client_id,
            scopes=stored.scopes,
            expires_at=stored.expires_at,
            grant_id=stored.grant_id,
            todoist_token=stored.todoist_token,
            resource=stored.resource,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: TodoistRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        if not await self._store.consume_token(refresh_token.token, "refresh"):
            raise TokenError("invalid_grant", "Refresh token was already used.")
        # Rotate: the old access token stops working too.
        await self._store.delete_grant(refresh_token.grant_id)
        return await self._issue(
            grant_id=refresh_token.grant_id,
            client_id=refresh_token.client_id,
            scopes=scopes,
            resource=refresh_token.resource,
            todoist_token=refresh_token.todoist_token,
        )

    async def load_access_token(self, token: str) -> TodoistAccessToken | None:
        stored = await self._store.get_token(token, "access")
        if stored is None:
            return None
        return TodoistAccessToken(
            token=token,
            client_id=stored.client_id,
            scopes=stored.scopes,
            expires_at=stored.expires_at,
            resource=stored.resource,
            grant_id=stored.grant_id,
            todoist_token=stored.todoist_token,
        )

    async def revoke_token(self, token: TodoistAccessToken | TodoistRefreshToken) -> None:
        await self._store.delete_grant(token.grant_id)

    async def _issue(
        self,
        *,
        grant_id: str,
        client_id: str,
        scopes: list[str],
        resource: str | None,
        todoist_token: str,
    ) -> OAuthToken:
        now = int(time.time())
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(32)
        common = {
            "grant_id": grant_id,
            "client_id": client_id,
            "scopes": scopes,
            "resource": resource,
            "todoist_token": todoist_token,
        }
        await self._store.put_token(
            access, "access", expires_at=now + self._settings.access_token_ttl, **common
        )
        await self._store.put_token(
            refresh, "refresh", expires_at=now + self._settings.refresh_token_ttl, **common
        )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=self._settings.access_token_ttl,
            refresh_token=refresh,
            scope=" ".join(scopes),
        )
