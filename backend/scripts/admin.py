#!/usr/bin/env python3
"""Administração de contas pela linha de comando.

Roda dentro do container do backend, que já tem DATABASE_URL e as demais
variáveis:

    docker compose exec backend python scripts/admin.py list
    docker compose exec backend python scripts/admin.py promote pessoa@example.com
    docker compose exec backend python scripts/admin.py set-password pessoa@example.com

O primeiro admin de uma instalação nova é criado sozinho na inicialização, a
partir de ADMIN_EMAIL e ADMIN_PASSWORD (app/admin/bootstrap.py). Este comando
serve para os casos seguintes: promover outra conta, trocar a senha do login
de emergência ou conferir quem é admin.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.admin.bootstrap import (  # noqa: E402
    MIN_ADMIN_PASSWORD_LENGTH,
    hash_password,
    make_admin,
    password_is_acceptable,
)
from app.admin.crud import get_user_by_email  # noqa: E402
from app.admin.models import User  # noqa: E402
from app.database import SessionLocal  # noqa: E402


def cmd_list(_: argparse.Namespace) -> int:
    with SessionLocal() as db:
        admins = db.query(User).filter(User.role == "admin").order_by(User.email).all()
        if not admins:
            print("Nenhum admin cadastrado.")
            return 1
        for user in admins:
            status = "ativo" if user.is_active and user.deleted_at is None else "inativo"
            local = "com senha local" if user.password_hash else "sem senha local"
            clerk = "vinculado ao Clerk" if user.clerk_id else "sem Clerk"
            print(f"{user.email}  [{status}, {local}, {clerk}]")
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        try:
            user = make_admin(db, args.email)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
    print(f"{user.email} agora é admin ativo.")
    return 0


def _read_new_password() -> str:
    first = getpass.getpass("Nova senha: ")
    if first != getpass.getpass("Repita a senha: "):
        raise ValueError("As senhas não conferem.")
    return first


def cmd_set_password(args: argparse.Namespace) -> int:
    try:
        password = _read_new_password()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    if not password_is_acceptable(password):
        print(f"A senha precisa ter pelo menos {MIN_ADMIN_PASSWORD_LENGTH} caracteres.", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        user = get_user_by_email(db, args.email.strip().lower())
        if user is None or user.role != "admin":
            print("Admin não encontrado. Use 'promote' primeiro.", file=sys.stderr)
            return 1
        user.password_hash = hash_password(password)
        db.commit()
    print(f"Senha local de {args.email} atualizada.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Administração de contas do ClipBuilder")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="lista os admins").set_defaults(func=cmd_list)
    promote = sub.add_parser("promote", help="torna uma conta admin ativo (cria se não existir)")
    promote.add_argument("email")
    promote.set_defaults(func=cmd_promote)
    set_password = sub.add_parser("set-password", help="define a senha do login de emergência")
    set_password.add_argument("email")
    set_password.set_defaults(func=cmd_set_password)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
