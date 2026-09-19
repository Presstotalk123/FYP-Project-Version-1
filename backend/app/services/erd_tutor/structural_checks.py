"""Deterministic verdicts for the three "how is it drawn" rubric checks.

WHY THIS EXISTS
weak_entity_correct, identifying_relationship_correct and
hierarchy_supertype_subtype_correct are lookups in the canonical model: is the
entity's entity_kind "weak", is the relationship's relationship_kind
"identifying", does a specialization join the two entities. The judge LLM was
asked to do them anyway, and measured on one question (3 weak entities, 6
identifying relationships, 2 ISA links) it failed a drawn SCHOLAR-AUTHOR
hierarchy as "unclear or unknown" in 2 of 9 gradings - while the canonical
model held both specializations in every run. Same defect, same cure, as the
cardinality pass in ``deterministic_checks``: the comparison is mechanical, so
it is done in Python.

POLICY (decide only what is definite; everything else stays with the judge)
  weak_entity_correct
    * the entity is drawn, entity_kind "weak"      -> pass
    * drawn, entity_kind "strong", no equivalences -> fail
  identifying_relationship_correct (matched by PARTICIPANTS - double diamonds
  are often unlabelled and the rubric's relationship name is the generator's)
    * a relationship joins them, kind "identifying"         -> pass
    * one joins them, all "normal", no equivalences         -> partial when the
      check says partial_allowed (the generator now gives a double diamond this
      ONE check and no relationship_presence check, so drawn-but-single is where
      the presence marks went), otherwise fail
    * both are drawn, NOTHING joins them, no equivalences   -> missing_policy
  relationship_presence (only when the target names two participants)
    * both are drawn, nothing joins them - no relationship, no ISA hierarchy,
      no common neighbour entity - and no equivalences      -> missing_policy
    Measured, 4 of 4 gradings: with the AUTHORING-ARTICLE diamond left out the
    judge passed both checks for it, because other double diamonds labelled
    "for" exist. Presence of the RIGHT relationship (label, meaning) is still
    a naming question and stays with the judge and ``name_matching``.
  hierarchy_supertype_subtype_correct (target.entities = [supertype, subtype...])
    * specializations give every subtype that supertype     -> pass
    * no specialization joins the supertype to any of them,
      in either direction, no equivalences                  -> fail
  Left to the judge: a kind of "unknown" (unclear_evidence_policy is its call),
  a name that does not resolve (it may be a synonym), a hierarchy drawn in the
  other direction or only partly, two entities joined only through a common
  neighbour (the associative pattern, which stored rubrics accept without
  listing it), and a non-match on a check that lists equivalence_options.
Every check decided here is stamped decided_by="deterministic", and
``name_matching`` leaves a stamped verdict alone: it matches relationships by
label, and a label shared with another diamond must not undo "not drawn".
"""

import logging

from app.services.erd_tutor.name_matching import flag, normalize_label

logger = logging.getLogger(__name__)


class _Model:
    """Index the canonical ERD for kind and hierarchy lookups."""

    def __init__(self, canonical):
        c = canonical or {}
        self.entities = c.get("entities") or []
        self.relationships = c.get("relationships") or []
        self.specializations = c.get("specializations") or []

    def entities_named(self, name):
        target = normalize_label(name)
        if not target:
            return []
        return [e for e in self.entities
                if target in {normalize_label(e.get("normalized_name")),
                              normalize_label(e.get("raw_name"))}]

    def ids(self, name):
        return [e.get("id") for e in self.entities_named(name)]

    def rels_between(self, ids_a, ids_b):
        out = []
        for r in self.relationships:
            ps = r.get("participant_entity_ids") or []
            if any(a in ps for a in ids_a) and any(b in ps for b in ids_b):
                out.append(r)
        return out

    def share_a_neighbour(self, ids_a, ids_b):
        """An entity X with rel(A,X) and rel(B,X): the associative pattern."""
        def neighbours(ids):
            return {p for r in self.relationships
                    for p in (r.get("participant_entity_ids") or [])
                    if p not in ids and any(i in (r.get("participant_entity_ids") or []) for i in ids)}
        return bool(neighbours(ids_a) & neighbours(ids_b))

    def is_subtype(self, sup_ids, sub_ids):
        return any(s.get("supertype_entity_id") in sup_ids
                   and any(x in sub_ids for x in s.get("subtype_entity_ids") or [])
                   for s in self.specializations)


def _drawn(item):
    return (item.get("raw_name") or item.get("normalized_name") or "").strip()


def _missing(policy, names):
    status = "not_applicable" if str((policy or {}).get("missing_policy")) == "not_applicable" else "fail"
    return (status, f"No relationship joins {names[0]} and {names[1]} in the diagram.")


def _weak_entity(model, target, has_equiv, policy):
    names = [target.get("entity")] if target.get("entity") else list(target.get("entities") or [])
    if len(names) != 1:
        return None
    found = model.entities_named(names[0])
    kinds = {e.get("entity_kind") for e in found}
    if "weak" in kinds:
        weak = next(e for e in found if e.get("entity_kind") == "weak")
        return ("pass", f"{_drawn(weak)} is drawn as a weak entity (double border).")
    if found and kinds == {"strong"} and not has_equiv:
        return ("fail", f"{_drawn(found[0])} is drawn with a single border, so it is a "
                        f"strong entity, not a weak entity (double rectangle).")
    return None


def _identifying_relationship(model, target, has_equiv, policy):
    names = list(target.get("participants") or [])
    if len(names) != 2:
        return None
    ids_a, ids_b = model.ids(names[0]), model.ids(names[1])
    if not ids_a or not ids_b:
        return None
    rels = model.rels_between(ids_a, ids_b)
    kinds = {r.get("relationship_kind") for r in rels}
    pair = f"{names[0]}-{names[1]}"
    if "identifying" in kinds:
        return ("pass", f"The {pair} relationship is drawn as an identifying "
                        f"relationship (double diamond).")
    if rels and kinds == {"normal"} and not has_equiv:
        if flag(policy, "partial_allowed"):
            return ("partial", f"The {pair} relationship is drawn, but as a single diamond, "
                               f"not an identifying relationship (double diamond).")
        return ("fail", f"The {pair} relationship is drawn as a single diamond, not an "
                        f"identifying relationship (double diamond).")
    if not rels and not has_equiv:
        return _missing(policy, names)
    return None


def _relationship_presence(model, target, has_equiv, policy):
    names = list(target.get("participants") or [])
    if len(names) != 2 or has_equiv:
        return None
    ids_a, ids_b = model.ids(names[0]), model.ids(names[1])
    if not ids_a or not ids_b or model.rels_between(ids_a, ids_b):
        return None
    # Older rubrics write an ISA link as a relationship, and accept an M:N drawn
    # through an associative entity without listing the equivalence.
    if (model.is_subtype(ids_a, ids_b) or model.is_subtype(ids_b, ids_a)
            or model.share_a_neighbour(ids_a, ids_b)):
        return None
    return _missing(policy, names)


def _hierarchy(model, target, has_equiv, policy):
    names = list(target.get("entities") or [])
    if len(names) < 2:
        return None
    sup_ids = model.ids(names[0])
    subs = [(name, model.ids(name)) for name in names[1:]]
    if not sup_ids or not all(ids for _, ids in subs):
        return None
    linked = [model.is_subtype(sup_ids, ids) for _, ids in subs]
    sub_names = ", ".join(name for name, _ in subs)
    if all(linked):
        return ("pass", f"{sub_names} drawn as subtype(s) of {names[0]} in an ISA hierarchy.")
    reverse = any(model.is_subtype(ids, sup_ids) for _, ids in subs)
    if not any(linked) and not reverse and not has_equiv:
        return ("fail", f"No ISA hierarchy (triangle) joins {names[0]} and {sub_names}.")
    return None


_DECIDERS = {
    "weak_entity_correct": _weak_entity,
    "identifying_relationship_correct": _identifying_relationship,
    "hierarchy_supertype_subtype_correct": _hierarchy,
    "relationship_presence": _relationship_presence,
}


def apply_structural_overrides(judge_result, rubric, canonical):
    """Return judge_result with the structural checks decided from the canonical
    model where that is definite. Never raises - any surprise defers to the judge."""
    try:
        return _apply(judge_result, rubric, canonical)
    except Exception:
        logger.exception("structural_checks: falling back to judge verdicts")
        return judge_result


def _apply(judge_result, rubric, canonical):
    checks = (rubric or {}).get("checks") or []
    model = _Model(canonical)
    judge = dict(judge_result or {})
    by_id = {str(j.get("id")): dict(j) for j in judge.get("checks") or []}

    for rc in checks:
        decide = _DECIDERS.get(str(rc.get("type") or ""))
        jc = by_id.get(str(rc.get("id")))
        if decide is None or jc is None:
            continue
        verdict = decide(model, rc.get("target") or {}, bool(rc.get("equivalence_options")),
                         rc.get("decision_policy"))
        if verdict is None:
            continue
        jc["status"], jc["brief_reason"] = verdict
        jc["decided_by"] = "deterministic"
        by_id[str(rc.get("id"))] = jc

    judge["checks"] = [by_id.get(str(j.get("id")), j) for j in judge.get("checks") or []]
    return judge
