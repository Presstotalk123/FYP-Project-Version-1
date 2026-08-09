"""Deterministic conversion of observed endpoint marks into cardinality and participation.

WHY
Turning a mark into a bound is a lookup table, not a judgement:

    ">=0" + curve  ->  0..N        "=1" + arrow  ->  1..1

The normalize LLM was doing this and getting it wrong even when handed exact
input from the draw.io parser. Measured on a real submission: two relationships
both named "Has", both touching Album, one marked ">=0"+curve and the other
"=1"+arrow — it returned 0..N/partial for BOTH, collapsing them, because it
matched on name rather than id. The student's correct marker was read correctly
by the parser and then discarded one stage later.

So the arithmetic is done here, keyed by (relationship_id, entity_id) so
same-named relationships cannot merge. The LLM keeps the work it is good at —
naming, OCR cleanup, deciding what is an entity — and normalize_node overwrites
only the two arrays it demonstrably cannot compute.

THE RULES (the platform's declared notation; see notation-related prompt text)
  text marker sets what it states:
      ">=n"            -> minimum n
      "<=n"            -> maximum n
      "=n"             -> minimum n (the cue then fixes the maximum)
      ">=0 or <=1"     -> 0..1
      "n..m" / "(n,m)" -> both bounds
      "1"              -> 1..1        "N" / "M" -> maximum N
  then, if the maximum is still open, the endpoint cue decides it:
      curved_arrowhead -> N     sharp_arrowhead -> 1
      no_arrow_visible -> 1     unknown         -> stays open
  participation depends ONLY on the minimum:
      min 0 -> partial     min >= 1 -> total     min open -> unknown
"""

import re

# normalized_cardinality must stay inside the schema's Literal set.
_ALLOWED = {"1", "N", "M", "0..1", "1..1", "0..N", "1..N", "unknown"}

_EXPLICIT = {
    "0..1": (0, 1), "1..1": (1, 1), "0..n": (0, "N"), "1..n": (1, "N"),
    "(0,1)": (0, 1), "(1,1)": (1, 1), "(0,n)": (0, "N"), "(1,n)": (1, "N"),
    "1": (1, 1), "n": (None, "N"), "m": (None, "N"),
}
_CUE_MAX = {"curved_arrowhead": "N", "sharp_arrowhead": 1, "no_arrow_visible": 1}


# Comparison clauses, scanned anywhere in the label. Order matters: ">=" and
# "<=" must be tried before bare "=". Scanning rather than whole-string matching
# is what lets one rule cover ">=1 and <=1", ">=0 or <=1" and "As child: >=0
# and <=1" — real markers from real submissions. Conjunction words need no
# special handling: taking the minimum from ">=" and the maximum from "<="
# gives the intended reading for both "and" and "or".
_CLAUSE = re.compile(r"(>=|<=|=)(\d+|[nm])")
_RANGE = re.compile(r"(\d+)\.\.(\d+|[nm])")


def _num(token):
    return "N" if token in ("n", "m") else int(token)


def parse_marker(text):
    """Text marker -> (min, max, status).

    status: "absent" (no mark), "read" (understood), "unreadable" (there is a
    mark and we failed to parse it). The distinction matters — an unreadable
    mark must NOT fall through to the endpoint cue, because the writing plainly
    states something and quietly substituting the cue's answer for it produces a
    confident wrong bound instead of a visible gap.
    """
    raw = str(text or "").strip()
    if not raw:
        return (None, None, "absent")
    t = raw.lower()
    t = t.rsplit(":", 1)[-1]                 # drop role prefixes ("as child: ...")
    t = t.replace(" ", "")
    if t in _EXPLICIT:
        lo, hi = _EXPLICIT[t]
        return (lo, hi, "read")
    m = _RANGE.fullmatch(t)
    if m:
        return (int(m.group(1)), _num(m.group(2)), "read")
    lo = hi = None
    for op, token in _CLAUSE.findall(t):
        value = _num(token)
        if op == "<=":
            hi = value if hi is None else min(hi, value, key=_rank)
        elif op == ">=":
            lo = value if lo is None else min(lo, value)
        else:                                 # bare "=n": states the minimum;
            lo = value if lo is None else lo   # the cue settles the maximum
    if lo is None and hi is None:
        return (None, None, "unreadable")
    return (lo, hi, "read")


def _rank(value):
    """Order maxima with N above every integer."""
    return float("inf") if value == "N" else value


def combine(lo, hi):
    """(min, max) -> a normalized_cardinality the schema accepts."""
    if lo is None and hi is None:
        return "unknown"
    if lo is None:
        return {1: "1", "N": "N"}.get(hi, "unknown")     # maximum only
    if hi is None:
        return "unknown"                                  # minimum only: not expressible
    value = f"{lo}..{hi}"
    return value if value in _ALLOWED else "unknown"


def participation_from_min(lo):
    if lo is None:
        return "unknown"
    return "partial" if lo == 0 else "total"


def derive_endpoint(marker, cue):
    """(marker, cue) -> (normalized_cardinality, participation_type, why)."""
    lo, hi, status = parse_marker(marker)
    if status == "unreadable":
        return ("unknown", "unknown",
                f"there is a mark at this endpoint ({marker!r}) but it is not in a "
                f"notation this grader recognises, so no bound was assumed from it")
    from_cue = False
    if hi is None:
        cue_max = _CUE_MAX.get((cue or "").strip())
        if cue_max is not None:
            hi, from_cue = cue_max, True
    why = (f"text marker {marker!r} gives "
           f"{'minimum ' + str(lo) if lo is not None else 'no minimum'}"
           if status == "read" else "no text marker at this endpoint")
    why += (f"; {cue} gives maximum {hi}" if from_cue
            else f"; maximum {hi} from the text marker" if hi is not None
            else "; maximum not established")
    return combine(lo, hi), participation_from_min(lo), why


def derive(observation: dict):
    """Observation -> (cardinalities, participation), both schema-shaped.

    Keyed by (relationship_id, entity_id): relationships sharing a name stay
    distinct, which is exactly what the LLM path got wrong.
    """
    cards, parts = [], []
    for ep in (observation or {}).get("relationship_endpoints") or []:
        rid, eid = ep.get("relationship_id"), ep.get("entity_id")
        marker = ep.get("observed_text_marker") or ""
        cue = ep.get("observed_endpoint_cue") or ""
        card, part, why = derive_endpoint(marker, cue)
        cards.append({
            "relationship_id": rid, "entity_id": eid,
            "raw_marker": marker or cue,
            "normalized_cardinality": card,
            "evidence": f"Derived deterministically: {why}.",
            "confidence": "high" if card != "unknown" else "low",
        })
        parts.append({
            "relationship_id": rid, "entity_id": eid,
            "participation_type": part,
            "evidence": f"Participation follows the minimum only: {why}.",
            "confidence": "high" if part != "unknown" else "low",
        })
    return cards, parts
