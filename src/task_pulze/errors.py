import logging

import httpx
from mcp.server.fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)


class TaskPulzeError(ToolError):
    """Error whose message is safe to show to the MCP client."""


class AuthenticationError(TaskPulzeError):
    pass


class PermissionDeniedError(TaskPulzeError):
    pass


class NotFoundError(TaskPulzeError):
    pass


class InvalidRequestError(TaskPulzeError):
    pass


class RateLimitError(TaskPulzeError):
    pass


class UpstreamError(TaskPulzeError):
    pass


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict):
        return str(body.get("error") or body.get("message") or body)[:200]
    return str(body)[:200]


def map_todoist_error(exc: Exception, *, resource: str) -> TaskPulzeError:
    if isinstance(exc, TaskPulzeError):
        return exc

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        logger.warning("Todoist returned HTTP %s for %s", status, resource)

        if status == 401:
            return AuthenticationError(
                "Todoist rejected the saved API token. Reconnect the connector with a valid token."
            )
        if status == 403:
            return PermissionDeniedError(
                f"Todoist denied access to {resource}. It may need a paid plan or more permissions."
            )
        if status == 404:
            return NotFoundError(f"{resource} was not found. It may have been completed or deleted.")
        if status in (400, 422):
            return InvalidRequestError(f"Todoist rejected the request: {_detail(exc.response)}")
        if status == 429:
            retry_after = exc.response.headers.get("Retry-After")
            hint = f" Retry after {retry_after}s." if retry_after else " Retry shortly."
            return RateLimitError(f"Todoist rate limit reached.{hint}")
        return UpstreamError(f"Todoist request failed with HTTP {status}. Try again later.")

    if isinstance(exc, httpx.TransportError):
        logger.warning("Network error for %s: %r", resource, exc)
        return UpstreamError("Could not reach Todoist (network error or timeout).")

    logger.exception("Unexpected error for %s", resource)
    return UpstreamError("Unexpected error while talking to Todoist.")
