"""Persistence for OAuth state: SQLite for local use, Postgres (e.g. Supabase) for hosting.

Bearer tokens, codes and sign-in links are stored only as SHA-256 hashes;
Todoist tokens are encrypted with Fernet.
"""

import asyncio
import hashlib
import json
import logging
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from task_pulze.config import Settings

logger = logging.getLogger(__name__)

_TABLES = """
CREATE TABLE IF NOT EXISTS clients (
    client_id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pending_auth (
    id_hash TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    params TEXT NOT NULL,
    expires_at DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_codes (
    code_hash TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    secret {blob} NOT NULL,
    expires_at DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens (
    token_hash TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    grant_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    scopes TEXT NOT NULL,
    resource TEXT,
    secret {blob} NOT NULL,
    expires_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS tokens_grant_idx ON tokens (grant_id);
CREATE INDEX IF NOT EXISTS tokens_expires_idx ON tokens (expires_at);
"""


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class StoredToken:
    grant_id: str
    client_id: str
    scopes: list[str]
    resource: str | None
    todoist_token: str
    expires_at: int


class Store(ABC):
    """Storage API used by the OAuth provider. Placeholders in SQL are `?`."""

    def __init__(self, secret_key: str) -> None:
        self._fernet = Fernet(secret_key.encode())

    @abstractmethod
    def setup(self) -> None:
        """Create tables and purge expired rows. Runs once, synchronously, at startup."""

    @abstractmethod
    async def _fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def _execute(self, sql: str, *args: Any) -> int:
        """Run a statement and return the number of affected rows."""

    def _encrypt(self, value: str) -> bytes:
        return self._fernet.encrypt(value.encode())

    def _decrypt(self, value: bytes) -> str:
        return self._fernet.decrypt(bytes(value)).decode()

    async def purge_expired(self) -> None:
        now = time.time()
        await self._execute("DELETE FROM pending_auth WHERE expires_at < ?", now)
        await self._execute("DELETE FROM auth_codes WHERE expires_at < ?", now)
        await self._execute("DELETE FROM tokens WHERE expires_at < ?", int(now))

    async def get_client(self, client_id: str) -> str | None:
        rows = await self._fetch("SELECT data FROM clients WHERE client_id = ?", client_id)
        return rows[0]["data"] if rows else None

    async def save_client(self, client_id: str, data: str) -> None:
        await self._execute(
            "INSERT INTO clients (client_id, data) VALUES (?, ?) "
            "ON CONFLICT (client_id) DO UPDATE SET data = excluded.data",
            client_id,
            data,
        )

    async def put_pending(
        self, request_id: str, client_id: str, params: str, expires_at: float
    ) -> None:
        await self._execute(
            "INSERT INTO pending_auth (id_hash, client_id, params, expires_at) VALUES (?, ?, ?, ?)",
            _hash(request_id),
            client_id,
            params,
            expires_at,
        )

    async def get_pending(self, request_id: str) -> tuple[str, str] | None:
        rows = await self._fetch(
            "SELECT client_id, params FROM pending_auth WHERE id_hash = ? AND expires_at >= ?",
            _hash(request_id),
            time.time(),
        )
        return (rows[0]["client_id"], rows[0]["params"]) if rows else None

    async def pop_pending(self, request_id: str) -> tuple[str, str] | None:
        rows = await self._fetch(
            "DELETE FROM pending_auth WHERE id_hash = ? RETURNING client_id, params, expires_at",
            _hash(request_id),
        )
        if not rows or rows[0]["expires_at"] < time.time():
            return None
        return rows[0]["client_id"], rows[0]["params"]

    async def put_code(self, code: str, data: str, todoist_token: str, expires_at: float) -> None:
        await self._execute(
            "INSERT INTO auth_codes (code_hash, data, secret, expires_at) VALUES (?, ?, ?, ?)",
            _hash(code),
            data,
            self._encrypt(todoist_token),
            expires_at,
        )

    async def get_code(self, code: str) -> tuple[dict[str, Any], str] | None:
        rows = await self._fetch(
            "SELECT data, secret FROM auth_codes WHERE code_hash = ? AND expires_at >= ?",
            _hash(code),
            time.time(),
        )
        if not rows:
            return None
        return json.loads(rows[0]["data"]), self._decrypt(rows[0]["secret"])

    async def consume_code(self, code: str) -> bool:
        return await self._execute("DELETE FROM auth_codes WHERE code_hash = ?", _hash(code)) == 1

    async def put_token(
        self,
        token: str,
        kind: str,
        *,
        grant_id: str,
        client_id: str,
        scopes: list[str],
        resource: str | None,
        todoist_token: str,
        expires_at: int,
    ) -> None:
        await self._execute(
            "INSERT INTO tokens (token_hash, kind, grant_id, client_id, scopes, resource, secret, "
            "expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            _hash(token),
            kind,
            grant_id,
            client_id,
            json.dumps(scopes),
            resource,
            self._encrypt(todoist_token),
            expires_at,
        )

    async def get_token(self, token: str, kind: str) -> StoredToken | None:
        rows = await self._fetch(
            "SELECT grant_id, client_id, scopes, resource, secret, expires_at FROM tokens "
            "WHERE token_hash = ? AND kind = ? AND expires_at >= ?",
            _hash(token),
            kind,
            int(time.time()),
        )
        if not rows:
            return None
        row = rows[0]
        return StoredToken(
            grant_id=row["grant_id"],
            client_id=row["client_id"],
            scopes=json.loads(row["scopes"]),
            resource=row["resource"],
            todoist_token=self._decrypt(row["secret"]),
            expires_at=row["expires_at"],
        )

    async def consume_token(self, token: str, kind: str) -> bool:
        deleted = await self._execute(
            "DELETE FROM tokens WHERE token_hash = ? AND kind = ?", _hash(token), kind
        )
        return deleted == 1

    async def delete_grant(self, grant_id: str) -> None:
        await self._execute("DELETE FROM tokens WHERE grant_id = ?", grant_id)


class SQLiteStore(Store):
    def __init__(self, path: Path, secret_key: str) -> None:
        super().__init__(secret_key)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")

    def setup(self) -> None:
        self._db.executescript(_TABLES.format(blob="BLOB"))
        asyncio.run(self.purge_expired())

    async def _fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(row) for row in self._db.execute(sql, args).fetchall()]

    async def _execute(self, sql: str, *args: Any) -> int:
        with self._lock:
            return self._db.execute(sql, args).rowcount


class PostgresStore(Store):
    def __init__(self, url: str, secret_key: str, pool_size: int) -> None:
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        super().__init__(secret_key)
        self._url = url
        # prepare_threshold=None keeps it compatible with Supabase's transaction pooler.
        self._pool = AsyncConnectionPool(
            url,
            min_size=1,
            max_size=pool_size,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": None, "row_factory": dict_row},
        )
        self._open_lock = asyncio.Lock()
        self._opened = False

    def setup(self) -> None:
        import psycopg

        with psycopg.connect(self._url, autocommit=True, prepare_threshold=None) as conn:
            conn.execute(_TABLES.format(blob="BYTEA"))
            now = time.time()
            conn.execute("DELETE FROM pending_auth WHERE expires_at < %s", (now,))
            conn.execute("DELETE FROM auth_codes WHERE expires_at < %s", (now,))
            conn.execute("DELETE FROM tokens WHERE expires_at < %s", (int(now),))
        logger.info("Postgres storage ready")

    async def _ensure_open(self) -> None:
        if self._opened:
            return
        async with self._open_lock:
            if not self._opened:
                await self._pool.open()
                self._opened = True

    async def _fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        await self._ensure_open()
        async with self._pool.connection() as conn:
            cursor = await conn.execute(sql.replace("?", "%s"), args)
            return await cursor.fetchall()  # type: ignore[return-value]

    async def _execute(self, sql: str, *args: Any) -> int:
        await self._ensure_open()
        async with self._pool.connection() as conn:
            cursor = await conn.execute(sql.replace("?", "%s"), args)
            return cursor.rowcount


def create_store(settings: Settings) -> Store:
    secret_key = settings.secret_key.get_secret_value()
    database_url = settings.database_url.get_secret_value() if settings.database_url else ""
    if database_url:
        store: Store = PostgresStore(database_url, secret_key, settings.db_pool_size)
    else:
        logger.info("Using SQLite storage at %s", settings.db_path)
        store = SQLiteStore(settings.db_path, secret_key)
    store.setup()
    return store
