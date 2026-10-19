# task-pulze

MCP server for Todoist. Connect it to Claude as a custom connector and manage your
tasks, projects, labels, comments and reminders from chat.

Each user signs in with their own Todoist API token. The token is stored encrypted.

## Setup

```
pip install -e .
```

Create `.env.dev`:

```
TASK_PULZE_PUBLIC_URL=http://127.0.0.1:8000
TASK_PULZE_SECRET_KEY=
TASK_PULZE_DATABASE_URL=
```

Generate the secret key with:

```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Leave `TASK_PULZE_DATABASE_URL` empty to use SQLite, or set a Postgres URL
(Supabase transaction pooler works).

## Run

```
python -m task_pulze
```

Server runs at `http://127.0.0.1:8000/mcp`. Test it with the MCP Inspector:

```
npx @modelcontextprotocol/inspector@latest
```

## Deploy

Set `TASK_PULZE_ENV=prod` on the host. In prod the public URL must be https and a
database URL is required.

On Render:

- Build: `pip install .`
- Start: `TASK_PULZE_PORT=$PORT task-pulze`
- Env: `TASK_PULZE_ENV`, `TASK_PULZE_PUBLIC_URL`, `TASK_PULZE_HOST=0.0.0.0`,
  `TASK_PULZE_SECRET_KEY`, `TASK_PULZE_DATABASE_URL`
- Health check: `/health`

Then add `https://<your-url>/mcp` in Claude under Settings > Connectors.

## Config

| Variable | Default |
|---|---|
| `TASK_PULZE_ENV` | `dev` |
| `TASK_PULZE_PUBLIC_URL` | `http://localhost:8000` |
| `TASK_PULZE_HOST` | `127.0.0.1` |
| `TASK_PULZE_PORT` | `8000` |
| `TASK_PULZE_SECRET_KEY` | required |
| `TASK_PULZE_DATABASE_URL` | empty (SQLite) |
| `TASK_PULZE_DB_PATH` | `task_pulze.db` |
| `TASK_PULZE_LOG_LEVEL` | `INFO` |

Don't change the secret key once users have signed in. They will have to sign in again.

## License

See [LICENSE](LICENSE).
