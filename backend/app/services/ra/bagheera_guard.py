"""Bagheera's leak guard: never show a reply that gives a question's answer away.

Bagheera is never given the model answer, but an AI can still work the question out and
write the solution. So before a reply is shown, every RA expression in it is found and
checked with the grader against every part of the question:

  * a correct answer to a part (same result as the model answer on every test database), or
  * an expression, or a step of one, that computes one of a part's model steps (its
    checkpoints: the R1 := … lines, or the prompts of a multi-step question)

means the reply leaks. Small examples on other relations, or a fragment that solves no
part or step, are fine. The check uses the test databases only (no proof), so it is quick;
it errs on the safe side, since an expression passing every test is treated as a leak.

Finding expressions: code blocks and inline code are tried whole; any other line with an
RA operator (σ, Π, ⋈ …, the look-alikes students paste, or \\select-style words) is cut
down to the longest piece that parses, and consecutive such lines are also tried together
as one program (R1 := … then R2 := … R1 …).
"""
import re
from typing import List, Sequence

from app.core.ra import RAError
from app.core.ra.grader import PreparedQuestion
from app.core.ra.parser import parse

MAX_CANDIDATES = 12
MAX_PARSES = 300

_OPERATOR = re.compile(r"[σπΠρδγ⋈⨝⟕⟖⟗×⨯÷∪⋃∩⋂−∏]|\\(?:select|project|rename|distinct|group|join|leftjoin|"
                       r"rightjoin|fulljoin|cross|divide|union|intersect|diff)\b|:=|←")
_CODE_BLOCK = re.compile(r"```[a-zA-Z]*\n?(.*?)```", re.S)
_INLINE = re.compile(r"`([^`\n]+)`")


def _parses(text: str, names: Sequence[str]) -> bool:
    try:
        parse(text, names)
        return True
    except RAError:
        return False
    except Exception:                      # a parser crash must not break the chat
        return False


def candidates(reply: str, names: Sequence[str]) -> List[str]:
    """The RA expressions (or programs) written in a reply."""
    found: List[str] = []
    budget = [MAX_PARSES]

    def add(text: str) -> bool:
        text = text.strip().strip(".,;:")
        if not text or text in found or budget[0] <= 0:
            return False
        budget[0] -= 1
        if _parses(text, names):
            found.append(text)
            return True
        return False

    for block in _CODE_BLOCK.findall(reply):
        add(block)
        for line in block.splitlines():
            add(line)
    prose = _CODE_BLOCK.sub("\n", reply)
    for code in _INLINE.findall(prose):
        add(code)
    run: List[str] = []
    for line in prose.splitlines() + [""]:
        pieces = _pieces(_INLINE.sub(lambda m: m.group(1), line), names, budget)
        if pieces:
            for piece in pieces:
                add(piece)
            run.extend(pieces)
            continue
        if len(run) > 1:
            add("\n".join(run))
        run = []
    return found[:MAX_CANDIDATES]


def _pieces(line: str, names: Sequence[str], budget: List[int]) -> List[str]:
    """Each longest run of words in the line that parses as RA and has an operator."""
    if not _OPERATOR.search(line):
        return []
    words = line.split()
    starts = [i for i, w in enumerate(words) if _OPERATOR.search(w) or w.lstrip("(").rstrip(",.;:)") in names
              or (i + 1 < len(words) and words[i + 1] in (":=", "←"))]
    out, done = [], 0
    for i in starts:
        if i < done:
            continue
        for j in range(len(words), i, -1):
            if budget[0] <= 0:
                return out
            text = " ".join(words[i:j]).strip().strip(".,;:")
            if not _OPERATOR.search(text):
                break
            budget[0] -= 1
            if _parses(text, names):
                out.append(text)
                done = j
                break
    return out


def leaks(reply: str, prepared: Sequence[PreparedQuestion]) -> List[str]:
    """The expressions in the reply that solve a part, or one of a part's model steps."""
    if not prepared:
        return []
    out = []
    for text in candidates(reply, prepared[0].names):
        for pq in prepared:
            try:
                g = pq.grade(text, with_steps=True, prove=False)
            except Exception:
                continue
            if g.verdict == "correct" or any(s.status == "match" for s in g.steps):
                out.append(text)
                break
    return out
