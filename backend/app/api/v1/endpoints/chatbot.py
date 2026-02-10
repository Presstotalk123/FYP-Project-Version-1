from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import httpx

from app.database import get_db
from app.dependencies import get_current_user
from app.config import settings
from app.models.user import User
from app.models.question import Question
from app.models.attempt import Attempt

router = APIRouter(prefix="/chatbot", tags=["chatbot"])


class ChatbotRequest(BaseModel):
    question_id: int
    user_message: str


class ChatbotResponse(BaseModel):
    answer: str
    timestamp: str


DIFY_API_URL = "https://api.dify.ai/v1/chat-messages"


@router.post("/send", response_model=ChatbotResponse)
async def send_chatbot_message(
    request: ChatbotRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Send a message to the AI tutor chatbot.
    Gathers question context and forwards to Dify API.
    """

    # Fetch question details
    question = db.query(Question).filter(Question.id == request.question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # Get student's latest query attempt for this question
    latest_attempt = (
        db.query(Attempt)
        .filter(
            Attempt.user_id == current_user.id,
            Attempt.question_id == request.question_id
        )
        .order_by(Attempt.submitted_at.desc())
        .first()
    )

    student_query = latest_attempt.query if latest_attempt else ""

    # Prepare context for Dify API
    dify_payload = {
        "inputs": {
            "question_text": question.description,
            "database_schema": question.schema_sql,
            "student_query": student_query,
            "user_message": request.user_message
        },
        "user": str(current_user.id),
        "response_mode": "blocking"
    }

    headers = {
        "Authorization": f"Bearer {settings.DIFY_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                DIFY_API_URL,
                json=dify_payload,
                headers=headers
            )
            response.raise_for_status()

        dify_response = response.json()
        answer = dify_response.get("answer", "")

        return ChatbotResponse(
            answer=answer,
            timestamp=datetime.utcnow().isoformat()
        )

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Dify API error: {e.response.text}"
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to Dify API: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
