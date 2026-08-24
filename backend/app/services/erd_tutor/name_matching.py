"""Deterministic name matching for the naming-sensitive rubric checks.

WHY THIS EXISTS
Three fields decided naming strictness on paper and nothing at all in practice.
The rubric generator writes ``exact_name_required``, ``semantic_alias_allowed``
and ``abbreviation_allowed`` on every naming check - 409 of them across the 43
stored rubrics - and no consumer existed: the judge prompt never named them and
no code read them. Naming was therefore decided entirely by the judge's own
reading of the problem statement, which is the one comparison an LLM should not
be doing alone. "USER has attribute name" against a box labelled "Names" is a
string comparison, not a judgement.

So the mechanical half is done here, and the judge keeps the half that needs
meaning (is ``cust_id`` the same idea as ``customer_id``?).

POLICY (asymmetric, the same shape as deterministic_checks)
For a naming-sensitive check whose required names all resolve in the canonical
model under ``normalize_label``:
  * every required name found -> override the judge to pass
  * anything else             -> leave the judge's verdict untouched
This can only raise a status, never lower one. A name this module cannot match
may still be a valid synonym, and only the judge can say so.

WHAT COUNTS AS THE SAME NAME
Case, punctuation, spacing and a trailing plural are noise: "Names", "name",
"NAME" and "name_" are one token. Meaning is not handled here - "client" does
not match "customer" at this stage, by design.
"""

import logging
import re

logger = logging.getLogger(__name__)

# The generator emits these only on checks where name matching decides the
# outcome; their presence is what marks a check as naming-sensitive.
NAMING_FLAGS = ("exact_name_required", "semantic_alias_allowed", "abbreviation_allowed")

_TRUE = {"true", "yes", "1"}
_FALSE = {"false", "no", "0"}


def normalize_label(text) -> str:
    """Casefold, drop punctuation and spacing, and strip a trailing plural.

    The "ss" guard keeps "Address" from becoming "addres" and failing to match
    itself. This is the same rule description_claims uses to resolve a name in
    prose against a drawn label, and both callers must stay in step.
    """
    t = re.sub(r"[^a-z0-9]", "", str(text or "").lower())
    if len(t) > 4 and t.endswith("sses"):
        t = t[:-2]      # "addresses" -> "address": keep the double s, drop the "es"
    elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]
    return t


def flag(policy, key):
    """A decision_policy flag as a real bool, or None when it is absent.

    Eight stored rubrics (question ids 19-24, 39, 40) hold the JSON strings
    "true"/"false" where the rest hold booleans, so an ``is False`` test read
    62 checks as "no policy given" and 341 as "policy says no". Same declared
    policy, two different grades. Coerce once, here.
    """
    if not isinstance(policy, dict) or key not in policy:
        return None
    value = policy[key]
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
    return None


def is_naming_check(check) -> bool:
    """True when the check's outcome turns on a name rather than on structure."""
    policy = (check or {}).get("decision_policy")
    return isinstance(policy, dict) and any(k in policy for k in NAMING_FLAGS)


class _Model:
    """Index the canonical ERD for name lookups."""

    def __init__(self, canonical):
        c = canonical or {}
        self.entities = c.get("entities") or []
        self.relationships = c.get("relationships") or []
        self.attributes = c.get("attributes") or []

    @staticmethod
    def _labels(item):
        return {normalize_label(item.get("normalized_name")),
                normalize_label(item.get("raw_name"))} - {""}

    def _match(self, items, name):
        """The first item whose drawn label normalizes to ``name``, or None."""
        target = normalize_label(name)
        if not target:
            return None
        for item in items:
            if target in self._labels(item):
                return item
        return None

    def ids(self, items, name):
        target = normalize_label(name)
        if not target:
            return []
        return [i.get("id") for i in items if target in self._labels(i)]

    def find_object(self, kind, name):
        return self._match(self.entities if kind == "entity" else self.relationships, name)

    def find_attribute(self, name, owner_ids, key_only):
        target = normalize_label(name)
        if not target:
            return None
        for attr in self.attributes:
            if target not in self._labels(attr):
                continue
            if owner_ids is not None and attr.get("owner_id") not in owner_ids:
                continue
            if key_only and attr.get("attribute_kind") != "key":
                continue
            return attr
        return None


def _split_key(text):
    """A composite primary key ("order_id, line_no") states several attributes."""
    return [p for p in re.split(r"[,+/]| and ", str(text or "")) if p.strip()]


def _requirements(check):
    """The names this check requires -> [(kind, name, owner_name, key_only)].

    An empty list means the check is not one this module can decide; the caller
    then leaves it with the judge.
    """
    target = check.get("target") or {}
    ctype = str(check.get("type") or "")
    dimension = str(check.get("dimension") or "")
    out = []

    if ctype == "attribute_presence" or (dimension == "attributes"
                                         and not ctype.startswith("relationship")):
        names = list(target.get("attributes_required") or [])
        if target.get("attribute"):
            names.append(target["attribute"])
        for name in names:
            out.append(("attribute", name, target.get("entity"), False))

    elif ctype == "key_presence" or dimension == "keys_constraints":
        for key in target.get("keys_required") or []:
            owner = key.get("entity") or target.get("entity")
            for part in _split_key(key.get("primary_key")):
                out.append(("attribute", part, owner, True))
        if not out and target.get("attribute"):
            out.append(("attribute", target["attribute"], target.get("entity"), True))

    elif ctype == "relationship_attribute_presence":
        for name in target.get("relationship_attributes_required") or []:
            out.append(("rel_attribute", name, target.get("relationship"), False))

    elif ctype == "entity_presence" or dimension == "entities":
        names = list(target.get("entities") or [])
        if target.get("entity"):
            names.append(target["entity"])
        for name in names:
            out.append(("entity", name, None, False))

    elif ctype == "relationship_presence":
        names = list(target.get("relationships_required") or [])
        if target.get("relationship"):
            names.append(target["relationship"])
        for name in names:
            out.append(("relationship", name, None, False))

    seen, unique = set(), []
    for req in out:
        key = (req[0], normalize_label(req[1]), normalize_label(req[2] or ""), req[3])
        if req[1] and key not in seen:
            seen.add(key)
            unique.append(req)
    return unique


def _drawn(item):
    return (item.get("raw_name") or item.get("normalized_name") or "").strip()


def _resolve(model, kind, name, owner_name, key_only):
    """-> (required, drawn) when the name is found, else None."""
    if kind in ("attribute", "rel_attribute"):
        owner_ids = None
        if owner_name:
            items = model.entities if kind == "attribute" else model.relationships
            owner_ids = model.ids(items, owner_name)
            if not owner_ids:
                return None      # owner not locatable: the judge decides this check
        found = model.find_attribute(name, owner_ids, key_only)
    else:
        found = model.find_object(kind, name)
    return (name, _drawn(found)) if found else None


def apply_naming_overrides(judge_result, rubric, canonical):
    """Pass any naming check whose required names are all drawn in the model.

    Never raises - a surprise defers to the judge, exactly as the cardinality
    pass does.
    """
    try:
        return _apply(judge_result, rubric, canonical)
    except Exception:
        logger.exception("name_matching: falling back to judge verdicts")
        return judge_result


def _apply(judge_result, rubric, canonical):
    checks = (rubric or {}).get("checks") or []
    model = _Model(canonical)
    judge = dict(judge_result or {})
    by_id = {str(j.get("id")): dict(j) for j in judge.get("checks") or []}

    for rc in checks:
        if not is_naming_check(rc):
            continue
        cid = str(rc.get("id"))
        jc = by_id.get(cid)
        if jc is None or jc.get("status") not in {"fail", "partial"}:
            continue        # only ever an upgrade
        reqs = _requirements(rc)
        if not reqs:
            continue

        pairs = [_resolve(model, *req) for req in reqs]
        if any(p is None for p in pairs):
            continue        # a required name is absent or only a synonym: judge keeps it

        detail = "; ".join(f"required {req!r}, drawn {drawn!r}" for req, drawn in pairs)
        jc["status"] = "pass"
        jc["brief_reason"] = (
            "Every required name is present. Case, punctuation, spacing and "
            f"plural form do not change a name: {detail}.")
        by_id[cid] = jc

    judge["checks"] = [by_id.get(str(j.get("id")), j) for j in judge.get("checks") or []]
    return judge
