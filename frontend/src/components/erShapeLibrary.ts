// Locks the embedded draw.io palette to a fixed set of stock ER shapes.
//
// draw.io is loaded with `configure=1`, so on startup it asks the host page for a
// configuration (see DrawioBoard's `configure` handshake). We answer with a single
// custom library and an empty "More Shapes" list, so the sidebar can only ever offer
// these shapes — nothing else can be dragged in.
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
//
// ER_MXLIBRARY below is GENERATED from this table, not hand-written. draw.io library
// entries store their `xml` deflate-compressed (base64 of pako.deflateRaw of the
// URI-encoded mxGraphModel) — plain XML is rejected by the loader. To change a shape,
// edit the spec and regenerate with this Node recipe:
//
//   const zlib = require("zlib");
//   const esc = v => v.replace(/&/g,"&amp;").replace(/</g,"&lt;")
//                      .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
//   const entryXml = s => `<mxGraphModel><root><mxCell id="0"/>`
//     + `<mxCell id="1" parent="0"/>`
//     + `<mxCell id="2" value="${esc(s.value)}" style="${esc(s.style)}" vertex="1" parent="1">`
//     + `<mxGeometry x="0" y="0" width="${s.w}" height="${s.h}" as="geometry"/></mxCell>`
//     + `</root></mxGraphModel>`;
//   const compress = xml => zlib.deflateRawSync(
//     Buffer.from(encodeURIComponent(xml),"utf8")).toString("base64");
//   const entries = SHAPES.map(s => ({ xml: compress(entryXml(s)),
//     w: s.w, h: s.h, aspect: "fixed", title: s.title }));
//   console.log("<mxlibrary>" + JSON.stringify(entries) + "</mxlibrary>");
//
// SHAPES spec (title, style, value, w, h):
//   Entity                   | rounded=0;whitespace=wrap;html=1;                          | "Entity"      | 120x60
//   Weak Entity              | shape=ext;double=1;whitespace=wrap;html=1;                 | "Weak Entity" | 120x60
//   Relationship             | rhombus;whitespace=wrap;html=1;                            | "Relationship"| 120x80
//   Identifying Relationship | rhombus;double=1;whitespace=wrap;html=1;                   | "Identifying" | 120x80
//   Attribute                | ellipse;whitespace=wrap;html=1;                            | "Attribute"   | 120x60
//   Key Attribute            | ellipse;whitespace=wrap;html=1;                            | "<u>Key</u>"  | 120x60
//   Triangle                 | triangle;whitespace=wrap;html=1;                           | ""            | 80x80
//   Arc                      | shape=mxgraph.basic.arc;html=1;startAngle=0.15;endAngle=0.55;arcWidth=0.5;fillColor=none; | "" | 100x100

const ER_MXLIBRARY =
  '<mxlibrary>[{"xml":"jZHNCoMwEISfZu9xA30Af099iNAsJhCNxLXq2xdNrPUg9Jb5hhmWCciiW5qgBvP0mhzICmQRvOf46paCnAMUVoMsAVEAImB942a7KwYVqOd/AhgDb+UmiqTq2fIa8cirSzj4qde0pQTIfDaWaRzUa3PnoAaQueHOgSwzkHkqpcC03B62o3RVQ74jDiugWH7PFutFzVazSemDGbKtSZWPxNQYdfutPScArNMKhzzX3r3LZ3wA","w":120,"h":60,"aspect":"fixed","title":"Entity"},{"xml":"jZHBDoIwDIafpvfRJT4AiJw8e57SuMXBllFkvL2BTZGDibf+/5e/61qQVReboLw+u5YsyBpkFZzjVHWxImsBhWlBHgFRACLg6QctViq8CtTzPwFMgaeyIyXnQuoBKOqeDc+JDjzbTAet/FJSZJBl68brSgqQ5aQN0+DVbTGmoDzIUnNnM84PUWCKP4ddrTxpQ64jDjOgiN9fEfNOTaZlndNvT5O569zykD01JH3/tN3WAnjKm3nL7QIr2x3oBQ==","w":120,"h":60,"aspect":"fixed","title":"Weak Entity"},{"xml":"jZHBDsIgEES/Zu+4XDy3tZ68+AdoN4UECoHVtn9vLGjtoYk3Zl5mMllA1m46RxX0xXdkQZ5A1tF7zi831WQtoDAdyAYQBSACtjv0sFARVKSB/wlgDjyVfVB2rmQVGz8kbUKGiWdbYNTe3R4JZDVqw5SCur/JGFUAWWl2FmRzAFmVWopM0+60xSq7zuQdcZwBxfQ7XMwbNZqOdUl/PE2m16XyWDyVsu6/tesRANtyh49c772wzXe8AA==","w":120,"h":80,"aspect":"fixed","title":"Relationship"},{"xml":"jZHNDsIgEISfZu+4XDy3/sSDD0FlLSRQGrq15O2NhVo9mHhjvsksywCy9ukcVW+uQZMDeQRZxxA4n3yqyTlAYTXIAyAKQAQ8/XB3iyt6FanjfwKYAw/lRsrkoqlje59t12Zv4NkVL5rgm3EAWekwNgvdgawmY5mGXt1eYIqqB1kZ9q7Y5QqKTOnnmgsqO54peOI4A4r0+Qgxf6nJajYlvTJDtjVl5L4wNWTdvsduhQCeSier3LpfvK+veQI=","w":120,"h":80,"aspect":"fixed","title":"Identifying Relationship"},{"xml":"jZHBDoIwEES/Zu9lm3gXEE5+RJUNbdJKUxYpf2+kVeRA4q0zLzOZbEFWLrZBeX0dOrIgLyCrMAycXi5WZC2gMB3IGhAFIAI2B7RYqfAq0IP/CWAKPJWdKDln5mBuE1MiIy82E7LW+JFAlrM2TKNX9zeZg/IgS83OgqwLkGXupMAUD3etVh7V0uCIwwIo4u9qsezUbDrWOf3xNJle58pT9tSYdP+t3S4A2OQjfOR27JXt/uIF","w":120,"h":60,"aspect":"fixed","title":"Attribute"},{"xml":"jZFNjoMwDIVP8/apI3EAaOliNIeIBotEMkMU3AK3H5UE2i4qzc7vPX2Wf2CbYbkmF/332LHAXmCbNI6aq2FpWARkQgd7BpEBEaj9kJ621ESX+Ff/A1AG7k5unB1QJQpb30BV/yi+eN09UHvYGZx0lQKySIgTw9azD8pTdD+PZE4uwtZeB4E9nw7yzkl5+Tj2ZpWZrzwOrGkFmeV1KbO+qTl06gu9e55D70vLqnhuyro/2j4PBGrLjXb5/MWWvb3qDw==","w":120,"h":60,"aspect":"fixed","title":"Key Attribute"},{"xml":"jZExDoMwDEVP4z11ls5AYeohomKRSAmJglvC7StIWsqA1M3/fdn6tkHWLnVRBX33PVmQN5B19J5z5VJN1gIK04NsAFEAImB74l42VwQVaeR/GjA3vJR9UiYZTLzYAjgaNQ6rqmZtmKagHqs1RxVAVpqdBdlcQFZlFkWmdJpnQyVMR94RxwVQpN+0Yjmo2fSsM7kWpMkMmo9MTVkP36n74oBt2f0j9xtv3uEFbw==","w":80,"h":80,"aspect":"fixed","title":"Triangle"},{"xml":"jZHBbsMgDIafxteIYPUBRrL2tHPPNPECEoQIvI28fZXAlnVSpd3s79cP/m3AzudL1It5CyM5wFfALobApfK5I+dACjsC9iClAClBnp+o7a6KRUea+T8GWQyf2n1QIQUkXl0FyehlK32etjGbm052aHQcAJVh7wD7FlAl1pFf5mm3iaY9ASqax4OcNqLjcLUjm0IA1bt1rgsuRMB+DjMBqjoSRab8NNaOaqYLBU8cV5Ai/w4t1ofuq368uUVlhuxk+A/UqYDp591jgyDPdYnf7XGsXXu45R0=","w":100,"h":100,"aspect":"fixed","title":"Arc"}]</mxlibrary>';

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
