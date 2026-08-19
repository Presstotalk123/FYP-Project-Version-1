'use client';

import { useMemo } from 'react';
import dagre from 'dagre';
import { buildQueryGraph } from '@/utils/queryGraph';
import { isQueryGraphError, GraphNode, GraphGroup, GraphEdge } from '@/types/queryGraph.types';

interface QueryGraphProps {
  query: string;
  /** Raw CREATE TABLE DDL (concatenated). Enables junction detection + full column lists. */
  schemaSql?: string | null;
}

/* ── layout constants ── */
const HEADER_H = 36;
const ROW_H = 26;
const PAD = 14;
const MIN_W = 176;
const MAX_W = 360;
const JUNCTION_R = 46;
const CHAR_TITLE = 7.6;
const CHAR_COL = 7;
const CHAR_FILTER = 6.6;
const GRP_PILL_W = 52;
const CLUSTER_PAD = 26; // extra space dagre reserves inside clusters

function measure(node: GraphNode): { width: number; height: number } {
  if (node.kind === 'junction') {
    return { width: JUNCTION_R * 2, height: JUNCTION_R * 2 };
  }
  if (node.kind === 'agg') {
    const lines = [...(node.agg?.aggregates ?? [])];
    if (node.agg?.having) lines.push(`HAVING ${node.agg.having}`);
    const longest = lines.reduce((m, l) => Math.max(m, l.length), 'Aggregation'.length);
    return {
      width: Math.min(MAX_W, Math.max(160, longest * CHAR_FILTER + PAD * 2 + 14)),
      height: HEADER_H + lines.length * ROW_H + PAD,
    };
  }
  const titleW =
    node.table.length * CHAR_TITLE + (node.alias ? node.alias.length * 7 + 18 : 0);
  let colW = 0;
  for (const c of node.columns) {
    let w = c.name.length * CHAR_COL + (c.pk ? 24 : 0) + (c.grouped ? GRP_PILL_W : 0);
    if (c.filter) w += c.filter.length * CHAR_FILTER + 12;
    colW = Math.max(colW, w);
  }
  const width = Math.min(MAX_W, Math.max(MIN_W, Math.max(titleW, colW) + PAD * 2));
  const height = HEADER_H + Math.max(1, node.columns.length) * ROW_H + PAD;
  return { width, height };
}

interface Point {
  x: number;
  y: number;
}

/**
 * Anchor an edge endpoint on the row of the joined column, on the box side that
 * faces the other node. Junction/agg nodes (and missing columns) anchor at the
 * node's vertical centre — for a circle that lands on its boundary.
 */
function anchorFor(p: Placed, columnName: string | undefined, otherCx: number): Point {
  const leftSide = otherCx < p.cx;
  const x = leftSide ? p.cx - p.w / 2 : p.cx + p.w / 2;
  const node = p.node;
  if (node.kind === 'entity' && node.columns.length) {
    let idx = -1;
    if (columnName) {
      idx = node.columns.findIndex((c) => c.name.toLowerCase() === columnName.toLowerCase());
    }
    if (idx < 0) idx = node.columns.findIndex((c) => c.projected);
    if (idx >= 0) {
      const top = p.cy - p.h / 2;
      return { x, y: top + HEADER_H + idx * ROW_H + ROW_H / 2 };
    }
  }
  return { x, y: p.cy };
}

function curveControls(a: Point, b: Point): { c1: Point; c2: Point } {
  const sign = Math.sign(b.x - a.x) || 1;
  const dx = Math.max(30, Math.abs(b.x - a.x) * 0.5);
  return { c1: { x: a.x + sign * dx, y: a.y }, c2: { x: b.x - sign * dx, y: b.y } };
}

/** A horizontal-tangent cubic bézier between two anchor points. */
function edgeCurve(a: Point, b: Point): string {
  const { c1, c2 } = curveControls(a, b);
  return `M ${a.x} ${a.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${b.x} ${b.y}`;
}

/** A point on that same curve at parameter t (0 = a, 1 = b). */
function curvePoint(a: Point, b: Point, t: number): Point {
  const { c1, c2 } = curveControls(a, b);
  const mt = 1 - t;
  return {
    x: mt * mt * mt * a.x + 3 * mt * mt * t * c1.x + 3 * mt * t * t * c2.x + t * t * t * b.x,
    y: mt * mt * mt * a.y + 3 * mt * mt * t * c1.y + 3 * mt * t * t * c2.y + t * t * t * b.y,
  };
}

function groupDepth(g: GraphGroup, byId: Map<string, GraphGroup>): number {
  let d = 0;
  let cur: GraphGroup | undefined = g;
  while (cur && cur.parentGroupId) {
    d++;
    cur = byId.get(cur.parentGroupId);
  }
  return d;
}

/** Pixel width of a rendered edge-label pill — must match EdgeLabel's own layout.
 *  Uses CHAR_FILTER, the file's measured width for this exact font/size (11px mono). */
function labelBoxWidth(text: string): number {
  return text.length * CHAR_FILTER + 12;
}

const LABEL_H = 20;
const LABEL_GAP = 10; // minimum breathing room enforced between two label pills
const LABEL_T_MIN = 0.2;
const LABEL_T_MAX = 0.8;
const LABEL_T_STEP = 0.08;

// Distinct hues cycled across join/subquery edges so overlapping lines and
// their label pills stay visually distinguishable from one another. Separate
// from GraphNode.color (table identity) — this is per-connection, not per-table.
const EDGE_PALETTE = ['#2563eb', '#dc2626', '#059669', '#d97706', '#7c3aed', '#0891b2', '#db2777', '#65a30d'];

/**
 * Place each edge's label pill on its own curve, sliding away from the
 * midpoint (t = 0.5) toward whichever nearby point on the *same* curve
 * doesn't collide with an already-placed label. The label always sits
 * exactly on its line — never off to the side — so the line visibly flows
 * through the pill no matter how it had to move to avoid a collision.
 */
function placeEdgeLabels(
  routed: { edge: GraphEdge; p1: Point; p2: Point; labelX: number; labelY: number }[],
): void {
  const placedBoxes: { x: number; y: number; w: number; h: number }[] = [];

  const order = routed
    .map((_, i) => i)
    .filter((i) => routed[i].edge.label)
    // Fixed left-to-right, top-to-bottom order keeps placement stable and
    // independent of edge parse order.
    .sort((i, j) => routed[i].p1.x - routed[j].p1.x || routed[i].p1.y - routed[j].p1.y || i - j);

  for (const i of order) {
    const re = routed[i];
    const w = labelBoxWidth(re.edge.label);

    const candidates = [0.5];
    for (let d = LABEL_T_STEP; 0.5 - d >= LABEL_T_MIN || 0.5 + d <= LABEL_T_MAX; d += LABEL_T_STEP) {
      if (0.5 - d >= LABEL_T_MIN) candidates.push(0.5 - d);
      if (0.5 + d <= LABEL_T_MAX) candidates.push(0.5 + d);
    }

    let chosen = curvePoint(re.p1, re.p2, 0.5);
    for (const t of candidates) {
      const p = curvePoint(re.p1, re.p2, t);
      const collides = placedBoxes.some(
        (bx) => Math.abs(p.x - bx.x) * 2 < w + bx.w + LABEL_GAP && Math.abs(p.y - bx.y) * 2 < LABEL_H + bx.h + LABEL_GAP,
      );
      if (!collides) {
        chosen = p;
        break;
      }
    }

    re.labelX = chosen.x;
    re.labelY = chosen.y;
    placedBoxes.push({ x: chosen.x, y: chosen.y, w, h: LABEL_H });
  }
}

export function QueryGraph({ query, schemaSql }: QueryGraphProps) {
  const layout = useMemo(() => {
    const result = buildQueryGraph(query, schemaSql);
    if (isQueryGraphError(result)) return { error: result.error };

    const { nodes, edges, groups, notes } = result;
    const nodeById = new Map(nodes.map((n) => [n.id, n]));
    const groupById = new Map(groups.map((g) => [g.id, g]));

    const g = new dagre.graphlib.Graph({ compound: true, multigraph: true });
    g.setGraph({ rankdir: 'LR', nodesep: 34, ranksep: 84, marginx: 24, marginy: 24 });
    g.setDefaultEdgeLabel(() => ({}));

    // Cluster nodes first, then nesting.
    for (const grp of groups) g.setNode(grp.id, { label: grp.label });

    const dims = new Map<string, { width: number; height: number }>();
    for (const n of nodes) {
      const d = measure(n);
      dims.set(n.id, d);
      g.setNode(n.id, { width: d.width, height: d.height });
      if (n.groupId) g.setParent(n.id, n.groupId);
    }
    for (const grp of groups) {
      if (grp.parentGroupId) g.setParent(grp.id, grp.parentGroupId);
    }

    edges.forEach((e, i) => {
      const labelW = e.label ? e.label.length * 6 + 12 : 0;
      g.setEdge(e.from, e.to, { width: labelW, height: e.label ? 20 : 0, labelpos: 'c' }, `e${i}`);
    });

    dagre.layout(g);

    const placed = nodes.map((n) => {
      const p = g.node(n.id) as { x: number; y: number };
      const d = dims.get(n.id)!;
      return { node: n, cx: p.x, cy: p.y, w: d.width, h: d.height };
    });

    const placedGroups = groups
      .map((grp) => {
        const p = g.node(grp.id) as { x: number; y: number; width: number; height: number };
        return {
          group: grp,
          x: p.x - p.width / 2,
          y: p.y - p.height / 2,
          w: p.width,
          h: p.height,
          depth: groupDepth(grp, groupById),
        };
      })
      .sort((a, b) => a.depth - b.depth); // outer clusters drawn first

    // Draw edges anchored to the joined column rows (dagre still spaced the nodes).
    const placedById = new Map(placed.map((p) => [p.node.id, p]));
    const routedEdges = edges
      // Aggregation cards are anchored by an invisible layout edge — don't draw it.
      .filter((e) => nodeById.get(e.to)?.kind !== 'agg')
      .map((e, i) => {
        const a = placedById.get(e.from);
        const b = placedById.get(e.to);
        if (!a || !b) return null;
        const p1 = anchorFor(a, e.fromColumn, b.cx);
        const p2 = anchorFor(b, e.toColumn, a.cx);
        const color = EDGE_PALETTE[i % EDGE_PALETTE.length];
        return { edge: e, p1, p2, path: edgeCurve(p1, p2), color, labelX: 0, labelY: 0 };
      })
      .filter((re): re is NonNullable<typeof re> => re !== null);

    // Place each label on its own curve, sliding away from the midpoint only
    // far enough to clear a collision with another label.
    placeEdgeLabels(routedEdges);

    const size = g.graph() as { width?: number; height?: number };
    return {
      placed,
      placedGroups,
      routedEdges,
      notes,
      width: size.width ?? 400,
      height: size.height ?? 300,
    };
  }, [query, schemaSql]);

  if ('error' in layout) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          padding: 24,
          textAlign: 'center',
          color: 'var(--text-muted)',
          fontSize: 13,
        }}
      >
        {layout.error}
      </div>
    );
  }

  const { placed, placedGroups, routedEdges, notes, width, height } = layout;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Legend */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 14,
          padding: '8px 12px',
          borderBottom: '1px solid var(--border)',
          fontSize: 11,
          color: 'var(--text-muted)',
          flexShrink: 0,
        }}
      >
        <LegendItem>
          <span style={swatch('box')} /> Table
        </LegendItem>
        <LegendItem>
          <span style={swatch('circle')} /> Link table
        </LegendItem>
        <LegendItem>
          <span style={swatch('proj')} /> Selected column
        </LegendItem>
        <LegendItem>
          <span style={{ fontSize: 9, fontWeight: 700, color: 'var(--brand-lilac)' }}>grouped</span>{' '}
          GROUP BY
        </LegendItem>
        <LegendItem>
          <span style={{ fontFamily: 'var(--font-geist-mono)', color: 'var(--brand-lilac)' }}>&lt; 10</span>{' '}
          Filter
        </LegendItem>
        <LegendItem>
          <span style={swatch('cluster')} /> Subquery
        </LegendItem>
        <LegendItem>
          <svg width="22" height="8" aria-hidden="true">
            <line x1="0" y1="4" x2="22" y2="4" stroke="var(--border-strong)" strokeWidth="1.5" strokeDasharray="4 3" />
          </svg>
          Subquery link
        </LegendItem>
        <LegendItem>
          <svg width="22" height="8" aria-hidden="true">
            <line x1="0" y1="4" x2="22" y2="4" stroke="var(--border-strong)" strokeWidth="2.5" />
          </svg>
          Set operation
        </LegendItem>
      </div>

      {/* Diagram (scrollable) */}
      <div style={{ flex: 1, overflow: 'auto', padding: 12 }}>
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: 'block' }}>
          {/* Subquery clusters (behind everything) */}
          {placedGroups.map((pg) => (
            <g key={`grp-${pg.group.id}`}>
              <rect
                x={pg.x}
                y={pg.y}
                width={pg.w}
                height={pg.h}
                rx={12}
                fill="var(--surface-brand)"
                fillOpacity={0.7}
                stroke="var(--brand-lilac)"
                strokeWidth={1.5}
                strokeDasharray="6 4"
              />
              <text
                x={pg.x + 10}
                y={pg.y + 14}
                fontSize={11}
                fontWeight={700}
                fill="var(--brand-lilac)"
                style={{ textTransform: 'uppercase', letterSpacing: '0.04em' }}
              >
                {pg.group.label}
              </text>
            </g>
          ))}

          {/* Edges */}
          {routedEdges.map((re, i) => (
            <g key={`edge-${i}`}>
              <path
                d={re.path}
                fill="none"
                stroke={re.color}
                strokeWidth={re.edge.kind === 'setop' ? 2.5 : 1.5}
                strokeDasharray={re.edge.kind === 'subquery' ? '6 4' : undefined}
              />
              {re.edge.label && (
                <EdgeLabel x={re.labelX} y={re.labelY} text={re.edge.label} color={re.color} bold={re.edge.kind !== 'join'} />
              )}
            </g>
          ))}

          {/* Nodes */}
          {placed.map((p) =>
            p.node.kind === 'junction' ? (
              <JunctionNode key={p.node.id} p={p} />
            ) : p.node.kind === 'agg' ? (
              <AggNode key={p.node.id} p={p} />
            ) : (
              <EntityNode key={p.node.id} p={p} />
            ),
          )}
        </svg>

        {notes.length > 0 && (
          <ul style={{ margin: '12px 0 0', padding: '0 0 0 16px', fontSize: 11, color: 'var(--text-muted)' }}>
            {notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/* ────────────────────────── sub-components ────────────────────────── */

function swatch(kind: 'box' | 'circle' | 'proj' | 'cluster'): React.CSSProperties {
  const base: React.CSSProperties = { display: 'inline-block', width: 12, height: 12, marginRight: 1 };
  switch (kind) {
    case 'box':
      return { ...base, width: 14, height: 10, border: '1.5px solid var(--border-strong)', borderRadius: 2, background: 'var(--surface)' };
    case 'circle':
      return { ...base, borderRadius: '50%', border: '1.5px solid var(--brand-lilac)', background: 'var(--surface-brand)' };
    case 'proj':
      return { ...base, width: 10, height: 10, borderRadius: 2, background: 'var(--brand-lilac)' };
    case 'cluster':
      return { ...base, width: 14, height: 10, border: '1.5px dashed var(--brand-lilac)', borderRadius: 3, background: 'var(--surface-brand)' };
  }
}

function LegendItem({ children }: { children: React.ReactNode }) {
  return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>{children}</span>;
}

interface Placed {
  node: GraphNode;
  cx: number;
  cy: number;
  w: number;
  h: number;
}

function EntityNode({ p }: { p: Placed }) {
  const { node, cx, cy, w, h } = p;
  const x = cx - w / 2;
  const y = cy - h / 2;
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={8} fill="var(--surface)" stroke="var(--border-strong)" strokeWidth={1.5} />
      {/* Header */}
      <path
        d={`M ${x} ${y + 8} Q ${x} ${y} ${x + 8} ${y} L ${x + w - 8} ${y} Q ${x + w} ${y} ${x + w} ${y + 8} L ${x + w} ${y + HEADER_H} L ${x} ${y + HEADER_H} Z`}
        fill={node.color + '1a'}
      />
      <line x1={x} y1={y + HEADER_H} x2={x + w} y2={y + HEADER_H} stroke="var(--border)" strokeWidth={1} />
      <text x={x + PAD} y={y + HEADER_H / 2} dominantBaseline="central" fontSize={13} fontWeight={700} fill="var(--text)">
        {node.table}
      </text>
      {node.alias && (
        <text x={x + w - PAD} y={y + HEADER_H / 2} dominantBaseline="central" textAnchor="end" fontSize={12} fontWeight={700} fill={node.color}>
          {node.alias}
        </text>
      )}
      {/* Columns */}
      {node.columns.map((c, i) => {
        const rowY = y + HEADER_H + i * ROW_H;
        let nameEnd = x + PAD + c.name.length * CHAR_COL + 6;
        return (
          <g key={c.name + i}>
            {c.projected && (
              <rect x={x + 3} y={rowY + 2} width={w - 6} height={ROW_H - 4} rx={4} fill={node.color + '14'} />
            )}
            <text x={x + PAD} y={rowY + ROW_H / 2} dominantBaseline="central" fontSize={12} fontWeight={c.projected ? 700 : 400} fill="var(--text)">
              {c.name}
            </text>
            {c.pk && (
              <text x={nameEnd} y={rowY + ROW_H / 2} dominantBaseline="central" fontSize={9} fontWeight={700} fill="var(--text-muted)">
                PK
              </text>
            )}
            {c.grouped &&
              (() => {
                const gx = nameEnd + (c.pk ? 18 : 0);
                nameEnd = gx + GRP_PILL_W;
                return (
                  <>
                    <rect x={gx} y={rowY + 4} width={GRP_PILL_W - 6} height={ROW_H - 8} rx={7} fill="var(--brand-lilac)" fillOpacity={0.15} />
                    <text x={gx + (GRP_PILL_W - 6) / 2} y={rowY + ROW_H / 2} dominantBaseline="central" textAnchor="middle" fontSize={9} fontWeight={700} fill="var(--brand-lilac)">
                      grouped
                    </text>
                  </>
                );
              })()}
            {c.filter && (
              <text x={x + w - PAD} y={rowY + ROW_H / 2} dominantBaseline="central" textAnchor="end" fontSize={11} fontFamily="var(--font-geist-mono)" fill={node.color}>
                {c.filter}
              </text>
            )}
          </g>
        );
      })}
    </g>
  );
}

function JunctionNode({ p }: { p: Placed }) {
  const { node, cx, cy } = p;
  return (
    <g>
      <circle cx={cx} cy={cy} r={JUNCTION_R} fill={node.color + '1a'} stroke={node.color} strokeWidth={2} />
      <text x={cx} y={cy - (node.alias ? 6 : 0)} textAnchor="middle" dominantBaseline="central" fontSize={12} fontWeight={700} fill="var(--text)">
        {node.table}
      </text>
      {node.alias && (
        <text x={cx} y={cy + 12} textAnchor="middle" dominantBaseline="central" fontSize={11} fontWeight={700} fill={node.color}>
          {node.alias}
        </text>
      )}
    </g>
  );
}

function AggNode({ p }: { p: Placed }) {
  const { node, cx, cy, w, h } = p;
  const x = cx - w / 2;
  const y = cy - h / 2;
  const aggregates = node.agg?.aggregates ?? [];
  const having = node.agg?.having ?? null;
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={8} fill="var(--surface-muted)" stroke="var(--border-strong)" strokeWidth={1.5} strokeDasharray="2 2" />
      <text x={x + PAD} y={y + HEADER_H / 2} dominantBaseline="central" fontSize={12} fontWeight={700} fill="var(--text-muted)">
        Σ Aggregation
      </text>
      <line x1={x} y1={y + HEADER_H} x2={x + w} y2={y + HEADER_H} stroke="var(--border)" strokeWidth={1} />
      {aggregates.map((a, i) => (
        <text key={i} x={x + PAD} y={y + HEADER_H + i * ROW_H + ROW_H / 2} dominantBaseline="central" fontSize={11} fontFamily="var(--font-geist-mono)" fill="var(--text)">
          {a}
        </text>
      ))}
      {having && (
        <text
          x={x + PAD}
          y={y + HEADER_H + aggregates.length * ROW_H + ROW_H / 2}
          dominantBaseline="central"
          fontSize={11}
          fontFamily="var(--font-geist-mono)"
          fontWeight={700}
          fill="var(--brand-lilac)"
        >
          HAVING {having}
        </text>
      )}
    </g>
  );
}

function EdgeLabel({ x, y, text, color, bold }: { x: number; y: number; text: string; color: string; bold?: boolean }) {
  const w = labelBoxWidth(text);
  return (
    <g>
      <rect x={x - w / 2} y={y - 10} width={w} height={20} rx={4} fill="var(--surface)" stroke={color} strokeWidth={1} />
      <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fontSize={11} fontFamily="var(--font-geist-mono)" fontWeight={bold ? 700 : 400} fill={color}>
        {text}
      </text>
    </g>
  );
}
