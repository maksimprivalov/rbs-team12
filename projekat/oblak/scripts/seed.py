"""
Seed skripta — kreira test korisnike u bazi.
Pokretanje: cd server && python ../scripts/seed.py
"""
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from db import SessionLocal, engine
from models import AuditLog, User
from db import Base

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

Base.metadata.create_all(bind=engine)

SEED_USERS = [
    {"username": "admin", "password": "admin123", "is_admin": True},
    {"username": "alice", "password": "alice123", "is_admin": False},
    {"username": "bob", "password": "bob123", "is_admin": False},
]


def seed(db: Session) -> None:
    for u in SEED_USERS:
        exists = db.query(User).filter(User.username == u["username"]).first()
        if exists:
            print(f"  skip: {u['username']} already exists")
            continue
        user = User(
            username=u["username"],
            hashed_password=pwd_context.hash(u["password"]),
            api_key=secrets.token_hex(32),
            is_admin=u["is_admin"],
        )
        db.add(user)
        db.flush()
        db.add(AuditLog(user_id=user.id, action="SEED_CREATE", details=f"seeded user {u['username']}"))
        print(f"  created: {u['username']} (admin={u['is_admin']})")
    db.commit()


if __name__ == "__main__":
    with SessionLocal() as db:
        print("Seeding database...")
        seed(db)
        print("Done.")
