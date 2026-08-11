from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Any, Optional
import json
import asyncio

from app.database import get_db
from app.dependencies import get_current_user
from app.config import settings
from app.models.user import User
from app.models.question import Question
from app.models.attempt import Attempt
from app.models.progress import UserProgress
from app.models.lab import Lab
from app.models.lab_task import LabTask
from app.models.lab_session import LabSession
from app.models.lab_attempt import LabAttempt
from app.models.lab_task_submission import LabTaskSubmission
from app.models.query_review import QueryReview
from app.utils.lab_db_manager import get_schema_info
from app.services.tutor_chat import persistence as tutor_persistence
from app.core.advanced_sql_grader import (
    run_advanced_pipeline,
    is_permissive_but_safe,
    AdvancedGradingError,
)
from app.core.answer_validator import generate_hash
from app.utils.db_generator import get_question_db_path

router = APIRouter(prefix="/chatbot", tags=["chatbot"])

# How many prior messages (user+assistant) to feed back to the LLM as memory.
# 10 messages ≈ 5 turns — enough continuity without bloating the prompt.
TUTOR_CHAT_MEMORY_TURNS = 10


def _persist_query_review(db: Session, **fields) -> None:
    """Store an AI query-review so staff analytics can show its history. Never-raise:
    persistence must not break the student-facing review response."""
    try:
        db.add(QueryReview(**fields))
        db.commit()
    except Exception:
        db.rollback()


def _openai_history(messages) -> list:
    """Prior TutorChatMessage rows → OpenAI chat messages (oldest first)."""
    return [{"role": m.role, "content": m.content or ""} for m in messages]


def _gemini_history(messages) -> list:
    """Prior TutorChatMessage rows → Gemini history (assistant→model, oldest first)."""
    return [
        {"role": ("model" if m.role == "assistant" else "user"), "parts": [m.content or ""]}
        for m in messages
    ]


async def _persist_assistant_reply(db: Session, conv, text: str) -> None:
    """Best-effort save of the fully-streamed assistant reply (offloaded so the
    blocking DB write never blocks the event loop). Never raises."""
    if not (text or "").strip():
        return

    def _write():
        tutor_persistence.append_message(db, conv, role="assistant", content=text)

    try:
        await asyncio.to_thread(_write)
    except Exception:
        # Never let a persistence failure break the already-delivered stream.
        pass



class ChatbotRequest(BaseModel):
    question_id: int
    user_message: str


@router.post("/send")
async def send_chatbot_message(
    request: ChatbotRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    AI Tutor conversational chat for SQL Questions.
    Provides guidance without revealing answers. (Streaming)
    """

    # Fetch question details
    question = db.query(Question).filter(Question.id == request.question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    if question.owner_assessment_id is not None and current_user.role.value == "student":
        raise HTTPException(status_code=403, detail="AI tutor is disabled for assessment questions.")

    # AI feedback would reveal correctness the question is meant to hide.
    if question.hide_correctness and current_user.role.value == "student":
        raise HTTPException(status_code=403, detail="AI tutor is disabled for this question.")

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

    student_query = latest_attempt.query if latest_attempt else "None yet"

    system_prompt = f"""You are a helpful SQL tutor assisting a student working on a SQL question.

Question:
{question.description}

Database schema:
{question.schema_sql}

Sample data:
{question.sample_data_sql}

Student's most recent query:
{student_query}

Your rules:
- NEVER give away the answer directly or write the correct SQL for them
- Explain SQL concepts clearly when asked
- Point out logical errors in thinking without rewriting queries for them
- Ask guiding questions to help the student reason through the problem
- Reference specific table and column names from the schema when relevant
- Keep responses concise and focused"""

    # Persist + memory: load prior turns for this (user, question), then record
    # the incoming message. History is fetched BEFORE appending so the current
    # message isn't duplicated in the prompt.
    conv = tutor_persistence.get_or_create_question_conversation(
        db, user_id=current_user.id, question_id=request.question_id,
    )
    history = tutor_persistence.recent_turns(db, conv, limit=TUTOR_CHAT_MEMORY_TURNS)
    tutor_persistence.append_message(db, conv, role="user", content=request.user_message)

    async def _chat_stream():
        provider = settings.AI_PROVIDER.lower()
        full_reply = ""
        stream_ok = True

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
                    *_openai_history(history),
                    {"role": "user", "content": request.user_message},
                ],
                "timeout": 30,
                "stream": True,
            }
            if not settings.AI_ENABLE_TEMPERATURE:
                pass  # Temperature explicitly disabled via env var
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
                            full_reply += content
                            yield content
            except Exception as e:
                stream_ok = False
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
                chat = model.start_chat(history=_gemini_history(history))
                response = await chat.send_message_async(
                    request.user_message,
                    generation_config=gemini_kwargs if gemini_kwargs else None,
                    stream=True
                )
                async for chunk in response:
                    if chunk.text:
                        full_reply += chunk.text
                        yield chunk.text
            except Exception as e:
                stream_ok = False
                yield f"\n[Error connecting to AI Tutor: {str(e)}]"

        else:
            stream_ok = False
            yield f"\n[Unsupported AI_PROVIDER: {provider}]"

        if stream_ok:
            await _persist_assistant_reply(db, conv, full_reply)

    return StreamingResponse(_chat_stream(), media_type="text/plain")


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


class CourseChatRequest(BaseModel):
    course_context: str
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

    async def _once():
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

            response = await client.chat.completions.create(**kwargs)
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

            response = await model.generate_content_async(
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
        return await _once()
    except Exception:
        return await _once()


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

    if question.owner_assessment_id is not None and current_user.role.value == "student":
        raise HTTPException(status_code=403, detail="AI tutor is disabled for assessment questions.")

    # A wrong-query review would reveal correctness the question is meant to hide.
    if question.hide_correctness and current_user.role.value == "student":
        raise HTTPException(status_code=403, detail="AI review is disabled for this question.")

    context = {
        "question_text": question.description,
        "database_schema": question.schema_sql,
        "sample_data": question.sample_data_sql,
        "student_query": request.student_query,
    }

    try:
        result = await call_ai_for_review(QUERY_REVIEW_SYSTEM_PROMPT, context)
        _persist_query_review(
            db,
            user_id=current_user.id,
            context_type="question",
            question_id=question.id,
            student_query=request.student_query,
            problem_token=result.get("problem_token", ""),
            explanation=result.get("explanation", ""),
            hint=result.get("hint", ""),
        )
        return QueryReviewResponse(
            problem_token=result.get("problem_token", ""),
            explanation=result.get("explanation", ""),
            hint=result.get("hint", ""),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI review failed: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint: POST /chatbot/counterexample
# Execution-verified counterexample for a wrong-but-plausible SQL query. ONE LLM
# call proposes several candidate breaking-row sets; we verify them LOCALLY (each
# verification is milliseconds) and return the first that actually makes the
# student query and reference query diverge. SQL-unique: proven, not asserted.
# ─────────────────────────────────────────────────────────────────────────────

COUNTEREXAMPLE_SYSTEM_PROMPT = """You are an SQL tutor building a *counterexample* that shows a student why their query is subtly wrong.

You will receive:
- question_text: the problem the student is solving
- database_schema: the CREATE TABLE statements
- sample_data: the existing sample INSERT statements
- student_query: the student's query (it is wrong, but happens to look right on the current data)
- reference_query: the correct query

Your job: propose UP TO 3 independent candidate counterexamples, ordered best first. Each candidate is a small set of rows to INSERT into the existing database so that, after inserting them, student_query and reference_query return DIFFERENT results. Each candidate should expose the specific flaw in the student's query (for example a NULL, a boundary value, a duplicate, an unmatched foreign key, or a tie). We will TEST each candidate against the database and use the first one that actually causes a divergence, so make the candidates varied.

Rules:
- Output ONLY new INSERT statements, valid against database_schema. Do NOT restate the existing sample data.
- Insert as FEW rows as possible per candidate — ideally one — that still cause the divergence.
- Respect foreign keys and NOT NULL constraints; insert into parent tables first if needed.
- Do NOT use ATTACH, DETACH, PRAGMA, or VACUUM. Do NOT modify or delete existing rows; only INSERT.
- Do NOT reveal the correct query. Each explanation must describe the CONCEPT the extra row exposes, in 1-2 plain-English sentences, without giving away the fix.

Respond ONLY with valid JSON in this exact shape — no markdown, no extra text:
{
  "candidates": [
    {
      "inserts": ["INSERT INTO ... VALUES ...;"],
      "explanation": "<1-2 sentences: what kind of row this is and why it trips up the student's query, without revealing the correct SQL>"
    }
  ]
}"""


class CounterexampleRequest(BaseModel):
    question_id: int
    student_query: str


class ResultBlock(BaseModel):
    columns: List[str]
    rows: List[List[Any]]


class CounterexampleResponse(BaseModel):
    available: bool
    injected_rows: List[str] = []
    student_result: Optional[ResultBlock] = None
    correct_result: Optional[ResultBlock] = None
    explanation: str = ""


def _rows_to_lists(rows) -> List[List[Any]]:
    """Make raw sqlite rows JSON-safe (decode bytes; leave scalars as-is)."""
    out: List[List[Any]] = []
    for row in rows:
        cells: List[Any] = []
        for v in row:
            if isinstance(v, bytes):
                try:
                    v = v.decode("utf-8")
                except Exception:
                    v = str(v)
            cells.append(v)
        out.append(cells)
    return out


@router.post("/counterexample", response_model=CounterexampleResponse)
async def counterexample(
    request: CounterexampleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Build an execution-verified counterexample for a wrong-but-valid SQL query.
    Returns available=false (never an error) when correctness is hidden, the
    question has no reference SELECT, or no divergence could be constructed.
    """
    question = db.query(Question).filter(Question.id == request.question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    if question.owner_assessment_id is not None and current_user.role.value == "student":
        raise HTTPException(status_code=403, detail="AI tutor is disabled for assessment questions.")

    # A counterexample would reveal correctness the question is meant to hide.
    if question.hide_correctness and current_user.role.value == "student":
        raise HTTPException(status_code=403, detail="AI tutor is disabled for this question.")

    # Needs a reference SELECT to diverge against, and a real result table to
    # diverge on — neither exists for advanced (trigger/DML) questions.
    if question.advanced_sql_testing or not (question.correct_answer_query or "").strip():
        return CounterexampleResponse(available=False)

    db_path = get_question_db_path(question.db_file_path)
    correct_query = question.correct_answer_query
    order_sensitive = bool(question.order_sensitive)

    context = {
        "question_text": question.description,
        "database_schema": question.schema_sql,
        "sample_data": question.sample_data_sql,
        "student_query": request.student_query,
        "reference_query": correct_query,
    }

    async def _run(inserts_sql: str, query: str):
        # Isolated in-memory clone (injected rows applied, then the query run as
        # the "check query"); the canonical DB file is never touched.
        # Runs off the event loop thread — run_advanced_pipeline blocks on a
        # thread.join() internally, which would otherwise stall the server.
        return await asyncio.to_thread(
            run_advanced_pipeline, db_path, inserts_sql, "", query, timeout_seconds=10
        )

    # ONE LLM call for several candidates, then verify each locally (cheap).
    try:
        proposal = await call_ai_for_review(COUNTEREXAMPLE_SYSTEM_PROMPT, context)
    except Exception:
        return CounterexampleResponse(available=False)

    candidates = proposal.get("candidates")
    if not isinstance(candidates, list):
        candidates = []

    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        inserts = cand.get("inserts") or []
        if isinstance(inserts, str):
            inserts = [inserts]
        inserts = [s for s in inserts if isinstance(s, str) and s.strip()]
        inserts_sql = "\n".join(inserts).strip()
        if not inserts_sql:
            continue

        # Never run LLM-authored SQL that could escape the sandbox.
        try:
            is_permissive_but_safe(inserts_sql, "student")
        except AdvancedGradingError:
            continue

        try:
            s_cols, s_rows, _t1 = await _run(inserts_sql, request.student_query)
            c_cols, c_rows, _t2 = await _run(inserts_sql, correct_query)
        except AdvancedGradingError:
            continue

        # Validated only when the two result sets genuinely diverge.
        if generate_hash(s_rows, s_cols, order_sensitive) == generate_hash(c_rows, c_cols, order_sensitive):
            continue

        explanation = cand.get("explanation", "")
        _persist_query_review(
            db,
            user_id=current_user.id,
            context_type="question",
            question_id=question.id,
            student_query=request.student_query,
            problem_token="counterexample",
            explanation=explanation,
            hint="",
        )

        return CounterexampleResponse(
            available=True,
            injected_rows=inserts,
            student_result=ResultBlock(columns=list(s_cols), rows=_rows_to_lists(s_rows)),
            correct_result=ResultBlock(columns=list(c_cols), rows=_rows_to_lists(c_rows)),
            explanation=explanation,
        )

    return CounterexampleResponse(available=False)


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint: POST /chatbot/contrast
# Contrasting cases: the student's wrong query vs a minimally-corrected variant,
# both run against the real data so the ONE differing concept is visible in the
# diverging rows. Reuses the same isolated-execution primitive.
# ─────────────────────────────────────────────────────────────────────────────

CONTRAST_SYSTEM_PROMPT = """You are an SQL tutor creating a *contrasting cases* lesson. A student submitted a query that is wrong. You will produce a minimally-corrected variant so the student can compare the two side by side and see the ONE concept that differs.

You will receive:
- question_text: the problem the student is solving
- database_schema: the CREATE TABLE statements
- student_query: the student's query (wrong)
- reference_query: a correct query (for your guidance only)

Your job:
1. Produce corrected_query: the SMALLEST possible edit of the student's OWN query that makes it correct. Keep their structure, style, aliases, and formatting; change only what is necessary. Do NOT rewrite it into the reference query wholesale.
2. Name the single concept that differs (for example "INNER vs LEFT JOIN", "WHERE vs HAVING", "COUNT(*) vs COUNT(column)", "missing GROUP BY column").
3. Explain the distinction in 1-2 plain-English sentences.

Respond ONLY with valid JSON — no markdown, no extra text:
{
  "corrected_query": "<minimal correct edit of the student's query>",
  "concept": "<short name of the one difference>",
  "explanation": "<1-2 sentences explaining the distinction>"
}"""


class ContrastRequest(BaseModel):
    question_id: int
    student_query: str


class ContrastResult(BaseModel):
    columns: List[str]
    rows: List[List[Any]]
    # Per-row flag: True where this row does not appear in the other query's
    # result (order-insensitive) — the frontend highlights these.
    diff: List[bool]


class ContrastResponse(BaseModel):
    available: bool
    concept: str = ""
    explanation: str = ""
    your_query: str = ""
    corrected_query: str = ""
    your_result: Optional[ContrastResult] = None
    corrected_result: Optional[ContrastResult] = None


def _row_signature(row) -> str:
    """Signature of a single result row (bytes decoded), for set comparison."""
    return json.dumps(_rows_to_lists([row])[0], default=str, sort_keys=True)


def _diff_flags(rows_self, rows_other) -> List[bool]:
    """True for each self-row whose signature is absent from the other result."""
    other = {_row_signature(r) for r in rows_other}
    return [_row_signature(r) not in other for r in rows_self]


@router.post("/contrast", response_model=ContrastResponse)
async def contrast(
    request: ContrastRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Build a contrasting-cases comparison (student query vs minimal correct edit),
    running both against the real data. Returns available=false (never an error)
    when correctness is hidden, there's no reference query, or execution fails.
    """
    question = db.query(Question).filter(Question.id == request.question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    if question.owner_assessment_id is not None and current_user.role.value == "student":
        raise HTTPException(status_code=403, detail="AI tutor is disabled for assessment questions.")

    # A corrected variant reveals correctness the question is meant to hide.
    if question.hide_correctness and current_user.role.value == "student":
        raise HTTPException(status_code=403, detail="AI tutor is disabled for this question.")

    if question.advanced_sql_testing or not (question.correct_answer_query or "").strip():
        return ContrastResponse(available=False)

    db_path = get_question_db_path(question.db_file_path)

    context = {
        "question_text": question.description,
        "database_schema": question.schema_sql,
        "student_query": request.student_query,
        "reference_query": question.correct_answer_query,
    }

    try:
        proposal = await call_ai_for_review(CONTRAST_SYSTEM_PROMPT, context)
    except Exception:
        return ContrastResponse(available=False)

    corrected_query = (proposal.get("corrected_query") or "").strip()
    if not corrected_query:
        return ContrastResponse(available=False)

    try:
        # No injected rows — run both queries against the real question data.
        s_cols, s_rows, _t1 = await asyncio.to_thread(
            run_advanced_pipeline, db_path, "", "", request.student_query, timeout_seconds=10
        )
        v_cols, v_rows, _t2 = await asyncio.to_thread(
            run_advanced_pipeline, db_path, "", "", corrected_query, timeout_seconds=10
        )
    except AdvancedGradingError:
        return ContrastResponse(available=False)

    _persist_query_review(
        db,
        user_id=current_user.id,
        context_type="question",
        question_id=question.id,
        student_query=request.student_query,
        problem_token="contrast",
        explanation=proposal.get("explanation", ""),
        hint="",
    )

    return ContrastResponse(
        available=True,
        concept=proposal.get("concept", ""),
        explanation=proposal.get("explanation", ""),
        your_query=request.student_query,
        corrected_query=corrected_query,
        your_result=ContrastResult(
            columns=list(s_cols), rows=_rows_to_lists(s_rows), diff=_diff_flags(s_rows, v_rows)
        ),
        corrected_result=ContrastResult(
            columns=list(v_cols), rows=_rows_to_lists(v_rows), diff=_diff_flags(v_rows, s_rows)
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint: POST /chatbot/worked-example
# Surface a SIMILAR question the student has ALREADY solved, with their own
# correct query, so they can look at it and adapt the approach. Similarity is
# chosen by LLM-rerank over their completed questions (no schema change). Never
# reveals the current answer — it shows a DIFFERENT, already-solved problem.
# ─────────────────────────────────────────────────────────────────────────────

WORKED_EXAMPLE_SYSTEM_PROMPT = """You help a student by pointing them to a similar SQL problem they have ALREADY solved, so they can look at their own past solution and adapt the approach.

You will receive:
- current_question: {title, description} of the problem the student is working on now
- candidates: a list of problems the student has already solved, each {id, title, description}

Your job:
1. Choose the ONE candidate whose SQL approach is most useful as a reference for the current problem (similar concepts: joins, aggregation, grouping, filtering, subqueries, and so on).
2. Write a short mapping_note (2-3 sentences) telling the student how the approach from that solved problem maps onto the current one — WITHOUT writing any SQL and WITHOUT solving the current problem.

Respond ONLY with valid JSON — no markdown, no extra text:
{
  "chosen_question_id": <an id from candidates>,
  "mapping_note": "<2-3 sentences relating the solved problem's approach to the current one, no SQL>"
}"""


class WorkedExampleRequest(BaseModel):
    question_id: int


class SourceQuestion(BaseModel):
    id: int
    title: str
    description: str


class WorkedExampleResponse(BaseModel):
    available: bool
    source_question: Optional[SourceQuestion] = None
    solution_query: str = ""
    mapping_note: str = ""


@router.post("/worked-example", response_model=WorkedExampleResponse)
async def worked_example(
    request: WorkedExampleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return a similar, already-solved question + the student's own correct query.
    available=false (never an error) when the student has no other completed
    questions to draw from.
    """
    question = db.query(Question).filter(Question.id == request.question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # Mirror the Bagheera chat's guards — the worked example lives inside it.
    if question.owner_assessment_id is not None and current_user.role.value == "student":
        raise HTTPException(status_code=403, detail="AI tutor is disabled for assessment questions.")
    if question.hide_correctness and current_user.role.value == "student":
        raise HTTPException(status_code=403, detail="AI tutor is disabled for this question.")

    # Candidate pool: the student's completed questions (most recent first),
    # excluding this one and assessment clones.
    completed = (
        db.query(Question)
        .join(UserProgress, UserProgress.question_id == Question.id)
        .filter(
            UserProgress.user_id == current_user.id,
            UserProgress.completed == 1,
            Question.id != request.question_id,
            Question.owner_assessment_id.is_(None),
            Question.is_deleted == 0,
        )
        .order_by(UserProgress.first_completed_at.desc())
        .limit(25)
        .all()
    )

    if not completed:
        return WorkedExampleResponse(available=False)

    by_id = {q.id: q for q in completed}
    context = {
        "current_question": {"title": question.title, "description": question.description},
        "candidates": [
            {"id": q.id, "title": q.title, "description": q.description}
            for q in completed
        ],
    }

    # LLM-rerank; fall back to the most-recently-completed question on any issue.
    chosen_id = completed[0].id
    mapping_note = ""
    try:
        proposal = await call_ai_for_review(WORKED_EXAMPLE_SYSTEM_PROMPT, context)
        candidate_id = proposal.get("chosen_question_id")
        if isinstance(candidate_id, int) and candidate_id in by_id:
            chosen_id = candidate_id
        mapping_note = proposal.get("mapping_note", "") or ""
    except Exception:
        pass

    chosen = by_id[chosen_id]

    # Prefer the student's OWN correct query; fall back to the reference.
    attempt = (
        db.query(Attempt)
        .filter(
            Attempt.user_id == current_user.id,
            Attempt.question_id == chosen_id,
            Attempt.is_correct == 1,
        )
        .order_by(Attempt.submitted_at.desc())
        .first()
    )
    solution_query = (attempt.query if attempt else (chosen.correct_answer_query or "")) or ""

    return WorkedExampleResponse(
        available=True,
        source_question=SourceQuestion(id=chosen.id, title=chosen.title, description=chosen.description),
        solution_query=solution_query,
        mapping_note=mapping_note,
    )


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

    if (lab.hide_correctness or lab.disable_ai_assist) and current_user.role.value == "student":
        raise HTTPException(status_code=403, detail="AI query review is disabled for this lab.")

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
        _persist_query_review(
            db,
            user_id=current_user.id,
            context_type="lab",
            lab_id=lab.id,
            task_id=request.task_id,
            session_id=request.session_id,
            student_query=request.student_query,
            problem_token=result.get("problem_token", ""),
            explanation=result.get("explanation", ""),
            hint=result.get("hint", ""),
            db_state_issue=("corrupted" if bool(result.get("db_state_issue", False)) else None),
            db_state_message=result.get("db_state_message", "") or None,
        )
        return LabQueryReviewResponse(
            db_state_issue=bool(result.get("db_state_issue", False)),
            db_state_message=result.get("db_state_message", ""),
            problem_token=result.get("problem_token", ""),
            explanation=result.get("explanation", ""),
            hint=result.get("hint", ""),
        )
    except HTTPException:
        raise
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
    # ("is my query right?") on labs where that's meant to be hidden, or the
    # lab may just have AI assist turned off independent of correctness.
    if (lab.hide_correctness or lab.disable_ai_assist) and current_user.role.value == "student":
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

    # Persist + memory: load prior turns for this (user, lab session), then
    # record the incoming message. History is fetched BEFORE appending so the
    # current message isn't duplicated in the prompt.
    conv = tutor_persistence.get_or_create_lab_conversation(
        db, user_id=current_user.id, lab_id=request.lab_id, session_id=request.session_id,
    )
    history = tutor_persistence.recent_turns(db, conv, limit=TUTOR_CHAT_MEMORY_TURNS)
    tutor_persistence.append_message(db, conv, role="user", content=request.user_message)

    async def _chat_stream():
        provider = settings.AI_PROVIDER.lower()
        full_reply = ""
        stream_ok = True

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
                    *_openai_history(history),
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
                            full_reply += content
                            yield content
            except Exception as e:
                stream_ok = False
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
                chat = model.start_chat(history=_gemini_history(history))
                response = await chat.send_message_async(
                    request.user_message,
                    generation_config=gemini_kwargs if gemini_kwargs else None,
                    stream=True
                )
                async for chunk in response:
                    if chunk.text:
                        full_reply += chunk.text
                        yield chunk.text
            except Exception as e:
                stream_ok = False
                yield f"\n[Error connecting to AI Tutor: {str(e)}]"

        else:
            stream_ok = False
            yield f"\n[Unsupported AI_PROVIDER: {provider}]"

        if stream_ok:
            await _persist_assistant_reply(db, conv, full_reply)

    return StreamingResponse(_chat_stream(), media_type="text/plain")


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint D: POST /chatbot/course-chat
# Friendly course assistant for the course info page.
# Answers questions about the course grounded in the syllabus sent by the page.
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/course-chat")
async def course_chat(
    request: CourseChatRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Conversational course assistant for the course info page.
    Answers questions about the course using only the provided course info. (Streaming)
    """
    system_prompt = f"""You are a friendly course assistant for the class described below.
Answer the student's questions about the course using ONLY the course information provided.
If something isn't covered by the course info, say you don't have that information and
suggest they ask the instructor. Keep answers concise and clear.

=== COURSE INFORMATION ===
{request.course_context}"""

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
                pass  # Temperature explicitly disabled via env var
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
                yield f"\n[Error connecting to course assistant: {str(e)}]"

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
                yield f"\n[Error connecting to course assistant: {str(e)}]"

        else:
            yield f"\n[Unsupported AI_PROVIDER: {provider}]"

    return StreamingResponse(_chat_stream(), media_type="text/plain")


# ─────────────────────────────────────────────────────────────────────────────
# Read endpoints: restore a student's own saved tutor transcript
# ─────────────────────────────────────────────────────────────────────────────

_EMPTY_TUTOR_CONVERSATION = {"exists": False, "conversation_id": None, "messages": []}


def _tutor_conversation_payload(db: Session, conv) -> dict:
    """Serialize a tutor conversation + transcript for the GET endpoints."""
    return {
        "exists": True,
        "conversation_id": conv.id,
        "context_type": conv.context_type,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in tutor_persistence.transcript(db, conv)
        ],
    }


@router.get("/conversation")
def get_question_conversation(
    question_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch the current user's SQL-question tutor transcript.

    Read-only — never creates a conversation. Returns ``exists: false`` with an
    empty transcript when there is nothing yet.
    """
    conv = tutor_persistence.find_question_conversation(
        db, user_id=current_user.id, question_id=question_id,
    )
    if conv is None:
        return _EMPTY_TUTOR_CONVERSATION
    return _tutor_conversation_payload(db, conv)


@router.get("/lab-conversation")
def get_lab_conversation(
    lab_id: int,
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch the current user's SQL-lab tutor transcript for a session.

    Read-only — never creates a conversation. Returns ``exists: false`` with an
    empty transcript when there is nothing yet.
    """
    conv = tutor_persistence.find_lab_conversation(
        db, user_id=current_user.id, session_id=session_id,
    )
    if conv is None:
        return _EMPTY_TUTOR_CONVERSATION
    return _tutor_conversation_payload(db, conv)

