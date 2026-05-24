from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

from auth.models import User
from auth.models import parse_datetime
from auth.models import utc_now_iso
from auth.security import hash_password
from auth.security import verify_password
from config.settings import AuthSettings


class AuthService:
    def __init__(self, settings: AuthSettings) -> None:
        self.settings = settings
        self.db_path = Path(settings.sqlite_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def create_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
        role: str | None = None,
    ) -> User:
        normalized_username = username.strip()
        normalized_email = email.strip().lower()
        if not normalized_username:
            raise ValueError("Username is required.")
        if "@" not in normalized_email:
            raise ValueError("A valid email is required.")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters.")

        resolved_role = role or ("admin" if self.count_users() == 0 else "user")
        user = User(
            user_id=uuid4().hex,
            username=normalized_username,
            email=normalized_email,
            password_hash=hash_password(password),
            role=resolved_role,
            created_at=parse_datetime(utc_now_iso()),
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO users (user_id, username, email, password_hash, role, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user.user_id,
                        user.username,
                        user.email,
                        user.password_hash,
                        user.role,
                        user.created_at.isoformat().replace("+00:00", "Z"),
                    ),
                )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("Username or email already exists.") from exc
        return user

    def authenticate(self, *, username_or_email: str, password: str) -> User | None:
        user = self.get_user_by_username_or_email(username_or_email)
        if user is None:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    def get_user_by_id(self, user_id: str) -> User | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return self._row_to_user(row)

    def get_user_by_username_or_email(self, value: str) -> User | None:
        normalized = value.strip().lower()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE lower(username) = ? OR lower(email) = ?",
                (normalized, normalized),
            ).fetchone()
        return self._row_to_user(row)

    def count_users(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()
        return int(row["count"]) if row else 0

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _row_to_user(self, row: sqlite3.Row | None) -> User | None:
        if row is None:
            return None
        return User(
            user_id=str(row["user_id"]),
            username=str(row["username"]),
            email=str(row["email"]),
            password_hash=str(row["password_hash"]),
            role=str(row["role"]),
            created_at=parse_datetime(str(row["created_at"])),
        )
