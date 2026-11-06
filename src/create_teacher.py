# src/create_teacher.py
# Usage (from src/):  python create_teacher.py teacher1
import getpass
import sys

from argon2 import PasswordHasher

import database

ph = PasswordHasher()


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: python create_teacher.py <username>")

    username = sys.argv[1].strip()
    if not 3 <= len(username) <= 50:
        sys.exit("Username must be 3-50 characters.")

    password = getpass.getpass("Password: ")
    if len(password) < 10:
        sys.exit("Password must be at least 10 characters.")
    if password != getpass.getpass("Confirm password: "):
        sys.exit("Passwords do not match.")

    database.Base.metadata.create_all(bind=database.engine)

    db = database.SessionLocal()
    try:
        if db.query(database.Teacher).filter_by(username=username).first():
            sys.exit(f"Teacher '{username}' already exists.")
        db.add(database.Teacher(username=username, password_hash=ph.hash(password)))
        db.commit()
        print(f"Created teacher '{username}'.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
