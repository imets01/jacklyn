from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db import get_db
from app.models import User

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(db: DbSession, settings: Annotated[Settings, Depends(get_settings)]) -> User:
    """Resolve the acting user.

    Phase 1 is single-user: everyone is the default user. Authentication will
    replace this function only; every route already scopes data by the user
    it returns.
    """
    user = db.scalars(select(User).where(User.email == settings.default_user_email)).first()
    if user is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Default user not initialised")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
