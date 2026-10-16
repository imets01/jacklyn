"""Time-based one-time passwords (authenticator apps) with replay protection."""

import hmac
import time

import pyotp
import segno

ISSUER = "Jacklyn"
STEP_SECONDS = 30


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, account: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=ISSUER)


def qr_svg_data_url(uri: str) -> str:
    # svg_data_uri includes the xmlns attribute that browsers need to render an SVG inside <img>.
    return segno.make(uri, error="m").svg_data_uri(scale=5, dark="#0f1a14", light="#ffffff", border=2)


def verify(secret: str, code: str, last_used_step: int | None) -> int | None:
    """Return the accepted time step, or None. Allows +-1 step of clock drift; a step is never reused."""
    code = "".join(code.split())
    if not (code.isdigit() and len(code) == 6):
        return None
    totp = pyotp.TOTP(secret)
    now = int(time.time())
    for offset in (0, -1, 1):
        step = now // STEP_SECONDS + offset
        if last_used_step is not None and step <= last_used_step:
            continue
        if hmac.compare_digest(totp.at(step * STEP_SECONDS), code):
            return step
    return None
