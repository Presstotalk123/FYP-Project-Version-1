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
// keys on (backend/app/services/erd_tutor/drawio_parser.py `_classify`/`_is_underlined`):
//   rounded=0;whitespace=wrap  -> entity                (rectangle)
//   shape=ext + double=1       -> weak entity           (double border)
//   rhombus                    -> relationship          (diamond)
//   rhombus + double=1         -> identifying relationship
//   ellipse                    -> attribute
//   ellipse + <u>…</u> label   -> key attribute         (underlined label, not style)
//   triangle                   -> specialization (ISA)
//   edge + endArrow=none       -> the three connectors; the glyph is the edge's own START
//                                 marker, read at whichever end touches the entity. Each
//                                 carries a child edgeLabel reading "Cardinality" for the
//                                 student to overwrite with the bound; the parser binds it by
//                                 parent id and ignores it while it still reads "Cardinality":
//     startArrow=none          ->   plain end   (no cue: "at most one")
//     startArrow=open          ->   arrow       (sharp cue: "one")
//     startArrow=halfCircle    ->   curve       (curved cue: "many"; a NEGATIVE startSize
//                                   flips it to open toward the diamond; its
//                                   endArrow=erdpad draws nothing and reads as no arrow —
//                                   it only sizes the palette thumbnail)
// Every node shape also carries points=[] (floating connections only): draw.io honours the
// curve's sourcePerimeterSpacing — what rests it on the border — only on those.
// The parser still reads a loose Arc shape (shape=mxgraph.basic.arc, within 90px of an
// endpoint) and loose text markers, so drafts drawn before the connectors keep grading; the
// standalone Arc palette entry is gone.
// Regenerate er-shapes.xml with `node scripts/gen-er-library.mjs`; that script is the single
// source of truth for the shape table. Changing a style there without changing the parser
// makes that shape unreadable on submit.

// NEXT_PUBLIC_ER_SHAPES_URL (frontend/.env.local, dev only) previews a palette before it
// lands on main. Never set it in a production build. Two ways:
//  - a pushed branch: .../FYP-Project-Version-1/<branch>/frontend/public/er-shapes.xml
//  - the local file, no push: serve frontend/public with CORS (`npx http-server
//    frontend/public -p 8099 --cors`) and point the variable at
//    http://localhost:8099/er-shapes.xml. draw.io only fetches hosts it treats as
//    CORS-enabled, so NEXT_PUBLIC_DRAWIO_ORIGIN must also carry
//    `&cors=<url-encoded regex matching that URL>`. The browser also blocks a public
//    site's iframe from reaching localhost ("Access Denied" in the Shapes panel) until the
//    iframe is delegated local-network-access and you click Allow on Chrome's one-time
//    prompt — DrawioBoard adds that delegation only while ER_LIBRARY_IS_LOCAL is true.
// The override gets a cache-buster: raw.githubusercontent caches ~5 min and the browser
// caches on top, which makes a regenerated palette look unchanged until they expire.
const ER_LIBRARY_URL = process.env.NEXT_PUBLIC_ER_SHAPES_URL
  ? `${process.env.NEXT_PUBLIC_ER_SHAPES_URL}?t=${Date.now()}`
  : "https://raw.githubusercontent.com/Presstotalk123/FYP-Project-Version-1/main/frontend/public/er-shapes.xml";

/** True only for the local palette preview; never in a production build. */
export const ER_LIBRARY_IS_LOCAL = /^https?:\/\/(localhost|127\.0\.0\.1)[:/]/.test(
  process.env.NEXT_PUBLIC_ER_SHAPES_URL ?? "",
);

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
