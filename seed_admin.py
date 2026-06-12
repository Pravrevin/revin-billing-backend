"""
seed_admin.py
-------------
Run AFTER applying sql_scripts/multitenancy_migration.sql.

Ensures the default pharmacy (id=1) exists and creates the super-admin login.
Prints the credentials to hand to the operator.

Usage:
    python seed_admin.py                       # uses defaults / env vars
    ADMIN_USERNAME=boss ADMIN_PASSWORD=secret python seed_admin.py
"""
import os
import sys

from app.database import SessionLocal
from app.models.auth import AppUser, Pharmacy
from app.auth.security import hash_password

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@123")
ADMIN_NAME = os.getenv("ADMIN_NAME", "Super Admin")


def run():
    db = SessionLocal()
    try:
        # Default pharmacy for any legacy data (migration also inserts id=1).
        default = db.query(Pharmacy).filter(Pharmacy.id == 1).first()
        if not default:
            default = Pharmacy(id=1, name="Default Pharmacy", code="DEFAULT", is_active=True)
            db.add(default)
            db.commit()
            print("[INFO] Created default pharmacy (id=1).")

        existing = db.query(AppUser).filter(AppUser.username == ADMIN_USERNAME).first()
        if existing:
            # Reset password / ensure superadmin role so the operator can always log in.
            existing.password_hash = hash_password(ADMIN_PASSWORD)
            existing.role = "superadmin"
            existing.is_active = True
            existing.pharmacy_id = None
            db.commit()
            action = "updated (password reset)"
        else:
            admin = AppUser(
                pharmacy_id=None,
                username=ADMIN_USERNAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                full_name=ADMIN_NAME,
                role="superadmin",
                is_active=True,
            )
            db.add(admin)
            db.commit()
            action = "created"

        print("=" * 56)
        print("  Super-admin account " + action)
        print("=" * 56)
        print(f"  Username : {ADMIN_USERNAME}")
        print(f"  Password : {ADMIN_PASSWORD}")
        print("  Login at : /login  (you'll be routed to /admin)")
        print("=" * 56)
        print("  Change ADMIN_PASSWORD via env var for production.")
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"[ERROR] {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    run()
