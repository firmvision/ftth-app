import datetime
import random
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from auth import get_current_user
from database import get_db
from models import (
    Answer, Exam, ExamQuestion, ExamSession, ExamStatus,
    Question, QuestionType, SessionStatus, User, ViolationLog
)

router = APIRouter()


# ─── Schemas ────────────────────────────────────────────────────────────────

class AnswerSubmit(BaseModel):
    question_id: int
    selected_option_ids: Optional[List[int]] = None
    text_answer: Optional[str] = None


class ViolationReport(BaseModel):
    type: str  # tab_switch | fullscreen_exit | copy_attempt | right_click


# ─── Helpers ────────────────────────────────────────────────────────────────

def _score_answer(answer: Answer, question: Question) -> float:
    if question.type == QuestionType.essay:
        return 0.0  # manual grading

    correct_ids = {o.id for o in question.options if o.is_correct}
    selected = set(answer.selected_option_ids or [])

    if question.type == QuestionType.mcq or question.type == QuestionType.true_false:
        return question.points if selected == correct_ids else 0.0

    if question.type == QuestionType.multi_select:
        if not correct_ids:
            return 0.0
        # partial credit: proportion of correct options selected, penalise wrong selections
        correct_selected = selected & correct_ids
        wrong_selected = selected - correct_ids
        score = question.points * (len(correct_selected) / len(correct_ids))
        score -= question.points * (len(wrong_selected) / len(correct_ids))
        return max(0.0, round(score, 2))

    return 0.0


def _fmt_question_for_student(q: Question, session: ExamSession, shuffle_options: bool):
    """Return question dict without revealing correct answers."""
    options = list(q.options)
    if shuffle_options and q.type != QuestionType.essay:
        # use stored option order per session if available
        opt_order_map = session.option_order or {}
        stored = opt_order_map.get(str(q.id))
        if stored:
            id_to_opt = {o.id: o for o in options}
            options = [id_to_opt[oid] for oid in stored if oid in id_to_opt]
        else:
            random.shuffle(options)
    return {
        "id": q.id,
        "text": q.text,
        "type": q.type,
        "points": q.points,
        "options": [{"id": o.id, "text": o.text} for o in options],
    }


# ─── Routes ─────────────────────────────────────────────────────────────────

@router.get("/exams")
def list_available_exams(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now = datetime.datetime.utcnow()
    exams = (
        db.query(Exam)
        .filter(Exam.status == ExamStatus.active)
        .all()
    )
    result = []
    for e in exams:
        if e.allowed_classes and user.class_name and user.class_name not in e.allowed_classes:
            continue
        existing = db.query(ExamSession).filter(
            ExamSession.exam_id == e.id,
            ExamSession.student_id == user.id,
        ).first()
        result.append({
            "id": e.id,
            "title": e.title,
            "subject_name": e.subject.name if e.subject else None,
            "duration_minutes": e.duration_minutes,
            "question_count": len(e.questions),
            "instructions": e.instructions,
            "start_time": e.start_time.isoformat() if e.start_time else None,
            "end_time": e.end_time.isoformat() if e.end_time else None,
            "session_status": existing.status if existing else None,
            "session_token": existing.token if existing else None,
        })
    return result


@router.post("/exams/{exam_id}/start")
def start_exam(
    exam_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam or exam.status != ExamStatus.active:
        raise HTTPException(404, "Exam not available")

    if exam.allowed_classes and user.class_name and user.class_name not in exam.allowed_classes:
        raise HTTPException(403, "You are not allowed to take this exam")

    existing = db.query(ExamSession).filter(
        ExamSession.exam_id == exam_id,
        ExamSession.student_id == user.id,
    ).first()

    if existing:
        if existing.status in (SessionStatus.submitted, SessionStatus.auto_submitted, SessionStatus.timed_out):
            raise HTTPException(400, "You have already submitted this exam")
        # resume
        return _build_session_response(existing, exam, db)

    # Build shuffled question order
    eq_links = list(exam.questions)
    if exam.shuffle_questions:
        random.shuffle(eq_links)
    question_order = [eq.question_id for eq in eq_links]

    # Build shuffled option order per question
    option_order: dict = {}
    if exam.shuffle_options:
        for eq in eq_links:
            q = eq.question
            if q.type != QuestionType.essay:
                shuffled_ids = [o.id for o in q.options]
                random.shuffle(shuffled_ids)
                option_order[str(q.id)] = shuffled_ids

    session = ExamSession(
        exam_id=exam_id,
        student_id=user.id,
        token=secrets.token_urlsafe(32),
        started_at=datetime.datetime.utcnow(),
        status=SessionStatus.in_progress,
        question_order=question_order,
        option_order=option_order,
        ip_address=request.client.host if request.client else None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _build_session_response(session, exam, db)


def _build_session_response(session: ExamSession, exam: Exam, db: Session):
    questions = []
    if session.question_order:
        id_to_q = {}
        for eq in exam.questions:
            id_to_q[eq.question_id] = eq.question
        for qid in session.question_order:
            q = id_to_q.get(qid)
            if q:
                questions.append(_fmt_question_for_student(q, session, exam.shuffle_options))

    existing_answers = {
        a.question_id: {
            "selected_option_ids": a.selected_option_ids,
            "text_answer": a.text_answer,
        }
        for a in session.answers
    }

    elapsed_seconds = 0
    if session.started_at:
        elapsed_seconds = (datetime.datetime.utcnow() - session.started_at).total_seconds()
    remaining_seconds = max(0, exam.duration_minutes * 60 - elapsed_seconds)

    return {
        "token": session.token,
        "session_id": session.id,
        "exam_title": exam.title,
        "exam_instructions": exam.instructions,
        "duration_minutes": exam.duration_minutes,
        "remaining_seconds": int(remaining_seconds),
        "max_violations": exam.max_violations,
        "violation_count": session.violation_count,
        "status": session.status,
        "questions": questions,
        "saved_answers": existing_answers,
    }


@router.get("/sessions/{token}")
def get_session(
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = db.query(ExamSession).filter(ExamSession.token == token).first()
    if not session or session.student_id != user.id:
        raise HTTPException(404, "Session not found")

    if session.status == SessionStatus.in_progress:
        elapsed = (datetime.datetime.utcnow() - session.started_at).total_seconds()
        if elapsed >= session.exam.duration_minutes * 60:
            _auto_submit(session, db)

    return _build_session_response(session, session.exam, db)


@router.post("/sessions/{token}/answer")
def save_answer(
    token: str,
    body: AnswerSubmit,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = db.query(ExamSession).filter(ExamSession.token == token).first()
    if not session or session.student_id != user.id:
        raise HTTPException(404, "Session not found")
    if session.status != SessionStatus.in_progress:
        raise HTTPException(400, "Exam already ended")

    answer = db.query(Answer).filter(
        Answer.session_id == session.id,
        Answer.question_id == body.question_id,
    ).first()

    if not answer:
        answer = Answer(session_id=session.id, question_id=body.question_id)
        db.add(answer)

    answer.selected_option_ids = body.selected_option_ids
    answer.text_answer = body.text_answer
    db.commit()
    return {"ok": True}


@router.post("/sessions/{token}/violation")
def log_violation(
    token: str,
    body: ViolationReport,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = db.query(ExamSession).filter(ExamSession.token == token).first()
    if not session or session.student_id != user.id:
        raise HTTPException(404, "Session not found")
    if session.status != SessionStatus.in_progress:
        return {"ok": True, "violation_count": session.violation_count}

    db.add(ViolationLog(session_id=session.id, type=body.type))
    session.violation_count += 1
    db.commit()

    max_v = session.exam.max_violations
    if session.violation_count >= max_v:
        _auto_submit(session, db)
        return {"ok": True, "auto_submitted": True, "violation_count": session.violation_count}

    return {"ok": True, "violation_count": session.violation_count, "max_violations": max_v}


@router.post("/sessions/{token}/submit")
def submit_exam(
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = db.query(ExamSession).filter(ExamSession.token == token).first()
    if not session or session.student_id != user.id:
        raise HTTPException(404, "Session not found")
    if session.status != SessionStatus.in_progress:
        raise HTTPException(400, "Exam already ended")

    score, total = _calculate_score(session, db)
    session.status = SessionStatus.submitted
    session.submitted_at = datetime.datetime.utcnow()
    session.score = score
    session.total_points = total
    db.commit()

    return {
        "ok": True,
        "score": score,
        "total_points": total,
        "percentage": round(score / total * 100, 1) if total else 0,
    }


@router.post("/sessions/{token}/heartbeat")
def heartbeat(
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = db.query(ExamSession).filter(ExamSession.token == token).first()
    if not session or session.student_id != user.id:
        raise HTTPException(404, "Session not found")

    if session.status == SessionStatus.in_progress:
        elapsed = (datetime.datetime.utcnow() - session.started_at).total_seconds()
        remaining = max(0, session.exam.duration_minutes * 60 - elapsed)
        if remaining <= 0:
            _auto_submit(session, db)
            return {"status": "timed_out", "remaining_seconds": 0}
        return {"status": "in_progress", "remaining_seconds": int(remaining)}

    return {"status": session.status, "remaining_seconds": 0}


# ─── Internal helpers ────────────────────────────────────────────────────────

def _calculate_score(session: ExamSession, db: Session):
    exam = session.exam
    total_points = sum(eq.question.points for eq in exam.questions)
    scored_points = 0.0

    for answer in session.answers:
        q = answer.question
        if q.type == QuestionType.essay:
            answer.points_awarded = 0.0
            answer.is_graded = False
        else:
            pts = _score_answer(answer, q)
            answer.points_awarded = pts
            answer.is_graded = True
            scored_points += pts

    db.flush()
    return round(scored_points, 2), round(total_points, 2)


def _auto_submit(session: ExamSession, db: Session):
    score, total = _calculate_score(session, db)
    session.status = SessionStatus.auto_submitted
    session.submitted_at = datetime.datetime.utcnow()
    session.score = score
    session.total_points = total
    db.commit()
