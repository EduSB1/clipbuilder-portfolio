#!/usr/bin/env python3
"""
Promote a user to admin role via direct PostgreSQL connection.

This script connects directly to PostgreSQL (default: localhost:5432)
so you do NOT need to run it inside the Docker container.

Usage:
    python promote_admin.py                                  # promotes admin@clipbuilder.com
    python promote_admin.py admin@example.com          # promotes specific user
    python promote_admin.py admin@example.com 123456   # promotes + resets password

Requirements:
    pip install psycopg2-binary bcrypt
    (or just: pip install psycopg2 bcrypt)

If psycopg2 is not installed, the script will try to install it automatically.
"""

import subprocess
import sys


def ensure_dependencies():
    """Install psycopg2-binary and bcrypt if not already available."""
    for pkg_import, pkg_install in [
        ("psycopg2", "psycopg2-binary"),
        ("bcrypt", "bcrypt"),
    ]:
        try:
            __import__(pkg_import)
        except ImportError:
            print(f"Installing {pkg_install}...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", pkg_install, "-q"]
            )


ensure_dependencies()

import uuid

import psycopg2
import psycopg2.extras

# ---------------------------------------------------------------------------
# Configuration – matches docker-compose.yml defaults
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "clipbuilder",
    "user": "clipbuilder",
    "password": "clipbuilder",
}





def promote_user(email: str, new_password: str | None = None):
    """Promote an existing user to admin, or create one if not found."""
    email = email.strip().lower()

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception as e:
        print(f"\n❌ Failed to connect to PostgreSQL: {e}")
        print(
            f"   Connection: {DB_CONFIG['user']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
        )
        print("   Is the database running? (sudo docker compose ps)")
        sys.exit(1)

    try:
        # Check if user exists
        cur.execute(
            "SELECT id, email, role, is_active, deleted_at FROM users WHERE email = %s",
            (email,),
        )
        user = cur.fetchone()

        if user:
            user_id = user["id"]
            changes = []

            # Promote to admin
            if user["role"] != "admin":
                cur.execute("UPDATE users SET role = 'admin' WHERE id = %s", (user_id,))
                changes.append(f"role: {user['role']} → admin")

            # Reactivate if needed
            if not user["is_active"]:
                cur.execute(
                    "UPDATE users SET is_active = true WHERE id = %s", (user_id,)
                )
                changes.append("is_active: false → true")

            # Clear soft delete if needed
            if user["deleted_at"] is not None:
                cur.execute(
                    "UPDATE users SET deleted_at = NULL WHERE id = %s", (user_id,)
                )
                changes.append("deleted_at: cleared")

            # Reset password if requested
            if new_password:
                changes.append("password: ignored (managed by Clerk)")

            # Update timestamp
            cur.execute("UPDATE users SET updated_at = NOW() WHERE id = %s", (user_id,))

            # Ensure permissions exist
            cur.execute(
                "SELECT id FROM user_permissions WHERE user_id = %s", (user_id,)
            )
            if not cur.fetchone():
                cur.execute(
                    """INSERT INTO user_permissions
                       (user_id, can_use_gemini, can_use_whisper, max_video_size_gb, created_at)
                       VALUES (%s, true, true, 6.0, NOW())""",
                    (user_id,),
                )
                changes.append("permissions: created (all enabled)")

            conn.commit()

            if changes:
                print(f"\n✅ User '{email}' updated:")
                for c in changes:
                    print(f"   • {c}")
            else:
                print(
                    f"\n✅ User '{email}' is already an active admin. No changes needed."
                )

        else:
            # Create new admin user
            user_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO users (id, email, full_name, role, is_active, created_at, updated_at)
                   VALUES (%s, %s, %s, 'admin', true, NOW(), NOW())""",
                (user_id, email, "Administrador"),
            )
            cur.execute(
                """INSERT INTO user_permissions
                   (user_id, can_use_gemini, can_use_whisper, max_video_size_gb, created_at)
                   VALUES (%s, true, true, 6.0, NOW())""",
                (user_id,),
            )
            conn.commit()

            print(f"\n✅ User '{email}' CREATED as admin.")
            print(f"   Password: {new_password or 'admin123'} (Log into Clerk to set)")

        # Show final state
        cur.execute(
            "SELECT id, email, role, is_active, full_name FROM users WHERE email = %s",
            (email,),
        )
        final = cur.fetchone()
        if final:
            print("\n   📋 Final state:")
            print(f"      ID:        {final['id']}")
            print(f"      Email:     {final['email']}")
            print(f"      Role:      {final['role']}")
            print(f"      Active:    {final['is_active']}")
            print(f"      Name:      {final['full_name'] or '(empty)'}")
            print()

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


def list_users():
    """List all users in the database."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception as e:
        print(f"\n❌ Failed to connect: {e}")
        sys.exit(1)

    try:
        cur.execute(
            "SELECT email, role, is_active, deleted_at IS NOT NULL as deleted, full_name "
            "FROM users ORDER BY created_at"
        )
        users = cur.fetchall()
        if not users:
            print("\n(no users found)")
            return

        print(f"\n{'Email':<40} {'Role':<10} {'Active':<8} {'Deleted':<9} {'Name'}")
        print("─" * 100)
        for u in users:
            status_icon = "✅" if u["is_active"] and not u["deleted"] else "❌"
            print(
                f"{status_icon} {u['email']:<38} {u['role']:<10} "
                f"{'yes' if u['is_active'] else 'no':<8} "
                f"{'yes' if u['deleted'] else 'no':<9} "
                f"{u['full_name'] or ''}"
            )
        print()
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--list", "-l"):
        list_users()
    else:
        email = sys.argv[1] if len(sys.argv) >= 2 else "admin@clipbuilder.com"
        password = sys.argv[2] if len(sys.argv) >= 3 else None

        print(f"🔧 Promoting '{email}' to admin...")
        promote_user(email, password)
