from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Protocol


class PermitConsumptionStore(Protocol):
    """Atomic one-shot permit consumption boundary."""

    def consume_once(self, permit_id: str, consumed_at: datetime) -> bool:
        """Return True exactly once for a permit id, False thereafter."""
        ...


class SQLitePermitConsumptionStore:
    """Durable cross-process one-shot store backed by SQLite.

    A single database path may be shared by multiple Gateway instances on the
    same durable filesystem. The PRIMARY KEY makes consumption atomic across
    processes and survives process restart.
    """

    ENV_PATH = "VALO_GATEWAY_PERMIT_STORE"

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @classmethod
    def default(cls) -> "SQLitePermitConsumptionStore":
        configured = os.environ.get(cls.ENV_PATH)
        if configured:
            return cls(configured)
        return cls(
            Path.home()
            / ".local"
            / "state"
            / "valo-gateway"
            / "permit-consumption.sqlite3"
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS consumed_permits (
                    permit_id TEXT PRIMARY KEY NOT NULL,
                    consumed_at TEXT NOT NULL
                )
                """
            )

    def consume_once(self, permit_id: str, consumed_at: datetime) -> bool:
        if not permit_id:
            raise ValueError("permit_id must be non-empty")
        timestamp = consumed_at.isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO consumed_permits (permit_id, consumed_at) VALUES (?, ?)",
                    (permit_id, timestamp),
                )
            except sqlite3.IntegrityError:
                connection.execute("ROLLBACK")
                return False
            connection.execute("COMMIT")
            return True
