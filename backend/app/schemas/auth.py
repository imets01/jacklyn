import datetime as dt
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _email(value: str) -> str:
    email = value.strip().lower()
    if not _EMAIL.match(email) or len(email) > 255:
        raise ValueError("Enter a valid email address.")
    return email


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    base_currency: str
    is_admin: bool
    totp_enabled: bool


class SessionStatus(BaseModel):
    authenticated: bool
    needs_setup: bool
    user: MeOut | None = None


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=256)
    totp_code: str | None = Field(default=None, max_length=12)


class _NewAccount(BaseModel):
    email: str
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(max_length=256)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        return _email(value)

    @field_validator("display_name")
    @classmethod
    def _name(cls, value: str) -> str:
        name = " ".join(value.split())
        if not name:
            raise ValueError("Enter a name.")
        return name


class SetupIn(_NewAccount):
    setup_token: str = Field(min_length=1, max_length=200)
    keep_demo_data: bool = True


class RegisterIn(_NewAccount):
    token: str = Field(min_length=10, max_length=200)


class LinkInfo(BaseModel):
    purpose: str
    label: str | None
    email: str | None
    expires_at: dt.datetime


class ResetIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(max_length=256)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class SessionOut(BaseModel):
    id: int
    created_at: dt.datetime
    last_seen_at: dt.datetime
    expires_at: dt.datetime
    ip_address: str | None
    user_agent: str | None
    current: bool


class TotpSetupOut(BaseModel):
    secret: str
    otpauth_uri: str
    qr_data_url: str


class TotpCodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=12)


class TotpDisableIn(BaseModel):
    password: str = Field(max_length=256)


# ---------------------------------------------------------------- admin


class UserAdminOut(BaseModel):
    id: int
    email: str
    display_name: str
    is_admin: bool
    is_active: bool
    totp_enabled: bool
    has_password: bool
    created_at: dt.datetime
    last_login_at: dt.datetime | None
    account_count: int


class UserAdminPatch(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None


class InviteCreate(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    grants_admin: bool = False
    days: int = Field(default=7, ge=1, le=30)


class InviteOut(BaseModel):
    id: int
    label: str | None
    grants_admin: bool
    created_at: dt.datetime
    expires_at: dt.datetime
    state: str  # pending | used | expired | revoked
    used_by: str | None


class CreatedLink(BaseModel):
    """The only time the raw token is returned; it is never stored in readable form."""

    path: str
    expires_at: dt.datetime
