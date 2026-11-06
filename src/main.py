# src/main.py
import os
import secrets
from datetime import date
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session

import database

app = FastAPI(title="Academic Radar Ingestion API")
security = HTTPBasic()

# Configure these environment variables instead of committing credentials.
TEACHER_USERNAME = os.getenv("TEACHER_USERNAME")
TEACHER_PASSWORD = os.getenv("TEACHER_PASSWORD")


# --- Authentication Dependency ---
def get_current_teacher(credentials: HTTPBasicCredentials = Depends(security)):
    if not TEACHER_USERNAME or not TEACHER_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Teacher authentication is not configured",
        )

    correct_username = secrets.compare_digest(credentials.username, TEACHER_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, TEACHER_PASSWORD)

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Pydantic Validation Models ---
class ScoreCreate(BaseModel):
    student_id: int
    subject: str
    marks_obtained: Optional[float] = None
    total_marks: float
    assessment_date: date
    status: str = "present"

    @model_validator(mode="after")
    def validate_marks(self):
        if self.status == "present" and self.marks_obtained is None:
            raise ValueError("Marks must be provided if student was present")
        if self.marks_obtained is not None:
            if self.marks_obtained < 0:
                raise ValueError("Marks cannot be negative")
            if self.marks_obtained > self.total_marks:
                raise ValueError(
                    f"Marks obtained ({self.marks_obtained}) cannot exceed total marks ({self.total_marks})"
                )
        return self


# --- Ingestion Routes ---
@app.post("/students/")
def create_student(
    name: str,
    db: Session = Depends(get_db),
    teacher: str = Depends(get_current_teacher),
):
    db_student = database.Student(name=name)
    db.add(db_student)
    db.commit()
    db.refresh(db_student)
    return db_student


@app.post("/scores/")
def submit_score(
    score: ScoreCreate,
    db: Session = Depends(get_db),
    teacher: str = Depends(get_current_teacher),
):
    student = db.query(database.Student).filter(database.Student.id == score.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    db_score = database.Score(**score.model_dump())
    db.add(db_score)
    db.commit()
    db.refresh(db_score)
    return {"message": f"Score ingested successfully by {teacher}", "data": db_score}
