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

# Checks on HOW a thing is drawn, which a name match cannot decide. They need
# naming by type because the flags above do not set them apart - the rubric
# schema writes all three onto every check - and because "entities" is their
# dimension, which sent weak_entity_correct down the entity_presence branch:
# the judge failed a single-bordered AUTHORING, this module found an entity
# named AUTHORING, and the fail became a pass.
_STRUCTURAL_TYPES = {"weak_entity_correct", "identifying_relationship_correct",
                     "hierarchy_supertype_subtype_correct"}

# The check types the rubric generator declares (erd_rubric.prompts, ALLOWED
# CHECK TYPE EXAMPLES), plus every equivalence_* type. A check typed one of
# these is that type, whatever dimension it sits in.
KNOWN_CHECK_TYPES = frozenset({
    "entity_presence", "attribute_presence", "key_presence", "relationship_presence",
    "relationship_endpoints_match", "relationship_attribute_presence", "cardinality_match",
    "participation_match", "integrity_constraint_match", "weak_entity_correct",
    "identifying_relationship_correct", "hierarchy_supertype_subtype_correct",
    "constraint_rule_present", "relationship_arity_match", "reflexive_relationship_correct",
    "aggregation_correct",
})

# What a check of any other type is, by the dimension it sits in.
_DIMENSION_TYPES = {"entities": "entity_presence", "attributes": "attribute_presence",
                    "keys_constraints": "key_presence", "relationships": "relationship_presence",
                    "cardinality": "cardinality_match"}

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


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def check_type(check) -> str:
    """What kind of check this is, the one reading every consumer shares.

    The declared ``type`` when it is a known one (KNOWN_CHECK_TYPES, or any
    equivalence_* type). Otherwise the dimension decides: "entities" ->
    entity_presence, "attributes" -> attribute_presence (or
    relationship_attribute_presence for a type that starts with
    "relationship"), "keys_constraints" -> key_presence, "relationships" ->
    relationship_presence, "cardinality" -> cardinality_match. Anything else
    keeps its type as written. A type or dimension that is not a string reads
    as absent; so does a check that is not an object ("").

    One reading, because the readers disagreed: requirements() went by type OR
    dimension while the extras guard and the pricing went by type alone, so a
    key check typed "pk_check" required its key and yet made no key underline
    chargeable, and an attribute check typed "attr_check" required its
    attribute and yet left an extra attribute to be priced from every check.
    """
    if not isinstance(check, dict):
        return ""
    declared, dimension = _text(check.get("type")), _text(check.get("dimension"))
    if declared in KNOWN_CHECK_TYPES or declared.startswith("equivalence_"):
        return declared
    if dimension == "attributes" and declared.startswith("relationship"):
        return "relationship_attribute_presence"
    return _DIMENSION_TYPES.get(dimension, declared)


def rubric_checks(rubric) -> list:
    """The rubric's checks in the shape every reader assumes: objects with a
    string id, type and dimension and an object target.

    A check that is not an object, or whose target is not an object, cannot be
    read; it is skipped and logged by id, and the walk goes on with the others.
    One such check used to raise inside the walk, and the guard's catch-all then
    gave up on the whole rubric: no candidates, no extras, whatever was drawn. A
    type or dimension that is not a string reads as "" (check_type then has
    nothing to go on but the other), and an absent target as {} (it names
    nothing). Each check is a shallow copy; the rubric is not changed.
    """
    checks = rubric.get("checks") if isinstance(rubric, dict) else None
    out = []
    for position, check in enumerate(checks if isinstance(checks, list) else [], 1):
        if not isinstance(check, dict):
            logger.warning("rubric: skipped check #%d: not an object (%r)", position, check)
            continue
        cid = str(check.get("id", "")).strip()
        target = check.get("target")
        if target is None:
            target = {}
        if not isinstance(target, dict):
            logger.warning("rubric: skipped check %r: its target is not an object (%r)",
                           cid or f"#{position}", target)
            continue
        out.append({**check, "id": cid, "type": _text(check.get("type")),
                    "dimension": _text(check.get("dimension")), "target": target})
    return out


def labels_of(item):
    """Every label a drawn element answers to, normalized: its normalized_name
    and its raw_name, whichever are non-empty."""
    return {normalize_label(item.get("normalized_name")),
            normalize_label(item.get("raw_name"))} - {""}


def drawn_label(item) -> str:
    """The name as the student drew it, stripped; "" when it has none."""
    return str(item.get("raw_name") or item.get("normalized_name") or "").strip()


class _Model:
    """Index the canonical ERD for name lookups."""

    def __init__(self, canonical):
        c = canonical or {}
        self.entities = c.get("entities") or []
        self.relationships = c.get("relationships") or []
        self.attributes = c.get("attributes") or []

    @staticmethod
    def _labels(item):
        return labels_of(item)

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


def _listed(value):
    """A target field that holds one name or a list of them -> the names given as
    strings. Anything else names nothing."""
    if isinstance(value, str):
        return [value]
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def requirements(check):
    """The names this check requires -> [(kind, name, owner_name, key_only)].

    An empty list means the check is not one this module can decide; the caller
    then leaves it with the judge. Never raises: a target, or a field of one,
    that is not the shape the rubric schema gives names nothing.
    """
    if not isinstance(check, dict):
        return []
    target = check.get("target")
    target = target if isinstance(target, dict) else {}
    ctype = check_type(check)
    out = []

    if ctype in _STRUCTURAL_TYPES:
        return out

    if ctype == "attribute_presence":
        names = _listed(target.get("attributes_required")) + _listed(target.get("attribute"))
        for name in names:
            out.append(("attribute", name, target.get("entity"), False))

    elif ctype == "key_presence":
        keys = target.get("keys_required")
        for key in keys if isinstance(keys, list) else []:
            if not isinstance(key, dict):
                continue
            owner = key.get("entity") or target.get("entity")
            for part in _split_key(key.get("primary_key")):
                out.append(("attribute", part, owner, True))
        if not out:
            for name in _listed(target.get("attribute")):
                out.append(("attribute", name, target.get("entity"), True))
        # A key check that lists attributes beside its keys asks for those too: in
        # the attributes dimension (the stored q20/q40 shape) each one was
        # required until the declared type began to win over the dimension. A name
        # that is already one of its key parts is required once, as the key.
        entity = target.get("entity")
        key_parts = {(normalize_label(req[1]), normalize_label(req[2])) for req in out}
        for name in _listed(target.get("attributes_required")) + _listed(target.get("attribute")):
            if (normalize_label(name), normalize_label(entity)) not in key_parts:
                out.append(("attribute", name, entity, False))

    elif ctype == "relationship_attribute_presence":
        for name in _listed(target.get("relationship_attributes_required")):
            out.append(("rel_attribute", name, target.get("relationship"), False))

    elif ctype == "entity_presence":
        names = _listed(target.get("entities")) + _listed(target.get("entity"))
        for name in names:
            out.append(("entity", name, None, False))

    elif ctype == "relationship_presence":
        names = (_listed(target.get("relationships_required"))
                 + _listed(target.get("relationship")))
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
    return drawn_label(item)


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
    # A check this pass cannot read keeps the judge's verdict; the others are
    # still decided (rubric_checks skips it instead of raising mid-walk).
    checks = rubric_checks(rubric)
    model = _Model(canonical)
    judge = dict(judge_result or {})
    # Ids are compared stripped, as scoring.compute_grade compares them.
    by_id = {str(j.get("id")).strip(): dict(j) for j in judge.get("checks") or []}

    for rc in checks:
        if not is_naming_check(rc):
            continue
        cid = rc["id"]
        jc = by_id.get(cid)
        if jc is None or jc.get("status") not in {"fail", "partial"}:
            continue        # only ever an upgrade
        if jc.get("decided_by") == "deterministic":
            continue        # a computed verdict is final: relationships match here by
                            # label, and "for" on another diamond is not this one drawn
        reqs = requirements(rc)
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

    judge["checks"] = [by_id.get(str(j.get("id")).strip(), j) for j in judge.get("checks") or []]
    return judge
