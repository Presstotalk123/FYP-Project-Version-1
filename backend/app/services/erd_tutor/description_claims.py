"""Let the student's own description supply cardinality the diagram did not yield.

WHY
On an image submission neither cardinality channel is trustworthy. Measured on a
professor-authored model answer (1292x852 PNG): the vision stage read 0 of 5
curved endpoint cues, and text markers only 5 of 12. Worse, the arcs are not
merely missed — they cannot be discriminated. Asked tersely the model denies a
real arc; asked openly it reports a curved stroke at every endpoint, including
the three that have none. Magnifying the crop 6x changes neither result, so no
prompt or zoom recovers them.

That leaves the student's description as the only reliable cardinality channel
for image submissions, which is what this module reads.

DESIGN
The description is NOT fed to the vision model. Asking a vision model to
reconcile prose against pixels it cannot resolve is the same mistake as asking
the judge to compare JSON fragments — it was tried, and the observe prompt still
forbids the description from adding anything "not visibly drawn", which is
exactly why it never helped. Instead a text-only pass reads the description
against the specific endpoints that came out unknown, and its answers are merged
deterministically.

PRECEDENCE (the important part)
  * Only endpoints whose value is UNKNOWN are eligible. Observed evidence is
    never overridden, so a description cannot contradict a mark the student drew.
  * Each claim must quote the words it came from; unquoted claims are dropped.
  * Filled values are labelled as description-sourced in their evidence string,
    so the judge, the tutor, staff analytics and the student all see which marks
    were read from the diagram and which were taken on the student's word.

On a draw.io submission this will almost never fire — the parser leaves no
endpoint unknown on any diagram measured so far — but it is not restricted to
images, so the rare unparseable endpoint can still be recovered.
"""

import logging
from typing import List, Literal, Optional

from pydantic import BaseModel
from langchain_core.messages import SystemMessage, HumanMessage

from app.services.erd_tutor.llm import make_llm

logger = logging.getLogger(__name__)

_CARD = Literal["1", "N", "M", "0..1", "1..1", "0..N", "1..N", "not_stated"]
_PART = Literal["total", "partial", "not_stated"]


class _Claim(BaseModel):
    relationship_id: str
    entity_id: str
    normalized_cardinality: _CARD
    participation_type: _PART
    # The student's own words this was taken from. Required: a claim that cannot
    # be traced to the text is a guess, and gets dropped.
    quote: str


class _Claims(BaseModel):
    claims: List[_Claim]


SYSTEM = """You read a student's written description of an ER diagram and report only what it explicitly states about specific relationship endpoints.

You are given endpoints whose cardinality could not be read from the diagram. For each one, report what the description says about it — nothing more.

RULES
- Report a value ONLY if the description states it for that specific relationship and entity. If it does not, use "not_stated".
- Never infer from the problem domain, from what is typical, or from what would make the diagram correct. You are transcribing a claim, not judging it.
- "quote" must be the student's own words, copied exactly, that support the value. If you cannot quote it, the value is "not_stated".

ENDPOINT CARDINALITY FRAME (the easiest thing to get backwards)
The value at an endpoint states how many instances of THAT relationship ONE instance of THAT SAME entity takes part in. It never counts the entity across the relationship.

Careful: in an English sentence the number usually lands on the OPPOSITE entity from the one being counted. Convert like this, where A and B are entities and R is the relationship between them:
- "each B has one or more A"        -> endpoint B = 1..N   (one B takes part in many instances of R)
- "each B has at most one A"        -> endpoint B = 0..1
- "each B has exactly one A"        -> endpoint B = 1..1
- "each B may have no A, or many"   -> endpoint B = 0..N
The endpoint named in the question is the one you are answering for. Answer each question about the entity it names, not the other one.

Two different relationships may join the SAME pair of entities. Use the relationship named in the question, and match it to the description by its wording, not by the entities alone.

Entity names in the diagram may be abbreviated or hyphenated relative to the student's prose ("OP-REC" for "operation record", "Membership-type" for "membership type"). Match them by meaning.

BEFORE ANSWERING, for each endpoint re-read your chosen value and confirm it answers "how many instances of this relationship does ONE of THIS entity take part in?". If it describes the other entity, swap it.

- participation_type follows the minimum: a minimum of 0 is "partial", 1 or more is "total".
- Cardinality must be exactly one of: 1, N, M, 0..1, 1..1, 0..N, 1..N, not_stated."""

USER = """Student_Description:
{description}

Endpoints whose cardinality could not be read from the diagram:
{endpoints}

For each endpoint above, report what the description states about it."""


def _name(items, key):
    for it in items or []:
        if it.get("id") == key:
            return (it.get("normalized_name") or it.get("raw_name") or "").strip()
    return ""


def _describe(observation, rel_id, ent_id):
    """Human-readable identification of one endpoint.

    Names the relationship's other participants, not just the relationship. A
    diagram may leave its diamonds unlabelled — the professor's hospital model
    answer leaves three unnamed — and without the participants all three read as
    the same endpoint, so the description could not be aligned to any of them.
    """
    obs = observation or {}
    entity = _name(obs.get("entities"), ent_id) or ent_id
    rel = _name(obs.get("relationships"), rel_id)
    others = []
    for r in obs.get("relationships") or []:
        if r.get("id") == rel_id:
            for pid in r.get("participant_entity_ids") or []:
                if pid != ent_id:
                    others.append(_name(obs.get("entities"), pid) or pid)
    link = (f'the "{rel}" relationship' if rel else "an unlabelled relationship")
    if others:
        link += " between " + " and ".join(f'"{o}"' for o in [entity] + others)
    return entity, link


async def fill_unknown_endpoints(cards, parts, observation, description: Optional[str]):
    """Fill unknown cardinality/participation from the description. Never raises.

    Returns (cards, parts, filled) where ``filled`` counts the endpoints changed.
    """
    try:
        return await _fill(cards, parts, observation, description)
    except Exception:
        logger.exception("description_claims: leaving observed values unchanged")
        return cards, parts, 0


async def _fill(cards, parts, observation, description):
    text = (description or "").strip()
    if not text:
        return cards, parts, 0

    part_by_key = {(p.get("relationship_id"), p.get("entity_id")): p for p in parts}
    gaps = []
    for c in cards:
        key = (c.get("relationship_id"), c.get("entity_id"))
        p = part_by_key.get(key) or {}
        if c.get("normalized_cardinality") == "unknown" or p.get("participation_type") == "unknown":
            gaps.append((key, c, p))
    if not gaps:
        return cards, parts, 0

    lines = []
    for k, _c, _p in gaps:
        entity, link = _describe(observation, k[0], k[1])
        lines.append(f'- relationship_id={k[0]} entity_id={k[1]}: how many instances of '
                     f'{link} does ONE "{entity}" take part in?')
    listing = "\n".join(lines)

    llm = make_llm("normalize").with_structured_output(_Claims)
    result = await llm.ainvoke([SystemMessage(SYSTEM),
                                HumanMessage(USER.format(description=text, endpoints=listing))])

    by_key = {(cl.relationship_id, cl.entity_id): cl for cl in result.claims}
    filled = 0
    for key, card, part in gaps:
        claim = by_key.get(key)
        if claim is None or not (claim.quote or "").strip():
            continue
        touched = False
        if (card.get("normalized_cardinality") == "unknown"
                and claim.normalized_cardinality != "not_stated"):
            card["normalized_cardinality"] = claim.normalized_cardinality
            card["raw_marker"] = "(from description)"
            card["evidence"] = ("Not readable in the diagram; taken from the student's "
                                f"description: \"{claim.quote.strip()}\".")
            card["confidence"] = "medium"
            touched = True
        if part and part.get("participation_type") == "unknown" \
                and claim.participation_type != "not_stated":
            part["participation_type"] = claim.participation_type
            part["evidence"] = ("Not readable in the diagram; taken from the student's "
                                f"description: \"{claim.quote.strip()}\".")
            part["confidence"] = "medium"
            touched = True
        filled += touched

    if filled:
        logger.info("description supplied %d endpoint value(s) the diagram did not yield", filled)
    return cards, parts, filled
