# src/database.py
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Date
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import datetime

# Offline-first SQLite database
SQLALCHEMY_DATABASE_URL = "sqlite:///./academic_radar.sqlite"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    enrollment_date = Column(Date, default=datetime.date.today)
    
    # Relationship to scores
    scores = relationship("Score", back_populates="student")

class Score(Base):
    __tablename__ = "scores"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    subject = Column(String, index=True)
    marks_obtained = Column(Float)
    total_marks = Column(Float)
    assessment_date = Column(Date, default=datetime.date.today)
    status = Column(String, default="present") # Edge case: "excused" or "absent"

    student = relationship("Student", back_populates="scores")

# Create tables
Base.metadata.create_all(bind=engine)
