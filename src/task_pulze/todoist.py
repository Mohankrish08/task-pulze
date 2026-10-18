"""Per-request Todoist client bound to the signed-in user's token."""

from collections.abc import AsyncIterator, Awaitable
from typing import TypeVar

import httpx
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context
from todoist_api_python.api_async import TodoistAPIAsync

from task_pulze.auth.provider import TodoistAccessToken
from task_pulze.errors import AuthenticationError, map_todoist_error

T = TypeVar("T")

_http: httpx.AsyncClient | None = None


def http_client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
    return _http


def todoist(ctx: Context) -> TodoistAPIAsync:  # type: ignore[type-arg]
    token = get_access_token()
    if token is None and ctx.request_context.request is not None:
        user = ctx.request_context.request.scope.get("user")
        token = getattr(user, "access_token", None)
    if not isinstance(token, TodoistAccessToken):
        raise AuthenticationError("Not connected to Todoist. Reconnect the connector.")
    return TodoistAPIAsync(token.todoist_token, client=http_client())


async def call(awaitable: Awaitable[T], resource: str) -> T:
    try:
        return await awaitable
    except Exception as exc:
        raise map_todoist_error(exc, resource=resource) from exc


async def collect(
    paginator: Awaitable[AsyncIterator[list[T]]], resource: str, limit: int
) -> list[T]:
    items: list[T] = []
    try:
        async for page in await paginator:
            items.extend(page)
            if len(items) >= limit:
                break
    except Exception as exc:
        raise map_todoist_error(exc, resource=resource) from exc
    return items[:limit]
