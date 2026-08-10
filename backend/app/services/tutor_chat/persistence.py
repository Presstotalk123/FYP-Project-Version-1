"""Persistence for the SQL-Question and SQL-Lab AI-tutor conversations.

Mirrors ``app.services.erd_tutor.persistence`` but for the plain-text SQL tutor
chats. One conversation per (user, context):
  - context_type="question" → keyed by (user_id, question_id)
  - context_type="lab"      → keyed by (user_id, session_id)
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.tutor_chat_conversation import TutorChatConversation
from app.models.tutor_chat_message import TutorChatMessage


def find_question_conversation(db: Session, *, user_id: int, question_id: int) -> Optional[TutorChatConversation]:
    """Read-only lookup — returns None instead of creating (for GET endpoints)."""
    return (
        db.query(TutorChatConversation)
        .filter(
            TutorChatConversation.user_id == user_id,
            TutorChatConversation.context_type == "question",
            TutorChatConversation.question_id == question_id,
        )
        .first()
    )


def find_lab_conversation(db: Session, *, user_id: int, session_id: int) -> Optional[TutorChatConversation]:
    """Read-only lookup — returns None instead of creating (for GET endpoints)."""
    return (
        db.query(TutorChatConversation)
        .filter(
            TutorChatConversation.user_id == user_id,
            TutorChatConversation.context_type == "lab",
            TutorChatConversation.session_id == session_id,
        )
        .first()
    )


def get_or_create_question_conversation(db: Session, *, user_id: int, question_id: int) -> TutorChatConversation:
    conv = find_question_conversation(db, user_id=user_id, question_id=question_id)
    if conv:
        return conv
    conv = TutorChatConversation(user_id=user_id, context_type="question", question_id=question_id)
    db.add(conv); db.commit(); db.refresh(conv)
    return conv


def get_or_create_lab_conversation(
    db: Session, *, user_id: int, lab_id: int, session_id: int
) -> TutorChatConversation:
    conv = find_lab_conversation(db, user_id=user_id, session_id=session_id)
    if conv:
        return conv
    conv = TutorChatConversation(
        user_id=user_id, context_type="lab", lab_id=lab_id, session_id=session_id
    )
    db.add(conv); db.commit(); db.refresh(conv)
    return conv


def append_message(db: Session, conv: TutorChatConversation, *, role: str,
                   content: Optional[str] = None) -> TutorChatMessage:
    m = TutorChatMessage(conversation_id=conv.id, role=role, content=content)
    db.add(m); db.commit(); db.refresh(m)
    return m


def transcript(db: Session, conv: TutorChatConversation) -> List[TutorChatMessage]:
    """Full conversation in chronological order."""
    return (
        db.query(TutorChatMessage)
        .filter(TutorChatMessage.conversation_id == conv.id)
        .order_by(TutorChatMessage.created_at, TutorChatMessage.id)
        .all()
    )


def recent_turns(db: Session, conv: TutorChatConversation, *, limit: int = 10) -> List[TutorChatMessage]:
    """Last ``limit`` messages, returned oldest-first for LLM memory injection."""
    rows = (
        db.query(TutorChatMessage)
        .filter(TutorChatMessage.conversation_id == conv.id)
        .order_by(TutorChatMessage.created_at.desc(), TutorChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(rows))
