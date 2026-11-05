"""Staff-only adapter for the existing AskNarelle Flask service."""
from typing import Annotated
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.config import settings
from app.dependencies import require_staff_role
from app.models.user import User

router = APIRouter(prefix="/chatbot-management", tags=["chatbot management"])
Staff = Annotated[User, Depends(require_staff_role)]
Code = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")]


class CourseCreate(BaseModel):
    code: Code
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=2000)


class CategoryCreate(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9]{1,63}$")


class ChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    conversation_id: str | None = None


def segment(value: str) -> str:
    if not value or value in {".", ".."} or any(c in value for c in "/\\?#"):
        raise HTTPException(422, "Invalid course or category identifier")
    return quote(value, safe="")


async def upstream(method: str, path: str, **kwargs):
    base = settings.ASKNARELLE_API_URL.strip().rstrip("/")
    if not base:
        raise HTTPException(503, "Connect AskNarelle by setting ASKNARELLE_API_URL in backend/.env, then restart the backend.")
    try:
        async with httpx.AsyncClient(timeout=180, follow_redirects=False) as client:
            response = await client.request(method, base + path, **kwargs)
    except httpx.TimeoutException:
        raise HTTPException(504, "AskNarelle took too long to respond. Refresh before retrying; the operation may have completed.")
    except httpx.RequestError:
        raise HTTPException(502, "Cannot reach AskNarelle. Check that its Flask service is running and ASKNARELLE_API_URL is correct.")
    try:
        data = response.json()
    except ValueError:
        raise HTTPException(502, "AskNarelle returned an invalid response.")
    if not response.is_success:
        detail = (data.get("error") or data.get("message")) if isinstance(data, dict) else None
        raise HTTPException(response.status_code if response.status_code < 500 else 502,
                            str(detail or "AskNarelle could not complete the request."))
    return data


async def courses_for(user: User):
    data = await upstream("GET", f"/api/collections/{segment(user.email.lower())}")
    if not isinstance(data, list):
        raise HTTPException(502, "AskNarelle could not load your courses.")
    return data


async def require_course(course: str, user: User):
    segment(course)
    if not any(c.get("course_name") == course for c in await courses_for(user)):
        raise HTTPException(403, "You do not have access to this AskNarelle course.")


@router.get("/courses")
async def list_courses(user: Staff):
    return await courses_for(user)


@router.post("/courses", status_code=201)
async def create_course(body: CourseCreate, user: Staff):
    await upstream("POST", "/vi/courses", json={
        "courseCode": body.code, "collectionName": body.code,
        "courseName": body.name, "description": body.description,
        "username": user.email.lower(),
    })
    try:
        await upstream("PUT", "/createindex", json={"collectionName": body.code})
    except HTTPException:
        raise HTTPException(502, "Course created, but search index setup failed. Open the course and use Repair search index before uploading.")
    return {"message": "Course created"}


@router.post("/courses/{course}/index")
async def repair_index(course: str, user: Staff):
    await require_course(course, user)
    return await upstream("PUT", "/createindex", json={"collectionName": course})


@router.get("/courses/{course}/categories")
async def list_categories(course: str, user: Staff):
    await require_course(course, user)
    data = await upstream("GET", f"/api/collections/{segment(user.email.lower())}/{segment(course)}/domains")
    if not isinstance(data, list):
        raise HTTPException(502, "AskNarelle could not load categories.")
    return data


@router.post("/courses/{course}/categories", status_code=201)
async def create_category(course: str, body: CategoryCreate, user: Staff):
    await require_course(course, user)
    return await upstream("PUT", "/api/createdomain", json={
        "domainName": body.name, "courseName": course,
        "user": user.email.lower(), "action": "Domain Creation",
    })


@router.get("/courses/{course}/categories/{category}/files")
async def list_files(course: str, category: str, user: Staff):
    await require_course(course, user)
    data = await upstream("GET", f"/api/collections/{segment(user.email.lower())}/{segment(course)}/{segment(category)}")
    if not isinstance(data, list):
        raise HTTPException(502, "AskNarelle could not load documents.")
    return data


@router.post("/courses/{course}/categories/{category}/files")
async def upload_files(course: str, category: str, user: Staff, files: list[UploadFile] = File(...)):
    await require_course(course, user)
    if not 1 <= len(files) <= 10:
        raise HTTPException(422, "Choose between 1 and 10 documents.")
    payload, total = [], 0
    for file in files:
        name = file.filename or ""
        if "/" in name or "\\" in name or not name.lower().endswith((".pdf", ".docx", ".pptx", ".txt")):
            raise HTTPException(422, "Supported documents: PDF, DOCX, PPTX, TXT.")
        content = await file.read(20 * 1024 * 1024 + 1)
        total += len(content)
        if not content or len(content) > 20 * 1024 * 1024 or total > 50 * 1024 * 1024:
            raise HTTPException(413, "Use nonempty files up to 20 MB each and 50 MB combined.")
        payload.append(("files", (name, content, file.content_type or "application/octet-stream")))
    path = f"/api/{segment(course)}/{segment(category)}/{segment(user.email.lower())}"
    await upstream("PUT", path + "/createblob", files=payload)
    try:
        await upstream("PUT", path + "/createdocument", files=payload)
        await upstream("PUT", "/vectorstore", json={
            "containername": course, "domainname": category, "chunksize": 1000, "overlap": 100,
        })
    except HTTPException as exc:
        raise HTTPException(exc.status_code, f"Files uploaded, but processing did not finish: {exc.detail} Refresh the file list before retrying.")
    return {"message": "Documents uploaded and indexed"}


@router.post("/courses/{course}/chat")
async def preview_chat(course: str, body: ChatMessage, user: Staff):
    await require_course(course, user)
    return await upstream("POST", f"/api/chat/{segment(course)}", json={
        "message": body.message, "user_id": user.email.lower(),
        "video_ids": [], "previous_messages": [], "conversation_id": body.conversation_id,
    })


@router.get("/overview")
async def overview(user: Staff):
    email = segment(user.email.lower())
    courses = await courses_for(user)
    users = await upstream("GET", f"/chats/totalUsers/{email}")
    conversations = await upstream("GET", f"/chats/totalQueries/{email}")
    if type(users) is not int or type(conversations) is not int:
        raise HTTPException(502, "AskNarelle could not load overview statistics.")
    return {"courses": len(courses), "users": users, "conversations": conversations}


@router.get("/activities")
async def activities(user: Staff):
    data = await upstream("GET", f"/activities/{segment(user.email.lower())}/viewactivities")
    if not isinstance(data, list):
        raise HTTPException(502, "AskNarelle could not load the activity log.")
    return data


@router.get("/dashboard")
async def dashboard(user: Staff):
    import asyncio
    email = segment(user.email.lower())
    courses, users, monthly, by_course = await asyncio.gather(
        courses_for(user), upstream("GET", f"/chats/totalUsers/{email}"),
        upstream("GET", f"/chats/queriesByMonth/{email}"),
        upstream("GET", f"/chats/queriesByCourse/{email}"),
    )

    def series(data, label_key):
        if not isinstance(data, dict):
            raise HTTPException(502, "AskNarelle returned invalid dashboard data.")
        labels, counts = data.get(label_key), data.get("counts")
        if (not isinstance(labels, list) or not isinstance(counts, list)
                or len(labels) != len(counts)
                or any(not isinstance(label, str) for label in labels)
                or any(type(count) is not int or count < 0 for count in counts)):
            raise HTTPException(502, "AskNarelle returned invalid dashboard data.")
        return [{"label": label, "count": count} for label, count in zip(labels, counts)]

    if type(users) is not int or users < 0:
        raise HTTPException(502, "AskNarelle could not load user statistics.")
    usage = series(monthly, "months")
    course_queries = series(by_course, "courses")
    # This endpoint counts individual user messages, unlike legacy totalQueries,
    # which counts conversation records and understates multi-turn usage.
    total_queries = sum(row["count"] for row in course_queries)
    counts = {row["label"]: row["count"] for row in course_queries}
    return {
        "courses": len(courses), "users": users, "queries": total_queries,
        "usage": usage,
        "by_course": [{"label": c["course_name"], "count": counts.get(c["course_name"], 0)} for c in courses],
    }
