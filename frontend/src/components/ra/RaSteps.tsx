'use client';

import { useState } from 'react';
import { RaStep, RaStepNode } from '@/types/ra.types';
import { RaTable } from './RaTable';

const OP_NAMES: Record<string, string> = {
  relation: 'Relation',
  select: 'Selection',
  project: 'Projection',
  rename: 'Rename',
  distinct: 'Duplicate elimination',
  group: 'Grouping & aggregation',
  product: 'Cartesian product',
  natural_join: 'Natural join',
  theta_join: 'Theta join',
  left_join: 'Left outer join',
  right_join: 'Right outer join',
  full_join: 'Full outer join',
  union: 'Union',
  intersect: 'Intersection',
  difference: 'Difference',
  division: 'Division',
};

/** One node of the expression tree: its operator, result size and (on demand) its tuples. */
function StepNode({ node, depth }: { node: RaStepNode; depth: number }) {
  // The top of each statement starts open; inputs start closed to keep the view short.
  const [open, setOpen] = useState(depth === 0);
  const isLeaf = node.children.length === 0;
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={{
          display: 'flex', alignItems: 'center', gap: 8, width: '100%', textAlign: 'left',
          padding: '6px 10px', borderRadius: 'var(--radius)', cursor: 'pointer',
          border: '1px solid var(--border)', background: isLeaf ? 'var(--surface-muted)' : 'var(--surface)',
        }}
      >
        <span style={{ fontSize: 11, color: 'var(--text-muted)', width: 10 }}>{open ? '▾' : '▸'}</span>
        <code style={{ fontSize: 13, fontWeight: 700, color: 'var(--brand-charcoal)', whiteSpace: 'pre-wrap' }}>
          {node.label}
        </code>
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{OP_NAMES[node.op] ?? node.op}</span>
        <span className="badge neutral" style={{ marginLeft: 'auto' }}>
          {node.row_count} {node.row_count === 1 ? 'tuple' : 'tuples'}
        </span>
      </button>
      {open && (
        <div style={{ paddingLeft: 18, display: 'grid', gap: 6 }}>
          <RaTable columns={node.columns} rows={node.rows} emptyText="Empty relation" />
          {node.row_count > node.rows.length && (
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              Showing the first {node.rows.length} of {node.row_count} tuples.
            </span>
          )}
        </div>
      )}
      {node.children.length > 0 && (
        <div style={{ borderLeft: '2px solid var(--border)', marginLeft: 12, paddingLeft: 12, display: 'grid', gap: 8 }}>
          {node.children.map((child, i) => (
            <StepNode key={i} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

/** Every statement of the answer, as on the lecture slides: R1, R2, … then the answer. */
export function RaSteps({ steps }: { steps: RaStep[] }) {
  if (steps.length === 0) {
    return <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>No steps to show.</p>;
  }
  return (
    <div style={{ display: 'grid', gap: 18 }}>
      <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
        Each operator&apos;s intermediate result. Click an
        operator to see its tuples; its inputs are listed underneath it.
      </p>
      {steps.map((step, i) => (
        <div key={i} style={{ display: 'grid', gap: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 700 }}>
            {step.name ? `${step.name} :=` : 'Answer'}
            {step.line ? <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}> (line {step.line})</span> : null}
          </span>
          <StepNode node={step.tree} depth={0} />
        </div>
      ))}
    </div>
  );
}
