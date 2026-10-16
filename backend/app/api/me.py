from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.api import UserOut, UserUpdate

router = APIRouter(prefix="/api/me", tags=["user"])


@router.get("", response_model=UserOut)
def read_me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("", response_model=UserOut)
def update_me(payload: UserUpdate, user: CurrentUser, session: DbSession) -> UserOut:
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.base_currency is not None:
        user.base_currency = payload.base_currency
    session.commit()
    return UserOut.model_validate(user)
