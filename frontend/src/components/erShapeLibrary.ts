// Locks the embedded draw.io palette to a fixed set of stock ER shapes.
//
// draw.io is loaded with `configure=1`, so on startup it asks the host page for a
// configuration (see DrawioBoard's `configure` handshake). We answer with a single
// custom library and restrict the allowed libraries to just that one, so the sidebar
// can only ever offer these shapes — nothing else can be dragged in or added via
// "More Shapes".
//
// Each shape's `style` is authored to match, verbatim, what the backend parser keys on
// (backend/app/services/erd_tutor/drawio_parser.py `_classify` / `_is_underlined`):
//   rounded=0;whitespace=wrap  -> entity                (rectangle)
//   shape=ext + double=1       -> weak entity           (double border)
//   rhombus                    -> relationship          (diamond)
//   rhombus + double=1         -> identifying relationship
//   ellipse                    -> attribute
//   ellipse + <u>…</u> label   -> key attribute         (underlined label, not style)
//   triangle                   -> specialization (ISA)
//   shape=mxgraph.basic.arc    -> arc
// Changing a style here without changing the parser will make that shape unreadable.

type ShapeSpec = {
  title: string;
  style: string;
  value: string;
  w: number;
  h: number;
};

const SHAPES: ShapeSpec[] = [
  { title: "Entity", style: "rounded=0;whitespace=wrap;html=1;", value: "Entity", w: 120, h: 60 },
  { title: "Weak Entity", style: "shape=ext;double=1;whitespace=wrap;html=1;", value: "Weak Entity", w: 120, h: 60 },
  { title: "Relationship", style: "rhombus;whitespace=wrap;html=1;", value: "Relationship", w: 120, h: 80 },
  { title: "Identifying Relationship", style: "rhombus;double=1;whitespace=wrap;html=1;", value: "Identifying", w: 120, h: 80 },
  { title: "Attribute", style: "ellipse;whitespace=wrap;html=1;", value: "Attribute", w: 120, h: 60 },
  // The key attribute is recognised by an underlined label, not by its style, so the
  // default value ships wrapped in <u>…</u>. Students rename the text, keeping the underline.
  { title: "Key Attribute", style: "ellipse;whitespace=wrap;html=1;", value: "<u>Key</u>", w: 120, h: 60 },
  { title: "Triangle", style: "triangle;whitespace=wrap;html=1;", value: "", w: 80, h: 80 },
  { title: "Arc", style: "shape=mxgraph.basic.arc;html=1;startAngle=0.15;endAngle=0.55;arcWidth=0.5;fillColor=none;", value: "", w: 100, h: 100 },
];

const escapeXml = (value: string): string =>
  value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

// One-vertex mxGraphModel per shape, kept as plain (uncompressed) XML. draw.io's library
// loader uses an entry's `xml` directly when it starts with '<' (EditorUi.addLibraryEntries:
// `img.xml.charAt(0) == '<' ? img.xml : Graph.decompress(img.xml)`), so no compression is
// needed — and JSON.stringify below handles all the quote-escaping in the library text.
const entryXml = (s: ShapeSpec): string =>
  `<mxGraphModel><root>` +
  `<mxCell id="0"/>` +
  `<mxCell id="1" parent="0"/>` +
  `<mxCell id="2" value="${escapeXml(s.value)}" style="${escapeXml(s.style)}" vertex="1" parent="1">` +
  `<mxGeometry x="0" y="0" width="${s.w}" height="${s.h}" as="geometry"/>` +
  `</mxCell>` +
  `</root></mxGraphModel>`;

const ER_MXLIBRARY =
  "<mxlibrary>" +
  JSON.stringify(
    SHAPES.map((s) => ({ xml: entryXml(s), w: s.w, h: s.h, aspect: "fixed", title: s.title })),
  ) +
  "</mxlibrary>";

/** draw.io embed configuration replied to the editor's `configure` request. */
export const ER_CONFIG = {
  // Only our custom entry opens in the sidebar...
  defaultLibraries: "erd",
  // ...and it is the ONLY library allowed anywhere (sidebar + "More Shapes"). Every
  // built-in library (general, uml, er, …) is excluded, so nothing else can be added.
  // NB: this must include "erd" — draw.io's isEntryVisible() also gates our own custom
  // library, so an empty array would hide it and fall back to the default sidebar.
  enabledLibraries: ["erd"],
  libraries: [
    {
      title: { main: "Entity–Relationship" },
      entries: [
        {
          id: "erd",
          title: { main: "ER Shapes" },
          desc: { main: "Stock ER notation" },
          libs: [
            {
              title: { main: "ER" },
              data: ER_MXLIBRARY,
            },
          ],
        },
      ],
    },
  ],
};
