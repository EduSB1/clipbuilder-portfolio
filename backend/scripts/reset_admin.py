import os
import sys

# Add the current directory to sys.path to make imports work
sys.path.append(os.getcwd())

try:
    from sqlalchemy import text

    from app.admin.models import User, UserPermission
    from app.database import SessionLocal
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    try:
        import bcrypt

        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    except ImportError:
        print("WARNING: bcrypt not installed. Password will not be set.")
        print("         Run: pip install bcrypt")
        return ""


def reset_user(email: str, password: str | None = None):
    """Reset (or create) admin user with the given email and optional password."""
    print(f"Ensuring admin role for {email}...")
    try:
        with SessionLocal() as db:
            # Check connection first
            try:
                db.execute(text("SELECT 1"))
            except Exception as e:
                print(f"DB Connection failed: {e}")
                return

            user = db.query(User).filter(User.email == email).first()

            if not user:
                print(f"User {email} not found. Creating...")
                import uuid

                pw_hash = hash_password(password) if password else ""

                user = User(
                    id=str(uuid.uuid4()),
                    email=email.strip().lower(),
                    full_name="Administrador",
                    role="admin",
                    is_active=True,
                    password_hash=pw_hash if pw_hash else None,
                )
                db.add(user)
                db.flush()

                perms = UserPermission(
                    user_id=user.id,
                    can_use_gemini=True,
                    
                    can_use_whisper=True,
                    max_video_size_gb=6.0,
                )
                db.add(perms)
                db.commit()

                print(f"SUCCESS: User {email} created.")
                print("Role: admin")
                if pw_hash:
                    print("Local password: set ✓")
                else:
                    print("Local password: NOT set (no password provided)")
                return

            # Update existing user
            user.role = "admin"
            user.is_active = True
            user.deleted_at = None

            # Set/update password if provided
            if password:
                pw_hash = hash_password(password)
                if pw_hash:
                    user.password_hash = pw_hash
                    print("Local password: updated ✓")

            # Ensure permissions exist
            if not user.permissions:
                perms = UserPermission(
                    user_id=user.id,
                    can_use_gemini=True,
                    
                    can_use_whisper=True,
                    max_video_size_gb=6.0,
                )
                db.add(perms)

            db.commit()
            print(f"SUCCESS: User {email} updated.")
            print("Role: admin")

            if user.password_hash:
                print("Local JWT login: available ✓")
            else:
                print("Local JWT login: no password set")
                print(f"  To enable: python reset_admin.py {email} <password>")

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    email = "admin@clipbuilder.com"
    password = None

    if len(sys.argv) >= 2:
        email = sys.argv[1]
    if len(sys.argv) >= 3:
        password = sys.argv[2]

    reset_user(email, password)
