from __future__ import annotations

from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from auth.models import User
from auth.models import parse_datetime
from auth.models import utc_now_iso
from auth.security import hash_password
from auth.security import verify_password
from config.settings import AuthSettings
from database.repositories import MetadataRepository


class AuthService:
    def __init__(
        self,
        settings: AuthSettings,
        *,
        repository: MetadataRepository,
    ) -> None:
        self.settings = settings
        self.repository = repository

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
            return self.repository.create_user(user)
        except IntegrityError as exc:
            raise ValueError("Username or email already exists.") from exc

    def authenticate(self, *, username_or_email: str, password: str) -> User | None:
        user = self.get_user_by_username_or_email(username_or_email)
        if user is None:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    def get_user_by_id(self, user_id: str) -> User | None:
        return self.repository.get_user_by_id(user_id)

    def get_user_by_username_or_email(self, value: str) -> User | None:
        return self.repository.get_user_by_username_or_email(value)

    def count_users(self) -> int:
        return self.repository.count_users()
