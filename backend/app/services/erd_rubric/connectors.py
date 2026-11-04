"""Connector (line-end mark) checks for relationships whose lines carry numbers.

WHY
The lectures teach two things at a line end: the degree constraint (the number,
">=1") and the integrity constraint (the arrowhead: pointed = at most one,
rounded = exactly one). A numbered line used to get its number check alone, so
on the EduBot question no arrowhead was graded at all; staff grade both. And
which head the generator reads off the image was a coin flip (0/7 to 7/7 across
runs on the conference question), while the numbers it reads are reliable. In
this notation an arrowhead constrains the entity at the OTHER end of its line,
so on a two-ended line the number there decides the head:
    other end exactly one ("1")         -> rounded_arrow
    other end at most one ("0..1")      -> arrow
    other end with no upper limit       -> plain
Anything else keeps what the generator read from the image: an end whose other
end has no readable number, a reflexive or 3+-ended relationship, and a pair of
entities joined by more than one relationship (which line is which cannot be
told from the rubric).

WHAT IT DOES (create mode only; see runner.py)
* corrects each connector check's marks to the numbers, one note per change;
* adds a connector check to every two-ended numbered relationship that lacks
  one, taking half of that relationship's number-check points so the total
  stays put.
It adds them even when the generator reported no arrowheads: on the EduBot
model answer 3 of 3 create runs wrote "no arrowheads are shown" and emitted no
connector check, though the image draws four rounded heads and a pointed one.
Whether a model answer draws heads cannot be read reliably off the image; the
heads its numbers call for can. Staff delete the added checks for a model
answer that deliberately draws none.
"""

from app.services.erd_tutor.deterministic_checks import (
    _compact, _min_from_participation, _norm_name, _parse_range,
)

NUMBER_TYPES = ("cardinality_match", "relationship_endpoints_match")
CONNECTOR_TYPE = "integrity_constraint_match"


def _bounds(endpoint):
    """(min, max) a rubric endpoint states; None where it states nothing."""
    value = endpoint.get("cardinality")
    lo, hi = _parse_range(value)          # strict: an odd value reads as unknown
    if lo is None and isinstance(hi, int) and _compact(value).isdigit():
        lo = hi                           # the course notation's "1" is exactly one
    if lo is None:
        lo = _min_from_participation(endpoint.get("participation"))
    return lo, hi


def _mark_for(other_end):
    """The head an end needs, given the number at the other end of its line;
    None when that number cannot tell."""
    lo, hi = _bounds(other_end)
    if hi == "N" or (isinstance(hi, int) and hi > 1):
        return "plain"
    if hi == 1 and lo == 1:
        return "rounded_arrow"
    if hi == 1 and lo == 0:
        return "arrow"
    return None


def _pair(check):
    """The two distinct entities a check joins, or None."""
    names = [_norm_name(e.get("entity")) for e in ((check.get("target") or {}).get("endpoints") or [])]
    if len(names) != 2 or not all(names) or names[0] == names[1]:
        return None
    return frozenset(names)


def _criteria(ends):
    names = "-".join(e.get("entity") for e in ends)
    said = ", ".join(f"{e.get('entity')} end {e.get('mark')}" for e in ends)
    return f"The {names} line ends are drawn as in the model answer: {said}"


def _correct(connector, wanted, number, relationship):
    ends = connector["target"]["endpoints"]
    by_name = {_norm_name(e.get("entity")): e for e in number["target"]["endpoints"]}
    changed = []
    for ep in ends:
        mark = wanted.get(_norm_name(ep.get("entity")))
        if mark and ep.get("mark") != mark:
            other = next(e for n, e in by_name.items() if n != _norm_name(ep.get("entity")))
            changed.append(f"{ep.get('entity')} end {ep.get('mark') or 'unread'} -> {mark} "
                           f"({other.get('entity')} is {other.get('cardinality')})")
            ep["mark"] = mark
    if not changed:
        return []
    connector["pass_criteria"] = _criteria(ends)
    return [f"{relationship}: " + ", ".join(changed)]


def _new_connector(number, wanted, taken_ids):
    a, b = (e.get("entity") for e in number["target"]["endpoints"])
    ends = [{"entity": a, "mark": wanted[_norm_name(a)]}, {"entity": b, "mark": wanted[_norm_name(b)]}]
    points = int(number.get("points") or 0)
    share = points // 2
    number["points"] = points - share
    n = 1
    while f"M{n}" in taken_ids:
        n += 1
    policy = dict(number.get("decision_policy") or {})
    policy.update(explicit_diagram_evidence_required=True, unclear_evidence_policy="fail",
                  missing_policy="fail", partial_allowed=False)
    return {
        "id": f"M{n}", "dimension": "cardinality", "type": CONNECTOR_TYPE,
        "target": {"relationship": number["target"].get("relationship"),
                   "participants": [a, b], "endpoints": ends},
        "requirement_level": number.get("requirement_level") or "must",
        "points": share,
        "pass_criteria": _criteria(ends),
        "fail_reason_template": f"The {a}-{b} line ends are not drawn as in the model answer.",
        "evidence": "diagram_llm_extraction",
        "equivalence_options": list(number.get("equivalence_options") or []),
        "notes": "Added after generation: each mark is set from the number at the other end of its line.",
        "decision_policy": policy,
    }


def add_connector_checks(rubric):
    """Correct and complete the connector checks of a freshly generated rubric.

    Mutates ``rubric`` (a rubric_json dict) and returns one note per change.
    """
    checks = (rubric or {}).get("checks") or []
    numbers_by_pair, connectors_by_pair = {}, {}
    for c in checks:
        key = _pair(c)
        if key is None:
            continue
        if c.get("type") in NUMBER_TYPES:
            numbers_by_pair.setdefault(key, []).append(c)
        elif c.get("type") == CONNECTOR_TYPE:
            connectors_by_pair.setdefault(key, []).append(c)

    notes = []
    for key, numbers in numbers_by_pair.items():
        existing = connectors_by_pair.get(key, [])
        if len(numbers) != 1 or len(existing) > 1:
            continue
        number = numbers[0]
        first, second = number["target"]["endpoints"]
        wanted = {_norm_name(first.get("entity")): _mark_for(second),
                  _norm_name(second.get("entity")): _mark_for(first)}
        relationship = number["target"].get("relationship") or "-".join(
            e.get("entity") for e in (first, second))
        if existing:
            notes += _correct(existing[0], wanted, number, relationship)
        elif all(wanted.values()):
            added = _new_connector(number, wanted, {str(c.get("id")) for c in checks})
            checks.append(added)
            notes.append(f"{relationship}: connector check {added['id']} added "
                         f"({added['pass_criteria'].split(': ', 1)[1]}), "
                         f"taking {added['points']} of {number.get('id')}'s points")
    return notes
