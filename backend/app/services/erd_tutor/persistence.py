import json
from typing import Optional
from sqlalchemy.orm import Session
from app.models.erd_tutor_conversation import ErdTutorConversation
from app.models.erd_tutor_message import ErdTutorMessage

def find_conversation(db: Session, *, user_id: int, context_type: str = "standalone",
                      er_diagram_question_id: Optional[int] = None) -> Optional[ErdTutorConversation]:
    """Read-only lookup — returns None instead of creating (for GET endpoints)."""
    return (
        db.query(ErdTutorConversation)
        .filter(ErdTutorConversation.user_id == user_id,
                ErdTutorConversation.er_diagram_question_id == er_diagram_question_id)
        .first()
    )

def get_or_create_conversation(db: Session, *, user_id: int, context_type: str = "standalone",
                               er_diagram_question_id: Optional[int] = None) -> ErdTutorConversation:
    conv = find_conversation(db, user_id=user_id, context_type=context_type,
                             er_diagram_question_id=er_diagram_question_id)
    if conv:
        return conv
    conv = ErdTutorConversation(
        user_id=user_id, context_type=context_type,
        er_diagram_question_id=er_diagram_question_id,
        ibl_stage="orientation", hint_level=1)
    db.add(conv); db.commit(); db.refresh(conv)
    return conv

def loaded_state(conv: ErdTutorConversation) -> dict:
    j = lambda s, d: json.loads(s) if s else d
    return {
        "ibl_stage": conv.ibl_stage, "hint_level": conv.hint_level,
        "misconceptions": j(conv.misconceptions, []),
        "current_erd_model": j(conv.current_erd_model, {}),
        "last_submit_report": j(conv.last_submit_report, {}),
        "last_submit_score": j(conv.last_submit_score, {}),
        "last_query_summary": conv.last_query_summary or "",
        "last_student_goal": conv.last_student_goal or "",
    }

def save_state(db: Session, conv: ErdTutorConversation, **fields) -> None:
    dumps = lambda v: json.dumps(v, ensure_ascii=False)
    for k, v in fields.items():
        if k in {"misconceptions", "current_erd_model", "last_submit_report", "last_submit_score"}:
            setattr(conv, k, dumps(v))
        else:
            setattr(conv, k, v)
    db.commit()

def append_message(db: Session, conv: ErdTutorConversation, *, role: str, mode: str,
                   content: Optional[str] = None, metadata: Optional[dict] = None) -> ErdTutorMessage:
    m = ErdTutorMessage(conversation_id=conv.id, role=role, mode=mode, content=content,
                        metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None)
    db.add(m); db.commit(); db.refresh(m)
    return m

def transcript(db: Session, conv: ErdTutorConversation):
    return (db.query(ErdTutorMessage)
              .filter(ErdTutorMessage.conversation_id == conv.id)
              .order_by(ErdTutorMessage.created_at, ErdTutorMessage.id).all())
