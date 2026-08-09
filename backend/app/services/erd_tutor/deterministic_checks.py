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

POLICY (deliberately asymmetric, conservative about equivalences)
For each rubric check with dimension "cardinality" and two explicit endpoints:
  * definite endpoint MATCH        -> override the judge to pass
  * definite MISMATCH or unreadable evidence, and the check has NO
    equivalence_options             -> override the judge to fail, naming the
                                       exact endpoint and values
  * anything else (structure not locatable, equivalence options present and
    direct evidence absent/mismatched, unparseable rubric values)
                                    -> leave the judge's verdict untouched
An "associative bridge" is treated as direct evidence: if A and B have no
direct relationship but both connect to one common entity X (e.g. an
associative/weak entity), A's endpoint on rel(A,X) and B's endpoint on
rel(B,X) are compared instead — that is how "Patient 0..N Operation" is
actually drawn in an OP-REC model.
"""

import logging
import re

logger = logging.getLogger(__name__)

_MANY = ("N", "M")

# The only accepted endpoint value shapes: "1", "N", "M", or "<int>..<int|N|M>".
_STRICT_RANGE = re.compile(r"\s*(?:\d+|[NnMm]|\d+\s*\.\.\s*(?:\d+|[NnMm]))\s*")


def _norm_name(s):
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


def _parse_range(text):
    """'1..N' / '0..1' / '1' / 'N' -> (min, max) with None for unknown; max 'N' for many.

    Anything not matching one of those exact shapes yields (None, None) — it must
    NOT be salvaged. A generator once emitted the two-relationship string
    "assigned_to: 1; manages: 0..1" into a single endpoint; a lenient split on
    ".." pulled a spurious max=1 out of it, which then "matched" the diagram and
    passed a check that had never actually been evaluated. Unparseable means
    unparseable, and the caller skips the check so the judge decides it.
    """
    t = str(text or "").strip()
    if not t or t.lower() == "unknown":
        return (None, None)
    if not _STRICT_RANGE.fullmatch(t):
        return (None, None)
    if ".." in t:
        lo, hi = t.split("..", 1)
        lo, hi = lo.strip(), hi.strip().upper()
        try:
            lo_v = int(lo)
        except ValueError:
            lo_v = None
        hi_v = "N" if hi in _MANY else (int(hi) if hi.isdigit() else None)
        return (lo_v, hi_v)
    if t.upper() in _MANY:
        return (None, "N")
    if t.isdigit():
        # A bare count states the maximum; the minimum comes from participation.
        return (None, int(t))
    return (None, None)


def _min_from_participation(part):
    return {"total": 1, "partial": 0}.get(str(part or "").strip().lower())


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
        rid = rel.get("id")
        for eid in ids:
            if (rid, eid) in self.card or (rid, eid) in self.part:
                card = (self.card.get((rid, eid)) or {}).get("normalized_cardinality")
                lo, hi = _parse_range(card)
                if lo is None:
                    lo = _min_from_participation(self.part.get((rid, eid)))
                return (lo, hi)
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
    """required/found are (min,max); None = unknown. -> 'match' | 'mismatch' | 'unknown'"""
    r_lo, r_hi = required
    f_lo, f_hi = found
    verdict = "match"
    for r, f in ((r_lo, f_lo), (r_hi, f_hi)):
        if r is None:
            continue  # rubric does not constrain this component
        if f is None:
            verdict = "unknown"
        elif f != r:
            return "mismatch"
    return verdict


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
            wanted.append((ep.get("entity"), (lo, hi)))
        if all(lo is None and hi is None for _, (lo, hi) in wanted):
            continue  # rubric endpoint values unparseable -> judge keeps it

        ids = [model.entity_ids(name) for name, _ in wanted]
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

        best = None  # (verdict_rank, detail) — prefer a match over unknown over mismatch
        rank = {"match": 0, "unknown": 1, "mismatch": 2}
        for rel_a, rel_b in candidates:
            found_a = model.endpoint(rel_a, ids[0])
            found_b = model.endpoint(rel_b, ids[1])
            if found_a is None or found_b is None:
                verdict, detail = "unknown", "endpoint not recorded"
            else:
                v_a = _match(wanted[0][1], found_a)
                v_b = _match(wanted[1][1], found_b)
                verdict = ("mismatch" if "mismatch" in (v_a, v_b)
                           else "unknown" if "unknown" in (v_a, v_b) else "match")
                detail = (f"{wanted[0][0]}: required {_fmt(wanted[0][1])}, drawn {_fmt(found_a)}; "
                          f"{wanted[1][0]}: required {_fmt(wanted[1][1])}, drawn {_fmt(found_b)}")
            if best is None or rank[verdict] < rank[best[0]]:
                best = (verdict, detail)
                if verdict == "match":
                    break

        verdict, detail = best
        via = " (via the associative entity)" if via_bridge else ""
        jc = by_id.get(cid)
        if jc is None:
            continue

        if verdict == "match":
            jc["status"] = "pass"
            jc["brief_reason"] = f"Endpoint values match the requirement{via}: {detail}."
        elif not has_equiv:
            # Definite mismatch, or unreadable evidence, with no equivalence escape:
            # the binding decision_policy (unclear_evidence_policy=fail) applies.
            jc["status"] = "fail"
            word = "do not match the requirement" if verdict == "mismatch" \
                else "could not be read from the diagram"
            jc["brief_reason"] = f"Endpoint values {word}{via}: {detail}."
        else:
            continue  # equivalence options exist and direct evidence is not a match
        by_id[cid] = jc

    judge["checks"] = [by_id.get(str(j.get("id")), j) for j in judge.get("checks") or []]
    return judge
