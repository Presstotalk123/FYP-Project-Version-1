"""Parse draw.io (mxGraph) XML into the same ObservationJSON the vision stage produces.

WHY
The submit pipeline renders the student's diagram to a PNG and asks a vision model
to recover its structure. But for diagrams authored in the embedded draw.io editor
that structure is already exact and machine-readable: shape kinds, double borders,
edge connectivity, arrowhead styles and label text are all explicit in the XML.
Recovering them statistically from pixels is what produced every extraction defect
measured on this pipeline — phantom curves, ">=1" read as ">=0", marks binding to a
neighbouring connector, invisible thin arcs, and specializations detected in one run
and missed in the next.

So when the XML is available it is parsed here, deterministically, and the vision
stage is skipped. Image uploads (and any XML this parser cannot make sense of) still
go through vision — see ``nodes.observe_node``.

CONTRACT
``parse_drawio`` returns a dict matching ``schemas.ObservationJSON`` exactly, so
everything downstream (normalize, grade, score) is unchanged.

NOTATION MAPPING (mxGraph style -> ERD construct)
  rectangle                          -> entity
  shape=ext + double=1               -> weak entity (double border)
  shape=rhombus                      -> relationship
  shape=rhombus + double=1           -> identifying relationship
  ellipse                            -> attribute; <u>...</u> marks a key
  triangle                           -> specialization (ISA)
  shape=mxgraph.basic.arc            -> curved endpoint cue ("many")
  edge endArrow/startArrow=open|...  -> sharp endpoint cue ("one")
  edgeLabel child / nearby text cell -> endpoint text marker (">=1", "0..1", ...)
"""

import html
import math
import re
import xml.etree.ElementTree as ET

_TAG = re.compile(r"<[^>]+>")


def _plain(value):
    """draw.io labels are HTML: unescape entities and strip tags.

    Order matters. Values are usually double-escaped ("&amp;gt;=1"), so one
    unescape reveals the real markup and a second reveals the text. Stripping
    tags must happen BETWEEN the two: doing both unescapes first turns "&lt;= 1"
    into "<= 1", which the tag regex then eats — that silently truncated
    ">=0 or <= 1" to ">=0 or".
    """
    if not value:
        return ""
    s = str(value)                         # ElementTree already unescaped once:
    s = s.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")
    s = _TAG.sub("", s)                    # ...so this level IS the markup
    s = html.unescape(s)                   # and the content's entities come last
    return " ".join(s.split()).strip()


def _is_underlined(value):
    return bool(value) and "<u>" in html.unescape(str(value)).lower()


def _style_of(cell):
    return (cell.get("style") or "").lower()


def _has(style, *needles):
    return any(n in style for n in needles)


def _geom(cell):
    g = cell.find("mxGeometry")
    if g is None:
        return None
    try:
        x = float(g.get("x") or 0.0)
        y = float(g.get("y") or 0.0)
        w = float(g.get("width") or 0.0)
        h = float(g.get("height") or 0.0)
    except (TypeError, ValueError):
        return None
    return (x, y, w, h)


def _centre(geom):
    x, y, w, h = geom
    return (x + w / 2.0, y + h / 2.0)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class _Cell:
    __slots__ = ("id", "value", "style", "geom", "centre", "source", "target",
                 "is_edge", "parent")

    def __init__(self, el):
        self.id = el.get("id")
        self.value = el.get("value") or ""
        self.style = _style_of(el)
        self.geom = _geom(el)
        self.centre = _centre(self.geom) if self.geom else None
        self.source = el.get("source")
        self.target = el.get("target")
        self.is_edge = el.get("edge") == "1"
        self.parent = el.get("parent")


def _classify(cell):
    s = cell.style
    if cell.is_edge:
        return "edge"
    if "edgelabel" in s:
        return "edgelabel"
    if "mxgraph.basic.arc" in s or ("shape=arc" in s):
        return "arc"
    if "triangle" in s:
        return "specialization"
    if "rhombus" in s:
        return "relationship"
    if "ellipse" in s:
        return "attribute"
    if s.startswith("text;") or "text;html=1" in s:
        return "text"
    if "shape=ext" in s:
        return "entity"          # weak entity: double border
    if s.strip() in ("", None):
        return "skip"
    if _has(s, "whitespace=wrap"):
        return "entity"
    return "skip"


def _style_num(style, key):
    """Read a numeric style property ("exitx=0.25" -> 0.25). None if absent."""
    m = re.search(rf"(?:^|;){key}=(-?[\d.]+)", style)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _arrow_kind(style, which):
    """which: 'end' or 'start'. Returns 'sharp' | None."""
    m = re.search(rf"{which}arrow=([a-z]+)", style)
    if not m:
        # draw.io default endArrow is a filled block arrow when unspecified,
        # but every ERD template used here sets it explicitly; treat absence
        # on the START side as "no arrow".
        return "sharp" if which == "end" and "endarrow" not in style else None
    kind = m.group(1)
    return None if kind == "none" else "sharp"


def parse_drawio(xml_text: str) -> dict:
    """Return an ObservationJSON-shaped dict, or raise ValueError if unusable."""
    if not xml_text or not xml_text.strip():
        raise ValueError("empty XML")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"not valid XML: {exc}") from exc

    cells = [_Cell(el) for el in root.iter("mxCell")]
    by_id = {c.id: c for c in cells}
    kinds = {c.id: _classify(c) for c in cells}

    entities, relationships, arcs, texts, specs, edges, edgelabels = [], [], [], [], [], [], []
    for c in cells:
        k = kinds[c.id]
        if k == "entity" and c.geom:
            entities.append(c)
        elif k == "relationship" and c.geom:
            relationships.append(c)
        elif k == "arc" and c.geom:
            arcs.append(c)
        elif k == "text" and c.geom:
            texts.append(c)
        elif k == "specialization" and c.geom:
            specs.append(c)
        elif k == "edge":
            edges.append(c)
        elif k == "edgelabel":
            edgelabels.append(c)

    if not entities or not relationships:
        raise ValueError(f"no ERD structure found "
                         f"({len(entities)} entities, {len(relationships)} relationships)")

    # ---- ids -------------------------------------------------------------
    ent_id, rel_id = {}, {}
    entities.sort(key=lambda c: (_plain(c.value).lower(), c.id or ""))
    relationships.sort(key=lambda c: (_plain(c.value).lower(), c.id or ""))
    for i, c in enumerate(entities, 1):
        ent_id[c.id] = f"E{i}"
    for i, c in enumerate(relationships, 1):
        rel_id[c.id] = f"R{i}"

    out_entities = [{
        "id": ent_id[c.id],
        "raw_name": _plain(c.value),
        "normalized_name": _plain(c.value),
        "entity_kind": "weak" if "double=1" in c.style else "strong",
        "evidence": f"{'Double-bordered' if 'double=1' in c.style else 'Single-bordered'} "
                    f"rectangle in the draw.io source (cell {c.id}).",
        "confidence": "high",
    } for c in entities]

    # ---- relationship participants ---------------------------------------
    def endpoints_of(rel):
        """Entities this relationship connects to, with the edge that connects them."""
        found = []
        for e in edges:
            if e.source == rel.id and e.target in ent_id:
                found.append((e.target, e, "target"))
            elif e.target == rel.id and e.source in ent_id:
                found.append((e.source, e, "source"))
        return found

    out_relationships, participants = [], {}
    for c in relationships:
        eps = endpoints_of(c)
        participants[c.id] = eps
        out_relationships.append({
            "id": rel_id[c.id],
            "raw_name": _plain(c.value),
            "normalized_name": _plain(c.value),
            "relationship_kind": "identifying" if "double=1" in c.style else "normal",
            "participant_entity_ids": [ent_id[t] for t, _, _ in eps],
            "evidence": f"{'Double' if 'double=1' in c.style else 'Single'} diamond in the "
                        f"draw.io source (cell {c.id}).",
            "confidence": "high",
        })

    # ---- attributes ------------------------------------------------------
    owners = {c.id: (ent_id.get(c.id) or rel_id.get(c.id)) for c in entities + relationships}
    out_attributes = []
    attr_cells = [c for c in cells if kinds[c.id] == "attribute" and c.geom]
    attr_cells.sort(key=lambda c: (_plain(c.value).lower(), c.id or ""))
    for i, c in enumerate(attr_cells, 1):
        owner_cell = None
        for e in edges:
            if e.source == c.id and e.target in owners:
                owner_cell = e.target
                break
            if e.target == c.id and e.source in owners:
                owner_cell = e.source
                break
        owner = owners.get(owner_cell) if owner_cell else None
        out_attributes.append({
            "id": f"A{i}",
            "raw_name": _plain(c.value),
            "normalized_name": _plain(c.value),
            "owner_id": owner or "",
            "owner_type": ("entity" if owner and owner.startswith("E")
                           else "relationship" if owner else "unknown"),
            "attribute_kind_observed": "key" if _is_underlined(c.value) else "normal",
            "evidence": f"Ellipse in the draw.io source (cell {c.id})"
                        + (" with an underlined label." if _is_underlined(c.value) else "."),
            "confidence": "high",
        })

    # ---- endpoint marks --------------------------------------------------
    def attach_point(edge, ent_cell, side):
        """Where this connector actually meets the entity box, if draw.io says so.

        Recorded as exitX/exitY (fractions of the source box) and entryX/entryY
        (of the target). This is the only thing that separates the two endpoints
        of a self-relationship: they share both centres, so a centre-derived
        anchor gives them the same point and their marks cannot be told apart.
        """
        prefix = "exit" if side == "source" else "entry"
        fx = _style_num(edge.style, prefix + "x")
        fy = _style_num(edge.style, prefix + "y")
        if fx is None or fy is None:
            return None
        x, y, w, h = ent_cell.geom
        return (x + fx * w, y + fy * h)

    def anchor(rel, ent_cell, edge, side):
        point = attach_point(edge, ent_cell, side)
        if point is not None:
            return point
        # Nothing explicit: a point just outside the entity, on the line toward
        # the relationship.
        rc, ec = rel.centre, ent_cell.centre
        return (ec[0] + 0.30 * (rc[0] - ec[0]), ec[1] + 0.30 * (rc[1] - ec[1]))

    anchors = []
    for rel in relationships:
        for tgt_id, edge, side in participants[rel.id]:
            ent_cell = by_id[tgt_id]
            anchors.append((rel, ent_cell, edge, anchor(rel, ent_cell, edge, side)))

    def box_distance(cell, point):
        """Point-to-rectangle distance (0 when inside).

        Label boxes are wide and their text is not centred in them, so
        centre-to-point distance mis-binds a wide label to a neighbouring
        connector. Distance to the box itself is what matches the eye.
        """
        x, y, w, h = cell.geom
        dx = max(x - point[0], 0.0, point[0] - (x + w))
        dy = max(y - point[1], 0.0, point[1] - (y + h))
        return math.hypot(dx, dy)

    def assign(cands, limit):
        """Globally greedy: shortest (mark, anchor) distance wins, then both are
        consumed. First-come binding let one wide label claim an anchor a nearer
        label needed, dropping the second mark entirely.

        Keyed by EDGE id, not (relationship, entity): a self-relationship reaches
        the same entity twice, so that pair collides and one endpoint's mark
        silently overwrote the other's.
        """
        pairs = sorted(
            ((box_distance(m, a[3]), i, j) for i, m in enumerate(cands)
             for j, a in enumerate(anchors) if box_distance(m, a[3]) <= limit),
            key=lambda t: t[0])
        used_m, used_a, out = set(), set(), {}
        for _d, i, j in pairs:
            if i in used_m or j in used_a:
                continue
            used_m.add(i)
            used_a.add(j)
            out[anchors[j][2].id] = cands[i]
        return out

    def marker_text(v):
        t = _plain(v)
        return t if re.search(r"[<>=]|\.\.|^\s*[0-9NnMm]\s*$", t) else ""

    # Everything below is keyed by edge id — one key per endpoint, including
    # both endpoints of a self-relationship.

    # Free-floating arcs -> curved cue at their endpoint.
    arc_at = {k: c.id for k, c in assign(arcs, limit=90.0).items()}

    # Edge labels bind to their own edge (exact, no geometry needed).
    marker_at = {}
    for lab in edgelabels:
        parent = by_id.get(lab.parent)
        text = marker_text(lab.value)
        if not parent or not parent.is_edge or not text:
            continue
        marker_at.setdefault(parent.id, text)

    # Free-floating text markers -> nearest free endpoint.
    free = [t for t in texts if marker_text(t.value)]
    for edge_id, cell in assign(free, limit=120.0).items():
        marker_at.setdefault(edge_id, marker_text(cell.value))

    out_endpoints = []
    for rel in relationships:
        for tgt_id, edge, side in participants[rel.id]:
            # An arrowhead on the edge is a "sharp" cue at the end it points to.
            cue = "no_arrow_visible"
            if edge.id in arc_at:
                cue = "curved_arrowhead"
            else:
                which = "end" if side == "target" else "start"
                if _arrow_kind(edge.style, which) == "sharp":
                    cue = "sharp_arrowhead"
            out_endpoints.append({
                "relationship_id": rel_id[rel.id],
                "entity_id": ent_id[tgt_id],
                "observed_text_marker": marker_at.get(edge.id, ""),
                "observed_endpoint_cue": cue,
                "evidence": "Read from the draw.io source: "
                            + (f"arc cell {arc_at[edge.id]} at this endpoint"
                               if edge.id in arc_at
                               else f"edge {edge.id} style {edge.style[:60]}"),
                "confidence": "high",
            })

    # ---- specializations --------------------------------------------------
    out_specs = []
    for i, tri in enumerate(specs, 1):
        linked = [e.target if e.source == tri.id else e.source
                  for e in edges if tri.id in (e.source, e.target)]
        linked = [x for x in linked if x in ent_id]
        if not linked:
            continue
        # The supertype sits above the triangle; subtypes below.
        above = [x for x in linked if by_id[x].centre[1] < tri.centre[1]]
        below = [x for x in linked if by_id[x].centre[1] >= tri.centre[1]]
        sup = above[0] if above else linked[0]
        subs = below or [x for x in linked if x != sup]
        label = ""
        for t in texts:
            if _dist(t.centre, tri.centre) <= 60 and _plain(t.value):
                label = _plain(t.value)
                break
        out_specs.append({
            "id": f"S{i}",
            "supertype_entity_id": ent_id[sup],
            "subtype_entity_ids": [ent_id[x] for x in subs],
            "raw_label": label,
            "disjointness": "unknown",
            "completeness": "unknown",
            "evidence": f"Triangle in the draw.io source (cell {tri.id}).",
            "confidence": "high",
        })

    return {
        "source_mode": "xml",     # parsed from source, not read from pixels
        "stage": "observation_extraction",
        "entities": out_entities,
        "relationships": out_relationships,
        "attributes": out_attributes,
        "relationship_endpoints": out_endpoints,
        "specializations": out_specs,
        "uncertain_items": [],
        # Cells this parser could not place. Surfacing them keeps a coverage gap
        # visible downstream instead of silently dropping structure the student
        # actually drew — the failure mode that would make XML-first worse than
        # vision rather than better.
        "unclassified_labels": [
            {"raw_text": _plain(c.value) or f"<{c.style.split(';')[0]}>",
             "evidence": f"draw.io cell {c.id}, style {c.style[:70]}",
             "reason": "shape not recognised as an ERD construct by the draw.io parser"}
            for c in cells
            if kinds[c.id] == "skip" and c.geom and (c.style or _plain(c.value))
        ],
    }
