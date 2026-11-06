# tests/conftest.py
from datetime import date

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import main

TEACHER_USER = "teacher1"
TEACHER_PASS = "correct-horse-battery"

# Hash once per test run; Argon2 is deliberately slow.
_PASSWORD_HASH = PasswordHasher().hash(TEACHER_PASS)


@pytest.fixture()
def session_factory():
    """A fresh in-memory SQLite database for every test: nothing touches disk."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared connection, so the in-memory DB persists
    )
    database.Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        session.add(database.Teacher(username=TEACHER_USER, password_hash=_PASSWORD_HASH))
        session.commit()

    yield factory
    engine.dispose()


@pytest.fixture()
def db_session(session_factory):
    """Direct DB access for tests that need to inspect or tweak rows."""
    with session_factory() as session:
        yield session


@pytest.fixture()
def anon_client(session_factory):
    """Client with NO credentials, wired to the in-memory database."""

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[main.get_db] = override_get_db
    # Not used as a context manager, so the startup lifespan (real DB file) never runs.
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


@pytest.fixture()
def client(anon_client):
    """Client that sends the teacher's Basic Auth credentials on every request."""
    anon_client.auth = (TEACHER_USER, TEACHER_PASS)
    return anon_client


@pytest.fixture()
def make_student(client):
    def _make(name="Test Student"):
        res = client.post("/students/", params={"name": name})
        assert res.status_code == 201, res.text
        return res.json()

    return _make


@pytest.fixture()
def make_payload():
    def _make(student_id, **overrides):
        payload = {
            "student_id": student_id,
            "subject": "Mathematics",
            "marks_obtained": 85,
            "total_marks": 100,
            "assessment_date": str(date.today()),
            "status": "present",
        }
        payload.update(overrides)
        return payload

    return _make
