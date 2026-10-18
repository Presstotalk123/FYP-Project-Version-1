"""Deterministic verdicts for integrity_constraint_match rubric checks.

WHY THIS EXISTS
The lectures draw an integrity constraint as the mark a relationship line
carries where it meets an entity: nothing (plain line), a pointed arrow (key
constraint, at most one) or a rounded arrow (referential integrity, exactly
one). A model answer can consist of nothing else — the conference-review
question draws a rounded arrow on all seven relationships and no number
anywhere, its statement waives degree constraints, and so its rubric checked
none of them. The rubric generator now records the mark at every entity end
(``target.endpoints[].mark``), and the draw.io parser reads the same three
marks exactly from the line's own style. Comparing two three-valued fields is
not a judgement, so — as with ``deterministic_checks`` and
``structural_checks`` — it is done here rather than asked of the judge.

This compares DRAWINGS, not meanings. It deliberately does not go through
``derivation``: that module turns a cue into the platform's per-endpoint
maximum (curve -> N, arrow -> 1), a frame in which a pointed arrow and a plain
end are the same value and the lecture's arrow-into-the-one-side reads
backwards. The mark itself has no such ambiguity.

POLICY (strict: every end must match, no partial credit)
For each check of type "integrity_constraint_match" whose endpoints all name an
entity and a mark, on a submission parsed from draw.io source:
  * a relationship joins those entities and every end carries the required
    mark                                   -> pass
  * one joins them, some end differs, no equivalence_options
                                           -> fail, naming each wrong end
  * the entities are drawn, NOTHING joins them, no equivalence_options
                                           -> missing_policy
  * anything else — an image upload (vision misses real curves, so its "no
    arrow" proves nothing), an entity name that resolves neither exactly nor
    to a single one-slip spelling (it may be a synonym), a mismatch on a check
    that lists equivalence_options, an unreadable mark
                                           -> the judge's verdict stands
Relationships are matched by their ENTITIES, never by label: that question has
two diamonds labelled "is", three "for" and two "has". When several
relationships join the same entities the best one counts, as in
``deterministic_checks``. A reflexive relationship names one entity twice; its
two marks are compared in either order.
Every check decided here is stamped decided_by="deterministic".
"""

import difflib
import logging
from collections import Counter

from app.services.erd_tutor.deterministic_checks import _Model, _norm_name

logger = logging.getLogger(__name__)

CHECK_TYPE = "integrity_constraint_match"

_MARK_OF_CUE = {"no_arrow_visible": "plain", "sharp_arrowhead": "arrow", "curved_arrowhead": "rounded_arrow"}
_WORDS = {"plain": "plain line", "arrow": "pointed arrow", "rounded_arrow": "rounded arrow"}


def apply_integrity_overrides(judge_result, rubric, canonical, observation):
    """Return judge_result with line-end-mark checks decided by direct
    comparison where that is possible. Never raises — any surprise defers to
    the judge."""
    try:
        return _apply(judge_result, rubric, canonical, observation)
    except Exception:
        logger.exception("integrity_checks: falling back to judge verdicts")
        return judge_result


def _apply(judge_result, rubric, canonical, observation):
    checks = [rc for rc in ((rubric or {}).get("checks") or []) if str(rc.get("type")) == CHECK_TYPE]
    # Only draw.io source can prove that a line end is plain; see the docstring.
    if not checks or (observation or {}).get("source_mode") != "xml":
        return judge_result

    model = _Model(canonical)
    drawn = {}                     # (relationship id, entity id) -> marks, one per line end
    for ep in observation.get("relationship_endpoints") or []:
        key = (ep.get("relationship_id"), ep.get("entity_id"))
        drawn.setdefault(key, []).append(_MARK_OF_CUE.get(ep.get("observed_endpoint_cue")))

    judge = dict(judge_result or {})
    by_id = {str(j.get("id")): dict(j) for j in judge.get("checks") or []}

    for rc in checks:
        jc = by_id.get(str(rc.get("id")))
        ends = [(ep.get("entity"), ep.get("mark")) for ep in ((rc.get("target") or {}).get("endpoints") or [])]
        if jc is None or len(ends) < 2 or any(not name or mark not in _WORDS for name, mark in ends):
            continue
        ids = {name: _entity_ids(model, name) for name, _ in ends}
        if not all(ids.values()):
            continue                                   # not locatable: it may be a synonym
        required = {}                                  # entity name -> marks required at its ends
        for name, mark in ends:
            required.setdefault(name, []).append(mark)

        best = None                                    # wrong ends of the closest relationship
        for rel in model.rels:
            participants = rel.get("participant_entity_ids") or []
            if not all(any(i in participants for i in ids[name]) for name in required):
                continue
            wrong, readable = [], True
            for name, marks in required.items():
                found = [m for i in ids[name] for m in drawn.get((rel.get("id"), i), [])]
                if None in found:
                    readable = False
                elif Counter(found) != Counter(marks):
                    wrong.append(f"{name} end: required {_say(marks)}, drawn {_say(found) or 'no line'}")
            if readable and (best is None or len(wrong) < len(best)):
                best = wrong
        has_equiv = bool(rc.get("equivalence_options"))

        if best == []:
            jc["status"] = "pass"
            jc["brief_reason"] = ("Line-end marks match the model answer: "
                                  + "; ".join(f"{name} end {_say(marks)}" for name, marks in required.items()) + ".")
        elif has_equiv:
            continue
        elif best:
            jc["status"] = "fail"
            jc["brief_reason"] = "Line-end marks do not match the model answer: " + "; ".join(best) + "."
        elif best is None and not _joined(model, ids):
            policy = rc.get("decision_policy") or {}
            jc["status"] = "not_applicable" if str(policy.get("missing_policy")) == "not_applicable" else "fail"
            jc["brief_reason"] = f"No relationship joins {' and '.join(required)} in the diagram."
        else:
            continue                                   # joined, but a mark was unreadable
        jc["decided_by"] = "deterministic"
        by_id[str(rc.get("id"))] = jc

    judge["checks"] = [by_id.get(str(j.get("id")), j) for j in judge.get("checks") or []]
    return judge


def _entity_ids(model, name):
    """The drawn entity with this name, or with ONE spelling slip of it.

    Not _Model.entity_ids: that also accepts containment ("Ward" for "Cardiology
    Ward"), which resolves a missing AUTHOR to AUTHORING — fine for a lenient
    lookup, wrong for a check that fails on what it finds. A near-match is a
    different thing: the conference question spells an entity AFFLIATION,
    students copy it, and the generator wrote AFFILIATION into these checks.
    It must be the only drawn name that close, or the judge keeps the check.
    """
    key = _norm_name(name)
    if key in model.ids_by_name:
        return model.ids_by_name[key]
    close = difflib.get_close_matches(key, list(model.ids_by_name), n=2, cutoff=0.9)
    return model.ids_by_name[close[0]] if len(close) == 1 else []


def _joined(model, ids):
    return any(all(any(i in (rel.get("participant_entity_ids") or []) for i in group) for group in ids.values())
               for rel in model.rels)


def _say(marks):
    return " and ".join(_WORDS.get(m, "unreadable") for m in marks)
