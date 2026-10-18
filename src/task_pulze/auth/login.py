"""Login page where the user connects their Todoist account with an API token."""

import html
from urllib.parse import parse_qs

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from task_pulze.auth.provider import TodoistAuthProvider
from task_pulze.todoist import http_client

TODOIST_USER_URL = "https://api.todoist.com/api/v1/user"
TOKEN_HELP_URL = "https://app.todoist.com/app/settings/integrations/developer"

_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Connect Todoist · Task Pulze</title>
<style>
  :root {{ color-scheme: light dark; --bg:#f6f6f4; --card:#fff; --fg:#1d1d1b; --muted:#6b6b66;
          --line:#deded8; --accent:#dc4c3e; --err:#b42318; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#161615; --card:#1f1f1d; --fg:#ececea;
          --muted:#a3a39d; --line:#34342f; --err:#ff8a7a; }} }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; min-height:100vh; display:grid; place-items:center; padding:16px;
         background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif; }}
  main {{ width:100%; max-width:420px; background:var(--card); border:1px solid var(--line);
         border-radius:12px; padding:28px; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  p {{ color:var(--muted); margin:0 0 20px; }}
  label {{ display:block; font-weight:600; margin-bottom:6px; }}
  input {{ width:100%; padding:10px 12px; font:inherit; border:1px solid var(--line);
          border-radius:8px; background:transparent; color:inherit; }}
  input:focus {{ outline:2px solid var(--accent); outline-offset:1px; }}
  .help {{ font-size:13px; margin:8px 0 20px; }}
  .help a {{ color:var(--accent); }}
  .error {{ color:var(--err); font-size:14px; margin:0 0 16px; }}
  .actions {{ display:flex; gap:8px; }}
  button {{ flex:1; padding:10px; font:inherit; font-weight:600; border-radius:8px; cursor:pointer;
           border:1px solid var(--line); background:transparent; color:inherit; }}
  button[value=approve] {{ background:var(--accent); border-color:var(--accent); color:#fff; }}
</style>
</head>
<body>
<main>
  <h1>Connect Todoist</h1>
  <p><strong>{client}</strong> wants to manage your Todoist tasks, projects, labels, comments and reminders.</p>
  {error}
  <form method="post" action="/login" autocomplete="off">
    <input type="hidden" name="request" value="{request}">
    <label for="token">Todoist API token</label>
    <input id="token" name="token" type="password" required minlength="20" maxlength="200"
           spellcheck="false" autofocus>
    <div class="help">Find it in Todoist under
      <a href="{help_url}" target="_blank" rel="noopener">Settings → Integrations → Developer</a>.</div>
    <div class="actions">
      <button type="submit" name="action" value="deny" formnovalidate>Cancel</button>
      <button type="submit" name="action" value="approve">Connect</button>
    </div>
  </form>
</main>
</body>
</html>"""

_EXPIRED = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Link expired</title></head>
<body style="font:15px system-ui,sans-serif;padding:24px">
<h1 style="font-size:20px">This sign-in link has expired</h1>
<p>Go back to Claude and connect Task Pulze again.</p></body></html>"""


def _page(client_name: str, request_id: str, error: str | None = None, status: int = 200) -> Response:
    body = _PAGE.format(
        client=html.escape(client_name),
        request=html.escape(request_id),
        help_url=TOKEN_HELP_URL,
        error=f'<p class="error" role="alert">{html.escape(error)}</p>' if error else "",
    )
    return HTMLResponse(body, status_code=status, headers=_SECURITY_HEADERS)


def _expired() -> Response:
    return HTMLResponse(_EXPIRED, status_code=400, headers=_SECURITY_HEADERS)


async def _check_todoist_token(token: str) -> str | None:
    """Return an error message, or None if Todoist accepts the token."""
    try:
        response = await http_client().get(
            TODOIST_USER_URL, headers={"Authorization": f"Bearer {token}"}
        )
    except httpx.TransportError:
        return "Could not reach Todoist. Please try again."
    if response.status_code in (401, 403):
        return "Todoist did not accept this token. Copy it again and retry."
    if response.status_code != 200:
        return f"Todoist returned an error (HTTP {response.status_code}). Please try again."
    return None


def register_login_routes(mcp: FastMCP, provider: TodoistAuthProvider) -> None:
    @mcp.custom_route("/login", methods=["GET"])
    async def login_page(request: Request) -> Response:
        request_id = request.query_params.get("request", "")
        client = await provider.pending_client(request_id)
        if client is None:
            return _expired()
        return _page(client.client_name or "An MCP client", request_id)

    @mcp.custom_route("/login", methods=["POST"])
    async def login_submit(request: Request) -> Response:
        form = parse_qs((await request.body()).decode(), max_num_fields=10)
        request_id = form.get("request", [""])[0]
        action = form.get("action", ["approve"])[0]
        token = form.get("token", [""])[0].strip()

        if action == "deny":
            redirect = await provider.deny(request_id)
            return RedirectResponse(redirect, status_code=302) if redirect else _expired()

        client = await provider.pending_client(request_id)
        if client is None:
            return _expired()
        client_name = client.client_name or "An MCP client"

        if not (20 <= len(token) <= 200) or not token.isalnum():
            return _page(client_name, request_id, "That doesn't look like a Todoist API token.", 400)
        if error := await _check_todoist_token(token):
            return _page(client_name, request_id, error, 400)

        redirect = await provider.approve(request_id, token)
        return RedirectResponse(redirect, status_code=302) if redirect else _expired()
