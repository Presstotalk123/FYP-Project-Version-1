"""Let the student's written description add to and correct what was extracted.

WHY
Two extraction defects motivate this, one per submission path. The draw.io parser
is exact on the notation it maps but silently drops anything drawn off-notation.
Vision is worse and in a measurable way: on a professor-authored model answer
(1292x852 PNG) it read 0 of 5 curved endpoint cues and only 5 of 12 text markers,
and the arcs cannot be discriminated at any magnification or prompting — asked
tersely it denies a real arc, asked openly it reports one at every endpoint,
including the three that have none.

So the description is treated as a full second channel over the submission, not
as a hint about the picture.

DESIGN
The description is NOT fed to the vision model. Asking a vision model to
reconcile prose against pixels it cannot resolve was tried and did not work; its
prompt still forbade adding anything "not visibly drawn", which is exactly why it
never helped. That channel has been removed. Instead one text-only pass reads the
description into typed claims, and those claims are merged deterministically.

PRECEDENCE (the important part — this REVERSES the original rule)
  * A definite claim OVERRIDES what was extracted. The description is taken as
    the authoritative statement of what the student meant, on both paths.
  * Claims may ADD objects that were never extracted: entities, relationships
    (with their endpoints seeded so derive() can reach them), and attributes.
  * "not_stated" / "unknown" mean the description said nothing about that field,
    and the extracted value stands.
  * Each claim must quote the words it came from; unquoted claims are dropped.
    This is not a limit on what a student may claim — it is what stops the claims
    model inventing a claim the student never made.
  * Every added or overridden item carries that quote in its evidence string, so
    the judge, the tutor, staff analytics and the student can all see which marks
    were read from the diagram and which were taken on the student's word.

Two consequences follow directly and were accepted when this was designed: a
sparse diagram with a thorough write-up will score, and a student who draws a
relationship correctly then mis-describes it loses the mark they had earned.

CONSEQUENTLY "observation" no longer means "what was extracted from the diagram".
It means "what was extracted from the submission" — diagram plus description.
"""

import copy
import logging
import re
from typing import List, Literal, Optional

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from app.services.erd_tutor.llm import make_llm

logger = logging.getLogger(__name__)

_CARD = Literal["1", "N", "M", "0..1", "1..1", "0..N", "1..N", "not_stated"]
_PART = Literal["total", "partial", "not_stated"]


class _EndpointClaim(BaseModel):
    relationship_id: str
    entity_id: str
    normalized_cardinality: _CARD
    participation_type: _PART
    # The student's own words this was taken from. Required: a claim that cannot
    # be traced to the text is a guess, and gets dropped.
    quote: str


class _EntityClaim(BaseModel):
    name: str
    entity_kind: Literal["strong", "weak", "unknown"]
    quote: str


class _RelationshipClaim(BaseModel):
    name: str
    relationship_kind: Literal["normal", "identifying", "unknown"]
    # Names, not ids — the student has no knowledge of internal ids.
    participant_names: List[str]
    quote: str


class _AttributeClaim(BaseModel):
    name: str
    owner_name: str
    owner_type: Literal["entity", "relationship"]
    attribute_kind: Literal["normal", "key", "unknown"]
    quote: str


class _Claims(BaseModel):
    # All optional: a model reporting only endpoints must still validate.
    endpoints: List[_EndpointClaim] = Field(default_factory=list)
    entities: List[_EntityClaim] = Field(default_factory=list)
    relationships: List[_RelationshipClaim] = Field(default_factory=list)
    attributes: List[_AttributeClaim] = Field(default_factory=list)


SYSTEM = """You read a student's written description of an ER diagram and report only what it explicitly states about the model.

You are given what was extracted from the diagram, and a list of endpoints whose cardinality could not be read. Report four things: endpoint values, entities, relationships, and attributes the description states.

RULES
- Report something ONLY if the description states it. If it does not, leave it out entirely (or use "not_stated"/"unknown" for a field).
- Never infer from the problem domain, from what is typical, or from what would make the diagram correct. You are transcribing a claim, not judging it.
- "quote" must be the student's own words, copied exactly, that support the claim. If you cannot quote it, do not report the claim.
- When the extracted diagram already contains the thing being described, use the DIAGRAM'S OWN LABEL for "name", not the student's phrasing. The diagram may abbreviate ("OP-REC" for operation record); matching is done by exact name afterwards, so using the diagram's label is what lets an update attach to the right object instead of creating a duplicate.
- Answering the endpoint questions is the PRIMARY task. Do that first and completely, before considering any entity, relationship or attribute.
- Only report an entity, relationship or attribute if the description ADDS one the extracted diagram lacks, or CORRECTS something about one it has. NEVER report an item merely because it appears in the extracted diagram: that list is context for naming, not a checklist to echo back. Most descriptions warrant zero such claims.

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

Already extracted from the diagram:
{known}

Endpoints whose cardinality could not be read from the diagram:
{endpoints}

Report what the description states: endpoint values for the endpoints above, and any entities, relationships or attributes it describes."""


def _name(items, key):
    for it in items or []:
        if it.get("id") == key:
            return (it.get("normalized_name") or it.get("raw_name") or "").strip()
    return ""


def _norm(text: str) -> str:
    """Casefold, drop punctuation and spacing, and strip a trailing plural.

    Prose and diagram labels diverge in punctuation and number far more often
    than in wording — "Membership-type" versus "membership type", "Orders"
    versus "Order". The "ss" guard keeps "Address" from becoming "addres" and
    failing to match itself.
    """
    t = re.sub(r"[^a-z0-9]", "", (text or "").lower())
    if len(t) > 4 and t.endswith("sses"):
        t = t[:-2]  # "addresses" -> "address": keep the double s, drop the "es"
    elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]
    return t


def resolve_name(name: str, items) -> Optional[str]:
    """The id of the observed item this name refers to, or None.

    Deliberately strict: it resolves spelling, not meaning. An abbreviation the
    diagram uses for a longer phrase ("OP-REC" for "operation record") is not
    matched here — the claims prompt is told to use the diagram's own label when
    it can identify the thing, which keeps the fuzzy half with the model and the
    deterministic half in code where it can be tested.
    """
    target = _norm(name)
    if not target:
        return None
    for item in items or []:
        for key in ("normalized_name", "raw_name"):
            if _norm(item.get(key, "")) == target:
                return item.get("id")
    return None


def _evidence(quote: str) -> str:
    return f'Taken from the student\'s description: "{quote.strip()}".'


def _mint(prefix: str, taken: set) -> str:
    """A short id that cannot collide with one already in the observation."""
    n = 1
    while f"desc-{prefix}{n}" in taken:
        n += 1
    new = f"desc-{prefix}{n}"
    taken.add(new)
    return new


def _all_ids(observation: dict) -> set:
    ids = set()
    for key in ("entities", "relationships", "attributes",
                "relationship_endpoints", "specializations"):
        for item in observation.get(key) or []:
            if item.get("id"):
                ids.add(item["id"])
    return ids


def merge_objects(observation: dict, claims) -> tuple:
    """Fold described objects into the observation. Returns (observation, provenance).

    ``provenance`` maps each touched item id to the evidence string describing
    where it came from. Both additions and overrides are recorded: an override
    needs its provenance re-stamped after the normalize LLM just as much as an
    addition does (see restamp_provenance).

    The observation is deep-copied; the caller's dict is never mutated. Never
    raises — a malformed claim must not fail a student's submission, so any
    failure returns the observation exactly as it was observed.
    """
    try:
        return _merge(observation, claims)
    except Exception:
        logger.exception("description_claims: leaving the observation unchanged")
        return observation, {}


def _merge(observation: dict, claims) -> tuple:
    obs = copy.deepcopy(observation or {})
    prov: dict = {}
    if claims is None:
        return obs, prov

    for key in ("entities", "relationships", "attributes", "relationship_endpoints"):
        obs.setdefault(key, [])
    taken = _all_ids(obs)

    for claim in getattr(claims, "entities", []) or []:
        quote = (claim.quote or "").strip()
        if not quote:
            continue
        existing_id = resolve_name(claim.name, obs["entities"])
        if existing_id:
            if claim.entity_kind == "unknown":
                continue  # said nothing definite; the observed value stands
            for e in obs["entities"]:
                if e.get("id") == existing_id:
                    e["entity_kind"] = claim.entity_kind
                    e["evidence"] = _evidence(quote)
                    e["confidence"] = "high"
                    prov[existing_id] = e["evidence"]
            continue
        new_id = _mint("e", taken)
        obs["entities"].append({
            "id": new_id, "raw_name": claim.name, "normalized_name": claim.name,
            "entity_kind": claim.entity_kind, "evidence": _evidence(quote),
            "confidence": "high",
        })
        prov[new_id] = _evidence(quote)

    for claim in getattr(claims, "relationships", []) or []:
        quote = (claim.quote or "").strip()
        if not quote:
            continue

        # Resolve participants first, minting any entity the description
        # introduced along with the relationship.
        participant_ids = []
        for pname in claim.participant_names or []:
            pid = resolve_name(pname, obs["entities"])
            if not pid:
                pid = _mint("e", taken)
                obs["entities"].append({
                    "id": pid, "raw_name": pname, "normalized_name": pname,
                    "entity_kind": "unknown", "evidence": _evidence(quote),
                    "confidence": "high",
                })
                prov[pid] = _evidence(quote)
            if pid not in participant_ids:
                participant_ids.append(pid)

        # A claim naming no participants describes nothing usable. Guarded here
        # because an empty set can never equal an existing relationship's, so it
        # would slip past the match below and be minted as a participant-less
        # phantom — observed live, when the model echoed the extracted diagram
        # back as claims and one arrived with participant_names=[]. Reflexive
        # relationships are unaffected: ["User","User"] dedupes to one, not zero.
        if not participant_ids:
            continue

        # Matched on name AND participants: two relationships may join the same
        # pair of entities, and two may share a name. Only both together identify.
        existing_id = None
        for r in obs["relationships"]:
            same_name = _norm(r.get("normalized_name", "")) == _norm(claim.name) or \
                        _norm(r.get("raw_name", "")) == _norm(claim.name)
            if same_name and set(r.get("participant_entity_ids") or []) == set(participant_ids):
                existing_id = r.get("id")
                break

        if existing_id:
            if claim.relationship_kind == "unknown":
                continue
            for r in obs["relationships"]:
                if r.get("id") == existing_id:
                    r["relationship_kind"] = claim.relationship_kind
                    r["evidence"] = _evidence(quote)
                    r["confidence"] = "high"
                    prov[existing_id] = r["evidence"]
            continue

        rel_id = _mint("r", taken)
        obs["relationships"].append({
            "id": rel_id, "raw_name": claim.name, "normalized_name": claim.name,
            "relationship_kind": claim.relationship_kind,
            "participant_entity_ids": participant_ids,
            "evidence": _evidence(quote), "confidence": "high",
        })
        prov[rel_id] = _evidence(quote)

        # Seed an endpoint per participant. derive() iterates
        # relationship_endpoints, so without these the relationship exists with
        # no cardinality at all and apply_endpoint_claims has no row to write into.
        for pid in participant_ids:
            obs["relationship_endpoints"].append({
                "relationship_id": rel_id, "entity_id": pid,
                "observed_text_marker": "", "observed_endpoint_cue": "unknown",
                "evidence": _evidence(quote), "confidence": "high",
            })

    for claim in getattr(claims, "attributes", []) or []:
        quote = (claim.quote or "").strip()
        if not quote:
            continue
        pool = obs["entities"] if claim.owner_type == "entity" else obs["relationships"]
        owner_id = resolve_name(claim.owner_name, pool)
        if not owner_id:
            continue  # nothing to hang it on; dropped rather than guessed
        existing_id = None
        for a in obs["attributes"]:
            if a.get("owner_id") == owner_id and _norm(a.get("normalized_name", "")) == _norm(claim.name):
                existing_id = a.get("id")
                break
        if existing_id:
            if claim.attribute_kind == "unknown":
                continue
            for a in obs["attributes"]:
                if a.get("id") == existing_id:
                    a["attribute_kind_observed"] = claim.attribute_kind
                    a["evidence"] = _evidence(quote)
                    a["confidence"] = "high"
                    prov[existing_id] = a["evidence"]
            continue
        new_id = _mint("a", taken)
        obs["attributes"].append({
            "id": new_id, "raw_name": claim.name, "normalized_name": claim.name,
            "owner_id": owner_id, "owner_type": claim.owner_type,
            "attribute_kind_observed": claim.attribute_kind,
            "evidence": _evidence(quote), "confidence": "high",
        })
        prov[new_id] = _evidence(quote)

    return obs, prov


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


def _known_listing(observation) -> str:
    """The entity and relationship labels already extracted, for the prompt.

    Given to the model so it can use the diagram's own label when describing
    something that already exists — which is what lets resolve_name attach the
    claim to the existing object instead of minting a duplicate.
    """
    obs = observation or {}
    ents = [(e.get("normalized_name") or e.get("raw_name") or "").strip()
            for e in obs.get("entities") or []]
    rels = [(r.get("normalized_name") or r.get("raw_name") or "").strip()
            for r in obs.get("relationships") or []]
    ents = [e for e in ents if e]
    rels = [r for r in rels if r]
    return (f"entities: {', '.join(ents) if ents else '(none)'}\n"
            f"relationships: {', '.join(rels) if rels else '(none)'}")


async def read_claims(description: Optional[str], observation) -> Optional[_Claims]:
    """One LLM call: what does the description explicitly state? Never raises.

    Returns None when there is no description or the call fails, which callers
    treat as "no claims" and therefore as today's behaviour.
    """
    text = (description or "").strip()
    if not text:
        return None
    try:
        obs = observation or {}
        lines = []
        for ep in obs.get("relationship_endpoints") or []:
            rid, eid = ep.get("relationship_id"), ep.get("entity_id")
            entity, link = _describe(obs, rid, eid)
            lines.append(f'- relationship_id={rid} entity_id={eid}: how many instances of '
                         f'{link} does ONE "{entity}" take part in?')
        llm = make_llm("normalize").with_structured_output(_Claims)
        return await llm.ainvoke([
            SystemMessage(SYSTEM),
            HumanMessage(USER.format(description=text,
                                     known=_known_listing(obs),
                                     endpoints="\n".join(lines) or "(none)")),
        ])
    except Exception:
        logger.exception("description_claims: could not read claims; ignoring the description")
        return None


def apply_endpoint_claims(cards, parts, claims) -> tuple:
    """Apply described endpoint values over the derived ones. Never raises.

    Returns (cards, parts, applied). Unlike the original fill-only behaviour, a
    definite claim OVERRIDES a value read from the diagram — the description is
    the authoritative statement of what the student meant. "not_stated" means
    the description said nothing about that endpoint, so the derived value
    stands.
    """
    try:
        if claims is None:
            return cards, parts, 0
        by_key = {(c.relationship_id, c.entity_id): c
                  for c in (getattr(claims, "endpoints", []) or [])}
        if not by_key:
            return cards, parts, 0

        part_by_key = {(p.get("relationship_id"), p.get("entity_id")): p for p in parts}
        applied = 0
        for card in cards:
            key = (card.get("relationship_id"), card.get("entity_id"))
            claim = by_key.get(key)
            if claim is None:
                continue
            quote = (claim.quote or "").strip()
            if not quote:
                continue
            touched = False
            if claim.normalized_cardinality != "not_stated":
                card["normalized_cardinality"] = claim.normalized_cardinality
                card["raw_marker"] = "(from description)"
                card["evidence"] = _evidence(quote)
                card["confidence"] = "high"
                touched = True
            part = part_by_key.get(key)
            if part is not None and claim.participation_type != "not_stated":
                part["participation_type"] = claim.participation_type
                part["evidence"] = _evidence(quote)
                part["confidence"] = "high"
                touched = True
            applied += touched

        if applied:
            logger.info("description set %d endpoint value(s)", applied)
        return cards, parts, applied
    except Exception:
        logger.exception("description_claims: leaving derived endpoint values unchanged")
        return cards, parts, 0


def restamp_provenance(canonical: dict, provenance: dict) -> dict:
    """Re-apply description provenance to the canonical model, matching by id.

    merge_objects writes evidence onto the observation, but the normalize LLM
    then rewrites that JSON and may paraphrase or drop an ``evidence`` field —
    losing provenance on exactly the items that most need it. Re-stamping here
    is deterministic and does not depend on the prompt preserving anything.
    """
    if not provenance:
        return canonical
    for key in ("entities", "relationships", "attributes", "specializations"):
        for item in canonical.get(key) or []:
            stamp = provenance.get(item.get("id"))
            if stamp:
                item["evidence"] = stamp
    return canonical
