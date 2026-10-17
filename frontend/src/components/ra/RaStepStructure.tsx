'use client';

import { useState } from 'react';
import { RaStep, RaStepFeedback } from '@/types/ra.types';
import { RaCaseView } from './RaCaseView';
import { StepNode } from './RaSteps';
import { RaTable } from './RaTable';

const DIRECTION: Record<RaStepFeedback['status'], { icon: string; label: string; badge: string }> = {
  match: { icon: '✓', label: 'Matches a step of the model solution', badge: 'badge-success' },
  close: { icon: '◐', label: 'Close to a step of the model solution', badge: 'badge-warn' },
  none: { icon: '○', label: 'No matching step in the model solution', badge: 'neutral' },
};

/**
 * Every step of the student's answer, each with a "Show structure" button: its operator
 * tree, its output, and how it compares with the model answer's steps (by content, not
 * by name). `showDirection` lets a question hide the comparison (e.g. in assessments).
 */
export function RaStepStructure({ feedback, steps, source, showDirection = true }: {
  feedback: RaStepFeedback[];
  /** The same statements evaluated on example data, for the trees and outputs. */
  steps: RaStep[] | null;
  source: 'sample' | 'generated' | null;
  showDirection?: boolean;
}) {
  if (feedback.length === 0) return null;
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      {feedback.map((fb, i) => (
        <StepRow key={i} fb={fb} step={steps?.[i] ?? null} source={source} showDirection={showDirection} />
      ))}
    </div>
  );
}

function StepRow({ fb, step, source, showDirection }: {
  fb: RaStepFeedback;
  step: RaStep | null;
  source: 'sample' | 'generated' | null;
  showDirection: boolean;
}) {
  const [open, setOpen] = useState(false);
  const d = DIRECTION[fb.status];
  const tree = step?.tree;
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius)', background: 'var(--surface)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', flexWrap: 'wrap' }}>
        {showDirection && (
          <span className={`badge ${d.badge}`} title={d.label} aria-label={d.label} style={{ fontSize: 13 }}>{d.icon}</span>
        )}
        <code style={{ fontSize: 13, whiteSpace: 'pre-wrap', flex: '1 1 260px', minWidth: 0, overflowWrap: 'anywhere' }}>
          {fb.name ? `${fb.name} := ` : ''}{fb.text}
        </code>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ minHeight: 28, padding: '0 10px', fontSize: 12 }}
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          {open ? 'Hide structure' : 'Show structure'}
        </button>
      </div>
      {open && (
        <div style={{ borderTop: '1px solid var(--border)', padding: 12, display: 'grid', gap: 14 }}>
          <Section title="Tree">
            {tree ? <StepNode node={tree} depth={0} /> : <Muted>Not available for this step.</Muted>}
          </Section>
          <Section title="Output">
            {tree ? (
              <>
                <Muted>
                  ({tree.columns.join(', ')}) · {tree.row_count} {tree.row_count === 1 ? 'tuple' : 'tuples'}{' '}
                  {source === 'sample' ? "on the question's data" : 'on an example generated database'}
                </Muted>
                <RaTable columns={tree.columns} rows={tree.rows} emptyText="Empty relation" />
              </>
            ) : <Muted>({fb.columns.join(', ')})</Muted>}
          </Section>
          {showDirection && (
            <Section title="Direction">
              <span style={{ fontSize: 13 }}>
                <strong>{d.icon} {d.label}</strong>
                {fb.checkpoint && fb.status !== 'none' && <> — <code>{fb.checkpoint}</code></>}
                {fb.renamed && ' (same tuples, different attribute names)'}
              </span>
              {fb.status === 'close' && (
                <Muted>Same attributes and the same kind of expression as that step, but it gives different tuples on some data. Check its conditions and constants.</Muted>
              )}
              {fb.status === 'none' && (
                <Muted>That&apos;s fine if you are solving it a different way: only the final answer is graded.</Muted>
              )}
              {fb.case && (
                <div style={{ marginTop: 6 }}>
                  <RaCaseView example={fb.case} studentLabel="This step" expectedLabel="The model's step" />
                </div>
              )}
            </Section>
          )}
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.4 }}>{title}</span>
      {children}
    </div>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{children}</span>;
}
