# tests/test_api.py
from datetime import date, timedelta

import pytest

import database
from conftest import TEACHER_PASS, TEACHER_USER

TODAY = date.today()


# ───────────────────────── Authentication ─────────────────────────

@pytest.mark.parametrize(
    "method, path",
    [
        ("post", "/students/?name=Nobody"),
        ("get", "/students/"),
        ("get", "/students/1"),
        ("get", "/scores/"),
        ("get", "/scores/1"),
    ],
)
def test_routes_require_credentials(anon_client, method, path):
    res = getattr(anon_client, method)(path)
    assert res.status_code == 401
    assert res.headers["www-authenticate"] == "Basic"


def test_wrong_password_rejected(anon_client):
    res = anon_client.get("/students/", auth=(TEACHER_USER, "wrong-password-123"))
    assert res.status_code == 401


def test_unknown_user_rejected(anon_client):
    res = anon_client.get("/students/", auth=("no_such_teacher", "whatever-123"))
    assert res.status_code == 401


def test_non_ascii_credentials_return_401_not_500(anon_client):
    res = anon_client.get("/students/", auth=("tëacher", "pässwörd-123"))
    assert res.status_code == 401


def test_valid_credentials_accepted(client):
    assert client.get("/students/").status_code == 200


def test_inactive_teacher_rejected(client, db_session):
    teacher = db_session.query(database.Teacher).filter_by(username=TEACHER_USER).one()
    teacher.is_active = False
    db_session.commit()

    assert client.get("/students/").status_code == 401


def test_password_is_stored_hashed(db_session):
    teacher = db_session.query(database.Teacher).filter_by(username=TEACHER_USER).one()
    assert teacher.password_hash != TEACHER_PASS
    assert teacher.password_hash.startswith("$argon2")


# ───────────────────────── Ingestion: students ─────────────────────────

def test_create_student(client):
    res = client.post("/students/", params={"name": "Amina Wanjiru"})
    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "Amina Wanjiru"
    assert isinstance(body["id"], int)


def test_create_student_strips_whitespace(client):
    res = client.post("/students/", params={"name": "  Brian Otieno  "})
    assert res.status_code == 201
    assert res.json()["name"] == "Brian Otieno"


def test_create_student_rejects_empty_name(client):
    assert client.post("/students/", params={"name": ""}).status_code == 422


def test_create_student_rejects_overlong_name(client):
    assert client.post("/students/", params={"name": "x" * 101}).status_code == 422


# ───────────────────────── Ingestion: scores ─────────────────────────

def test_submit_valid_score(client, make_student, make_payload):
    student = make_student()
    res = client.post("/scores/", json=make_payload(student["id"]))

    assert res.status_code == 201
    body = res.json()
    assert TEACHER_USER in body["message"]
    assert body["data"]["marks_obtained"] == 85
    assert body["data"]["student_id"] == student["id"]
    assert "id" in body["data"]


def test_excused_absence_needs_no_marks(client, make_student, make_payload):
    student = make_student()
    payload = make_payload(student["id"], status="excused", marks_obtained=None)

    res = client.post("/scores/", json=payload)

    assert res.status_code == 201
    assert res.json()["data"]["marks_obtained"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"marks_obtained": 120}, id="marks-exceed-total"),
        pytest.param({"marks_obtained": -10}, id="negative-marks"),
        pytest.param({"marks_obtained": None}, id="present-without-marks"),
        pytest.param({"status": "late"}, id="invalid-status"),
        pytest.param({"total_marks": 0, "marks_obtained": 0}, id="zero-total"),
        pytest.param({"subject": ""}, id="empty-subject"),
        pytest.param({"subject": "x" * 101}, id="overlong-subject"),
        pytest.param({"student_id": 0}, id="non-positive-student-id"),
        pytest.param({"assessment_date": "not-a-date"}, id="bad-date"),
    ],
)
def test_invalid_scores_rejected(client, make_student, make_payload, overrides):
    student = make_student()
    res = client.post("/scores/", json=make_payload(student["id"], **overrides))
    assert res.status_code == 422


def test_score_for_unknown_student_returns_404(client, make_payload):
    res = client.post("/scores/", json=make_payload(999_999))
    assert res.status_code == 404


def test_rejected_score_is_not_saved(client, make_student, make_payload):
    student = make_student()
    client.post("/scores/", json=make_payload(student["id"], marks_obtained=120))

    res = client.get("/scores/", params={"student_id": student["id"]})
    assert res.json() == []


# ───────────────────────── Reads: students ─────────────────────────

def test_get_student_by_id(client, make_student):
    student = make_student("Carol Njeri")
    res = client.get(f"/students/{student['id']}")
    assert res.status_code == 200
    assert res.json() == student


def test_get_unknown_student_returns_404(client):
    assert client.get("/students/999999").status_code == 404


def test_search_students_is_case_insensitive(client, make_student):
    make_student("David Kamau")
    make_student("Esther Mutua")

    res = client.get("/students/", params={"search": "dAvId"})

    assert res.status_code == 200
    assert [s["name"] for s in res.json()] == ["David Kamau"]


def test_student_pagination(client, make_student):
    for i in range(5):
        make_student(f"Student {i}")

    first = client.get("/students/", params={"limit": 2}).json()
    second = client.get("/students/", params={"limit": 2, "offset": 2}).json()

    assert len(first) == 2 and len(second) == 2
    assert {s["id"] for s in first}.isdisjoint({s["id"] for s in second})


# ───────────────────────── Reads: scores ─────────────────────────

@pytest.fixture()
def seeded(client, make_student, make_payload):
    """One student with three scores, plus a second student with one score."""
    s1, s2 = make_student("Seeded One"), make_student("Seeded Two")

    rows = [
        make_payload(s1["id"], subject="Mathematics", marks_obtained=85,
                     assessment_date=str(TODAY - timedelta(days=10))),
        make_payload(s1["id"], subject="Physics", marks_obtained=70,
                     assessment_date=str(TODAY - timedelta(days=5))),
        make_payload(s1["id"], subject="Mathematics", status="excused",
                     marks_obtained=None, assessment_date=str(TODAY)),
        make_payload(s2["id"], subject="Chemistry", marks_obtained=60),
    ]
    for row in rows:
        assert client.post("/scores/", json=row).status_code == 201

    return {"s1": s1, "s2": s2}


def test_list_scores_filtered_by_student(client, seeded):
    res = client.get("/scores/", params={"student_id": seeded["s1"]["id"]})
    scores = res.json()

    assert res.status_code == 200
    assert len(scores) == 3
    assert all(s["student_id"] == seeded["s1"]["id"] for s in scores)


def test_scores_are_newest_first(client, seeded):
    scores = client.get("/scores/", params={"student_id": seeded["s1"]["id"]}).json()
    dates = [s["assessment_date"] for s in scores]
    assert dates == sorted(dates, reverse=True)


def test_filter_by_status(client, seeded):
    res = client.get(
        "/scores/", params={"student_id": seeded["s1"]["id"], "status": "excused"}
    )
    assert [s["status"] for s in res.json()] == ["excused"]


def test_subject_filter_is_case_insensitive(client, seeded):
    res = client.get(
        "/scores/", params={"student_id": seeded["s1"]["id"], "subject": "mathematics"}
    )
    assert len(res.json()) == 2


def test_date_range_filter(client, seeded):
    res = client.get(
        "/scores/",
        params={
            "student_id": seeded["s1"]["id"],
            "date_from": str(TODAY - timedelta(days=6)),
            "date_to": str(TODAY - timedelta(days=1)),
        },
    )
    scores = res.json()
    assert len(scores) == 1 and scores[0]["subject"] == "Physics"


def test_date_range_with_no_matches(client, seeded):
    res = client.get(
        "/scores/",
        params={"student_id": seeded["s1"]["id"],
                "date_to": str(TODAY - timedelta(days=30))},
    )
    assert res.json() == []


def test_inverted_date_range_rejected(client):
    res = client.get(
        "/scores/",
        params={"date_from": str(TODAY), "date_to": str(TODAY - timedelta(days=7))},
    )
    assert res.status_code == 422


def test_score_pagination(client, seeded):
    sid = seeded["s1"]["id"]
    page1 = client.get("/scores/", params={"student_id": sid, "limit": 1}).json()
    page2 = client.get("/scores/", params={"student_id": sid, "limit": 1, "offset": 1}).json()

    assert len(page1) == 1 and len(page2) == 1
    assert page1[0]["id"] != page2[0]["id"]


@pytest.mark.parametrize("limit", [0, 201, -5])
def test_invalid_limit_rejected(client, limit):
    assert client.get("/scores/", params={"limit": limit}).status_code == 422


def test_get_score_by_id(client, seeded):
    first = client.get("/scores/", params={"student_id": seeded["s2"]["id"]}).json()[0]

    res = client.get(f"/scores/{first['id']}")

    assert res.status_code == 200
    assert res.json()["subject"] == "Chemistry"


def test_get_unknown_score_returns_404(client):
    assert client.get("/scores/999999").status_code == 404


def test_tests_are_isolated(client):
    """Each test gets a fresh database, so no rows leak between tests."""
    assert client.get("/students/").json() == []
