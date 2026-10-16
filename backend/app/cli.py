"""Server-side admin commands (for when nobody can sign in).

docker compose exec backend python -m app.cli users
docker compose exec backend python -m app.cli reset-link you@example.com
"""

import argparse
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuthTokenPurpose, User
from app.services.auth import create_link, needs_setup, normalize_email


def list_users() -> int:
    with SessionLocal() as db:
        if needs_setup(db):
            print("Setup isn't complete yet - use the setup token from the server log (data/setup-token.txt).")
        for user in db.scalars(select(User).order_by(User.id)):
            flags = [
                f
                for f, on in (("admin", user.is_admin), ("2fa", user.totp_enabled), ("inactive", not user.is_active))
                if on
            ]
            print(f"{user.id:>4}  {user.email:<40} {user.display_name:<24} {' '.join(flags)}")
    return 0


def reset_link(email: str) -> int:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == normalize_email(email)))
        if user is None or not user.is_active:
            print(f"No active account for {email}.", file=sys.stderr)
            return 1
        link, token = create_link(db, purpose=AuthTokenPurpose.PASSWORD_RESET, created_by=None, user=user, days=1)
        print(f"Password reset link for {user.email} (valid until {link.expires_at:%Y-%m-%d %H:%M} UTC):")
        print(f"\n    <your Jacklyn address>/reset/{token}\n")
        print("Using it sets a new password, turns off two-factor and signs out every other session.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__.splitlines()[0] if __doc__ else None)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("users", help="list accounts")
    reset = commands.add_parser("reset-link", help="print a one-time password-reset link")
    reset.add_argument("email")
    args = parser.parse_args(argv)
    if args.command == "users":
        return list_users()
    return reset_link(args.email)


if __name__ == "__main__":
    raise SystemExit(main())
