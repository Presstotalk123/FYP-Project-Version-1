'use client';

import React, { useMemo, useState } from 'react';
import dagre from 'dagre';
import { ConceptGraph as ConceptGraphData, MasteryBand } from '@/types/lad.types';

interface ConceptGraphProps {
  data: ConceptGraphData;
  // Optional per-concept class average, keyed by concept id (for the tooltip).
  peerAvgByConcept?: Record<number, number>;
}

// Mastery band -> fill. Sequential ramp from "untouched" (grey) to "mastered".
// Swap these for the project's dataviz palette when one is adopted.
const BAND_FILL: Record<MasteryBand, string> = {
  untouched: '#e5e7eb',
  novice: '#fca5a5',
  developing: '#fcd34d',
  proficient: '#86efac',
  mastered: '#34d399',
};

const BAND_LABEL: Record<MasteryBand, string> = {
  untouched: 'Not started',
  novice: 'Novice',
  developing: 'Developing',
  proficient: 'Proficient',
  mastered: 'Mastered',
};

const NODE_W = 150;
const NODE_H = 46;

export function ConceptGraph({ data, peerAvgByConcept }: ConceptGraphProps) {
  const [hovered, setHovered] = useState<number | null>(null);

  const layout = useMemo(() => {
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: 'LR', nodesep: 24, ranksep: 70, marginx: 20, marginy: 20 });
    g.setDefaultEdgeLabel(() => ({}));

    const nodeIds = new Set(data.nodes.map((n) => n.id));
    for (const n of data.nodes) {
      g.setNode(String(n.id), { width: NODE_W, height: NODE_H });
    }
    for (const e of data.edges) {
      // Only wire edges whose endpoints are both present, so a deactivated
      // concept's dangling prerequisite edge doesn't spawn a phantom dagre node.
      if (nodeIds.has(e.from) && nodeIds.has(e.to)) {
        g.setEdge(String(e.from), String(e.to));
      }
    }
    dagre.layout(g);

    const size = g.graph() as { width?: number; height?: number };
    const positions: Record<number, { x: number; y: number }> = {};
    for (const n of data.nodes) {
      const gn = g.node(String(n.id));
      if (gn) positions[n.id] = { x: gn.x, y: gn.y };
    }
    const edgePaths = data.edges
      .map((e) => {
        const a = positions[e.from];
        const b = positions[e.to];
        if (!a || !b) return null;
        return { from: e.from, to: e.to, a, b };
      })
      .filter(Boolean) as { from: number; to: number; a: { x: number; y: number }; b: { x: number; y: number } }[];

    return {
      width: size.width ?? 800,
      height: size.height ?? 400,
      positions,
      edgePaths,
    };
  }, [data]);

  if (!data.nodes.length) {
    return <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>No concepts to display yet.</p>;
  }

  return (
    <div style={{ width: '100%', overflowX: 'auto' }}>
      <svg
        width={layout.width}
        height={layout.height}
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        style={{ maxWidth: '100%', height: 'auto', minWidth: Math.min(layout.width, 320) }}
        role="img"
        aria-label="Concept dependency graph coloured by your mastery"
      >
        <defs>
          <marker
            id="lad-arrow" viewBox="0 0 10 10" refX="9" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
          </marker>
        </defs>

        {/* Prerequisite edges */}
        {layout.edgePaths.map((e, i) => (
          <line
            key={`e-${i}`}
            x1={e.a.x + NODE_W / 2}
            y1={e.a.y}
            x2={e.b.x - NODE_W / 2}
            y2={e.b.y}
            stroke="#94a3b8"
            strokeWidth={1.5}
            markerEnd="url(#lad-arrow)"
            opacity={hovered == null || hovered === e.from || hovered === e.to ? 0.9 : 0.25}
          />
        ))}

        {/* Concept nodes */}
        {data.nodes.map((n) => {
          const pos = layout.positions[n.id];
          if (!pos) return null;
          const fill = BAND_FILL[n.mastery_band];
          const peer = peerAvgByConcept?.[n.id];
          const tooltip =
            `${n.display_name} — ${BAND_LABEL[n.mastery_band]}` +
            (n.mastery_level != null ? ` (${Math.round(n.mastery_level * 100)}%)` : '') +
            (peer != null ? ` · class avg ${Math.round(peer * 100)}%` : '');
          return (
            <g
              key={n.id}
              transform={`translate(${pos.x - NODE_W / 2}, ${pos.y - NODE_H / 2})`}
              onMouseEnter={() => setHovered(n.id)}
              onMouseLeave={() => setHovered(null)}
              style={{ cursor: 'default' }}
            >
              <title>{tooltip}</title>
              <rect
                width={NODE_W}
                height={NODE_H}
                rx={8}
                fill={fill}
                stroke={hovered === n.id ? '#0f172a' : '#0f172a22'}
                strokeWidth={hovered === n.id ? 2 : 1}
              />
              <text
                x={NODE_W / 2}
                y={NODE_H / 2}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={12}
                fontWeight={600}
                fill="#0f172a"
              >
                {n.display_name.length > 20 ? n.display_name.slice(0, 19) + '…' : n.display_name}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginTop: 8 }}>
        {(Object.keys(BAND_FILL) as MasteryBand[]).map((band) => (
          <span key={band} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-muted)' }}>
            <span style={{ width: 12, height: 12, borderRadius: 3, background: BAND_FILL[band], display: 'inline-block', border: '1px solid #0f172a22' }} />
            {BAND_LABEL[band]}
          </span>
        ))}
      </div>
    </div>
  );
}
