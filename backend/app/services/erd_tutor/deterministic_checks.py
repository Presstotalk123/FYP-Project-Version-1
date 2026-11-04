"""Deterministic verdicts for cardinality rubric checks.

WHY THIS EXISTS
The judge LLM proved unreliable at exactly one job: comparing two small JSON
fragments. With a canonical model whose endpoints matched a rubric check
endpoint-for-endpoint, the judge returned "unclear or unknown" — repeatedly,
and in one measured run it failed four such exact matches at once (60 points).
It also passed checks whose evidence was definitely wrong. Since the rubric
generator and the extractor now share one declared endpoint frame (the value at
an endpoint is that entity's own (min,max) participation), this comparison is
mechanical — so it is done here in Python, the same reasoning that put scoring
in ``scoring.py``.

POLICY (conservative about equivalences; missing is a lesser error than wrong)
For each rubric check with dimension "cardinality" and two explicit endpoints:
  * definite endpoint MATCH        -> override the judge to pass
  * definite MISMATCH, and the check has NO equivalence_options
                                    -> override the judge to fail, naming the
                                       exact endpoint and values
  * two numbers that differ in meaning written at one end, WHATEVER the
    equivalence_options             -> override the judge to fail (staff,
                                       2026-11-05: no way of drawing the
                                       relationship makes that end right)
  * no contradiction, at least one required bound confirmed, the rest not
    stated in the diagram, and NO equivalence_options
                                    -> override the judge to partial. A student
                                       who draws the maximum correctly and
                                       omits the minimum made a lesser error
                                       than one who drew a wrong value; before
                                       this rule both lost the full check.
  * nothing readable at either endpoint, and NO equivalence_options
                                    -> override the judge to fail
  * anything else (structure not locatable, equivalence options present and
    direct evidence absent/mismatched, unparseable rubric values)
                                    -> leave the judge's verdict untouched
A rubric endpoint constrains only the components it states: a bare "N" with no
participation value checks the maximum alone, so any drawn minimum satisfies
it. Every check decided here is stamped decided_by="deterministic"; scoring.py
uses the stamp to keep a deliberate partial that it would strip from the judge
(an LLM returning partial out of mere uncertainty, which rule 13 forbids).
An "associative bridge" is treated as direct evidence: if A and B have no
direct relationship but both connect to one common entity X (e.g. an
associative/weak entity), A's endpoint on rel(A,X) and B's endpoint on
rel(B,X) are compared instead — that is how "Patient 0..N Operation" is
actually drawn in an OP-REC model.

WRITTEN NUMBERS, IN THE COURSE NOTATION
Rubric values follow the model answer's own labels (">=1", ">=0", "1",
"0..1"); saved rubrics may still hold the older ranges ("1..N", "1..1"). Both
are read by what they mean: ">=n" is n or more with no upper limit, "<=n" is up
to n, "1" is exactly one. A student's end is the NUMBER written there, read the
same way, so "1..N" satisfies ">=1" and "1" does not. The arrowhead at an end
plays no part here — integrity_checks grades it — because a number that took
its maximum from the arrowhead at its own end was read wrongly whenever the
course drew that arrowhead to bound the OTHER end: the EduBot model answer
failed its own Model-Tool check that way. An end the parser did not produce
(an LLM-built model, or a value the student gave in words) still counts by
its derived value. An end with more than one number (written_markers) is read
as one number when they all mean the same (">=1" and "1..N"), and is wrong
when they do not (">=1" and "1"): the student has not said which.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Rubric endpoint values. Saved rubrics hold "1", "N", "M", "<int>..<int|N|M>";
# new ones hold the course notation (">=1", ">=0", "<=5", ">=1 and <=5", "=1").
_STRICT_RANGE = re.compile(r"\d+|[nm]|\d+\.\.(?:\d+|[nm*])|\(\d+,(?:\d+|[nm*])\)")
_STRICT_BOUND = re.compile(r">=\d+(?:(?:and|or)<=\d+)?|<=\d+|=\d+")

_RANGE = re.compile(r"\(?(\d+)(?:\.\.|,)(\d+|[nm*])\)?")
_CLAUSE = re.compile(r"(>=|<=|=)(\d+|[nm*])")    # ">=" and "<=" before bare "="

# raw_marker at an end where the student typed nothing: derive() stores the cue.
_NOTHING_WRITTEN = {"", "no_arrow_visible", "sharp_arrowhead", "curved_arrowhead", "unknown"}
_FROM_DESCRIPTION = "(from description)"


def _norm_name(s):
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


def _compact(text):
    """Lower-case, the slides' glyphs spelled out, spaces removed."""
    return (str(text or "").strip().lower()
            .replace("≥", ">=").replace("≤", "<=").replace(" ", ""))


def _cap(token):
    return "N" if token in ("n", "m", "*") else int(token)


def _bounds(t):
    """Compact label -> (min, max) by what it says; (None, None) if unreadable.

    ">=n" is n or more with no upper limit, "<=n" is up to n (none allowed),
    "=n" or a bare count is exactly n, "N"/"M" is many with no minimum stated.
    """
    if t in ("n", "m", "*"):
        return (None, "N")
    if t.isdigit():
        return (int(t), int(t))
    m = _RANGE.fullmatch(t)
    if m:
        return (int(m.group(1)), _cap(m.group(2)))
    clauses = _CLAUSE.findall(t)
    if not clauses:
        return (None, None)
    lo = hi = None
    for op, token in clauses:
        value = _cap(token)
        if op == ">=":
            lo = value
        elif op == "<=":
            hi = value
        else:
            lo = hi = value
    return (0 if lo is None else lo, "N" if hi is None else hi)


def _parse_range(text):
    """Rubric endpoint value -> (min, max) with None for unknown; max 'N' for many.

    Anything not in one of the accepted shapes yields (None, None) — it must
    NOT be salvaged. A generator once emitted the two-relationship string
    "assigned_to: 1; manages: 0..1" into a single endpoint; a lenient split on
    ".." pulled a spurious max=1 out of it, which then "matched" the diagram and
    passed a check that had never actually been evaluated. Unparseable means
    unparseable, and the caller skips the check so the judge decides it.
    """
    t = _compact(text)
    if not t or t == "unknown":
        return (None, None)
    if _STRICT_BOUND.fullmatch(t):
        return _bounds(t)
    if not _STRICT_RANGE.fullmatch(t):
        return (None, None)
    if t.isdigit():
        # A bare count states the maximum; the minimum comes from participation
        # (saved rubrics pair "1" with "partial" for at most one).
        return (None, int(t))
    return _bounds(t)


def _written(card):
    """The label a student typed at this end: a string, "" when the end carries
    no number, or None when the end did not come from the parser (an LLM-built
    model) or was given in words, whose derived value then stands."""
    if "endpoint_cue" not in card:
        return None
    marker = str(card.get("raw_marker") or "").strip()
    if marker == _FROM_DESCRIPTION:
        return None
    return "" if marker in _NOTHING_WRITTEN else marker


def _read_written(label):
    """A typed label -> (min, max), read as a rubric value is, but leniently:
    a role prefix ("As child: >=0 and <=1") is dropped first."""
    return _bounds(_compact(label).rsplit(":", 1)[-1])


# What _Model.endpoint finds at an end carrying two different numbers.
_CONFLICT = object()


def _differing(card):
    """Every number written at this end when they do not all mean the same,
    else None. A label that cannot be read is compared by its text."""
    markers = [str(m).strip() for m in card.get("written_markers") or [] if str(m).strip()]
    meanings = {_read_written(m) if _read_written(m) != (None, None) else _compact(m)
                for m in markers}
    return markers if len(meanings) > 1 else None


def _min_from_participation(part):
    return {"total": 1, "partial": 0}.get(str(part or "").strip().lower())


def _required(ep, rng):
    """What the rubric asks for at an end, in its own words. A saved rubric's
    bare value is only half the requirement: its participation word is the
    minimum, so it is named whenever it changes what the value says alone."""
    value = str(ep.get("cardinality") or "").strip()
    if not value:
        return _fmt(rng)
    if _bounds(_compact(value)) == rng:
        return value
    part = str(ep.get("participation") or "").strip().lower()
    return f"{value} ({part if part in ('total', 'partial') else 'maximum only'})"


class _Model:
    """Index the canonical ERD for endpoint lookups."""

    def __init__(self, canonical):
        c = canonical or {}
        self.ent_by_id, self.ids_by_name = {}, {}
        for e in c.get("entities", []):
            self.ent_by_id[e.get("id")] = e
            for key in {_norm_name(e.get("normalized_name")), _norm_name(e.get("raw_name"))}:
                if key:
                    self.ids_by_name.setdefault(key, []).append(e.get("id"))
        self.rels = c.get("relationships", [])
        self.card = {(x.get("relationship_id"), x.get("entity_id")): x
                     for x in c.get("cardinalities", [])}
        self.part = {(p.get("relationship_id"), p.get("entity_id")): p.get("participation_type")
                     for p in c.get("participation", [])}

    def entity_ids(self, name):
        n = _norm_name(name)
        if n in self.ids_by_name:
            return self.ids_by_name[n]
        # A qualified rubric name ("Cardiology Ward") may be drawn unqualified, or
        # vice versa — accept containment either way when it is unambiguous.
        hits = [ids for key, ids in self.ids_by_name.items() if n in key or key in n]
        return hits[0] if len(hits) == 1 else []

    def rels_between(self, ids_a, ids_b):
        out = []
        for r in self.rels:
            ps = r.get("participant_entity_ids") or []
            if any(a in ps for a in ids_a) and any(b in ps for b in ids_b):
                out.append(r)
        return out

    def endpoint(self, rel, ids):
        """-> ((min, max), what the diagram shows) for this end of rel, or None
        when the end is not recorded at all."""
        rid = rel.get("id")
        for eid in ids:
            if (rid, eid) in self.card or (rid, eid) in self.part:
                card = self.card.get((rid, eid)) or {}
                written = _written(card)
                if written == "":
                    return ((None, None), "nothing written")
                if written is not None:
                    several = _differing(card)
                    if several:
                        return (_CONFLICT, f"written {' and '.join(several)}")
                    return (_read_written(written), f"written {written}")
                lo, hi = _parse_range(card.get("normalized_cardinality"))
                if lo is None:
                    lo = _min_from_participation(self.part.get((rid, eid)))
                return ((lo, hi), f"drawn {_fmt((lo, hi))}")
        return None  # endpoint not recorded at all

    def bridge(self, ids_a, ids_b):
        """Common-neighbour entity X with rel(A,X) and rel(B,X): the associative pattern."""
        def neighbours(ids):
            n = {}
            for r in self.rels:
                ps = r.get("participant_entity_ids") or []
                if any(i in ps for i in ids):
                    for other in ps:
                        if other not in ids:
                            n.setdefault(other, []).append(r)
            return n
        na, nb = neighbours(ids_a), neighbours(ids_b)
        for x in na:
            if x in nb:
                return na[x][0], nb[x][0]
        return None


def _match(required, found):
    """required/found are (min,max); None = unknown.

    -> (verdict, confirmed): verdict is 'match' | 'mismatch' | 'unknown';
    confirmed counts required components the diagram states AND matches. The
    count is what separates "partly verified" (-> partial) from "nothing
    readable at all" (-> fail). Two different numbers at the end (_CONFLICT)
    are 'conflict', which confirms nothing.
    """
    if found is _CONFLICT:
        return ("conflict", 0)
    r_lo, r_hi = required
    f_lo, f_hi = found
    verdict, confirmed = "match", 0
    for r, f in ((r_lo, f_lo), (r_hi, f_hi)):
        if r is None:
            continue  # rubric does not constrain this component
        if f is None:
            verdict = "unknown"
        elif f != r:
            return ("mismatch", confirmed)
        else:
            confirmed += 1
    return (verdict, confirmed)


def _fmt(rng):
    lo, hi = rng
    return f"{'?' if lo is None else lo}..{'?' if hi is None else hi}"


def apply_deterministic_overrides(judge_result, rubric, canonical):
    """Return judge_result with cardinality checks decided by direct comparison
    where that is possible. Never raises — any surprise defers to the judge."""
    try:
        return _apply(judge_result, rubric, canonical)
    except Exception:
        logger.exception("deterministic_checks: falling back to judge verdicts")
        return judge_result


def _apply(judge_result, rubric, canonical):
    checks = (rubric or {}).get("checks") or []
    model = _Model(canonical)
    judge = dict(judge_result or {})
    by_id = {str(j.get("id")): dict(j) for j in judge.get("checks") or []}

    for rc in checks:
        if str(rc.get("dimension")) != "cardinality":
            continue
        if str(rc.get("type")) == "integrity_constraint_match":
            continue  # compares line-end marks, not (min,max): integrity_checks decides it
        eps = ((rc.get("target") or {}).get("endpoints") or [])
        if len(eps) != 2:
            continue
        has_equiv = bool(rc.get("equivalence_options"))
        cid = str(rc.get("id"))

        wanted = []
        for ep in eps:
            lo, hi = _parse_range(ep.get("cardinality"))
            if lo is None:
                lo = _min_from_participation(ep.get("participation"))
            wanted.append((ep.get("entity"), (lo, hi), _required(ep, (lo, hi))))
        if all(lo is None and hi is None for _, (lo, hi), _ in wanted):
            continue  # rubric endpoint values unparseable -> judge keeps it

        ids = [model.entity_ids(name) for name, _, _ in wanted]
        if not ids[0] or not ids[1]:
            continue  # entities not locatable -> judge keeps it

        # Direct relationship(s) first; associative bridge as the fallback.
        candidates = [(r, r) for r in model.rels_between(ids[0], ids[1])]
        via_bridge = False
        if not candidates:
            b = model.bridge(ids[0], ids[1])
            if b:
                candidates, via_bridge = [b], True
        if not candidates:
            continue  # no structure found -> judge keeps it (may be equivalence)

        # Prefer a match over a partly-confirmed unknown, that over a fully
        # unreadable one, and any of them over a mismatch. A single recorded
        # endpoint still counts: one labelled end and one bare end is partial
        # evidence, not unreadable evidence.
        best = None  # (verdict, confirmed, detail)
        rank = {"match": 0, "unknown": 1, "mismatch": 2, "conflict": 2}
        for rel_a, rel_b in candidates:
            end_a = model.endpoint(rel_a, ids[0])
            end_b = model.endpoint(rel_b, ids[1])
            if end_a is None and end_b is None:
                verdict, confirmed, detail = "unknown", 0, "endpoint not recorded"
            else:
                fa, shown_a = end_a or ((None, None), "not recorded")
                fb, shown_b = end_b or ((None, None), "not recorded")
                v_a, c_a = _match(wanted[0][1], fa)
                v_b, c_b = _match(wanted[1][1], fb)
                confirmed = c_a + c_b
                verdict = ("conflict" if "conflict" in (v_a, v_b)
                           else "mismatch" if "mismatch" in (v_a, v_b)
                           else "unknown" if "unknown" in (v_a, v_b) else "match")
                detail = (f"{wanted[0][0]}: required {wanted[0][2]}, {shown_a}; "
                          f"{wanted[1][0]}: required {wanted[1][2]}, {shown_b}")
            if best is None or (rank[verdict], -confirmed) < (rank[best[0]], -best[1]):
                best = (verdict, confirmed, detail)
                if verdict == "match":
                    break

        verdict, confirmed, detail = best
        via = " (via the associative entity)" if via_bridge else ""
        jc = by_id.get(cid)
        if jc is None:
            continue

        if verdict == "match":
            jc["status"] = "pass"
            jc["brief_reason"] = f"Endpoint values match the requirement{via}: {detail}."
        elif verdict == "conflict":
            # Wrong in every drawing of the relationship, so no equivalence
            # option hands it to the judge.
            jc["status"] = "fail"
            jc["brief_reason"] = (f"Endpoint values do not match the requirement{via}: two "
                                  f"different numbers are written at one end: {detail}.")
        elif has_equiv:
            continue  # equivalence options exist and direct evidence is not a match
        elif verdict == "mismatch":
            # A stated value contradicts the rubric: the binding decision_policy
            # (unclear_evidence_policy=fail) applies with no softening.
            jc["status"] = "fail"
            jc["brief_reason"] = f"Endpoint values do not match the requirement{via}: {detail}."
        elif confirmed:
            # Missing is not wrong. Nothing the student drew contradicts the
            # requirement and part of it is confirmed; the rest is simply not
            # stated. Half marks, and the reason names what is absent.
            jc["status"] = "partial"
            jc["brief_reason"] = (f"Partly verified{via}: no drawn value contradicts the "
                                  f"requirement, but not every required bound is stated "
                                  f"in the diagram: {detail}.")
        else:
            # The structure is drawn but carries no readable cardinality
            # evidence at all — there is nothing to award.
            jc["status"] = "fail"
            jc["brief_reason"] = f"Endpoint values could not be read from the diagram{via}: {detail}."
        # The stamp lets scoring.py tell this deliberate decision apart from a
        # judge LLM hedging with "partial" where its policy forbids one.
        jc["decided_by"] = "deterministic"
        by_id[cid] = jc

    judge["checks"] = [by_id.get(str(j.get("id")), j) for j in judge.get("checks") or []]
    return judge
