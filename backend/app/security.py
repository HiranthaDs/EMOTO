import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from .config import settings
from .database import get_db
from .models import AuditLog, Session, User

password_hash = PasswordHash.recommended()

ROLE_PERMISSIONS = {
    "Super Admin": {"*"},
    "Sales": {"dashboard:view", "customers:manage", "vehicles:manage", "parts:view", "quotations:manage", "orders:manage", "invoices:view", "warranties:view"},
    "Purchasing": {"dashboard:view", "suppliers:manage", "rfqs:manage", "parts:view", "costs:view"},
    "Inventory": {"dashboard:view", "parts:manage", "inventory:manage", "orders:view", "warranties:manage", "costs:view"},
    "Accounts": {"dashboard:view", "customers:view", "orders:view", "invoices:manage", "payments:manage", "reports:view", "finance:manage", "costs:view"},
}


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def new_session(db: DBSession, user: User) -> Session:
    raw = secrets.token_urlsafe(32)
    sid = hashlib.sha256((raw + settings.session_secret).encode()).hexdigest()
    session = Session(id=sid, user_id=user.id, csrf_token=secrets.token_urlsafe(24), expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.session_hours))
    db.add(session)
    db.commit()
    session.raw_id = raw
    return session


def session_key(raw: str) -> str:
    return hashlib.sha256((raw + settings.session_secret).encode()).hexdigest()


def current_user(emoto_session: str | None = Cookie(None), db: DBSession = Depends(get_db)) -> User:
    if not emoto_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    session = db.get(Session, session_key(emoto_session))
    expires = session.expires_at if session else None
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if not session or expires <= datetime.now(timezone.utc):
        if session:
            db.delete(session)
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    if not session.user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is inactive")
    return session.user


def csrf_protect(request: Request, user: User = Depends(current_user), db: DBSession = Depends(get_db), x_csrf_token: str | None = Header(None)) -> User:
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        raw = request.cookies.get("emoto_session", "")
        session = db.get(Session, session_key(raw))
        if not session or not x_csrf_token or not hmac.compare_digest(session.csrf_token, x_csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid CSRF token")
    return user


def require(permission: str):
    def checker(user: User = Depends(csrf_protect)) -> User:
        allowed = ROLE_PERMISSIONS.get(user.role, set())
        if "*" not in allowed and permission not in allowed:
            resource, action = permission.split(":", 1)
            if action != "view" or f"{resource}:manage" not in allowed:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permission")
        return user
    return checker


def audit(db: DBSession, user: User | None, action: str, entity_type: str | None = None, entity_id: int | None = None, details: str | None = None, ip: str | None = None):
    db.add(AuditLog(user_id=user.id if user else None, action=action, entity_type=entity_type, entity_id=entity_id, details=details, ip_address=ip))

