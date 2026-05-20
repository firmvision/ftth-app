import datetime
import enum

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, JSON, String, Text
)
from sqlalchemy.orm import relationship

from database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    teacher = "teacher"
    student = "student"


class QuestionType(str, enum.Enum):
    mcq = "mcq"
    true_false = "true_false"
    multi_select = "multi_select"
    essay = "essay"


class ExamStatus(str, enum.Enum):
    draft = "draft"
    scheduled = "scheduled"
    active = "active"
    ended = "ended"


class SessionStatus(str, enum.Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    submitted = "submitted"
    timed_out = "timed_out"
    auto_submitted = "auto_submitted"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    full_name = Column(String(200), nullable=False)
    email = Column(String(200), unique=True, nullable=True)
    reg_number = Column(String(50), unique=True, nullable=True)
    class_name = Column(String(100), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.student, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    exam_sessions = relationship("ExamSession", back_populates="student")
    created_exams = relationship("Exam", back_populates="created_by_user")


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    code = Column(String(20), unique=True, nullable=False)

    questions = relationship("Question", back_populates="subject")
    exams = relationship("Exam", back_populates="subject")


class Exam(Base):
    __tablename__ = "exams"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(300), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True)
    duration_minutes = Column(Integer, nullable=False, default=60)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    status = Column(Enum(ExamStatus), default=ExamStatus.draft)
    created_by = Column(Integer, ForeignKey("users.id"))
    instructions = Column(Text, nullable=True)
    shuffle_questions = Column(Boolean, default=True)
    shuffle_options = Column(Boolean, default=True)
    pass_score = Column(Float, default=50.0)
    allowed_classes = Column(JSON, default=list)
    max_violations = Column(Integer, default=3)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    subject = relationship("Subject", back_populates="exams")
    created_by_user = relationship("User", back_populates="created_exams")
    questions = relationship("ExamQuestion", back_populates="exam", cascade="all, delete-orphan")
    sessions = relationship("ExamSession", back_populates="exam")


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True)
    text = Column(Text, nullable=False)
    type = Column(Enum(QuestionType), nullable=False)
    points = Column(Float, default=1.0)
    explanation = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    subject = relationship("Subject", back_populates="questions")
    options = relationship("QuestionOption", back_populates="question", cascade="all, delete-orphan", order_by="QuestionOption.order")
    exam_links = relationship("ExamQuestion", back_populates="question")
    answers = relationship("Answer", back_populates="question")


class QuestionOption(Base):
    __tablename__ = "question_options"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"))
    text = Column(Text, nullable=False)
    is_correct = Column(Boolean, default=False)
    order = Column(Integer, default=0)

    question = relationship("Question", back_populates="options")


class ExamQuestion(Base):
    __tablename__ = "exam_questions"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"))
    question_id = Column(Integer, ForeignKey("questions.id"))
    order = Column(Integer, default=0)

    exam = relationship("Exam", back_populates="questions")
    question = relationship("Question", back_populates="exam_links")


class ExamSession(Base):
    __tablename__ = "exam_sessions"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"))
    student_id = Column(Integer, ForeignKey("users.id"))
    token = Column(String(255), unique=True, index=True, nullable=False)
    started_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    score = Column(Float, nullable=True)
    total_points = Column(Float, nullable=True)
    violation_count = Column(Integer, default=0)
    status = Column(Enum(SessionStatus), default=SessionStatus.not_started)
    question_order = Column(JSON, nullable=True)
    option_order = Column(JSON, nullable=True)
    ip_address = Column(String(50), nullable=True)

    exam = relationship("Exam", back_populates="sessions")
    student = relationship("User", back_populates="exam_sessions")
    answers = relationship("Answer", back_populates="session", cascade="all, delete-orphan")
    violations = relationship("ViolationLog", back_populates="session", cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = "answers"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("exam_sessions.id"))
    question_id = Column(Integer, ForeignKey("questions.id"))
    selected_option_ids = Column(JSON, nullable=True)
    text_answer = Column(Text, nullable=True)
    points_awarded = Column(Float, nullable=True)
    is_graded = Column(Boolean, default=False)

    session = relationship("ExamSession", back_populates="answers")
    question = relationship("Question", back_populates="answers")


class ViolationLog(Base):
    __tablename__ = "violation_logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("exam_sessions.id"))
    type = Column(String(50))  # tab_switch | fullscreen_exit | copy_attempt | right_click
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    session = relationship("ExamSession", back_populates="violations")
