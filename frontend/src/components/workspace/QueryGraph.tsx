'use client';

import { useMemo } from 'react';
import dagre from 'dagre';
import { buildQueryGraph } from '@/utils/queryGraph';
import { isQueryGraphError, GraphNode } from '@/types/queryGraph.types';

interface QueryGraphProps {
  query: string;
  /** Raw CREATE TABLE DDL (concatenated). Enables junction detection + full column lists. */
  schemaSql?: string | null;
}

/* ── layout constants ── */
const HEADER_H = 34;
const ROW_H = 24;
const PAD = 12;
const MIN_W = 150;
const MAX_W = 320;
const JUNCTION_R = 46;
const CHAR_TITLE = 7.6;
const CHAR_COL = 7;
const CHAR_FILTER = 6.6;

function measure(node: GraphNode): { width: number; height: number } {
  if (node.kind === 'junction') {
    return { width: JUNCTION_R * 2, height: JUNCTION_R * 2 };
  }
  const titleW =
    node.table.length * CHAR_TITLE + (node.alias ? node.alias.length * 7 + 18 : 0);
  let colW = 0;
  for (const c of node.columns) {
    let w = c.name.length * CHAR_COL + (c.pk ? 24 : 0);
    if (c.filter) w += c.filter.length * CHAR_FILTER + 12;
    colW = Math.max(colW, w);
  }
  const width = Math.min(MAX_W, Math.max(MIN_W, Math.max(titleW, colW) + PAD * 2));
  const height = HEADER_H + Math.max(1, node.columns.length) * ROW_H + PAD;
  return { width, height };
}

/** Build an SVG path string from dagre's edge points. */
function edgePath(points: { x: number; y: number }[]): string {
  if (!points || points.length === 0) return '';
  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length; i++) d += ` L ${points[i].x} ${points[i].y}`;
  return d;
}

export function QueryGraph({ query, schemaSql }: QueryGraphProps) {
  const layout = useMemo(() => {
    const result = buildQueryGraph(query, schemaSql);
    if (isQueryGraphError(result)) return { error: result.error };

    const { nodes, edges, notes } = result;

    const g = new dagre.graphlib.Graph({ multigraph: true });
    g.setGraph({ rankdir: 'LR', nodesep: 36, ranksep: 88, marginx: 24, marginy: 24 });
    g.setDefaultEdgeLabel(() => ({}));

    const dims = new Map<string, { width: number; height: number }>();
    for (const n of nodes) {
      const d = measure(n);
      dims.set(n.id, d);
      g.setNode(n.id, { width: d.width, height: d.height });
    }
    edges.forEach((e, i) => {
      g.setEdge(
        e.from,
        e.to,
        { width: e.label.length * 6 + 12, height: 20, labelpos: 'c' },
        `e${i}`,
      );
    });

    dagre.layout(g);

    const placed = nodes.map((n) => {
      const p = g.node(n.id) as { x: number; y: number };
      const d = dims.get(n.id)!;
      return { node: n, cx: p.x, cy: p.y, w: d.width, h: d.height };
    });

    const routedEdges = edges.map((e, i) => {
      const ge = g.edge(e.from, e.to, `e${i}`) as unknown as {
        points: { x: number; y: number }[];
        x: number;
        y: number;
      };
      return { edge: e, points: ge.points, lx: ge.x, ly: ge.y };
    });

    const size = g.graph() as { width?: number; height?: number };
    return {
      placed,
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

  const { placed, routedEdges, notes, width, height } = layout;

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
          <span
            style={{
              display: 'inline-block',
              width: 14,
              height: 10,
              border: '1.5px solid var(--border-strong)',
              borderRadius: 2,
              background: 'var(--surface)',
            }}
          />
          Table
        </LegendItem>
        <LegendItem>
          <span
            style={{
              display: 'inline-block',
              width: 12,
              height: 12,
              borderRadius: '50%',
              border: '1.5px solid var(--brand-lilac)',
              background: 'var(--surface-brand)',
            }}
          />
          Link table
        </LegendItem>
        <LegendItem>
          <span
            style={{
              display: 'inline-block',
              width: 10,
              height: 10,
              borderRadius: 2,
              background: 'var(--brand-lilac)',
            }}
          />
          Selected column
        </LegendItem>
        <LegendItem>
          <span style={{ fontFamily: 'var(--font-geist-mono)', color: 'var(--brand-lilac)' }}>
            &lt; 10
          </span>
          Filter
        </LegendItem>
        <LegendItem>
          <span style={{ fontWeight: 700, fontSize: 10 }}>PK</span>
          Primary key
        </LegendItem>
      </div>

      {/* Diagram (scrollable) */}
      <div style={{ flex: 1, overflow: 'auto', padding: 12 }}>
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          style={{ display: 'block' }}
        >
          <defs>
            <marker
              id="qg-arrow"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 9 5 L 0 9" fill="none" stroke="var(--border-strong)" strokeWidth="1.5" />
            </marker>
          </defs>

          {/* Edges first, so nodes sit on top */}
          {routedEdges.map((re, i) => (
            <g key={`edge-${i}`}>
              <path
                d={edgePath(re.points)}
                fill="none"
                stroke="var(--border-strong)"
                strokeWidth={1.5}
              />
              {re.edge.label && (
                <EdgeLabel x={re.lx} y={re.ly} text={re.edge.label} />
              )}
            </g>
          ))}

          {/* Nodes */}
          {placed.map((p) =>
            p.node.kind === 'junction' ? (
              <JunctionNode key={p.node.id} p={p} />
            ) : (
              <EntityNode key={p.node.id} p={p} />
            ),
          )}
        </svg>

        {notes.length > 0 && (
          <ul
            style={{
              margin: '12px 0 0',
              padding: '0 0 0 16px',
              fontSize: 11,
              color: 'var(--text-muted)',
            }}
          >
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

function LegendItem({ children }: { children: React.ReactNode }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>{children}</span>
  );
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
      {/* Card */}
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={8}
        fill="var(--surface)"
        stroke="var(--border-strong)"
        strokeWidth={1.5}
      />
      {/* Header */}
      <path
        d={`M ${x} ${y + 8} Q ${x} ${y} ${x + 8} ${y} L ${x + w - 8} ${y} Q ${x + w} ${y} ${x + w} ${y + 8} L ${x + w} ${y + HEADER_H} L ${x} ${y + HEADER_H} Z`}
        fill={node.color + '1a'}
      />
      <line
        x1={x}
        y1={y + HEADER_H}
        x2={x + w}
        y2={y + HEADER_H}
        stroke="var(--border)"
        strokeWidth={1}
      />
      <text
        x={x + PAD}
        y={y + HEADER_H / 2}
        dominantBaseline="central"
        fontSize={13}
        fontWeight={700}
        fill="var(--text)"
      >
        {node.table}
      </text>
      {node.alias && (
        <text
          x={x + w - PAD}
          y={y + HEADER_H / 2}
          dominantBaseline="central"
          textAnchor="end"
          fontSize={12}
          fontWeight={700}
          fill={node.color}
        >
          {node.alias}
        </text>
      )}
      {/* Columns */}
      {node.columns.map((c, i) => {
        const rowY = y + HEADER_H + i * ROW_H;
        return (
          <g key={c.name + i}>
            {c.projected && (
              <rect
                x={x + 3}
                y={rowY + 2}
                width={w - 6}
                height={ROW_H - 4}
                rx={4}
                fill={node.color + '14'}
              />
            )}
            <text
              x={x + PAD}
              y={rowY + ROW_H / 2}
              dominantBaseline="central"
              fontSize={12}
              fontWeight={c.projected ? 700 : 400}
              fill="var(--text)"
            >
              {c.name}
            </text>
            {c.pk && (
              <text
                x={x + PAD + c.name.length * CHAR_COL + 6}
                y={rowY + ROW_H / 2}
                dominantBaseline="central"
                fontSize={9}
                fontWeight={700}
                fill="var(--text-muted)"
              >
                PK
              </text>
            )}
            {c.filter && (
              <text
                x={x + w - PAD}
                y={rowY + ROW_H / 2}
                dominantBaseline="central"
                textAnchor="end"
                fontSize={11}
                fontFamily="var(--font-geist-mono)"
                fill={node.color}
              >
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
      <circle
        cx={cx}
        cy={cy}
        r={JUNCTION_R}
        fill={node.color + '1a'}
        stroke={node.color}
        strokeWidth={2}
      />
      <text
        x={cx}
        y={cy - (node.alias ? 6 : 0)}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={12}
        fontWeight={700}
        fill="var(--text)"
      >
        {node.table}
      </text>
      {node.alias && (
        <text
          x={cx}
          y={cy + 12}
          textAnchor="middle"
          dominantBaseline="central"
          fontSize={11}
          fontWeight={700}
          fill={node.color}
        >
          {node.alias}
        </text>
      )}
    </g>
  );
}

function EdgeLabel({ x, y, text }: { x: number; y: number; text: string }) {
  const w = text.length * 6 + 10;
  return (
    <g>
      <rect
        x={x - w / 2}
        y={y - 10}
        width={w}
        height={20}
        rx={4}
        fill="var(--surface)"
        stroke="var(--border)"
        strokeWidth={1}
      />
      <text
        x={x}
        y={y}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={11}
        fontFamily="var(--font-geist-mono)"
        fill="var(--text-muted)"
      >
        {text}
      </text>
    </g>
  );
}
