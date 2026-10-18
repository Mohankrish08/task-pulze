from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from task_pulze import __version__
from task_pulze.auth.login import register_login_routes
from task_pulze.auth.provider import SCOPE, TodoistAuthProvider
from task_pulze.auth.storage import create_store
from task_pulze.config import Settings
from task_pulze.tools import register_all

INSTRUCTIONS = """Task Pulze manages the user's Todoist account.
- Review the schedule with search_tasks (e.g. 'today | overdue', '7 days') and list_completed_tasks.
- Look up IDs with list_projects, list_sections and list_labels before creating or moving tasks.
- Priorities use the app's labels: P1 is most urgent, P4 is normal.
- Prefer complete_task over delete_task, and archive_project over delete_project.
- Confirm with the user before deleting anything."""


def create_server(settings: Settings) -> FastMCP:
    provider = TodoistAuthProvider(create_store(settings), settings)

    mcp = FastMCP(
        name="task-pulze",
        instructions=INSTRUCTIONS,
        auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=settings.base_url,  # type: ignore[arg-type]
            resource_server_url=f"{settings.base_url}/mcp",  # type: ignore[arg-type]
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]
            ),
            revocation_options=RevocationOptions(enabled=True),
            required_scopes=[SCOPE],
        ),
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[settings.public_host, "localhost:*", "127.0.0.1:*"],
            allowed_origins=[settings.base_url, "https://claude.ai", "http://localhost:*"],
        ),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        stateless_http=True,
    )

    register_login_routes(mcp, provider)
    register_all(mcp)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "server": "task-pulze", "version": __version__})

    return mcp
