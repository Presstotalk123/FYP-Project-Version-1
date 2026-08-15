'use client';

import React from 'react';
import { ConceptNode, PeerBenchmark } from '@/types/lad.types';

interface PeerBenchmarkPanelProps {
  nodes: ConceptNode[];
  benchmark: PeerBenchmark;
}

/**
 * Compares the student's own mastery against the anonymized class average, per
 * concept. Renders a suppression notice when the cohort is too small (the backend
 * enforces the minimum-cohort floor and never returns per-student peer data).
 */
export function PeerBenchmarkPanel({ nodes, benchmark }: PeerBenchmarkPanelProps) {
  if (benchmark.suppressed) {
    const msg =
      benchmark.reason === 'cohort_too_small'
        ? 'Your class is too small to show anonymized peer comparisons.'
        : 'Peer comparison is unavailable (no class group set).';
    return (
      <div className="da-alert alert-info">
        <strong>Peer comparison unavailable</strong>
        <span>{msg}</span>
      </div>
    );
  }

  const avgByConcept: Record<number, number> = {};
  for (const a of benchmark.averages) avgByConcept[a.concept_id] = a.avg_mastery;

  // Only show concepts that either the student or the class has engaged with.
  const rows = nodes
    .map((n) => ({
      node: n,
      you: n.mastery_level,
      peer: avgByConcept[n.id] ?? null,
    }))
    .filter((r) => r.you != null || r.peer != null);

  if (!rows.length) {
    return (
      <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
        No mastery data yet — solve some tagged questions to see how you compare.
      </p>
    );
  }

  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <div style={{ display: 'flex', gap: 16, fontSize: 11, color: 'var(--text-muted)' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 12, height: 12, borderRadius: 3, background: '#2563eb', display: 'inline-block' }} /> You
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 12, height: 12, borderRadius: 3, background: '#94a3b8', display: 'inline-block' }} /> Class average
        </span>
      </div>

      {rows.map(({ node, you, peer }) => (
        <div key={node.id} style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: 10, alignItems: 'center' }}>
          <span style={{ fontSize: 12, fontWeight: 600 }} title={node.display_name}>
            {node.display_name}
          </span>
          <div style={{ display: 'grid', gap: 4 }}>
            <Bar value={you} color="#2563eb" label="You" />
            <Bar value={peer} color="#94a3b8" label="Class" />
          </div>
        </div>
      ))}
    </div>
  );
}

function Bar({ value, color, label }: { value: number | null; color: string; label: string }) {
  const pct = value != null ? Math.round(value * 100) : 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }} aria-label={`${label}: ${value != null ? pct + '%' : 'no data'}`}>
      <div style={{ flex: 1, height: 10, background: '#e5e7eb', borderRadius: 999, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 999 }} />
      </div>
      <span style={{ width: 38, textAlign: 'right', fontSize: 11, color: 'var(--text-muted)' }}>
        {value != null ? `${pct}%` : '—'}
      </span>
    </div>
  );
}
