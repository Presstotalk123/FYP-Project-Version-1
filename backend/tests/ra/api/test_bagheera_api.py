"""Bagheera on RA questions over HTTP, with the AI replaced by a stub."""
import pytest

from app.services.ra import bagheera, bagheera_llm
from app.services.ra.tutorial_5_5 import UNIVERSITY

BASE = "/api/v1/ra/questions"
MODEL = "π Pname (PROF ⋈ σ Numphds < 50 DEPT)"
HINT = "Which relation tells you a department's number of PhDs? Start from there."


class Stub:
    """Replies in turn; records what Bagheera was told."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    async def __call__(self, system, messages):
        self.calls.append((system, messages))
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


@pytest.fixture
def ai(monkeypatch):
    monkeypatch.setattr(bagheera_llm, "configured", lambda: True)

    def use(*replies):
        stub = Stub(*replies)
        monkeypatch.setattr(bagheera_llm, "complete", stub)
        return stub
    return use


def _question(client, staff_headers, **changes):
    body = {"title": "Small departments", "description": "Professors in departments with fewer than 50 PhDs.",
            "schema_sql": UNIVERSITY, "is_published": True, "answer_format": "mixed",
            "parts": [{"model_answer": MODEL}]}
    body.update(changes)
    r = client.post(BASE, json=body, headers=staff_headers)
    assert r.status_code == 201, r.text
    return r.json()


def _chat(client, headers, q, message="How do I start?", answer="π Pname PROF"):
    return client.post(f"{BASE}/{q['id']}/bagheera/chat", headers=headers,
                       json={"part_id": q["parts"][0]["id"], "message": message, "answer": answer})


def test_bagheera_needs_the_ai_set_up(client, staff_headers, student_headers, ra_on, monkeypatch):
    monkeypatch.setattr(bagheera_llm, "configured", lambda: False)
    q = _question(client, staff_headers)
    got = client.get(f"{BASE}/{q['id']}/bagheera", headers=student_headers).json()
    assert got == {"available": False, "reason": "Bagheera isn't set up on this server.", "messages": []}


def test_a_hint_is_saved_and_bagheera_never_sees_the_model_answer(client, staff_headers, student_headers, ra_on, ai):
    stub = ai(HINT)
    q = _question(client, staff_headers)
    reply = _chat(client, student_headers, q).json()
    assert reply["content"] == HINT and reply["guarded"] is False and "blocked_content" not in reply
    system, messages = stub.calls[0]
    assert "Small departments" in system and "π Pname PROF" in system      # the question and the current answer
    assert MODEL not in system and "Numphds < 50 DEPT" not in system
    assert messages[-1] == {"role": "user", "content": "How do I start?"}
    got = client.get(f"{BASE}/{q['id']}/bagheera", headers=student_headers).json()
    assert got["available"] and [m["role"] for m in got["messages"]] == ["user", "assistant"]
    # The next message remembers the conversation.
    _chat(client, student_headers, q, "And then?")
    assert [m["role"] for m in stub.calls[1][1]] == ["user", "assistant", "user"]


def test_a_reply_that_gives_the_answer_away_is_replaced(client, staff_headers, student_headers, ra_on, ai):
    stub = ai(f"Just write `{MODEL}`.", HINT)
    q = _question(client, staff_headers)
    reply = _chat(client, student_headers, q).json()
    assert reply["content"] == HINT and reply["guarded"] is True and len(stub.calls) == 2
    # Staff can see what was held back; the student can't.
    mine = client.get(f"{BASE}/{q['id']}/bagheera", headers=student_headers).json()["messages"]
    assert "blocked_content" not in mine[-1]


def test_when_both_replies_leak_a_fixed_hint_is_shown(client, staff_headers, student_headers, ra_on, ai):
    ai(f"`{MODEL}`")
    q = _question(client, staff_headers)
    reply = _chat(client, student_headers, q).json()
    assert reply["content"] == bagheera.SAFE_REPLY and reply["guarded"] is True


def test_explain_my_mistake_once_per_wrong_attempt(client, staff_headers, student_headers, ra_on, ai):
    stub = ai("Your answer lists every professor: the counterexample has one in a big department.")
    q = _question(client, staff_headers)
    pid = q["parts"][0]["id"]
    wrong = client.post(f"{BASE}/{q['id']}/submit", headers=student_headers,
                        json={"part_id": pid, "answer": "π Pname PROF"}).json()["attempt_id"]
    first = client.post(f"{BASE}/{q['id']}/bagheera/explain", headers=student_headers, json={"attempt_id": wrong})
    assert first.status_code == 200 and first.json()["kind"] == "explain" and first.json()["attempt_id"] == wrong
    assert "Counterexample database" in stub.calls[0][0]
    again = client.post(f"{BASE}/{q['id']}/bagheera/explain", headers=student_headers, json={"attempt_id": wrong})
    assert again.json()["id"] == first.json()["id"] and len(stub.calls) == 1        # saved, not asked again
    right = client.post(f"{BASE}/{q['id']}/submit", headers=student_headers,
                        json={"part_id": pid, "answer": MODEL}).json()["attempt_id"]
    assert client.post(f"{BASE}/{q['id']}/bagheera/explain", headers=student_headers,
                       json={"attempt_id": right}).status_code == 422
    # Someone else's attempt can't be explained.
    assert client.post(f"{BASE}/{q['id']}/bagheera/explain", headers=staff_headers,
                       json={"attempt_id": wrong}).status_code == 404


def test_staff_read_the_conversation_in_analytics(client, staff_headers, student_headers, ra_on, ai):
    ai(f"`{MODEL}`", HINT)
    q = _question(client, staff_headers)
    client.post(f"{BASE}/{q['id']}/submit", headers=student_headers,
                json={"part_id": q["parts"][0]["id"], "answer": "π Pname PROF"})
    _chat(client, student_headers, q)
    data = client.get(f"/api/v1/ra/analytics/questions/{q['id']}", headers=staff_headers).json()
    sid = data["students"][0]["user_id"]
    chat = client.get(f"/api/v1/ra/analytics/questions/{q['id']}/students/{sid}", headers=staff_headers).json()["bagheera"]
    assert [m["role"] for m in chat] == ["user", "assistant"]
    assert chat[1]["guarded"] and MODEL in chat[1]["blocked_content"]


def test_bagheera_is_off_where_it_could_reveal_correctness(client, staff_headers, student_headers, ra_on, ai):
    ai(HINT)
    q = _question(client, staff_headers, hide_correctness=True)
    got = client.get(f"{BASE}/{q['id']}/bagheera", headers=student_headers).json()
    assert got["available"] is False and got["reason"] == "Bagheera is off for this question."
    assert _chat(client, student_headers, q).status_code == 403
    assert _chat(client, staff_headers, q).status_code == 200          # staff may try it


def test_assessment_questions_have_no_bagheera(monkeypatch):
    monkeypatch.setattr(bagheera_llm, "configured", lambda: True)

    class Q:
        owner_assessment_id, hide_correctness = 7, 0

    class Student:
        role = None
    monkeypatch.setattr(bagheera.svc, "is_staff", lambda u: False)
    assert bagheera.available(Q(), Student()) == "Bagheera is off in assessments."


def test_an_ai_failure_is_reported_not_saved(client, staff_headers, student_headers, ra_on, monkeypatch):
    monkeypatch.setattr(bagheera_llm, "configured", lambda: True)

    async def down(system, messages):
        raise bagheera_llm.TutorUnavailable("Bagheera couldn't be reached (Timeout).")
    monkeypatch.setattr(bagheera_llm, "complete", down)
    q = _question(client, staff_headers)
    r = _chat(client, student_headers, q)
    assert r.status_code == 503 and "couldn't be reached" in r.json()["detail"]
    assert client.get(f"{BASE}/{q['id']}/bagheera", headers=student_headers).json()["messages"] == []
