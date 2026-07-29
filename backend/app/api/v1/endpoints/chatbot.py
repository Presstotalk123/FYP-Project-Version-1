from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import httpx
import json
import asyncio

from app.database import get_db
from app.dependencies import get_current_user
from app.config import settings
from app.models.user import User
from app.models.question import Question
from app.models.attempt import Attempt
from app.models.lab import Lab
from app.models.lab_task import LabTask
from app.models.lab_session import LabSession
from app.models.lab_attempt import LabAttempt
from app.models.lab_task_submission import LabTaskSubmission
from app.utils.lab_db_manager import get_schema_info

router = APIRouter(prefix="/chatbot", tags=["chatbot"])



class ChatbotRequest(BaseModel):
    question_id: int
    user_message: str


class ChatbotResponse(BaseModel):
    answer: str
    timestamp: str


DIFY_API_URL = "https://api.dify.ai/v1/workflows/run"


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
            "student_current_query": student_query,
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

        # Extract answer from workflow response
        # Workflow response format: {"data": {"outputs": {"text": "..."}}}
        if "data" in dify_response and "outputs" in dify_response["data"]:
            answer = dify_response["data"]["outputs"].get("text", "")
        else:
            # Fallback to direct answer field (for compatibility)
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


# ─────────────────────────────────────────────────────────────────────────────
# Schemas for new AI Query Review endpoints
# ─────────────────────────────────────────────────────────────────────────────

class QueryReviewRequest(BaseModel):
    question_id: int
    student_query: str


class QueryReviewResponse(BaseModel):
    problem_token: str
    explanation: str
    hint: str


class LabQueryReviewRequest(BaseModel):
    lab_id: int
    session_id: int
    task_id: int
    student_query: str


class LabQueryReviewResponse(BaseModel):
    db_state_issue: bool
    db_state_message: str
    problem_token: str
    explanation: str
    hint: str


class LabChatRequest(BaseModel):
    lab_id: int
    session_id: int
    user_message: str


# ─────────────────────────────────────────────────────────────────────────────
# Flexible AI helper — supports Azure OpenAI, OpenAI, Gemini
# Controlled by settings.AI_PROVIDER env variable
# ─────────────────────────────────────────────────────────────────────────────

async def call_ai_for_review(system_prompt: str, context: dict) -> dict:
    """
    Call the configured AI provider with a system prompt and context dict.
    Returns a parsed dict from the JSON response.
    Raises an exception if the call fails (caller handles it).

    Provider is selected by AI_PROVIDER env var:
      - "azure_openai" → AzureOpenAI client (requires AI_AZURE_ENDPOINT + AI_AZURE_API_VERSION)
      - "openai"       → direct OpenAI client
      - "gemini"       → Google Generative AI
    """
    user_message = f"Review this submission:\n{json.dumps(context, indent=2)}"

    def _call():
        provider = settings.AI_PROVIDER.lower()

        if provider in ("azure_openai", "openai"):
            from openai import AzureOpenAI, OpenAI

            if provider == "azure_openai":
                client = AzureOpenAI(
                    api_key=settings.AI_API_KEY,
                    azure_endpoint=settings.AI_AZURE_ENDPOINT,
                    api_version=settings.AI_AZURE_API_VERSION,
                )
            else:
                client = OpenAI(api_key=settings.AI_API_KEY)

            kwargs = {
                "model": settings.AI_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "timeout": 30,
            }
            if not settings.AI_ENABLE_TEMPERATURE:
                pass # Temperature explicitly disabled via env var
            elif settings.AI_TEMPERATURE is not None:
                kwargs["temperature"] = settings.AI_TEMPERATURE
            else:
                kwargs["temperature"] = 0.2

            response = client.chat.completions.create(**kwargs)
            raw = response.choices[0].message.content or ""

        elif provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=settings.AI_API_KEY)
            model = genai.GenerativeModel(
                model_name=settings.AI_MODEL,
                system_instruction=system_prompt,
            )
            gemini_kwargs = {}
            if settings.AI_TEMPERATURE is not None:
                gemini_kwargs["temperature"] = settings.AI_TEMPERATURE
            else:
                gemini_kwargs["temperature"] = 0.2
                
            response = model.generate_content(
                user_message,
                generation_config=gemini_kwargs if gemini_kwargs else None
            )
            raw = response.text or ""

        else:
            raise ValueError(f"Unsupported AI_PROVIDER: {provider}")

        # Strip markdown code fences if the model wraps the JSON
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0].strip()

        return json.loads(raw)

    # 1 retry
    try:
        return await asyncio.wait_for(asyncio.to_thread(_call), timeout=35)
    except Exception:
        return await asyncio.wait_for(asyncio.to_thread(_call), timeout=35)


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint A: POST /chatbot/query-review
# Auto review for SQL Questions (called when student runs a wrong query)
# ─────────────────────────────────────────────────────────────────────────────

QUERY_REVIEW_SYSTEM_PROMPT = """You are an SQL tutor. A student has submitted a query that does not produce the correct result.

You will receive:
- question_text: The problem the student is trying to solve
- database_schema: The CREATE TABLE statements for this database
- sample_data: Sample INSERT statements showing the data
- student_query: The SQL query the student submitted (which is wrong)

Your job:
1. Identify the single most important clause or column in the student's query that is causing the problem.
2. Explain briefly why it is wrong in plain English (1-2 sentences max).
3. Give a short hint pointing toward the correct approach WITHOUT revealing the answer or writing the correct SQL.

You MUST respond ONLY with valid JSON in this exact shape — no extra text, no markdown:
{
  "problem_token": "<the exact column name, keyword, or short clause that is wrong, e.g. 'payment_date' or 'GROUP BY'>",
  "explanation": "<1-2 sentence plain-English explanation of why this is incorrect>",
  "hint": "<one sentence hint pointing toward the right approach>"
}"""


@router.post("/query-review", response_model=QueryReviewResponse)
async def review_query(
    request: QueryReviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Auto query review for SQL Questions.
    Called when a student runs a query that is wrong (but valid SQL).
    """
    question = db.query(Question).filter(Question.id == request.question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    context = {
        "question_text": question.description,
        "database_schema": question.schema_sql,
        "sample_data": question.sample_data_sql,
        "student_query": request.student_query,
    }

    try:
        result = await call_ai_for_review(QUERY_REVIEW_SYSTEM_PROMPT, context)
        return QueryReviewResponse(
            problem_token=result.get("problem_token", ""),
            explanation=result.get("explanation", ""),
            hint=result.get("hint", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI review failed: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint B: POST /chatbot/lab-query-review
# Auto review for SQL Labs (called when student submits a wrong task answer)
# ─────────────────────────────────────────────────────────────────────────────

LAB_QUERY_REVIEW_SYSTEM_PROMPT = """You are an SQL tutor reviewing a student's query submission in a multi-task lab environment.

You will receive:
- lab_title and lab_description: The overall context and goal of the lab
- template_schema: The original CREATE TABLE SQL before any student modifications
- all_tasks: A list of all tasks in this lab, each with title, description, and whether the student has completed it
- current_task_title and current_task_description: The specific task the student is currently submitting for
- current_live_schema: The current state of the student's database (CREATE TABLE SQL as it exists right now)
- query_history: The last 10 successful queries this student has run in this session (chronological)
- student_query: The query the student submitted for the current task (which is wrong)

Step 1 — Check database state integrity:
Read the lab description and all task descriptions carefully.
Compare the template_schema against the current_live_schema.
Look at the query_history.
Determine: Has the student made any changes to the database (dropped tables, deleted all data, dropped columns) that are NOT intended by any of the tasks, AND that would prevent the current task from being answered correctly?
- If the live schema is missing tables or columns that were in the template and no task description accounts for their removal, this is likely unintended corruption.
- If the live schema has new tables/columns not in the template, check if a prior task description accounts for them.
- Set db_state_issue to true only if the corruption would DIRECTLY impact answering the current task.

Step 2 — Review the student's query:
Identify the single most important clause or column in the student's query that is causing the problem.
Explain why it is wrong in 1-2 sentences.
Give a one-sentence hint without revealing the correct SQL.

Rules:
- Do NOT reveal the correct answer or write any corrected SQL
- Do NOT flag intentional schema changes that are part of completed or in-progress tasks
- The hint must guide thinking, not give away the solution

You MUST respond ONLY with valid JSON — no extra text, no markdown:
{
  "db_state_issue": false,
  "db_state_message": "",
  "problem_token": "<exact column name, keyword, or clause that is wrong>",
  "explanation": "<1-2 sentences why it is incorrect>",
  "hint": "<one sentence pointing toward the right approach>"
}

If db_state_issue is true, fill db_state_message with one sentence describing what looks corrupted and suggest using the Reset button.
If db_state_issue is false, leave db_state_message as an empty string."""


@router.post("/lab-query-review", response_model=LabQueryReviewResponse)
async def review_lab_query(
    request: LabQueryReviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Auto query review for SQL Labs.
    Called when a student submits an answer to a task and it is incorrect.
    """
    # Fetch lab
    lab = db.query(Lab).filter(Lab.id == request.lab_id, Lab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")

    # Fetch all tasks for this lab (ordered)
    all_tasks = (
        db.query(LabTask)
        .filter(LabTask.lab_id == request.lab_id, LabTask.is_deleted == 0)
        .order_by(LabTask.order_index.asc())
        .all()
    )

    # Fetch current task
    current_task = db.query(LabTask).filter(LabTask.id == request.task_id).first()
    if not current_task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Fetch session
    session = db.query(LabSession).filter(LabSession.id == request.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get live schema from session DB file
    try:
        schema_info = get_schema_info(session.db_file_path)
        live_schema_string = "\n\n".join(
            table["create_sql"] for table in schema_info["tables"] if table.get("create_sql")
        )
    except Exception:
        live_schema_string = "(Could not read live schema)"

    # Last 10 SUCCESSFUL queries for this session
    recent_queries = (
        db.query(LabAttempt)
        .filter(
            LabAttempt.session_id == request.session_id,
            LabAttempt.success == 1,
        )
        .order_by(LabAttempt.submitted_at.asc())
        .limit(10)
        .all()
    )

    # Completed task IDs for this session
    completed_rows = (
        db.query(LabTaskSubmission.task_id)
        .filter(
            LabTaskSubmission.session_id == request.session_id,
            LabTaskSubmission.is_correct == 1,
        )
        .all()
    )
    completed_ids = {row[0] for row in completed_rows}

    context = {
        "lab_title": lab.title,
        "lab_description": lab.description,
        "template_schema": lab.schema_sql,
        "all_tasks": [
            {
                "order": task.order_index,
                "title": task.title,
                "description": task.description,
                "completed": task.id in completed_ids,
            }
            for task in all_tasks
        ],
        "current_task_title": current_task.title,
        "current_task_description": current_task.description,
        "current_live_schema": live_schema_string,
        "query_history": [a.query for a in recent_queries],
        "student_query": request.student_query,
    }

    try:
        result = await call_ai_for_review(LAB_QUERY_REVIEW_SYSTEM_PROMPT, context)
        return LabQueryReviewResponse(
            db_state_issue=bool(result.get("db_state_issue", False)),
            db_state_message=result.get("db_state_message", ""),
            problem_token=result.get("problem_token", ""),
            explanation=result.get("explanation", ""),
            hint=result.get("hint", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI review failed: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint C: POST /chatbot/lab-chat
# AI Tutor chat for SQL Labs (new 4th tab in LabResultsPanel)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/lab-chat")
async def lab_chat(
    request: LabChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    AI Tutor conversational chat for SQL Labs.
    Provides guidance without revealing answers. (Streaming)
    """
    lab = db.query(Lab).filter(Lab.id == request.lab_id, Lab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")

    session = db.query(LabSession).filter(LabSession.id == request.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Free-form chat could otherwise be used to fish for correctness hints
    # ("is my query right?") on labs where that's meant to be hidden.
    if lab.hide_correctness and current_user.role.value == "student":
        raise HTTPException(status_code=403, detail="AI Tutor is disabled for this lab.")

    # Live schema
    try:
        schema_info = get_schema_info(session.db_file_path)
        live_schema = "\n\n".join(
            table["create_sql"] for table in schema_info["tables"] if table.get("create_sql")
        )
    except Exception:
        live_schema = "(Schema unavailable)"

    # Most recent successful query for context
    last_attempt = (
        db.query(LabAttempt)
        .filter(LabAttempt.session_id == request.session_id, LabAttempt.success == 1)
        .order_by(LabAttempt.submitted_at.desc())
        .first()
    )
    last_query = last_attempt.query if last_attempt else "None yet"

    system_prompt = f"""You are a helpful SQL tutor assisting a student working in a live SQL lab environment.

Lab: {lab.title}
Description: {lab.description}

Current database schema:
{live_schema}

Student's most recent query:
{last_query}

Your rules:
- NEVER give away the answer directly or write the correct SQL for them
- Explain SQL concepts clearly when asked
- Point out logical errors in thinking without rewriting queries for them
- Ask guiding questions to help the student reason through the problem
- Reference specific table and column names from the schema when relevant
- Keep responses concise and focused"""

    async def _chat_stream():
        provider = settings.AI_PROVIDER.lower()

        if provider in ("azure_openai", "openai"):
            from openai import AsyncAzureOpenAI, AsyncOpenAI

            if provider == "azure_openai":
                client = AsyncAzureOpenAI(
                    api_key=settings.AI_API_KEY,
                    azure_endpoint=settings.AI_AZURE_ENDPOINT,
                    api_version=settings.AI_AZURE_API_VERSION,
                )
            else:
                client = AsyncOpenAI(api_key=settings.AI_API_KEY)

            kwargs = {
                "model": settings.AI_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": request.user_message},
                ],
                "timeout": 30,
                "stream": True,
            }
            if not settings.AI_ENABLE_TEMPERATURE:
                pass # Temperature explicitly disabled via env var
            elif settings.AI_TEMPERATURE is not None:
                kwargs["temperature"] = settings.AI_TEMPERATURE
            else:
                kwargs["temperature"] = 0.5

            try:
                response = await client.chat.completions.create(**kwargs)
                async for chunk in response:
                    if chunk.choices and len(chunk.choices) > 0:
                        content = chunk.choices[0].delta.content
                        if content:
                            yield content
            except Exception as e:
                yield f"\n[Error connecting to AI Tutor: {str(e)}]"

        elif provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=settings.AI_API_KEY)
            model = genai.GenerativeModel(
                model_name=settings.AI_MODEL,
                system_instruction=system_prompt,
            )
            gemini_kwargs = {}
            if settings.AI_TEMPERATURE is not None:
                gemini_kwargs["temperature"] = settings.AI_TEMPERATURE
            else:
                gemini_kwargs["temperature"] = 0.5
                
            try:
                response = await model.generate_content_async(
                    request.user_message,
                    generation_config=gemini_kwargs if gemini_kwargs else None,
                    stream=True
                )
                async for chunk in response:
                    if chunk.text:
                        yield chunk.text
            except Exception as e:
                yield f"\n[Error connecting to AI Tutor: {str(e)}]"

        else:
            yield f"\n[Unsupported AI_PROVIDER: {provider}]"

    return StreamingResponse(_chat_stream(), media_type="text/plain")

