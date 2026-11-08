"""Create (or reset) an admin user from the command line.

docker compose exec api python -m scripts.create_admin --email admin@example.com --password 'S3cure!pass' --name Admin
(The first admin can also be created in the browser on first visit.)
"""
import argparse
import getpass

from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.models import Role, User
from app.db.session import session_scope


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--password")
    ap.add_argument("--name", default="Administrator")
    a = ap.parse_args()
    pw = a.password or getpass.getpass("Password: ")
    if len(pw) < 8:
        raise SystemExit("Password must be at least 8 characters")
    with session_scope() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == a.email.lower()))
        if user:
            user.password_hash = hash_password(pw)
            user.role = Role.admin
            user.is_active = True
            print(f"Updated existing user {a.email} -> admin")
        else:
            db.add(User(email=a.email.lower(), full_name=a.name, password_hash=hash_password(pw), role=Role.admin))
            print(f"Created admin {a.email}")


if __name__ == "__main__":
    main()
