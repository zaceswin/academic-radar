# src/main.py
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, model_validator
from datetime import date
from typing import Optional

# Import our storage layer
import database

app = FastAPI(title="Academic Radar Ingestion API")

# Dependency to get DB session
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
    status: str = "present" # Can be "present", "excused"

    @model_validator(mode='after')
    def validate_marks(self):
        # Edge case handling: Teacher typos
        if self.status == "present" and self.marks_obtained is None:
            raise ValueError("Marks must be provided if student was present")
        if self.marks_obtained is not None:
            if self.marks_obtained < 0:
                raise ValueError("Marks cannot be negative")
            if self.marks_obtained > self.total_marks:
                raise ValueError(f"Marks obtained ({self.marks_obtained}) cannot exceed total marks ({self.total_marks})")
        return self

# --- Ingestion Routes ---
@app.post("/students/")
def create_student(name: str, db: Session = Depends(get_db)):
    db_student = database.Student(name=name)
    db.add(db_student)
    db.commit()
    db.refresh(db_student)
    return db_student

@app.post("/scores/")
def submit_score(score: ScoreCreate, db: Session = Depends(get_db)):
    # Verify student exists
    student = db.query(database.Student).filter(database.Student.id == score.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    db_score = database.Score(**score.model_dump())
    db.add(db_score)
    db.commit()
    db.refresh(db_score)
    return {"message": "Score ingested successfully", "data": db_score}
