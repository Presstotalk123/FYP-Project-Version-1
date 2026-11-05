'use client';

import { ReactNode, useState } from 'react';
import { RaBoxCheck, RaError, RaStepMarking, RaStepSpec } from '@/types/ra.types';
import { RaEditor } from './RaEditor';
import { BoxStructure, RaStepResultView } from './RaStepMarking';

/**
 * A multi-step answer: one box per step the professor set, each under its prompt. Box k
 * is named like step k (R1, R2 …, shown in front of it) and may use the earlier steps'
 * names; the last box is the final answer. After Check each box can show its structure
 * (tree and table); after Submit each box shows the marks of its step.
 *
 * Used by students (RaStepsAnswer) and by the staff form's preview (RaStepsPreview).
 */
export function RaStepBoxes({
  steps, values, onChange, names, onRun, toolbar, checked, checkSource, marking, showDirection,
}: {
  steps: RaStepSpec[];
  values: string[];
  onChange: (index: number, value: string) => void;
  /** The schema's relation and attribute names. */
  names: string[];
  onRun?: () => void;
  /** The Check / Submit buttons, shown once above the boxes. */
  toolbar?: ReactNode;
  checked: RaBoxCheck[] | null;
  checkSource: 'sample' | 'example' | 'generated' | null;
  marking: RaStepMarking | null;
  showDirection: boolean;
}) {
  const last = steps.length - 1;
  // Which step each box earned, when it is another one (steps done in another order).
  const creditOf = new Map<number, number>();
  marking?.steps.forEach((s) => {
    if (s.credited_by != null && s.credited_by !== s.index) creditOf.set(s.credited_by, s.index);
  });

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      {toolbar && (
        <div className="card" style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {toolbar}
        </div>
      )}
      {steps.map((step, i) => {
        const result = marking?.steps[i] ?? null;
        const box = checked?.[i] ?? null;
        const error: RaError | null = result?.box_error ?? box?.error ?? null;
        const earlier = steps.slice(0, i).map((s) => s.name).filter((n): n is string => !!n);
        const tone = result ? (result.earned > 0 ? 'var(--success)' : 'var(--error)') : 'var(--border)';
        return (
          <section key={i} className="card"
            style={{ padding: 12, display: 'grid', gap: 8, minWidth: 0, borderLeft: `4px solid ${tone}` }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
              <strong style={{ fontSize: 14 }}>{i === last ? 'Final answer' : `Step ${i + 1}`}</strong>
              <span style={{ fontSize: 14 }}>{step.prompt}</span>
              <span className="badge neutral" style={{ marginLeft: 'auto' }}>
                {step.marks} {step.marks === 1 ? 'mark' : 'marks'}
              </span>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', minWidth: 0 }}>
              <code style={{ fontSize: 15, fontWeight: 700, paddingTop: 10, whiteSpace: 'nowrap', color: 'var(--brand-charcoal)' }}>
                {step.name ? `${step.name} :=` : ''}
              </code>
              <div style={{ flex: 1, minWidth: 0 }}>
                <RaEditor value={values[i] ?? ''} onChange={(v) => onChange(i, v)} onRun={onRun} error={error}
                  height={84} names={[...names, ...earlier]} hint={i === 0 ? (
                    <>
                      One expression per box{step.name ? `; later boxes can use it as ${step.name}` : ''}.
                      Press <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+<kbd>Enter</kbd> to check.
                    </>
                  ) : (
                    <>One expression{earlier.length ? `; it can use ${earlier.join(', ')}` : ''}.</>
                  )} />
              </div>
            </div>
            {result ? (
              <RaStepResultView result={result} steps={marking!.steps}
                credits={creditOf.has(i) ? marking!.steps[creditOf.get(i)!] : null}
                source={marking!.source} showDirection={showDirection} />
            ) : box ? (
              <BoxCheckView box={box} source={checkSource} />
            ) : null}
          </section>
        );
      })}
    </div>
  );
}

function BoxCheckView({ box, source }: { box: RaBoxCheck; source: 'sample' | 'example' | 'generated' | null }) {
  const [open, setOpen] = useState(false);
  if (box.status === 'empty') return <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Empty.</span>;
  if (box.status === 'error' && box.error) {
    return (
      <div className="alert-error" style={{ fontSize: 13 }}>
        {box.error.line ? `Line ${box.error.line}${box.error.col ? `, column ${box.error.col}` : ''}: ` : ''}
        {box.error.message}
        {box.error.hint && <div>{box.error.hint}</div>}
      </div>
    );
  }
  if (!box.step) return null;
  const tree = box.step.tree;
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          Runs: ({tree.columns.join(', ')}) · {tree.row_count} {tree.row_count === 1 ? 'tuple' : 'tuples'}
        </span>
        <button type="button" className="btn btn-secondary" style={{ minHeight: 26, padding: '0 10px', fontSize: 12, marginLeft: 'auto' }}
          onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? 'Hide structure' : 'Show structure'}
        </button>
      </div>
      {open && <BoxStructure step={box.step} source={source} />}
    </div>
  );
}
