"""Check wording for a new rubric: no shape's name reads as a requirement.

WHY
Staff read "A relationship starts connects USER and CONVERSATION" as "the
student must write starts". A relationship's name is never graded - it is the
relationship joining its entities (structural_checks) - so its check names
only those entities. An entity, attribute or key check names the model
answer's label plainly ("USER is present as an entity"); staff struck an "(or
a similar name)" suffix from that wording. Accepting a similar name is the
decision_policy's job (semantic_alias_allowed, the judge's rule 14c), not the
text's. The generator words these checks freely, so the wording is set here
rather than asked for.

WHAT IS LEFT AS WRITTEN
A check whose policy fixes the exact name (exact_name_required - the problem
statement told students to use that name), a check that lacks the names its
wording needs, and every check on how a thing is drawn or numbered.
Create mode only (runner.py): saved rubrics keep their text.
"""

from app.services.erd_tutor.name_matching import check_type, flag, normalize_label


def _names(value):
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [v.strip() for v in value if isinstance(v, str) and v.strip()]
    return []


def _one(*values):
    """The single name the fields give, or None when they give none or several."""
    names = []
    for value in values:
        for name in _names(value):
            if normalize_label(name) not in {normalize_label(n) for n in names}:
                names.append(name)
    return names[0] if len(names) == 1 else None


def _joined(names):
    if len(names) == 2 and normalize_label(names[0]) == normalize_label(names[1]):
        return f"{names[0]} to itself"
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _wording(check):
    """(pass_criteria, fail_reason_template) for a check this module words, else None."""
    target = check.get("target") or {}
    ctype = check_type(check)
    if ctype == "relationship_presence":
        participants = _names(target.get("participants"))
        if len(participants) < 2:
            return None
        joined = _joined(participants)
        return (f"A relationship connects {joined}", f"No relationship connects {joined}.")

    if flag(check.get("decision_policy"), "exact_name_required"):
        return None
    if ctype == "entity_presence":
        entity = _one(target.get("entity"), target.get("entities"))
        if entity:
            return (f"{entity} is present as an entity", f"No entity named {entity} is drawn.")
    elif ctype == "attribute_presence":
        entity = _one(target.get("entity"))
        attribute = _one(target.get("attribute"), target.get("attributes_required"))
        if entity and attribute:
            return (f"{entity} has an attribute {attribute}", f"{entity} has no attribute {attribute}.")
    elif ctype == "key_presence":
        keys = [k for k in (target.get("keys_required") or []) if isinstance(k, dict)]
        entity = _one(target.get("entity"), [k.get("entity") for k in keys])
        key = _one(target.get("attribute"), [k.get("primary_key") for k in keys])
        if entity and key:
            return (f"{entity} has the key {key} underlined", f"{entity} has no underlined key {key}.")
    elif ctype == "relationship_attribute_presence":
        participants = _names(target.get("participants"))
        attribute = _one(target.get("attribute"), target.get("relationship_attributes_required"))
        if len(participants) >= 2 and attribute:
            joined = _joined(participants)
            return (f"The relationship connecting {joined} has an attribute {attribute}",
                    f"The relationship connecting {joined} has no attribute {attribute}.")
    return None


def standardise_wording(rubric):
    """Reword the naming checks of a freshly generated rubric (see the module
    docstring). Mutates ``rubric`` (a rubric_json dict)."""
    for check in (rubric or {}).get("checks") or []:
        if not isinstance(check, dict):
            continue
        wording = _wording(check)
        if wording:
            check["pass_criteria"], check["fail_reason_template"] = wording
