"""Guard for the extra elements the judge reports.

WHY THIS EXISTS
The grader is additive, so a drawn element no check asks for costs the student
nothing, and a wrong diagram with every required element scores 100%. The judge
now lists those elements (``extras``) and scoring takes points off for each one.
That reverses the usual risk. A wrong verdict on a check meets the deterministic
passes that run after the judge; a wrong ENTRY here takes points away and nothing
downstream looks at it. An LLM can list an id that was never drawn, name an
element a check plainly requires, or charge one element twice, so those mistakes
are caught here, before anything is priced.

WHAT IS DECIDED HERE
Existence and counts, which are mechanical:
  * the id is a drawn element of the canonical model, of the kind the judge said
  * the rubric checks that kind of element or mark at all: one with no scoring
    check of a kind never charges it (chargeable_kinds, MARK_CHECK_TYPES)
  * no rubric check requires it - or the student drew more copies of a required
    label than the rubric asks for, and only the surplus copies can be extras.
    A relationship is also required by its participants: a diamond joining the
    two entities a check names, labelled or not (an identifying diamond usually
    is not), counts as that check's relationship, and so does an associative
    entity drawn between them in its place, with its two relationships (_bridged)
  * a mark extra (key, weak, ...) sits on an element that is drawn with that mark
    and that no check asks to see marked; a hierarchy mark sits on the hierarchy
  * no element is charged twice
Every rubric check that can be read is used; one that cannot is skipped
(name_matching.rubric_checks), so a malformed check never switches the guard off.

WHAT THE JUDGE CANNOT SKIP
The judge only reports the extras it notices, and a missed extra costs nothing.
unaccounted_elements runs this same guard over every drawn entity, relationship
and attribute before the judge does, which leaves the elements no check
accounts for. The judge is handed them as candidates it must rule on, and one it
does not rule on is treated as an extra (scoring.compute_grade). Ruling on a
candidate means listing the element as an extra under the kind it is drawn as, or
accounting for it; for a mark candidate, listing or accounting for that mark. An
entry that only names a mark on an element, or that gives it the wrong kind (the
guard drops that), does not count, and neither does accounting for an element the
same result lists as an extra (rulings_on_candidates, unruled_candidates).

WHAT STAYS WITH THE JUDGE
Meaning. Whether "client" is the required "customer", whether a box is the
associative entity of an M:N, whether an attribute belongs to the entity a check
names: the judge decides, and an entry this module cannot refute is kept. The one
place it drops on doubt is an attribute whose owner cannot be located while its
label is required somewhere: no deduction on a guess.
"""

import itertools
import json
import logging
from collections import Counter, defaultdict
from typing import NamedTuple

from app.services.erd_tutor.name_matching import (
    check_type, drawn_label, labels_of, normalize_label, requirements, rubric_checks,
)

logger = logging.getLogger(__name__)

_EXTRA_KINDS = {"entity", "relationship", "attribute", "mark", "line"}
_MARK_KINDS = {"key", "weak", "identifying", "hierarchy", "cardinality"}
# A "line" is a bare line: one that joins two entity boxes with no diamond
# (drawio_parser; carried onto the canonical model by carry_bare_lines). The
# first three collections are the elements the candidate walk covers.
_COLLECTIONS = (("entity", "entities"), ("relationship", "relationships"),
                ("attribute", "attributes"), ("specialization", "specializations"),
                ("line", "bare_lines"))

# Checks that ask for a relationship between named participants, and checks that
# only presuppose one (they name endpoints on a relationship that must exist).
_PRESENCE_TYPES = {"relationship_presence", "identifying_relationship_correct"}
_ENDPOINT_TYPES = {"integrity_constraint_match", "cardinality_match",
                   "relationship_endpoints_match"}
# Checks that ask for a cardinality mark on a relationship.
_CARDINALITY_TYPES = _ENDPOINT_TYPES | {"participation_match"}

# The check types (check_type) each kind of extra mirrors: scoring prices an
# extra from the rubric's scoring checks of these types. A rubric with no
# scoring check of an element kind's types never checks that kind, and an
# element of it is never charged (chargeable_kinds); an identifying relationship
# is a relationship, so it is in that pool too.
ELEMENT_CHECK_TYPES = {"entity": {"entity_presence"},
                       "relationship": {"relationship_presence",
                                        "identifying_relationship_correct"},
                       "attribute": {"attribute_presence", "relationship_attribute_presence"},
                       # A bare line stands where a relationship would, and costs one.
                       "line": {"relationship_presence", "identifying_relationship_correct"}}
# The same for marks. A rubric with none of a mark's types does not look at that
# mark at all.
MARK_CHECK_TYPES = {"key": {"key_presence"}, "weak": {"weak_entity_correct"},
                    "identifying": {"identifying_relationship_correct"},
                    "hierarchy": {"hierarchy_supertype_subtype_correct"},
                    "cardinality": _CARDINALITY_TYPES}

# attribute_kind values that say the attribute is drawn WITHOUT a key underline.
# "unknown" (and an absent kind) is not here: the model cannot refute the judge.
_NOT_KEY = {"normal", "multivalued", "derived", "composite_part"}

# What raw_marker holds at a line end where nothing is drawn: derive() stores the
# text marker, else the cue, and "no_arrow_visible" and "unknown" are cues that
# say there is no mark; description_claims writes "(from description)" for a value
# the student gave in prose. A relationship with nothing else at its ends shows
# no cardinality label, so none can be extra.
_NO_MARK = {"", "no_arrow_visible", "unknown", "(from description)"}


def _as_dict(x):
    if isinstance(x, dict):
        return x
    if isinstance(x, str) and x.strip():
        try:
            parsed = json.loads(x)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _dicts(x):
    return [i for i in x if isinstance(i, dict)] if isinstance(x, list) else []


def _names(value):
    """A target field that holds one name or a list of them -> the non-empty strings."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, str) and normalize_label(v)]


def _pair_key(names):
    """The sorted unique labels of the entities a check lists as the participants
    of one relationship, or None when it lists fewer than two. A repeated entity
    (a recursive relationship: Employee, Employee) gives a one-label key."""
    labels = [lab for lab in (normalize_label(n) for n in names) if lab]
    return tuple(sorted(set(labels))) if len(labels) >= 2 else None


def _drawn_pair_keys(relationship, by_id):
    """Every key a drawn relationship can answer to, from the entities it joins.

    An entity answers to several labels (labels_of), so the keys are one label
    per participant in every combination. An id that does not resolve to an
    entity is skipped. A one-entity key is built only for a true recursive
    relationship, every id of which points at the same entity: a binary
    relationship with one dangling id must not compete with a required
    recursive one.
    """
    ids = relationship.get("participant_entity_ids")
    resolved, dangling = [], False
    for eid in ids if isinstance(ids, list) else []:
        key = str(eid).strip()
        found = by_id.get(key)
        if found and found[0] == "entity" and labels_of(found[1]):
            resolved.append((key, sorted(labels_of(found[1]))))
        else:
            dangling = True
    if len({key for key, _ in resolved}) == 1:
        return set() if dangling else {(lab,) for lab in resolved[0][1]}
    if not resolved:
        return set()
    return {tuple(sorted(set(choice)))
            for choice in itertools.product(*(labels for _, labels in resolved))}


def _index_canonical(canonical):
    """id -> (collection, item) over every drawn element of the canonical model."""
    out = {}
    for collection, key in _COLLECTIONS:
        for item in _dicts(canonical.get(key)):
            iid = str(item.get("id", "")).strip()
            if iid:
                out[iid] = (collection, item)
    return out


def _required_counts(checks):
    """(collection, label, owner) -> how many copies the checks ask for (the
    rubric's readable checks: rubric_checks).

    Counts distinct ELEMENTS, not checks: a presence check and a weak-entity
    check on Dependent ask for one Dependent, an attribute check and a key check
    on customer_id for one customer_id. owner is "" except for attributes.
      * entity: 1 whenever any check names it. Entity names are unique in an ERD,
        so a second drawn copy is always an extra.
      * attribute, per (label, owner): 1.
      * relationship, per label: the larger of the number of distinct participant
        sets among the checks that name it with participants (two "has" checks on
        different pairs ask for two) and the number of relationship_presence
        checks naming it (two "has" checks, one with a pair and one without, ask
        for two); at least 1.
      * ("relationship_participants", labels, ""): the relationship between those
        entities, however it is labelled. The number of distinct labels among the
        presence-level checks for that set (Employee-Project as "works_on" and
        as "manages" is two); at least 1. Unlabelled diamonds, which is how an
        identifying relationship is usually drawn, are protected through this.
    """
    entities, attributes, rel_named = set(), set(), set()
    rel_pairs, rel_presence = defaultdict(set), Counter()
    pair_labels, pair_named = defaultdict(set), set()

    for rc in checks:
        target = rc["target"]
        ctype = check_type(rc)
        rel_labels = {normalize_label(n) for n in _names(target.get("relationship"))
                      + _names(target.get("relationships_required"))}

        for kind, name, owner, _key_only in requirements(rc):
            if kind in ("attribute", "rel_attribute"):
                owner_label = normalize_label(owner)
                attributes.add((normalize_label(name), owner_label))
                if owner_label:
                    (rel_labels if kind == "rel_attribute" else entities).add(owner_label)
            elif kind == "entity":
                entities.add(normalize_label(name))
            else:
                rel_labels.add(normalize_label(name))

        # The entities a check names, wherever it names them: its target, a
        # participant list, a cardinality endpoint, a key's owner.
        endpoint_names = [n for ep in _dicts(target.get("endpoints")) for n in _names(ep.get("entity"))]
        entities.update(normalize_label(n) for n in (
            _names(target.get("entity")) + _names(target.get("entities"))
            + _names(target.get("participants")) + endpoint_names
            + [n for k in _dicts(target.get("keys_required")) for n in _names(k.get("entity"))]))

        # An identifying diamond is usually unlabelled, so a check names it by the
        # entities it joins; a drawn relationship can match on those too.
        pairs = {_pair_key(_names(target.get("participants")))}
        if ctype in _ENDPOINT_TYPES:
            pairs.add(_pair_key(endpoint_names))
        pairs.discard(None)

        rel_labels.discard("")
        rel_named |= rel_labels
        for label in rel_labels:
            rel_pairs[label] |= pairs
            if ctype == "relationship_presence":
                rel_presence[label] += 1
        pair_named |= pairs
        if ctype in _PRESENCE_TYPES:
            for pair in pairs:
                pair_labels[pair] |= rel_labels

    required = Counter()
    for label in entities - {""}:
        required[("entity", label, "")] = 1
    for label, owner_label in attributes:
        if label:
            required[("attribute", label, owner_label)] = 1
    for label in rel_named:
        required[("relationship", label, "")] = max(len(rel_pairs[label]), rel_presence[label], 1)
    for pair in pair_named:
        required[("relationship_participants", pair, "")] = max(1, len(pair_labels.get(pair, ())))
    return required


def _bridged(required, by_id):
    """-> (required, halves): the counts with each associative bridge added.

    A pair of entities the rubric asks to be related (a key
    ("relationship_participants", (a, b), ""), from a presence, identifying,
    cardinality, endpoints or integrity check) that no drawn relationship joins
    directly may be drawn through an associative entity X: one relationship
    joining A and X, another joining X and B. deterministic_checks reads the
    pair's cardinality from exactly those two (_Model.bridge, the same rule:
    the first such X), so X and the two relationships are what the student drew
    for the pair. Each counts as required once, unless the rubric already asks
    for it: X by its label, each relationship by the pair it joins, so a second
    copy of either is still a surplus. halves maps each bridged pair to the pair
    keys of its two relationships, so that the marks the rubric asks of the pair
    are asked of them (_rules).
    """
    required = Counter(required)
    halves = {}
    entities = {eid: item for eid, (c, item) in by_id.items() if c == "entity"}
    joins = [[p for p in _participant_ids(item) if p in entities]
             for c, item in by_id.values() if c == "relationship"]

    def ensure(keys):
        if not any(required[k] > 0 for k in keys):
            required[keys[0]] = 1

    pairs = sorted(k[1] for k, n in required.items()
                   if k[0] == "relationship_participants" and n > 0 and len(k[1]) == 2)
    for a, b in pairs:
        ids_a = {eid for eid, item in entities.items() if a in labels_of(item)}
        ids_b = {eid for eid, item in entities.items() if b in labels_of(item)}
        if not ids_a or not ids_b or any(ids_a & set(ps) and ids_b & set(ps) for ps in joins):
            continue        # not drawn, or joined directly
        x = _bridge_entity(ids_a, ids_b, joins)
        x_labels = sorted(labels_of(entities[x])) if x is not None else []
        if not x_labels:
            continue
        ensure([("entity", lab, "") for lab in x_labels])
        keys = set()
        for end in (a, b):
            options = [("relationship_participants", tuple(sorted({end, lab})), "")
                       for lab in x_labels]
            ensure(options)
            keys |= {k[1] for k in options}
        halves[(a, b)] = keys
    return required, halves


def _bridge_entity(ids_a, ids_b, joins):
    """The first entity joined to A by one relationship and to B by another
    (joins: the entity ids of each drawn relationship), as
    deterministic_checks._Model.bridge finds it; None when there is none."""
    def neighbours(ids):
        out = []
        for ps in joins:
            if any(p in ids for p in ps):
                out += [p for p in ps if p not in ids and p not in out]
        return out

    beside_b = set(neighbours(ids_b))
    return next((x for x in neighbours(ids_a) if x in beside_b), None)


class _Limit(NamedTuple):
    """One way the rubric names a drawn element, and how many copies it allows."""
    group: tuple        # keys the copies that share this allowance
    allowed: int        # how many drawn copies exceed the rubric's count
    reason: str
    required: int       # how many copies the rubric asks for
    peers: tuple        # the ids of the drawn copies that share it
    label: str          # the name as drawn, for a candidate's "why"


def _drawn_name(normalized, collection, by_id):
    """The first drawn element of this kind that answers to a normalized label,
    as the student wrote it."""
    return next((drawn_label(other) for c, other in by_id.values()
                 if c == collection and normalized in labels_of(other)), normalized)


def _owner_labels(attribute, by_id):
    owner = by_id.get(str(attribute.get("owner_id") or "").strip())
    return labels_of(owner[1]) if owner else set()


def _allowance(collection, item, by_id, required):
    """-> (limits, why) for an entity, relationship or attribute extra.

    limits is a list of _Limit, one per way the rubric names the element; empty
    when no check does (nothing limits it). allowed is how many drawn copies
    exceed the rubric's count, and group keys the copies that share that
    allowance. A relationship can be named by its label, by the entities it
    joins, or both; each is its own limit. An attribute asked for on an entity by
    name is counted across every copy of that entity that answers to the name, so
    a "date" on both of two Order boxes is two dates, while a "name" on one and an
    "email" on the other are one each. why is set when the element is dropped
    whatever the count.

    The copies (peers) of a required name are the drawn elements that answer to
    THAT name, not every element that shares some label with this one: Phone and
    Mobile, both normalized to phone_number, are not two copies of a required
    "phone", and a Client beside a Customer normalized to client is not a second
    Customer.
    """
    labels = labels_of(item)
    limits = []
    if collection in ("entity", "relationship"):
        matching = [(collection, lab, "") for lab in sorted(labels)
                    if required[(collection, lab, "")] > 0]
        if matching:
            wanted = {lab for _c, lab, _o in matching}
            peers = tuple(i for i, (c, other) in by_id.items()
                          if c == collection and wanted & labels_of(other))
            asked = sum(required[k] for k in matching)
            limits.append(_Limit((collection, matching[0][1], None),
                                 max(0, len(peers) - asked),
                                 "a rubric check requires it", asked, peers,
                                 _drawn_name(matching[0][1], collection, by_id)))
        if collection == "relationship":
            for pair in sorted(_drawn_pair_keys(item, by_id)):
                count = required[("relationship_participants", pair, "")]
                if count > 0:
                    peers = tuple(i for i, (c, other) in by_id.items()
                                  if c == "relationship" and pair in _drawn_pair_keys(other, by_id))
                    limits.append(_Limit(("relationship_participants", pair, None),
                                         max(0, len(peers) - count),
                                         "a rubric check requires a relationship between these "
                                         "participants", count, peers,
                                         " \u2013 ".join(_drawn_name(lab, "entity", by_id)
                                                        for lab in pair)))
        return limits, None

    owner_id = str(item.get("owner_id") or "").strip()
    owner_labels = _owner_labels(item, by_id)
    if not any(k[0] == "attribute" and k[1] in labels and n > 0 for k, n in required.items()):
        return [], None
    if not owner_labels:
        return [], "its owner cannot be located and its label is required"
    matching = [("attribute", lab, o) for lab in sorted(labels)
                for o in sorted(owner_labels | {""})
                if required[("attribute", lab, o)] > 0]
    if not matching:
        return [], None         # required, but on another owner
    asked = sum(required[k] for k in matching)
    wanted = {k[1] for k in matching}
    named = [k for k in matching if k[2]]
    if named:
        # Asked for on an owner by its name: counted across the copies of that owner.
        lab, owner_label = named[0][1], named[0][2]
        group = ("attribute", lab, owner_label)
        peers = tuple(i for i, (c, other) in by_id.items()
                      if c == "attribute" and wanted & labels_of(other)
                      and owner_label in _owner_labels(other, by_id))
    else:
        lab = matching[0][1]
        group = ("attribute", lab, owner_id)
        peers = tuple(i for i, (c, other) in by_id.items()
                      if c == "attribute"
                      and str(other.get("owner_id") or "").strip() == owner_id
                      and wanted & labels_of(other))
    return [_Limit(group, max(0, len(peers) - asked), "a rubric check requires it", asked,
                   peers, _drawn_name(lab, "attribute", by_id))], None


def _mark_problem(mark, collection, item, rules):
    """Why the carrier is not drawn with this mark, or None. An "unknown" or
    absent kind passes: the model cannot refute the judge there. A hierarchy
    mark sits on a specialization (_confirm has already read one keyed on an
    entity as the hierarchy that entity is in)."""
    if mark == "key":
        if collection != "attribute":
            return f"a {collection} cannot carry a key underline"
        if item.get("attribute_kind") in _NOT_KEY:
            return f"it is drawn as a {item.get('attribute_kind')} attribute"
    elif mark == "weak":
        if collection != "entity":
            return f"a {collection} cannot be a weak entity"
        if item.get("entity_kind") == "strong":
            return "it is drawn as a strong entity"
    elif mark == "identifying":
        if collection != "relationship":
            return f"a {collection} cannot be an identifying relationship"
        if item.get("relationship_kind") == "normal":
            return "it is drawn as a normal relationship"
    elif mark == "hierarchy":
        if collection != "specialization":
            return f"a {collection} is not a drawn hierarchy"
    elif mark == "cardinality":
        if collection != "relationship":
            return f"a {collection} carries no cardinality mark"
        if str(item.get("id", "")).strip() not in rules.marked:
            return "no cardinality marker is drawn on it"
    return None


def _required_marks(checks):
    """What the rubric's (readable) checks ask to see marked, for the mark extras.

    key: (attribute label, owner label) pairs from the key checks.
    weak: labels of the entities a weak_entity_correct check names.
    identifying / cardinality: the participant keys (the pair of entities) each
    check on that mark names; the relationship label only for a check that names
    no pair. A check about the "has" between SUBMISSION and CONFERENCE asks for
    the mark on that relationship, not on every other "has" in the diagram.
    hierarchy: one label set per hierarchy check.
    """
    marks = {"key": set(), "weak": set(), "hierarchy": [],
             "identifying_labels": set(), "identifying_pairs": set(),
             "cardinality_labels": set(), "cardinality_pairs": set()}

    def ask(mark, pairs, labels):
        """One check on this mark: it protects the pairs it names, else its labels."""
        if pairs:
            marks[f"{mark}_pairs"] |= pairs
        else:
            marks[f"{mark}_labels"] |= labels

    for rc in checks:
        target = rc["target"]
        ctype = check_type(rc)
        for kind, name, owner, key_only in requirements(rc):
            if key_only and kind == "attribute":
                marks["key"].add((normalize_label(name), normalize_label(owner)))
        relationship = {normalize_label(n) for n in _names(target.get("relationship"))} - {""}
        participants = _pair_key(_names(target.get("participants")))
        if ctype == "weak_entity_correct":
            names = _names(target.get("entity")) or _names(target.get("entities"))
            marks["weak"] |= {normalize_label(n) for n in names} - {""}
        elif ctype == "identifying_relationship_correct":
            ask("identifying", {participants} - {None}, relationship)
        elif ctype == "hierarchy_supertype_subtype_correct":
            marks["hierarchy"].append({normalize_label(n) for n in _names(target.get("entities"))}
                                      - {""})
        elif ctype in _CARDINALITY_TYPES:
            endpoints = _pair_key([n for ep in _dicts(target.get("endpoints"))
                                   for n in _names(ep.get("entity"))])
            ask("cardinality", {participants, endpoints} - {None}, relationship)
    return marks


def _mark_required(mark, collection, item, by_id, marks):
    """Whether a rubric check asks for this mark on this carrier, so that drawing
    it is what the student was told to do."""
    labels = labels_of(item)
    if mark == "key":
        owner = by_id.get(str(item.get("owner_id") or "").strip())
        owner_labels = labels_of(owner[1]) if owner else set()
        # No owner to compare with, or a key check that names none: the label decides.
        return any(label in labels and (not owner_label or not owner_labels
                                        or owner_label in owner_labels)
                   for label, owner_label in marks["key"])
    if mark == "weak":
        return bool(labels & marks["weak"])
    if mark == "identifying":
        return bool(labels & marks["identifying_labels"]
                    or marks["identifying_pairs"] & _drawn_pair_keys(item, by_id))
    if mark == "cardinality":
        return bool(labels & marks["cardinality_labels"]
                    or marks["cardinality_pairs"] & _drawn_pair_keys(item, by_id))
    if mark == "hierarchy":
        # Asked for when a hierarchy check names an entity of this hierarchy.
        if collection != "specialization":
            return False
        labels = set()
        for eid in _hierarchy_ids(item):
            found = by_id.get(eid)
            if found and found[0] == "entity":
                labels |= labels_of(found[1])
        return any(labels & names for names in marks["hierarchy"])
    return False


def _open_marks(rules):
    """The marks with a check that names something not drawn under any exact
    label: a weak check on an entity no box is called, a key check on an
    attribute not drawn, a double-diamond or cardinality check on a pair nothing
    joins, a hierarchy check on an entity not drawn. Such a check could mean a
    drawn element under a synonym, so the judge may account for a mark of that
    kind. A mark with every check of its kind met by name has no such reading:
    it is extra whatever the judge says, and an accounted_candidates entry does
    not rule on it (the candidate carries _sure; unruled_candidates). Measured
    on q48: Scholar drawn weak, with W1-W3 naming three other entities that are
    all drawn, was cleared by the judge in one grading of four."""
    by_id, marks = rules.by_id, rules.marks
    drawn = defaultdict(list)
    for collection, item in by_id.values():
        drawn[collection].append(item)
    entity_labels = set().union(*(labels_of(e) for e in drawn["entity"]))
    relationship_labels = set().union(*(labels_of(r) for r in drawn["relationship"]))
    pairs = set().union(*(_drawn_pair_keys(r, by_id) for r in drawn["relationship"]))

    def key_drawn(label, owner):
        return any(label in labels_of(a)
                   and (not owner or not _owner_labels(a, by_id) or owner in _owner_labels(a, by_id))
                   for a in drawn["attribute"])

    open_marks = set()
    if marks["weak"] - entity_labels:
        open_marks.add("weak")
    if any(not key_drawn(label, owner) for label, owner in marks["key"]):
        open_marks.add("key")
    for mark in ("identifying", "cardinality"):
        if marks[f"{mark}_labels"] - relationship_labels or marks[f"{mark}_pairs"] - pairs:
            open_marks.add(mark)
    if any(names - entity_labels for names in marks["hierarchy"]):
        open_marks.add("hierarchy")
    return open_marks


class _Rules(NamedTuple):
    """What the rubric asks for, read once per pass against one drawn model and
    shared by the guard (_confirm) and the candidate walk (_unaccounted)."""
    by_id: dict             # id -> (collection, item), every drawn element
    checks: list            # the readable checks (rubric_checks)
    required: Counter       # _required_counts, with the associative bridges (_bridged)
    marks: dict             # _required_marks, the bridged pairs' marks on their bridges
    scored_marks: set       # the marks the rubric checks (MARK_CHECK_TYPES)
    chargeable: set         # the element kinds it checks (ELEMENT_CHECK_TYPES)
    in_hierarchies: dict    # entity id -> the ids of the specializations it is in
    marked: set             # ids of the relationships drawn with a cardinality marker


def _rules(rubric, canonical):
    checks = rubric_checks(rubric)
    by_id = _index_canonical(canonical)
    # A relationship shows a cardinality label when a marker (or a positive cue,
    # an arrowhead) is recorded at one of its ends; _NO_MARK says nothing is drawn.
    marked = {str(c.get("relationship_id", "")).strip()
              for c in _dicts(canonical.get("cardinalities"))
              if str(c.get("raw_marker") or "").strip() not in _NO_MARK}
    scored = {check_type(rc) for rc in scoring_checks(checks)}
    in_hierarchies = defaultdict(list)
    for sid, (collection, item) in by_id.items():
        if collection == "specialization":
            for eid in dict.fromkeys(_hierarchy_ids(item)):
                in_hierarchies[eid].append(sid)
    required, halves = _bridged(_required_counts(checks), by_id)
    marks = _required_marks(checks)
    for pair, keys in halves.items():
        # The cardinality (or the double line) asked of the pair is read on its
        # bridge, so it is asked of the bridge's two relationships.
        for asked in ("identifying_pairs", "cardinality_pairs"):
            if pair in marks[asked]:
                marks[asked] |= keys
    return _Rules(by_id=by_id, checks=checks, required=required, marks=marks,
                  scored_marks={m for m, pool in MARK_CHECK_TYPES.items() if pool & scored},
                  chargeable={k for k, pool in ELEMENT_CHECK_TYPES.items() if pool & scored},
                  in_hierarchies=dict(in_hierarchies), marked=marked)


def scoring_checks(checks):
    """The checks that score: must or should, with points. checks are readable
    ones (rubric_checks)."""
    def points(rc):
        try:
            return float(rc.get("points", 0))
        except (TypeError, ValueError):
            return 0.0
    return [rc for rc in checks
            if rc.get("requirement_level") in ("must", "should") and points(rc) > 0]


def chargeable_kinds(rubric):
    """The element kinds (entity, relationship, attribute, and line, priced as a
    relationship) the rubric checks: those with at least one scoring check of a
    type in ELEMENT_CHECK_TYPES. An element of
    any other kind is never a candidate and never charged, whoever lists it. A
    rubric that never checks attributes asks nothing about them, and the
    attributes on a correct diagram are not extras."""
    scored = {check_type(rc) for rc in scoring_checks(rubric_checks(_as_dict(rubric)))}
    return {kind for kind, pool in ELEMENT_CHECK_TYPES.items() if pool & scored}


def confirm_extras(extras, rubric, canonical, quiet=False):
    """The judge's extras that survive the guard, in the judge's order.

    Never raises: a surprise confirms nothing, and no deduction is made. Every
    drop is logged, so a judge that invents extras is visible. quiet=True
    silences the per-drop warnings, for a caller that feeds the guard a list it
    built itself (unaccounted_elements) and so expects most of it to be dropped.
    A rubric check that cannot be read is skipped (rubric_checks) and the guard
    runs on the others.

    An extra of a kind the rubric has no scoring check for is dropped: an
    element kind outside chargeable_kinds, or a mark with none of its
    MARK_CHECK_TYPES. The rubric asks nothing about that kind, and there is no
    check to price it from. A hierarchy mark keyed on an entity is read as the
    one hierarchy that entity is in (dropped when it is in none, or in several).
    """
    try:
        return _confirm(extras, _rules(_as_dict(rubric), _as_dict(canonical)), quiet)
    except Exception:
        logger.exception("extras: guard failed, no extras confirmed")
        return []


def _hierarchy_of(cid, rules, warn, note):
    """The specialization a hierarchy mark keyed on entity cid means: the one
    hierarchy that entity is in. None, with the reason logged, when it is in none
    or in several (the mark does not say which)."""
    sids = rules.in_hierarchies.get(cid, [])
    if len(sids) == 1:
        note("extras: hierarchy mark on entity %r read as the hierarchy %r it is in",
             cid, sids[0])
        return sids[0]
    if sids:
        warn("extras: dropped %r (mark/hierarchy): it is in %d drawn hierarchies (%s), and "
             "the mark does not say which", cid, len(sids), ", ".join(sids))
    else:
        warn("extras: dropped %r (mark/hierarchy): it is in no drawn hierarchy", cid)
    return None


def _confirm(extras, rules, quiet=False):
    warn = (lambda *args, **kwargs: None) if quiet else logger.warning
    note = (lambda *args, **kwargs: None) if quiet else logger.info
    by_id = rules.by_id
    required, required_marks, scored_marks = rules.required, rules.marks, rules.scored_marks
    kept, seen, used = [], set(), Counter()

    for ex in extras if isinstance(extras, list) else []:
        if not isinstance(ex, dict):
            warn("extras: dropped %r: not an object", ex)
            continue
        cid = str(ex.get("canonical_id", "")).strip()
        kind = ex["kind"].strip() if isinstance(ex.get("kind"), str) else None
        mark = ex["mark"].strip() if kind == "mark" and isinstance(ex.get("mark"), str) else None
        if kind not in _EXTRA_KINDS or (kind == "mark" and mark not in _MARK_KINDS):
            warn("extras: dropped %r: invalid kind or mark (%r/%r)",
                 cid, ex.get("kind"), ex.get("mark"))
            continue
        found = by_id.get(cid)
        if found is None:
            warn("extras: dropped %r (%s/%s): not a drawn element", cid, kind, mark)
            continue
        if mark == "hierarchy" and found[0] == "entity":
            # A hierarchy is one mark however many entities it has: keyed on
            # one of them it is still that hierarchy's mark, so it is checked,
            # deduplicated and charged as the specialization.
            cid = _hierarchy_of(cid, rules, warn, note)
            if cid is None:
                continue
            found = by_id[cid]
        collection, item = found
        key = (cid, kind, mark)
        if key in seen:
            warn("extras: dropped duplicate %r (%s/%s)", cid, kind, mark)
            continue

        if kind == "mark":
            problem = _mark_problem(mark, collection, item, rules)
            if problem:
                warn("extras: dropped %r (mark/%s): %s", cid, mark, problem)
                continue
            if mark not in scored_marks:
                warn("extras: dropped %r (mark/%s): the rubric has no %s check", cid, mark, mark)
                continue
            if _mark_required(mark, collection, item, by_id, required_marks):
                warn("extras: dropped %r (mark/%s): a rubric check requires this mark",
                     cid, mark)
                continue
        else:
            if collection != kind:
                warn("extras: dropped %r: judge said %s, the model holds a %s",
                     cid, kind, collection)
                continue
            if kind not in rules.chargeable:
                warn("extras: dropped %r (%s): the rubric has no %s check", cid, kind, kind)
                continue
            # A bare line is never asked for, so it has no allowance to use up.
            limits, why = ([], None) if kind == "line" else _allowance(collection, item,
                                                                       by_id, required)
            if why:
                warn("extras: dropped %r (%s): %s", cid, kind, why)
                continue
            spent = next((lim.reason for lim in limits if used[lim.group] >= lim.allowed), None)
            if spent:
                warn("extras: dropped %r (%s): %s", cid, kind, spent)
                continue
            for lim in limits:
                used[lim.group] += 1

        seen.add(key)
        kept.append({"canonical_id": cid, "kind": kind, "mark": mark,
                     "label": (_carrier_label(collection, item, by_id)
                               or str(ex.get("label") or "").strip()
                               or " \u2013 ".join(_describe(collection, item, by_id)
                                                  .get("participants", []))),
                     "brief_reason": str(ex.get("brief_reason") or "").strip()})

    # A mark on an element that is already an extra is charged twice for the one
    # element; the element's own deduction stands. So does a hierarchy with an
    # extra entity in it: the entity is what is charged.
    charged = {k["canonical_id"] for k in kept if k["kind"] != "mark"}
    final = []
    for k in kept:
        if k["kind"] == "mark" and k["canonical_id"] in charged:
            warn("extras: dropped mark %r on %r: the element is already an extra",
                 k["mark"], k["canonical_id"])
            continue
        if k["kind"] == "mark" and k["mark"] == "hierarchy":
            extra = charged & set(_hierarchy_ids(by_id[k["canonical_id"]][1]))
            if extra:
                warn("extras: dropped mark %r on %r: %s in it is already an extra",
                     k["mark"], k["canonical_id"], ", ".join(sorted(extra)))
                continue
        final.append(k)
    return final


def unaccounted_elements(rubric, canonical):
    """The drawn entities, relationships and attributes no rubric check accounts
    for: the candidates the judge must rule on. Only of the kinds the rubric
    checks (chargeable_kinds): a rubric with no attribute check lists no
    attribute, however many are drawn.

    Each is {canonical_id, kind, label, why}, plus owner and owner_id for an
    attribute, or participants and participant_ids for a relationship (the drawn
    labels, and the ids of the entities it joins). why says what makes it a
    candidate: "no check names it"; "surplus copy: the rubric asks for N 'label',
    M are drawn" (the label as drawn); or, for an attribute the rubric asks for on
    an entity that is not drawn, "required on Customer, which is not drawn". Keys
    that start with an underscore are bookkeeping, for unruled_candidates, which
    public_candidates drops before the judge sees the list.

    After the elements come the marks (kind "mark", with the mark in "mark"): a
    mark the model shows on an element that is not a candidate itself, that no
    check asks for, and of a kind the rubric has a scoring check for. A mark on an
    extra element is never listed separately: the element's own deduction stands.
    See _mark_candidates.

    Computed by the guard's own rules, so the two cannot disagree: every drawn
    element is put to confirm_extras as if the judge had listed it, and what
    survives is what no check names by label, owner or participants (an
    associative entity standing for a required relationship, and its two
    relationships, count as named: _bridged), plus the surplus copies of a name
    the rubric asks for fewer times than it is drawn.
    Copies are counted across the copies of what they belong to (see
    _allowance), so whatever the student hung on the extra copy of an entity is
    not charged unless it duplicates what hangs on the other.

    Of two copies of a name the rubric asks for once, the guard charges the first
    it is handed, so the copy that keeps the requirement is handed last: the one
    with more connections (the attributes it owns plus the relationships it takes
    part in), so that the bare copy is the surplus and what the student wired to
    the other is not charged with it; of equally connected copies, the one drawn
    first (they are handed back to front). Elements that satisfy several
    requirements at once (a "has" between A and B is both a "has" and a
    relationship between A and B) go after the elements that satisfy one,
    whatever order they were drawn in: they use up an allowance in each group, and
    handled early they would use up the allowances of the elements that are really
    surplus. The result is in model order. Never raises; any surprise yields no
    candidates.

    Known limitation: when one check names a relationship by its label and
    another check names a different relationship between the same two entities
    only by its participants (a presence check beside an identifying one), the
    pair is counted as asked for once, so the second relationship drawn there is a
    candidate.
    """
    try:
        return _unaccounted(_as_dict(rubric), _as_dict(canonical))
    except Exception:
        logger.exception("extras: candidate enumeration failed, no candidates")
        return []


def _participant_ids(item):
    ids = item.get("participant_entity_ids")
    return [i for i in (str(x).strip() for x in ids) if i] if isinstance(ids, list) else []


def _hierarchy_ids(item):
    """The ids of the entities in a specialization: its supertype, then its subtypes."""
    subtypes = item.get("subtype_entity_ids")
    raw = [item.get("supertype_entity_id")] + (subtypes if isinstance(subtypes, list) else [])
    return [i for i in (str(x).strip() for x in raw if x is not None) if i]


def _stand_ins(collection, item, by_id, required):
    """-> (ids, group, cap, absent), or None: where an attribute or a relationship
    may be hung in place of a required entity the student did not draw under any
    name, and the labels of the required entities that are not drawn.

    The rubric asks for "name" on Customer, and the student drew no Customer but a
    Client with a name: if the judge accepts Client as the Customer, its name is
    the required one. Same for a relationship that no check names by label but
    that joins the present entity of a required pair and a stand-in for the
    absent one. ids are the stand-in entities; the copies of the element on them
    share group, and the rubric asks for cap of them: a second "name" on Client is
    not the Customer's name.
    """
    drawn = set()
    for c, other in by_id.values():
        if c == "entity":
            drawn |= labels_of(other)
    absent = {k[1] for k, n in required.items() if k[0] == "entity" and n > 0} - drawn
    if not absent:
        return None
    if collection == "attribute":
        owner_id = str(item.get("owner_id") or "").strip()
        owner = by_id.get(owner_id)
        if not owner or owner[0] != "entity":
            return None
        labels = labels_of(item)
        asked, owners = Counter(), set()
        for k, n in required.items():
            if k[0] == "attribute" and k[1] in labels and k[2] in absent and n > 0:
                asked[k[1]] += n
                owners.add(k[2])
        if not asked:
            return None
        return [owner_id], ("attribute", min(asked), owner_id), sum(asked.values()), sorted(owners)
    if collection != "relationship":
        return None
    joined = {}
    for eid in _participant_ids(item):
        found = by_id.get(eid)
        if found and found[0] == "entity" and labels_of(found[1]):
            joined[eid] = labels_of(found[1])
    ids, cap, gone = [], 0, set()
    for key, n in required.items():
        if key[0] != "relationship_participants" or n <= 0:
            continue
        pair = set(key[1])
        missing, present = pair & absent, pair - absent
        if not missing or len(joined) != len(pair):
            continue
        stand = [eid for eid, labs in joined.items() if not labs & pair]
        if len(stand) == len(missing) and all(
                any(lab in labs for labs in joined.values()) for lab in present):
            ids += [eid for eid in stand if eid not in ids]
            cap += n
            gone |= missing
    return (ids, ("relationship", tuple(sorted(joined))), cap, sorted(gone)) if ids else None


def _rubric_spellings(checks):
    """normalized label -> the entity name as the rubric writes it (the first
    spelling found), for saying what a check asks for."""
    out = {}
    for rc in checks:
        target = rc["target"]
        names = (_names(target.get("entity")) + _names(target.get("entities"))
                 + _names(target.get("participants"))
                 + [n for ep in _dicts(target.get("endpoints")) for n in _names(ep.get("entity"))]
                 + [n for k in _dicts(target.get("keys_required"))
                    for n in _names(k.get("entity"))])
        for name in names:
            out.setdefault(normalize_label(name), name.strip())
    return out


def _carrier_label(collection, item, by_id):
    """What a drawn element is called: its drawn label. A hierarchy has none, so
    it is called by its entities, supertype first ("Person \u2013 Student")."""
    if collection == "specialization":
        names = [drawn_label(by_id[i][1]) for i in _hierarchy_ids(item)
                 if i in by_id and by_id[i][0] == "entity"]
        return " \u2013 ".join(n for n in names if n)
    if collection == "line":
        # A bare line is called by the entities it joins, whatever is typed on it.
        names = [drawn_label(by_id[i][1]) for i in _participant_ids(item)
                 if i in by_id and by_id[i][0] == "entity"]
        return " \u2013 ".join(n for n in names if n)
    return drawn_label(item)


def _describe(collection, item, by_id):
    """What names a carrier besides its label: the owner of an attribute, the
    entities a relationship joins (entities only, as _drawn_pair_keys reads them),
    each as the drawn label and the id."""
    if collection == "attribute":
        owner_id = str(item.get("owner_id") or "").strip()
        owner = by_id.get(owner_id)
        return {"owner": drawn_label(owner[1]) if owner else "", "owner_id": owner_id}
    if collection in ("relationship", "line"):
        ids = [i for i in _participant_ids(item) if i in by_id and by_id[i][0] == "entity"]
        return {"participants": [lab for lab in (drawn_label(by_id[i][1]) for i in ids) if lab],
                "participant_ids": ids}
    return {}


def _open_requirements(rules):
    """The requirements (keys of _required_counts) the drawing does not meet by
    exact label: an entity no box is called, an attribute not drawn on its
    owner, a relationship label nothing carries, a pair nothing joins. Only
    these can be met by a candidate under a naming rule, so only a candidate
    that could fill one keeps the judge's say; every other element candidate
    carries _sure (_closed_for), and accounting does not rule on it. Measured
    on q48, with every attribute the rubric asks for drawn: Phone on Scholar
    and Role on the Author-Authoring "Is" were each cleared by the judge in one
    grading of three."""
    by_id, required = rules.by_id, rules.required
    drawn = defaultdict(list)
    for collection, item in by_id.values():
        drawn[collection].append(item)

    def met(key):
        collection, label, owner = key
        if collection == "entity":
            return sum(label in labels_of(e) for e in drawn["entity"])
        if collection == "attribute":
            return sum(label in labels_of(a) and (not owner or owner in _owner_labels(a, by_id))
                       for a in drawn["attribute"])
        if collection == "relationship":
            return sum(label in labels_of(r) for r in drawn["relationship"])
        return sum(label in _drawn_pair_keys(r, by_id) for r in drawn["relationship"])

    return {key for key, asked in required.items() if asked > 0 and met(key) < asked}


def _closed_for(candidate, by_id, open_keys):
    """Whether no open requirement could be met by this candidate: no open
    entity for an entity; no open relationship, by label or by pair, for a
    relationship; for an attribute, no open attribute on its owner (or on any
    owner, for a check that names none) and none of its own label anywhere (an
    attribute drawn on the wrong owner keeps the judge's say)."""
    kind = candidate["kind"]
    if kind == "entity":
        return not any(k[0] == "entity" for k in open_keys)
    if kind == "relationship":
        return not any(k[0] in ("relationship", "relationship_participants") for k in open_keys)
    owner = by_id.get(str(candidate.get("owner_id") or "").strip())
    owner_labels = labels_of(owner[1]) if owner else set()
    labels = labels_of(by_id[candidate["canonical_id"]][1])
    return not any(k[0] == "attribute" and (not k[2] or k[2] in owner_labels or k[1] in labels)
                   for k in open_keys)


def _why(limits):
    if not limits:
        return "no check names it"
    first = limits[0]
    return (f"surplus copy: the rubric asks for {first.required} '{first.label}', "
            f"{len(first.peers)} are drawn")


def _unaccounted(rubric, canonical):
    rules = _rules(rubric, canonical)
    by_id, required = rules.by_id, rules.required
    drawn = []
    for collection, key in _COLLECTIONS[:3]:
        for item in _dicts(canonical.get(key)):
            cid = str(item.get("id", "")).strip()
            if cid:
                drawn.append({"canonical_id": cid, "kind": collection,
                              "label": drawn_label(item)})

    def found_of(entry):
        found = by_id.get(entry["canonical_id"])
        return found if found and found[0] == entry["kind"] else None

    limits = {}
    for entry in drawn:
        found = found_of(entry)
        if found:
            limits[entry["canonical_id"]] = _allowance(found[0], found[1], by_id, required)[0]

    # What each element has attached: the attributes it owns, and one for every
    # place it takes in a relationship.
    attached = Counter()
    for item in _dicts(canonical.get("attributes")):
        attached[str(item.get("owner_id") or "").strip()] += 1
    for item in _dicts(canonical.get("relationships")):
        for eid in _participant_ids(item):
            attached[eid] += 1

    def walk_position(entry):
        cid = entry["canonical_id"]
        return len(limits.get(cid, ())), attached[cid]

    order = sorted(reversed(drawn), key=walk_position)
    kept = _confirm(order, rules, quiet=True)
    wanted = {(k["canonical_id"], k["kind"]): _why(limits.get(k["canonical_id"])) for k in kept}

    signature = {cid: frozenset(lim.group for lim in lims) for cid, lims in limits.items()}
    spellings = _rubric_spellings(rules.checks)
    open_keys = _open_requirements(rules)
    out, emitted = [], set()
    for entry in drawn:
        ident = (entry["canonical_id"], entry["kind"])
        if ident not in wanted or ident in emitted:
            continue
        emitted.add(ident)
        cid = entry["canonical_id"]
        item = by_id[cid][1]
        candidate = {**entry, "why": wanted[ident], **_describe(entry["kind"], item, by_id)}
        if limits.get(cid):
            candidate["_surplus"] = True
            candidate["_peers"] = tuple(other for other, sig in signature.items()
                                        if sig == signature[cid])
        else:
            # Only an element no check limits can be the stand-in's: a surplus copy
            # of a name is surplus whatever the entity it hangs on is accepted as.
            follow = _stand_ins(entry["kind"], item, by_id, required)
            if follow:
                ids, group, cap, absent = follow
                candidate["_follows"], candidate["_follow_group"], candidate["_follow_cap"] = (
                    ids, group, cap)
                if entry["kind"] == "attribute":
                    names = [spellings.get(lab, lab) for lab in absent]
                    candidate["why"] = (f"required on {' or '.join(names)}, which "
                                        f"{'is' if len(names) == 1 else 'are'} not drawn")
            elif _closed_for(candidate, by_id, open_keys):
                # Nothing it could be under a naming rule: accounting does not
                # rule on it (unruled_candidates).
                candidate["_sure"] = True
        out.append(candidate)
    try:
        marks = _mark_candidates(rules, canonical, drawn, {c["canonical_id"] for c in out})
    except Exception:
        # The elements are worth listing without the marks.
        logger.exception("extras: mark candidates failed, none listed")
        marks = []
    return out + marks


def _mark_candidates(rules, canonical, drawn, skip):
    """The marks the model shows that no check asks for, as candidates.

    The model shows a key when an attribute is drawn as a key, a weak border on
    an entity drawn weak, a double diamond on a relationship drawn identifying, a
    hierarchy for every specialization, and a cardinality label for a
    relationship with a marker (or a positive cue, an arrowhead) at any end. An
    "unknown" kind is not shown: the model cannot refute the judge there. Whether
    a check asks for the mark is _mark_required's answer, the guard's own. Only
    the kinds of mark the rubric has a scoring check for are listed
    (rules.scored_marks): a mark extra is priced from those checks, and a rubric
    with none of them asks nothing about that mark.

    A carrier that is itself a candidate (skip) has no mark candidate: its mark is
    part of the extra element, which is charged once. The same for a hierarchy
    with an extra entity in it. In model order after the elements: entities,
    relationships, attributes, then hierarchies.

    A hierarchy candidate carries _aliases: the entities that are in it and in no
    other hierarchy. A judge that keys the hierarchy mark on one of them means
    this hierarchy (the guard reads it so, _hierarchy_of), so unruled_candidates
    counts that as a ruling on it.

    A mark whose every check of its kind is met by name carries _sure
    (_open_marks): accounting does not rule on it. That includes a key
    underline: with every key check met, an underline elsewhere is extra
    (measured on q48: Comments underlined on ASSIGN_REVIEW was cleared by the
    judge in one grading of three).
    """
    scored = rules.scored_marks
    if not scored:
        return []
    by_id, required = rules.by_id, rules.marks
    open_marks = _open_marks(rules)
    out, seen = [], set()

    def add(cid, mark, collection, item, label, **bookkeeping):
        if (mark not in scored or (cid, mark) in seen
                or _mark_problem(mark, collection, item, rules)
                or _mark_required(mark, collection, item, by_id, required)):
            return
        seen.add((cid, mark))
        sure = mark not in open_marks
        out.append({"canonical_id": cid, "kind": "mark", "mark": mark, "label": label,
                    "why": "no check asks for this mark", **_describe(collection, item, by_id),
                    **({"_sure": True} if sure else {}), **bookkeeping})

    for entry in drawn:
        cid = entry["canonical_id"]
        found = by_id.get(cid)
        if cid in skip or not found or found[0] != entry["kind"]:
            continue
        collection, item = found
        if collection == "entity" and item.get("entity_kind") == "weak":
            add(cid, "weak", collection, item, entry["label"])
        elif collection == "relationship":
            if item.get("relationship_kind") == "identifying":
                add(cid, "identifying", collection, item, entry["label"])
            add(cid, "cardinality", collection, item, entry["label"])     # if marked
        elif collection == "attribute" and item.get("attribute_kind") == "key":
            add(cid, "key", collection, item, entry["label"])

    for spec in _dicts(canonical.get("specializations")):
        sid = str(spec.get("id", "")).strip()
        found = by_id.get(sid)
        if not sid or not found or found[0] != "specialization":
            continue
        ids = _hierarchy_ids(found[1])
        if any(i in skip for i in ids):
            continue
        aliases = [i for i in dict.fromkeys(ids) if i in by_id and by_id[i][0] == "entity"
                   and rules.in_hierarchies.get(i) == [sid]]
        add(sid, "hierarchy", "specialization", found[1],
            _carrier_label("specialization", found[1], by_id), _aliases=aliases)
    return out


def carry_bare_lines(observation, canonical):
    """The parser's bare lines (drawio_parser: a line that joins two entity boxes
    with no diamond), with their entity ids resolved against the canonical model,
    for normalize_node to put on it. The normalizer keeps the parser's entity
    ids; an end it renamed is matched by label, and a line with an end that
    resolves to no drawn entity is dropped, logged."""
    observation = _as_dict(observation)
    entities = {str(e.get("id", "")).strip(): e for e in _dicts(canonical.get("entities"))}
    by_label = {}
    for entity in entities.values():
        for label in labels_of(entity):
            by_label.setdefault(label, str(entity.get("id", "")).strip())
    observed = {str(e.get("id", "")).strip(): e for e in _dicts(observation.get("entities"))}

    def resolve(eid):
        if eid in entities:
            return eid
        return next((by_label[label] for label in labels_of(observed.get(eid) or {})
                     if label in by_label), None)

    out = []
    for line in _dicts(observation.get("bare_lines")):
        ends = [resolve(i) for i in _participant_ids(line)]
        if len(ends) != 2 or not all(ends):
            logger.warning("extras: bare line %r (%r) does not join two drawn entities; dropped",
                           line.get("id"), line.get("participant_entity_ids"))
            continue
        out.append({**line, "participant_entity_ids": ends})
    return out


def bare_line_extras(canonical):
    """Every bare line of the canonical model as an extra for the guard. A line
    that joins two entities with no diamond is not an ER construct and no check
    can ask for one, so it is charged outright, without a ruling from the judge,
    at the relationship price (ELEMENT_CHECK_TYPES). The guard still drops one
    whose id is not drawn, or on a rubric that checks no relationships."""
    canonical = _as_dict(canonical)
    by_id = _index_canonical(canonical)
    out = []
    for line in _dicts(canonical.get("bare_lines")):
        lid = str(line.get("id", "")).strip()
        if not lid:
            continue
        ends = _describe("line", line, by_id).get("participants", [])
        joined = " and ".join(ends) if len(ends) == 2 else (" \u2013 ".join(ends) or "two entities")
        typed = drawn_label(line)
        out.append({"canonical_id": lid, "kind": "line", "mark": None,
                    "label": _carrier_label("line", line, by_id),
                    "brief_reason": (f"A line{f' labelled {typed!r}' if typed else ''} joins "
                                     f"{joined} with no relationship diamond; a relationship is "
                                     f"drawn as a diamond, and no rubric check asks for a bare "
                                     f"line.")})
    return out


def public_candidates(candidates):
    """The candidates as the judge sees them: without the keys that start with an
    underscore."""
    return [{k: v for k, v in c.items() if not k.startswith("_")} for c in candidates]


def rulings_on_candidates(judge):
    """-> (listed, accounted): what a judge result rules on, as two sets.

    listed holds a (canonical_id, kind) pair for each of its extras entries about
    an ELEMENT, that is, of any kind but "mark". The kind is part of the pair
    because an entry rules on a candidate only as what the candidate is drawn as:
    one that calls an attribute an entity is dropped by the guard (the model holds
    an attribute), so counting it would let the element escape the charge. A mark
    entry does not count either: it rules on the mark, not on the element that
    carries it, and a judge that only calls the key underline on "phone" extra has
    not said whether the attribute is. accounted holds the plain ids of its
    accounted_candidates entries that name no mark: those account for an element
    candidate with that id and for nothing else, not for a mark on it. An entry
    that names a mark accounts for that mark alone (_ruled_marks).

    These are the raw sets; unruled_candidates is what applies them.
    """
    judge = judge if isinstance(judge, dict) else {}

    def kind(entry):
        value = entry.get("kind")
        return value.strip() if isinstance(value, str) else ""

    listed = {(_cid(e), kind(e)) for e in _dicts(judge.get("extras")) if kind(e) != "mark"}
    accounted = {_cid(a) for a in _dicts(judge.get("accounted_candidates"))
                 if _mark_of(a) is None}
    return {pair for pair in listed if pair[0]}, accounted - {""}


def _cid(entry):
    return str(entry.get("canonical_id", "")).strip()


def _mark_of(entry):
    """The mark a ruling names, stripped; None when it names none."""
    value = entry.get("mark")
    return (value.strip() or None) if isinstance(value, str) else None


def _ruled_marks(judge):
    """-> (listed, accounted): the (canonical_id, mark) pairs a judge result
    rules on as marks, its mark extras and its accounted_candidates entries that
    name a mark. Nothing else rules on a mark candidate: an entry that names the
    carrier and no mark is about the element (the judge accounting for Comments
    as the required attribute has said nothing about the underline on it)."""
    judge = judge if isinstance(judge, dict) else {}
    listed = {(_cid(e), _mark_of(e)) for e in _dicts(judge.get("extras"))
              if isinstance(e.get("kind"), str) and e["kind"].strip() == "mark"}
    accounted = {(_cid(a), _mark_of(a)) for a in _dicts(judge.get("accounted_candidates"))}
    return ({(cid, mark) for cid, mark in listed if cid and mark},
            {(cid, mark) for cid, mark in accounted if cid and mark})


def unruled_candidates(judge, candidates):
    """The candidates (from unaccounted_elements) the judge ruled on neither way.

    The one place that test is written down: nodes (the retry) and scoring (the
    charge) both ask it, so they cannot disagree about what "ruled on" means. A
    candidate is ruled on when:
      * it is a mark and the judge lists a mark extra with the same id and the
        same mark, or accounts for that mark (an accounted_candidates entry with
        the same id and mark), and only then. Accounting does not rule on a mark
        that carries _sure (every check on that mark is met by name, _open_marks):
        no rule can read it as one of them. A hierarchy is ruled on the same
        way through an entity that is in it and in no other hierarchy (its
        _aliases): the guard reads a hierarchy mark keyed on that entity as this
        hierarchy's. An accounted entry that names no mark is not a ruling on any
        mark, and one mark accounted for does not rule on another on the same
        carrier;
      * the judge lists it under its own kind, or, unless it is a surplus copy,
        accounts for its id (with no mark: an entry that names a mark accounts
        for that mark). A surplus copy is ruled on by a listing only: the rubric
        asks for fewer copies of its name than are drawn, so no rule can make
        this copy the one it asks for. So is an attribute or a relationship of
        an entity candidate that is charged (listed, or ruled on by nothing):
        its owner is not required, so neither is it. And so is a candidate
        that carries _sure: no requirement of its kind is left open
        (_open_requirements), so no naming rule can make it one the rubric
        asks for. An accounted entry with no mark rules on
        the element candidate with its id and on nothing else; with no such
        candidate it rules on nothing. An id the
        judge accounts for AND lists under any element kind is extra: accounting
        never clears an extra, even one whose kind is wrong and that the guard
        will therefore drop. (That is about the element candidates: a mark
        candidate's carrier is not one, and accounting for it rules on the mark.)
      * it follows a stand-in the judge accounted for: an attribute, or a
        relationship named only by its participants, that the rubric asks for on
        an entity the student did not draw under any name, hung on an entity
        candidate the judge accounted for (accepted as the missing one), is
        covered by that ruling, as many of them as the rubric asks for. A copy
        the judge accounted for itself is one of them, whichever copy it is: it
        is the one the rubric asks for, so it uses up a place before the copies
        it did not account for are let through. Listing the stand-in as an extra
        rejects it as the missing entity, so what hangs on it is not what the
        rubric asks for and is not covered, and an entry for an entity that is no
        candidate rules on nothing, followers included;
      * the judge listed another copy of the same name. The copies are
        interchangeable, so one listing rules on one candidate, however it was
        drawn.
    """
    listed, accounted = rulings_on_candidates(judge)
    element_ids = {c["canonical_id"] for c in candidates if c["kind"] != "mark"}
    accounted = accounted - ({cid for cid, _kind in listed} & element_ids)
    # An attribute or a relationship of an entity that is charged (listed, or
    # ruled on by nothing) is an extra in its own right: no rule can read it as
    # required when its owner is not, so accounting does not rule on it.
    # Measured on q48: Capacity on an extra Venue box was accounted for as "the
    # required AUTHOR attribute PreferredCitationName", rubric check A4, while
    # the candidate's id was the student's A4.
    charged = {c["canonical_id"] for c in candidates
               if c["kind"] == "entity" and c["canonical_id"] not in accounted}

    def hung_on_charged(c):
        ids = [c.get("owner_id")] if c["kind"] == "attribute" else c.get("participant_ids") or []
        return any(i in charged for i in ids if i)
    # Only an ACCOUNTED stand-in carries its followers: one the judge lists as an
    # extra is not the missing entity, and neither is what hangs on it. And only
    # one that is a candidate: an entry naming no candidate rules on nothing.
    entities_ruled = accounted & element_ids
    listed_marks, accounted_marks = _ruled_marks(judge)

    def on_a_ruled_stand_in(c):
        return any(eid in entities_ruled for eid in c.get("_follows") or ())

    # The copies the judge accounted for use up the places on a stand-in first: each
    # IS the one the rubric asks for, so a copy it left out can only be a surplus one,
    # however early in the model it is drawn.
    followed = Counter(c.get("_follow_group") for c in candidates
                       if c["kind"] != "mark" and c["canonical_id"] in accounted
                       and on_a_ruled_stand_in(c))
    unruled = []
    for c in candidates:
        cid = c["canonical_id"]
        if c["kind"] == "mark":
            keys = [(i, c.get("mark")) for i in [cid] + list(c.get("_aliases") or ())]
            ruled = any(k in listed_marks for k in keys) or (
                not c.get("_sure") and any(k in accounted_marks for k in keys))
            if not ruled:
                unruled.append(c)
            continue
        if (cid, c["kind"]) in listed:
            continue
        # Accounting does not rule on a surplus copy. Measured on q48: shown the
        # fourth "for" (the student's R1), the judge accounted for it in two of
        # three gradings, each time with a reason about rubric check R1, the
        # SCHOLAR-AFFLIATION "has"; the drawing scored 100%.
        if (cid in accounted and not c.get("_surplus") and not c.get("_sure")
                and not hung_on_charged(c)):
            continue
        group = c.get("_follow_group")
        if on_a_ruled_stand_in(c) and (group is None or followed[group] < c.get("_follow_cap", 1)):
            followed[group] += 1
            continue
        unruled.append(c)

    credit, out = {}, []
    for c in unruled:
        peers = frozenset(c.get("_peers") or ())
        if peers:
            if peers not in credit:
                credit[peers] = len({cid for cid, kind in listed
                                     if kind == c["kind"] and cid in peers
                                     and cid not in element_ids})
            if credit[peers] > 0:
                credit[peers] -= 1
                continue
        out.append(c)
    return out
