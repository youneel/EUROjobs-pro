"""Command-line entrypoint.

Usage:
    python manage.py init-db
    python manage.py ingest [--source NAME ...] [--pages N]
    python manage.py check-links
    python manage.py make-admin EMAIL
    python manage.py serve [--host 127.0.0.1] [--port 8000] [--reload]
"""
from __future__ import annotations

import argparse
import asyncio
import sys


def cmd_init_db(_args: argparse.Namespace) -> int:
    from app.db import init_db

    init_db()
    print("Database schema is up to date.")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    from app.db import init_db
    from app.ingest import run_ingestion

    init_db()
    result = asyncio.run(run_ingestion(args.source or None, args.pages))
    print(
        f"{result['sources']} sources · {result['fetched']} fetched · "
        f"{result['accepted']} accepted · {result['errors']} errors"
    )
    return 0


def cmd_check_links(_args: argparse.Namespace) -> int:
    from app.db import init_db
    from app.links import check_overdue

    init_db()
    result = asyncio.run(check_overdue())
    print(result)
    return 0


def cmd_make_admin(args: argparse.Namespace) -> int:
    from sqlalchemy import select

    from app.config import settings
    from app.db import SessionLocal, init_db
    from app.models import User

    init_db()
    email = args.email.strip().lower()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"No account exists for {email}. Register first, then rerun.", file=sys.stderr)
            return 1
        configured = settings.admin_email_list
        if email not in configured:
            print(
                "Add this address to ADMIN_EMAILS in .env so the admin page stays locked "
                "to the configured allow-list:",
                file=sys.stderr,
            )
            print(f"ADMIN_EMAILS={','.join(configured + [email])}", file=sys.stderr)
            return 2
    print(f"{email} is an administrator.")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manage.py", description="EuroJobs Pro maintenance CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create missing database tables").set_defaults(func=cmd_init_db)

    ingest = sub.add_parser("ingest", help="fetch and store listings once")
    ingest.add_argument("--source", action="append", help="limit to one source (repeatable)")
    ingest.add_argument("--pages", type=int, default=None, help="pages per paginated source")
    ingest.set_defaults(func=cmd_ingest)

    sub.add_parser("check-links", help="revalidate overdue apply links").set_defaults(
        func=cmd_check_links
    )

    admin = sub.add_parser("make-admin", help="verify an account is an administrator")
    admin.add_argument("email")
    admin.set_defaults(func=cmd_make_admin)

    serve = sub.add_parser("serve", help="run the web application")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.add_argument("--log-level", default="info")
    serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
