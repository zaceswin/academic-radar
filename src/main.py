# src/main.py
import logging
import secrets
from datetime import date
from typing import Annotated, Literal, Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

# Import our storage layer
import database
from contextlib import asynccontextmanager

from fastapi import Depends, HTTPException, Query, status   # FastAPI removed from this line
from fastapi_offline import FastAPIOffline
# ... the rest of your imports unchanged ...


@asynccontextmanager
async def lifespan(app):
    # Create tables on startup (not at import time, so tests never touch the real DB file).
    database.Base.metadata.create_all(bind=database.engine)
    yield


app = FastAPIOffline(title="Academic Radar Ingestion API", lifespan=lifespan)
logger = logging.getLogger("academic_radar")

app = FastAPI(title="Academic Radar Ingestion API")
security = HTTPBasic()
ph = PasswordHasher()

# Verified against when the username doesn't exist, so response time doesn't
# reveal which usernames are valid.
_DUMMY_HASH = ph.hash(secrets.token_urlsafe(16))


# --- Dependencies ---
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_current_teacher(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
    db: DbSession,
) -> database.Teacher:
    teacher = db.scalar(
        select(database.Teacher).where(database.Teacher.username == credentials.username)
    )

    try:
        ph.verify(teacher.password_hash if teacher else _DUMMY_HASH, credentials.password)
        password_ok = True
    except (VerificationError, InvalidHashError):
        password_ok = False

    if not (teacher and teacher.is_active and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Transparently upgrade the hash if the Argon2 parameters have been strengthened.
    if ph.check_needs_rehash(teacher.password_hash):
        teacher.password_hash = ph.hash(credentials.password)
        db.commit()

    return teacher


CurrentTeacher = Annotated[database.Teacher, Depends(get_current_teacher)]


# --- Pydantic Models ---
class ScoreCreate(BaseModel):
    student_id: int = Field(gt=0)
    subject: str = Field(min_length=1, max_length=100)
    marks_obtained: Optional[float] = Field(default=None, ge=0)
    total_marks: float = Field(gt=0)
    assessment_date: date
    status: Literal["present", "excused"] = "present"

    @model_validator(mode="after")
    def validate_marks(self):
        # Edge case handling: teacher typos
        if self.status == "present" and self.marks_obtained is None:
            raise ValueError("Marks must be provided if student was present")
        if self.marks_obtained is not None and self.marks_obtained > self.total_marks:
            raise ValueError(
                f"Marks obtained ({self.marks_obtained}) cannot exceed "
                f"total marks ({self.total_marks})"
            )
        return self


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


# Plain output model (no input validators), so one odd legacy row
# can't turn a read request into a 500 error.
class ScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    subject: str
    marks_obtained: Optional[float]
    total_marks: float
    assessment_date: date
    status: str


class ScoreResponse(BaseModel):
    message: str
    data: ScoreOut


# --- Helpers ---
def commit_or_rollback(db: Session) -> None:
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database commit failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save data. Please try again.",
        )


Limit = Annotated[int, Query(ge=1, le=200, description="Max rows to return")]
Offset = Annotated[int, Query(ge=0, description="Rows to skip")]


# --- Ingestion Routes ---
@app.post("/students/", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
def create_student(
    name: Annotated[str, Query(min_length=1, max_length=100)],
    db: DbSession,
    teacher: CurrentTeacher,
):
    db_student = database.Student(name=name.strip())
    db.add(db_student)
    commit_or_rollback(db)
    db.refresh(db_student)
    return db_student


@app.post("/scores/", response_model=ScoreResponse, status_code=status.HTTP_201_CREATED)
def submit_score(score: ScoreCreate, db: DbSession, teacher: CurrentTeacher):
    # Verify student exists
    if not db.get(database.Student, score.student_id):
        raise HTTPException(status_code=404, detail="Student not found")

    db_score = database.Score(**score.model_dump())
    db.add(db_score)
    commit_or_rollback(db)
    db.refresh(db_score)
    return {
        "message": f"Score ingested successfully by {teacher.username}",
        "data": db_score,
    }


# --- Read Routes ---
@app.get("/students/", response_model=list[StudentOut])
def list_students(
    db: DbSession,
    teacher: CurrentTeacher,
    search: Annotated[Optional[str], Query(max_length=100, description="Name contains")] = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    query = select(database.Student).order_by(database.Student.id)
    if search:
        query = query.where(database.Student.name.ilike(f"%{search.strip()}%"))
    return db.scalars(query.limit(limit).offset(offset)).all()


@app.get("/students/{student_id}", response_model=StudentOut)
def get_student(student_id: int, db: DbSession, teacher: CurrentTeacher):
    student = db.get(database.Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@app.get("/scores/", response_model=list[ScoreOut])
def list_scores(
    db: DbSession,
    teacher: CurrentTeacher,
    student_id: Optional[int] = Query(default=None, gt=0),
    subject: Optional[str] = Query(default=None, max_length=100),
    status_filter: Optional[Literal["present", "excused"]] = Query(default=None, alias="status"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from cannot be after date_to")

    query = select(database.Score)
    if student_id is not None:
        query = query.where(database.Score.student_id == student_id)
    if subject:
        query = query.where(database.Score.subject.ilike(subject.strip()))
    if status_filter:
        query = query.where(database.Score.status == status_filter)
    if date_from:
        query = query.where(database.Score.assessment_date >= date_from)
    if date_to:
        query = query.where(database.Score.assessment_date <= date_to)

    query = query.order_by(
        database.Score.assessment_date.desc(), database.Score.id.desc()
    )
    return db.scalars(query.limit(limit).offset(offset)).all()


@app.get("/scores/{score_id}", response_model=ScoreOut)
def get_score(score_id: int, db: DbSession, teacher: CurrentTeacher):
    score = db.get(database.Score, score_id)
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")
    return score
