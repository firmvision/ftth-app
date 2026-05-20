import csv
import io
import random
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import hash_password, require_admin, require_super_admin
from database import get_db
from models import (
    Answer, Exam, ExamQuestion, ExamSession, ExamStatus,
    Question, QuestionOption, QuestionType, SessionStatus,
    Subject, User, UserRole, ViolationLog
)

router = APIRouter()

# ─── Schemas ────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    full_name: str
    password: str
    role: UserRole = UserRole.student
    email: Optional[str] = None
    reg_number: Optional[str] = None
    class_name: Optional[str] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    reg_number: Optional[str] = None
    class_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class SubjectCreate(BaseModel):
    name: str
    code: str


class OptionCreate(BaseModel):
    text: str
    is_correct: bool = False
    order: int = 0


class QuestionCreate(BaseModel):
    text: str
    type: QuestionType
    points: float = 1.0
    subject_id: Optional[int] = None
    explanation: Optional[str] = None
    options: List[OptionCreate] = []


class QuestionUpdate(BaseModel):
    text: Optional[str] = None
    type: Optional[QuestionType] = None
    points: Optional[float] = None
    subject_id: Optional[int] = None
    explanation: Optional[str] = None
    options: Optional[List[OptionCreate]] = None


class ExamCreate(BaseModel):
    title: str
    subject_id: Optional[int] = None
    duration_minutes: int = 60
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    instructions: Optional[str] = None
    shuffle_questions: bool = True
    shuffle_options: bool = True
    pass_score: float = 50.0
    allowed_classes: List[str] = []
    max_violations: int = 3


class ExamUpdate(BaseModel):
    title: Optional[str] = None
    subject_id: Optional[int] = None
    duration_minutes: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    instructions: Optional[str] = None
    shuffle_questions: Optional[bool] = None
    shuffle_options: Optional[bool] = None
    pass_score: Optional[float] = None
    allowed_classes: Optional[List[str]] = None
    max_violations: Optional[int] = None
    status: Optional[ExamStatus] = None


class GradeEssay(BaseModel):
    session_id: int
    question_id: int
    points_awarded: float
    feedback: Optional[str] = None


# ─── Users ──────────────────────────────────────────────────────────────────

@router.get("/users")
def list_users(
    role: Optional[str] = None,
    class_name: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    if class_name:
        q = q.filter(User.class_name == class_name)
    users = q.order_by(User.full_name).all()
    return [
        {
            "id": u.id, "username": u.username, "full_name": u.full_name,
            "role": u.role, "class_name": u.class_name, "reg_number": u.reg_number,
            "email": u.email, "is_active": u.is_active, "created_at": u.created_at,
        }
        for u in users
    ]


@router.post("/users", status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(400, "Username already exists")
    user = User(
        username=body.username,
        full_name=body.full_name,
        role=body.role,
        email=body.email,
        reg_number=body.reg_number,
        class_name=body.class_name,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "full_name": user.full_name}


@router.post("/users/bulk-import")
async def bulk_import_users(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    created, skipped, errors = 0, 0, []
    for i, row in enumerate(reader, 2):
        username = (row.get("username") or "").strip()
        full_name = (row.get("full_name") or "").strip()
        password = (row.get("password") or "").strip()
        if not username or not full_name or not password:
            errors.append(f"Row {i}: missing required fields")
            continue
        if db.query(User).filter(User.username == username).first():
            skipped += 1
            continue
        user = User(
            username=username,
            full_name=full_name,
            password_hash=hash_password(password),
            role=row.get("role", "student").strip(),
            email=row.get("email", "").strip() or None,
            reg_number=row.get("reg_number", "").strip() or None,
            class_name=row.get("class_name", "").strip() or None,
        )
        db.add(user)
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped, "errors": errors}


@router.put("/users/{user_id}")
def update_user(
    user_id: int, body: UserUpdate,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    for field, value in body.model_dump(exclude_none=True).items():
        if field == "password":
            user.password_hash = hash_password(value)
        else:
            setattr(user, field, value)
    db.commit()
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), _=Depends(require_super_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    db.delete(user)
    db.commit()
    return {"ok": True}


# ─── Subjects ───────────────────────────────────────────────────────────────

@router.get("/subjects")
def list_subjects(db: Session = Depends(get_db), _=Depends(require_admin)):
    subjects = db.query(Subject).order_by(Subject.name).all()
    return [{"id": s.id, "name": s.name, "code": s.code} for s in subjects]


@router.post("/subjects", status_code=201)
def create_subject(body: SubjectCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if db.query(Subject).filter(Subject.code == body.code).first():
        raise HTTPException(400, "Subject code already exists")
    s = Subject(name=body.name, code=body.code)
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id, "name": s.name, "code": s.code}


@router.put("/subjects/{subject_id}")
def update_subject(
    subject_id: int, body: SubjectCreate,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    s = db.query(Subject).filter(Subject.id == subject_id).first()
    if not s:
        raise HTTPException(404, "Subject not found")
    s.name = body.name
    s.code = body.code
    db.commit()
    return {"ok": True}


@router.delete("/subjects/{subject_id}")
def delete_subject(subject_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    s = db.query(Subject).filter(Subject.id == subject_id).first()
    if not s:
        raise HTTPException(404, "Subject not found")
    db.delete(s)
    db.commit()
    return {"ok": True}


# ─── Questions ──────────────────────────────────────────────────────────────

def _fmt_question(q: Question):
    return {
        "id": q.id,
        "text": q.text,
        "type": q.type,
        "points": q.points,
        "subject_id": q.subject_id,
        "explanation": q.explanation,
        "options": [
            {"id": o.id, "text": o.text, "is_correct": o.is_correct, "order": o.order}
            for o in q.options
        ],
    }


@router.get("/questions")
def list_questions(
    subject_id: Optional[int] = None,
    q_type: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    q = db.query(Question)
    if subject_id:
        q = q.filter(Question.subject_id == subject_id)
    if q_type:
        q = q.filter(Question.type == q_type)
    if search:
        q = q.filter(Question.text.ilike(f"%{search}%"))
    return [_fmt_question(qu) for qu in q.order_by(Question.id.desc()).all()]


@router.post("/questions", status_code=201)
def create_question(
    body: QuestionCreate,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    q = Question(
        text=body.text,
        type=body.type,
        points=body.points,
        subject_id=body.subject_id,
        explanation=body.explanation,
        created_by=user.id,
    )
    db.add(q)
    db.flush()
    for i, opt in enumerate(body.options):
        db.add(QuestionOption(
            question_id=q.id, text=opt.text,
            is_correct=opt.is_correct, order=opt.order or i,
        ))
    db.commit()
    db.refresh(q)
    return _fmt_question(q)


@router.get("/questions/{question_id}")
def get_question(question_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise HTTPException(404, "Question not found")
    return _fmt_question(q)


@router.put("/questions/{question_id}")
def update_question(
    question_id: int, body: QuestionUpdate,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise HTTPException(404, "Question not found")
    for field, value in body.model_dump(exclude_none=True).items():
        if field == "options":
            for opt in q.options:
                db.delete(opt)
            db.flush()
            for i, opt in enumerate(value):
                db.add(QuestionOption(
                    question_id=q.id, text=opt["text"],
                    is_correct=opt["is_correct"], order=opt.get("order", i),
                ))
        else:
            setattr(q, field, value)
    db.commit()
    db.refresh(q)
    return _fmt_question(q)


@router.delete("/questions/{question_id}")
def delete_question(question_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise HTTPException(404, "Question not found")
    db.delete(q)
    db.commit()
    return {"ok": True}


# ─── Exams ──────────────────────────────────────────────────────────────────

def _parse_dt(s: Optional[str]):
    if not s:
        return None
    from datetime import datetime
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _fmt_exam(e: Exam, include_questions: bool = False):
    out = {
        "id": e.id, "title": e.title, "status": e.status,
        "subject_id": e.subject_id,
        "subject_name": e.subject.name if e.subject else None,
        "duration_minutes": e.duration_minutes,
        "start_time": e.start_time.isoformat() if e.start_time else None,
        "end_time": e.end_time.isoformat() if e.end_time else None,
        "instructions": e.instructions,
        "shuffle_questions": e.shuffle_questions,
        "shuffle_options": e.shuffle_options,
        "pass_score": e.pass_score,
        "allowed_classes": e.allowed_classes or [],
        "max_violations": e.max_violations,
        "question_count": len(e.questions),
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
    if include_questions:
        out["questions"] = [
            {
                "exam_question_id": eq.id,
                "order": eq.order,
                **_fmt_question(eq.question),
            }
            for eq in sorted(e.questions, key=lambda x: x.order)
        ]
    return out


@router.get("/exams")
def list_exams(db: Session = Depends(get_db), _=Depends(require_admin)):
    exams = db.query(Exam).order_by(Exam.created_at.desc()).all()
    return [_fmt_exam(e) for e in exams]


@router.post("/exams", status_code=201)
def create_exam(body: ExamCreate, db: Session = Depends(get_db), user=Depends(require_admin)):
    e = Exam(
        title=body.title,
        subject_id=body.subject_id,
        duration_minutes=body.duration_minutes,
        start_time=_parse_dt(body.start_time),
        end_time=_parse_dt(body.end_time),
        instructions=body.instructions,
        shuffle_questions=body.shuffle_questions,
        shuffle_options=body.shuffle_options,
        pass_score=body.pass_score,
        allowed_classes=body.allowed_classes,
        max_violations=body.max_violations,
        created_by=user.id,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return _fmt_exam(e)


@router.get("/exams/{exam_id}")
def get_exam(exam_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    e = db.query(Exam).filter(Exam.id == exam_id).first()
    if not e:
        raise HTTPException(404, "Exam not found")
    return _fmt_exam(e, include_questions=True)


@router.put("/exams/{exam_id}")
def update_exam(
    exam_id: int, body: ExamUpdate,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    e = db.query(Exam).filter(Exam.id == exam_id).first()
    if not e:
        raise HTTPException(404, "Exam not found")
    for field, value in body.model_dump(exclude_none=True).items():
        if field in ("start_time", "end_time"):
            setattr(e, field, _parse_dt(value))
        else:
            setattr(e, field, value)
    db.commit()
    return _fmt_exam(e)


@router.delete("/exams/{exam_id}")
def delete_exam(exam_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    e = db.query(Exam).filter(Exam.id == exam_id).first()
    if not e:
        raise HTTPException(404, "Exam not found")
    db.delete(e)
    db.commit()
    return {"ok": True}


class AddQuestionsBody(BaseModel):
    question_ids: List[int]


@router.post("/exams/{exam_id}/questions")
def add_questions_to_exam(
    exam_id: int, body: AddQuestionsBody,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    e = db.query(Exam).filter(Exam.id == exam_id).first()
    if not e:
        raise HTTPException(404, "Exam not found")
    existing_ids = {eq.question_id for eq in e.questions}
    max_order = max((eq.order for eq in e.questions), default=0)
    added = 0
    for qid in body.question_ids:
        if qid not in existing_ids:
            q = db.query(Question).filter(Question.id == qid).first()
            if q:
                max_order += 1
                db.add(ExamQuestion(exam_id=exam_id, question_id=qid, order=max_order))
                added += 1
    db.commit()
    return {"added": added}


@router.delete("/exams/{exam_id}/questions/{question_id}")
def remove_question_from_exam(
    exam_id: int, question_id: int,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    eq = db.query(ExamQuestion).filter(
        ExamQuestion.exam_id == exam_id,
        ExamQuestion.question_id == question_id,
    ).first()
    if not eq:
        raise HTTPException(404, "Not found")
    db.delete(eq)
    db.commit()
    return {"ok": True}


# ─── Results & Grading ──────────────────────────────────────────────────────

@router.get("/exams/{exam_id}/results")
def exam_results(exam_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    sessions = (
        db.query(ExamSession)
        .filter(ExamSession.exam_id == exam_id)
        .filter(ExamSession.status.in_([SessionStatus.submitted, SessionStatus.auto_submitted, SessionStatus.timed_out]))
        .all()
    )
    rows = []
    for s in sessions:
        rows.append({
            "session_id": s.id,
            "student_id": s.student_id,
            "student_name": s.student.full_name,
            "reg_number": s.student.reg_number,
            "class_name": s.student.class_name,
            "score": s.score,
            "total_points": s.total_points,
            "percentage": round(s.score / s.total_points * 100, 1) if s.total_points else None,
            "status": s.status,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
            "violation_count": s.violation_count,
        })
    rows.sort(key=lambda r: (r["percentage"] or 0), reverse=True)
    return rows


@router.get("/sessions/{session_id}")
def get_session_detail(session_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    s = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not s:
        raise HTTPException(404, "Session not found")
    answers = []
    for a in s.answers:
        q = a.question
        answers.append({
            "question_id": q.id,
            "question_text": q.text,
            "question_type": q.type,
            "points": q.points,
            "selected_option_ids": a.selected_option_ids,
            "text_answer": a.text_answer,
            "points_awarded": a.points_awarded,
            "is_graded": a.is_graded,
            "explanation": q.explanation,
            "options": [
                {"id": o.id, "text": o.text, "is_correct": o.is_correct}
                for o in q.options
            ],
        })
    violations = [
        {"type": v.type, "timestamp": v.timestamp.isoformat()}
        for v in s.violations
    ]
    return {
        "session_id": s.id,
        "student": {"id": s.student.id, "full_name": s.student.full_name, "reg_number": s.student.reg_number},
        "exam_title": s.exam.title,
        "status": s.status,
        "score": s.score,
        "total_points": s.total_points,
        "violation_count": s.violation_count,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
        "answers": answers,
        "violations": violations,
    }


@router.post("/sessions/grade-essay")
def grade_essay(body: GradeEssay, db: Session = Depends(get_db), _=Depends(require_admin)):
    answer = (
        db.query(Answer)
        .filter(Answer.session_id == body.session_id, Answer.question_id == body.question_id)
        .first()
    )
    if not answer:
        raise HTTPException(404, "Answer not found")
    answer.points_awarded = body.points_awarded
    answer.is_graded = True
    # recalculate session score
    session = db.query(ExamSession).filter(ExamSession.id == body.session_id).first()
    total_awarded = sum(a.points_awarded or 0 for a in session.answers if a.is_graded)
    session.score = total_awarded
    db.commit()
    return {"ok": True, "new_score": total_awarded}


@router.get("/classes")
def list_classes(db: Session = Depends(get_db), _=Depends(require_admin)):
    rows = db.query(User.class_name).filter(User.class_name.isnot(None)).distinct().all()
    return sorted([r[0] for r in rows if r[0]])
