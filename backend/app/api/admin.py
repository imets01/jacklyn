"""Admin-only: invite friends, manage accounts, issue password-reset links."""

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select

from app.api.deps import AdminUser, DbSession
from app.config import get_settings
from app.models import Account, AuthToken, AuthTokenPurpose, User
from app.models._common import utcnow
from app.schemas.auth import CreatedLink, InviteCreate, InviteOut, UserAdminOut, UserAdminPatch
from app.services import auth as auth_service

router = APIRouter(prefix="/api/admin", tags=["admin"])
RESET_LINK_DAYS = 2


def _user_out(user: User, account_count: int) -> UserAdminOut:
    return UserAdminOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        totp_enabled=user.totp_enabled,
        has_password=user.password_hash is not None,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        account_count=account_count,
    )


@router.get("/users", response_model=list[UserAdminOut])
def list_users(_admin: AdminUser, db: DbSession) -> list[UserAdminOut]:
    counts = dict(db.execute(select(Account.user_id, func.count(Account.id)).group_by(Account.user_id)).tuples().all())
    return [_user_out(user, counts.get(user.id, 0)) for user in db.scalars(select(User).order_by(User.id))]


@router.patch("/users/{user_id}", response_model=UserAdminOut)
def update_user(user_id: int, payload: UserAdminPatch, admin: AdminUser, db: DbSession) -> UserAdminOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == admin.id and (payload.is_active is False or payload.is_admin is False):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't deactivate or demote yourself.")
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.is_admin is not None:
        user.is_admin = payload.is_admin
    db.commit()
    if not user.is_active:
        auth_service.revoke_sessions(db, user.id)  # signs them out immediately
    count = db.scalar(select(func.count(Account.id)).where(Account.user_id == user.id)) or 0
    return _user_out(user, count)


@router.post("/users/{user_id}/reset-link", response_model=CreatedLink, status_code=status.HTTP_201_CREATED)
def create_reset_link(user_id: int, admin: AdminUser, db: DbSession) -> CreatedLink:
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    link, token = auth_service.create_link(
        db, purpose=AuthTokenPurpose.PASSWORD_RESET, created_by=admin, user=user, days=RESET_LINK_DAYS
    )
    return CreatedLink(path=f"/reset/{token}", expires_at=link.expires_at)


@router.get("/invites", response_model=list[InviteOut])
def list_invites(_admin: AdminUser, db: DbSession) -> list[InviteOut]:
    rows = db.execute(
        select(AuthToken, User.display_name)
        .outerjoin(User, User.id == AuthToken.user_id)
        .where(AuthToken.purpose == AuthTokenPurpose.INVITE)
        .order_by(AuthToken.created_at.desc())
        .limit(100)
    ).all()
    return [
        InviteOut(
            id=link.id,
            label=link.label,
            grants_admin=link.grants_admin,
            created_at=link.created_at,
            expires_at=link.expires_at,
            state=auth_service.link_state(link),
            used_by=used_by,
        )
        for link, used_by in rows
    ]


@router.post("/invites", response_model=CreatedLink, status_code=status.HTTP_201_CREATED)
def create_invite(payload: InviteCreate, admin: AdminUser, db: DbSession) -> CreatedLink:
    link, token = auth_service.create_link(
        db,
        purpose=AuthTokenPurpose.INVITE,
        created_by=admin,
        days=payload.days or get_settings().invite_days,
        label=payload.label,
        grants_admin=payload.grants_admin,
    )
    return CreatedLink(path=f"/invite/{token}", expires_at=link.expires_at)


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(invite_id: int, _admin: AdminUser, db: DbSession) -> Response:
    link = db.get(AuthToken, invite_id)
    if link is None or link.purpose is not AuthTokenPurpose.INVITE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found")
    if link.used_at is None and link.revoked_at is None:
        link.revoked_at = utcnow()
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
