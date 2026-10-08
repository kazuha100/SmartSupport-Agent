from datetime import datetime, timedelta, timezone
from typing import Callable

import bcrypt
import jwt
from uuid import uuid4
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings
from app.models import AuthUser
from app.repository import Repository


bearer_scheme = HTTPBearer(auto_error=False)


class AuthService:
    def __init__(self, repository: Repository, settings: Settings):
        self.repository = repository
        self.settings = settings

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        return bcrypt.checkpw(password.encode(), password_hash.encode())

    def seed_staff_users(self) -> None:
        users = (("admin-001", "admin", "客服管理员", "admin", "Admin123!"),)
        for user_id, username, display_name, role, password in users:
            if self.repository.get_user_by_username(username) is None:
                self.repository.create_user_if_missing(
                    {
                        "user_id": user_id,
                        "username": username,
                        "password_hash": self.hash_password(password),
                        "display_name": display_name,
                        "role": role,
                        "active": 1,
                    }
                )
            else:
                self.repository.update_user_display_name(username, display_name)
        self.repository.consolidate_staff_accounts("admin", ("agent",))

    def register_customer(self, username: str, display_name: str, password: str) -> tuple[str, AuthUser] | None:
        if self.repository.get_user_by_username(username) is not None:
            return None
        record = self.repository.create_user_if_missing({
            "user_id": f"USR-{uuid4().hex[:16].upper()}",
            "username": username,
            "password_hash": self.hash_password(password),
            "display_name": display_name.strip(),
            "role": "customer",
            "active": 1,
        })
        user = AuthUser(**{key: record[key] for key in ("user_id", "username", "display_name", "role")})
        return self._issue_token(user), user

    def login(self, username: str, password: str) -> tuple[str, AuthUser] | None:
        record = self.repository.get_user_by_username(username)
        if not record or not record["active"] or not self.verify_password(password, record["password_hash"]):
            return None
        user = AuthUser(**{key: record[key] for key in ("user_id", "username", "display_name", "role")})
        return self._issue_token(user), user

    def _issue_token(self, user: AuthUser) -> str:
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                "sub": user.user_id,
                "role": user.role,
                "iat": now,
                "exp": now + timedelta(minutes=self.settings.auth_token_minutes),
            },
            self.settings.auth_secret,
            algorithm="HS256",
        )

    def decode_user(self, token: str) -> AuthUser:
        try:
            payload = jwt.decode(token, self.settings.auth_secret, algorithms=["HS256"])
            record = self.repository.get_user_by_id(payload["sub"])
        except (jwt.PyJWTError, KeyError) as exc:
            raise HTTPException(status_code=401, detail="登录已失效") from exc
        if not record or not record["active"]:
            raise HTTPException(status_code=401, detail="用户不可用")
        return AuthUser(**{key: record[key] for key in ("user_id", "username", "display_name", "role")})


def build_auth_dependencies(auth_service: AuthService) -> tuple[Callable, Callable]:
    def current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> AuthUser:
        if credentials is None:
            raise HTTPException(status_code=401, detail="请先登录")
        return auth_service.decode_user(credentials.credentials)

    def require_roles(*roles: str) -> Callable:
        def dependency(user: AuthUser = Depends(current_user)) -> AuthUser:
            if user.role not in roles:
                raise HTTPException(status_code=403, detail="权限不足")
            return user

        return dependency

    return current_user, require_roles
