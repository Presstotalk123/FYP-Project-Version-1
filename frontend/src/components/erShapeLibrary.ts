// Locks the embedded draw.io palette to a fixed set of stock ER shapes.
//
// draw.io is loaded with `configure=1`, so on startup it asks the host page for a
// configuration (see DrawioBoard's `configure` handshake). We answer with a single
// custom library (loaded by URL) and restrict the allowed libraries to just that one,
// so the sidebar can only ever offer these shapes — nothing else can be dragged in or
// added via "More Shapes".
//
// WHY A URL AND NOT INLINE DATA
// draw.io's `libraries` config only renders a library when it is fetched through its
// loadLibrary() path. Inline `data:` on a custom entry builds an empty palette shell
// (verified), and a `data:` URI is rejected by its loader. A real, fetchable URL works.
// `raw.githubusercontent.com` is explicitly treated as CORS-enabled by draw.io
// (Editor.isCorsEnabledForUrl), so it is fetched directly — no proxy, no CORS setup —
// and this repo is public. The file is served in prod from /er-shapes.xml too, but the
// raw URL is what draw.io actually loads.
//
// THE LIBRARY FILE: frontend/public/er-shapes.xml
// It is an <mxlibrary> whose shapes' styles match, verbatim, what the backend parser
// keys on (backend/app/services/erd_tutor/drawio_parser.py `_classify`/`_is_underlined`
// /`_arrow_kind`):
//   rounded=0;whitespace=wrap  -> entity                (rectangle)
//   shape=ext + double=1       -> weak entity           (double border)
//   rhombus                    -> relationship          (diamond)
//   rhombus + double=1         -> identifying relationship
//   ellipse                    -> attribute
//   ellipse + <u>…</u> label   -> key attribute         (underlined label, not style)
//   triangle                   -> specialization (ISA)
//   edge + endArrow=none       -> cardinality line "one"  (child edgeLabel 1..1 / 0..1)
//   edge + endArrow=halfCircle -> cardinality line "many" (child edgeLabel 1..N / 0..N)
// The parser still reads standalone arcs (shape=mxgraph.basic.arc) and loose text
// markers from old drafts, but the palette no longer offers the Arc — the N-lines
// carry the curve as their own arrowhead.
// Regenerate er-shapes.xml with `node scripts/gen-er-library.mjs`; that script is the
// single source of truth for the shape table. Changing a style there without changing
// the parser makes that shape unreadable on submit.

const ER_LIBRARY_URL =
  "https://raw.githubusercontent.com/Presstotalk123/FYP-Project-Version-1/main/frontend/public/er-shapes.xml";

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
      title: { main: "Entity-Relationship" },
      entries: [
        {
          id: "erd",
          title: { main: "ER Shapes" },
          desc: { main: "Stock ER notation" },
          libs: [
            {
              title: { main: "ER" },
              url: ER_LIBRARY_URL,
            },
          ],
        },
      ],
    },
  ],
};
