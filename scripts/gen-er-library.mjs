// Regenerates frontend/public/er-shapes.xml — the ONLY palette the embedded
// draw.io editor offers (see frontend/src/components/erShapeLibrary.ts).
//
// Library format: <mxlibrary>[{xml,w,h,aspect,title}, ...]</mxlibrary> where
// each entry's `xml` is base64(deflateRaw(encodeURIComponent(mxGraphModel))).
// Styles here are load-bearing: the backend parser
// (backend/app/services/erd_tutor/drawio_parser.py) keys on them verbatim.
// Change a style in SHAPES and the parser together, or submissions using that
// shape stop being readable.
//
//   node scripts/gen-er-library.mjs           # rewrite er-shapes.xml
//   node scripts/gen-er-library.mjs --decode  # print decoded models of the current file
import { deflateRawSync, inflateRawSync } from "node:zlib";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "frontend", "public", "er-shapes.xml");

// Minimal XML-attribute escaping for cell values/labels used inside
// value="...". This is a syntactic safety net, not a correctness proof — the
// well-formedness proof is
// backend/tests/test_drawio_parser_lines.py::test_shipped_palette_lines_match_parser
// (which XML-parses every shipped entry) — run it after regenerating.
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const model = (inner) =>
  `<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>${inner}</root></mxGraphModel>`;

const vertex = (value, style, w, h) =>
  `<mxCell id="2" value="${esc(value)}" style="${style}" vertex="1" parent="1">` +
  `<mxGeometry x="0" y="0" width="${w}" height="${h}" as="geometry"/></mxCell>`;

// A cardinality line: a vertical edge whose range label is a CHILD of the
// edge — the parser binds child edgeLabels by parent id, exactly, with no
// proximity matching. endArrow=none is explicit because the parser reads a
// missing endArrow as a sharp arrowhead. The label sits at relative x=-0.5
// (75% of the way to the SOURCE end, the entity end).
//
// The "many" lines draw the course's arc cue as the edge's own START marker:
// startArrow=halfCircle with a NEGATIVE startSize flips draw.io's half-circle
// so the cup sits at the line's source end with its back to the entity,
// opening toward the diamond — the course's hand-drawn notation. Being a
// marker (not a separate cell), it follows the endpoint wherever it is
// attached or dragged, rotates with the line, and steals no clicks. Students
// attach the cup/labelled (source) end to the entity; the parser reads
// halfCircle on either end as the curved "many" cue, so a backwards
// attachment still grades right via the range label.
const ONE_STYLE = "rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=none;endFill=0;startArrow=none;";
const MANY_STYLE = "rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=none;endFill=0;startArrow=halfCircle;startSize=-20;startFill=0;";

const line = (style, label) =>
  `<mxCell id="2" style="${style}" edge="1" parent="1">` +
  `<mxGeometry relative="1" as="geometry">` +
  `<mxPoint x="50" y="180" as="sourcePoint"/><mxPoint x="50" y="50" as="targetPoint"/>` +
  `</mxGeometry></mxCell>` +
  `<mxCell id="3" value="${esc(label)}" style="edgeLabel;html=1;align=center;verticalAlign=middle;resizable=0;points=[];" vertex="1" connectable="0" parent="2">` +
  `<mxGeometry x="-0.5" y="0" relative="1" as="geometry"><mxPoint x="26" y="0" as="offset"/></mxGeometry></mxCell>`;

const oneLine = (label) => line(ONE_STYLE, label);
const manyLine = (label) => line(MANY_STYLE, label);

// Titles are what students see in the palette. Stock shapes are byte-for-byte
// the models decoded from the previous er-shapes.xml. The old standalone Arc
// entry is gone: the N-lines carry the curve themselves (the parser still
// reads loose arcs, so old drafts keep grading).
const SHAPES = [
  { title: "Entity", w: 120, h: 60, xml: model(vertex("Entity", "rounded=0;whitespace=wrap;html=1;", 120, 60)) },
  { title: "Weak Entity", w: 120, h: 60, xml: model(vertex("Weak Entity", "shape=ext;double=1;whitespace=wrap;html=1;", 120, 60)) },
  { title: "Relationship", w: 120, h: 80, xml: model(vertex("Relationship", "rhombus;whitespace=wrap;html=1;", 120, 80)) },
  { title: "Identifying Relationship", w: 120, h: 80, xml: model(vertex("Identifying", "rhombus;double=1;whitespace=wrap;html=1;", 120, 80)) },
  { title: "Attribute", w: 120, h: 60, xml: model(vertex("Attribute", "ellipse;whitespace=wrap;html=1;", 120, 60)) },
  { title: "Key Attribute", w: 120, h: 60, xml: model(vertex("<u>Key</u>", "ellipse;whitespace=wrap;html=1;", 120, 60)) },
  { title: "Triangle", w: 80, h: 80, xml: model(vertex("", "triangle;whitespace=wrap;html=1;", 80, 80)) },
  { title: "Exactly one (1..1)", w: 100, h: 180, xml: model(oneLine("1..1")) },
  { title: "At most one (0..1)", w: 100, h: 180, xml: model(oneLine("0..1")) },
  { title: "One or more (1..N)", w: 100, h: 180, xml: model(manyLine("1..N")) },
  { title: "Zero or more (0..N)", w: 100, h: 180, xml: model(manyLine("0..N")) },
];

const encode = (xml) => deflateRawSync(Buffer.from(encodeURIComponent(xml), "utf8")).toString("base64");
const decode = (b64) => decodeURIComponent(inflateRawSync(Buffer.from(b64, "base64")).toString("utf8"));

const args = process.argv.slice(2);
if (args.length > 1 || (args.length === 1 && args[0] !== "--decode")) {
  console.error(`unknown arguments: ${args.join(" ")} (only --decode is supported)`);
  process.exit(1);
}

if (args[0] === "--decode") {
  const current = readFileSync(OUT, "utf8")
    .replace(/^﻿/, "")
    .replace(/^<mxlibrary>/, "")
    .replace(/<\/mxlibrary>\s*$/, "");
  for (const e of JSON.parse(current)) console.log(`=== ${e.title}\n${decode(e.xml)}`);
} else {
  const entries = SHAPES.map(({ title, w, h, xml }) => ({ xml: encode(xml), w, h, aspect: "fixed", title }));
  writeFileSync(OUT, `<mxlibrary>${JSON.stringify(entries)}</mxlibrary>\n`);
  console.log(`wrote ${OUT}: ${entries.length} entries (${entries.map((e) => e.title).join(", ")})`);
}
