// Regenerates frontend/public/er-shapes.xml — the ONLY palette the embedded
// draw.io editor offers (see frontend/src/components/erShapeLibrary.ts).
//
// Library format: <mxlibrary>[{xml,w,h,aspect,title}, ...]</mxlibrary> where
// each entry's `xml` is base64(deflateRaw(encodeURIComponent(mxGraphModel))).
// Styles here are load-bearing: the backend parser
// (backend/app/services/erd_tutor/drawio_parser.py) keys on them verbatim.
// Change a style in SHAPES and the parser together, or submissions using that
// shape stop being readable. The proof that they agree — and that every entry
// is well-formed XML, which plain Node cannot check — is
// backend/tests/test_drawio_parser_lines.py::test_shipped_palette_connectors_read_as_the_guide_says
// Run it after regenerating.
//
//   node scripts/gen-er-library.mjs           # rewrite er-shapes.xml
//   node scripts/gen-er-library.mjs --decode  # print decoded models of the current file
import { deflateRawSync, inflateRawSync } from "node:zlib";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "frontend", "public", "er-shapes.xml");

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const model = (inner) =>
  `<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>${inner}</root></mxGraphModel>`;

// Every node shape carries points=[] — NO fixed connection points — so every
// attachment is floating. draw.io honours sourcePerimeterSpacing (what seats
// the curved connector's cup on the border) only on floating connections; a
// fixed × point would bury the cup inside the shape.
const vertex = (value, style, w, h) =>
  `<mxCell id="2" value="${esc(value)}" style="${style}points=[];" vertex="1" parent="1">` +
  `<mxGeometry x="0" y="0" width="${w}" height="${h}" as="geometry"/></mxCell>`;

// THE CONNECTORS. Each glyph is the edge's own START marker, so it lives in
// the style string: no student manipulation (rotating, grouping, dragging)
// can separate it from its line, it turns with the line by itself, and the
// parser reads it exactly, from whichever end touches the entity. The marked
// (source) end is the one that goes on the entity. endArrow=none is explicit
// because the parser reads a missing endArrow as draw.io's default arrowhead.
//
// Arrow: a positive-size marker is drawn BEHIND the terminal, so the tip
// lands exactly on the border with no spacing needed.
//
// Curve: draw.io's halfCircle with a NEGATIVE startSize, which flips it to
// open toward the diamond with its back to the entity — the course's curve.
// A negative-size marker is drawn PAST the terminal, so the endpoint dot sits
// at the cup's tips rather than on the border; only a self-hosted draw.io
// could move it. sourcePerimeterSpacing holds the terminal off the border so
// the cup's back rests on it. SIZE AND SPACING ARE A TUNED PAIR (rendered
// sweep, 2026-09-19): the spacing inflates the shape's perimeter box, so a
// line meeting a flat side stops `spacing` px out while one meeting a corner
// stops spacing*sqrt(2) out — yet the glyph always reaches `size` px past the
// terminal. No pair is exact for both; 16/13 splits the error (~3px overlap
// square-on, ~2px gap at a corner) so the cup reads as attached from every
// angle. 20/15 visibly punched into the box; 20/20 floated off the corners.
//
// The curve's END marker is a PAD, not a glyph. draw.io sizes an edge's
// bounding box by growing it by the largest marker size, and the cup's size
// is negative: a bare vertical line (width 0) came out with a NEGATIVE-width
// box, so its palette thumbnail was never scaled into view — a blank slot
// (seen in the real editor, 2026-09-19). "erdpad" is a marker name draw.io
// does not know, so it draws nothing, but its positive endSize still wins the
// max() and grows the box enough to hold the cup. The parser reads "erdpad"
// as no arrow.
const LINE = "rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=none;endFill=0;";
const PLAIN_STYLE = LINE + "startArrow=none;";
const ARROW_STYLE = LINE + "startArrow=open;startSize=12;startFill=0;";
const CURVED_STYLE = "rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=erdpad;endSize=20;endFill=0;" +
  "startArrow=halfCircle;startSize=-16;startFill=0;sourcePerimeterSpacing=13;";

// Every connector carries an editable label for the bound: a CHILD of the
// edge, which the parser binds by parent id — exactly, with no proximity
// matching — sitting on the line (draw.io's standard edge label, so it reads
// the same at any angle) at relative x=-0.5, three quarters of the way to the
// source, i.e. the entity end. The placeholder text is deliberately NOT a
// marker: it has no <, >, = or "..", so the parser ignores a label the
// student never overwrote instead of grading it.
const PLACEHOLDER = "Cardinality";

// Drawn vertically with the marked end at the bottom, as it will sit on an
// entity below a diamond.
const connector = (style) =>
  `<mxCell id="2" style="${style}" edge="1" parent="1">` +
  `<mxGeometry relative="1" as="geometry">` +
  `<mxPoint x="50" y="180" as="sourcePoint"/><mxPoint x="50" y="50" as="targetPoint"/>` +
  `</mxGeometry></mxCell>` +
  `<mxCell id="3" value="${esc(PLACEHOLDER)}" style="edgeLabel;html=1;align=center;verticalAlign=middle;resizable=0;points=[];" vertex="1" connectable="0" parent="2">` +
  `<mxGeometry x="-0.5" relative="1" as="geometry"><mxPoint as="offset"/></mxGeometry></mxCell>`;

// Titles are what students see in the palette; the connector titles carry the
// COURSE's reading of the mark at the entity end: no arrow = many, pointed
// arrow = may be one (at most one), curved arrow = must be one (exactly one).
// That is the lectures' frame, NOT derivation.py's cue table (curve -> N,
// arrow/plain -> 1), which is unchanged. There is no standalone Arc entry: the
// curved connector replaces hand-placing one (the parser still reads loose
// arcs, so old drafts keep grading).
const SHAPES = [
  { title: "Entity", w: 120, h: 60, xml: model(vertex("Entity", "rounded=0;whitespace=wrap;html=1;", 120, 60)) },
  { title: "Weak Entity", w: 120, h: 60, xml: model(vertex("Weak Entity", "shape=ext;double=1;whitespace=wrap;html=1;", 120, 60)) },
  { title: "Relationship", w: 120, h: 80, xml: model(vertex("Relationship", "rhombus;whitespace=wrap;html=1;", 120, 80)) },
  { title: "Identifying Relationship", w: 120, h: 80, xml: model(vertex("Identifying", "rhombus;double=1;whitespace=wrap;html=1;", 120, 80)) },
  { title: "Attribute", w: 120, h: 60, xml: model(vertex("Attribute", "ellipse;whitespace=wrap;html=1;", 120, 60)) },
  { title: "Key Attribute", w: 120, h: 60, xml: model(vertex("<u>Key</u>", "ellipse;whitespace=wrap;html=1;", 120, 60)) },
  { title: "Triangle", w: 80, h: 80, xml: model(vertex("", "triangle;whitespace=wrap;html=1;", 80, 80)) },
  { title: "Plain line (many)", w: 100, h: 180, xml: model(connector(PLAIN_STYLE)) },
  { title: "Sharp arrow (may be one)", w: 100, h: 180, xml: model(connector(ARROW_STYLE)) },
  { title: "Curved arrow (must be one)", w: 100, h: 180, xml: model(connector(CURVED_STYLE)) },
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
    .replace(/^\uFEFF/, "")
    .replace(/^<mxlibrary>/, "")
    .replace(/<\/mxlibrary>\s*$/, "");
  for (const e of JSON.parse(current)) console.log(`=== ${e.title}\n${decode(e.xml)}`);
} else {
  const entries = SHAPES.map(({ title, w, h, xml }) => ({ xml: encode(xml), w, h, aspect: "fixed", title }));
  writeFileSync(OUT, `<mxlibrary>${JSON.stringify(entries)}</mxlibrary>\n`);
  console.log(`wrote ${OUT}: ${entries.length} entries (${entries.map((e) => e.title).join(", ")})`);
}
