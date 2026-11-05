'use client';

import { useState } from 'react';
import { RaGradeResult, RaStep, RaStepMarking, RaStepResult } from '@/types/ra.types';
import { RaCaseView } from './RaCaseView';
import { StepNode } from './RaSteps';
import { RaTable } from './RaTable';
import { RaVerdict } from './RaVerdict';

type Source = RaStepMarking['source'];

function where(source: Source) {
  return source === 'sample' ? "on the question's data"
    : source === 'example' ? 'on the example data shown with the question' : 'on an example generated database';
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

/** The marks of a multi-step answer at the top: the total, then the final answer's verdict. */
export function RaStepMarkingSummary({ marking, grade }: { marking: RaStepMarking; grade: RaGradeResult }) {
  const reached = marking.steps.filter((s) => s.earned > 0).length;
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div className={marking.final_correct ? 'alert-success' : marking.earned > 0 ? 'alert-warn' : 'alert-error'}
        style={{ display: 'grid', gap: 4 }}>
        <strong style={{ fontSize: 15 }}>
          {marking.final_correct ? '✓' : '✗'} {marking.earned} of {plural(marking.total, 'mark')}
        </strong>
        <span style={{ fontSize: 13 }}>
          {marking.final_correct
            ? 'Your final answer is correct, so every step gets its marks.'
            : `Your final answer is not correct. ${reached} of ${plural(marking.steps.length, 'step')} earned marks: each step counts when one of your boxes computes it, in any order, or computes it given the model's earlier steps.`}
        </span>
      </div>
      {grade.verdict !== 'invalid_expression' || grade.error ? (
        <div style={{ display: 'grid', gap: 6 }}>
          <span style={{ fontSize: 13, fontWeight: 700 }}>Your final answer</span>
          <RaVerdict grade={grade} />
        </div>
      ) : null}
    </div>
  );
}

/** Under one step box after Submit: its marks, how they were earned, and what to look at. */
export function RaStepResultView({ result, steps, credits, source, showDirection }: {
  result: RaStepResult;
  /** Every step's result, to name the box that earned this one. */
  steps: RaStepResult[];
  /** The step this box earned, when it is another one (steps done in another order). */
  credits: RaStepResult | null;
  source: Source;
  showDirection: boolean;
}) {
  const [open, setOpen] = useState(false);
  const good = result.earned > 0;
  const by = result.credited_by != null ? steps[result.credited_by] : null;
  const byName = by ? (by.name ?? 'final answer') : null;
  let note: string;
  if (result.status === 'full') note = 'Your final answer is correct, so this step gets its marks.';
  else if (result.status === 'reached') {
    note = result.credited_by === result.index ? 'This box computes this step.' : `Your step ${byName} computes this step.`;
  } else if (result.status === 'carried') {
    note = `Right, given your earlier steps: with the model's earlier steps in their place, ${result.credited_by === result.index ? 'this box' : `your step ${byName}`} gives this step's result.`;
  } else if (result.box_status === 'empty') note = 'Left empty, so no marks.';
  else if (result.box_status === 'error') note = 'This box has an error, so no marks.';
  else note = "This box doesn't give this step's result.";
  const fb = result.feedback;
  const tree = result.structure?.tree;

  return (
    <div style={{ display: 'grid', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span className={`badge ${good ? 'badge-success' : 'badge-danger'}`} style={{ fontSize: 13 }}>
          {good ? '✓' : '✗'} {result.earned} / {plural(result.marks, 'mark')}
        </span>
        <span style={{ fontSize: 13, color: good ? 'var(--success)' : 'var(--error)' }}>{note}</span>
        {tree && (
          <button type="button" className="btn btn-secondary" style={{ minHeight: 26, padding: '0 10px', fontSize: 12, marginLeft: 'auto' }}
            onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            {open ? 'Hide structure' : 'Show structure'}
          </button>
        )}
      </div>
      {credits && (
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          This box counts for step {credits.index + 1} ({credits.prompt}) instead: steps may come in any order.
        </span>
      )}
      {result.box_status === 'error' && result.box_error && (
        <div className="alert-error" style={{ fontSize: 13 }}>
          {result.box_error.line ? `Line ${result.box_error.line}${result.box_error.col ? `, column ${result.box_error.col}` : ''}: ` : ''}
          {result.box_error.message}
        </div>
      )}
      {result.student && result.expected && (
        <div style={{ display: 'grid', gap: 6 }}>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Your box and the model&apos;s step {where(source)}:</span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
            <div style={{ minWidth: 160, flex: 1 }}>
              <RaTable caption={`Your box returns (${plural(result.student.rows.length, 'tuple')})`}
                columns={result.student.columns} rows={result.student.rows} emptyText="No tuples" />
            </div>
            <div style={{ minWidth: 160, flex: 1 }}>
              <RaTable caption={`The model's step returns (${plural(result.expected.rows.length, 'tuple')})`}
                columns={result.expected.columns} rows={result.expected.rows} emptyText="No tuples" />
            </div>
          </div>
        </div>
      )}
      {open && tree && <BoxStructure step={result.structure!} source={source} />}
      {open && showDirection && fb && fb.status === 'close' && (
        <div style={{ display: 'grid', gap: 6, fontSize: 13 }}>
          <strong>◐ Close to a step of the model solution{fb.checkpoint ? ` — ${fb.checkpoint}` : ''}</strong>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Same attributes and the same kind of expression, but different tuples on some data. Check its conditions and constants.
          </span>
          {fb.case && <RaCaseView example={fb.case} studentLabel="This box" expectedLabel="The model's step" />}
        </div>
      )}
    </div>
  );
}

/** One box's operator tree and output (its "Show structure"). */
export function BoxStructure({ step, source }: { step: RaStep; source: Source }) {
  const tree = step.tree;
  return (
    <div style={{ display: 'grid', gap: 10, borderTop: '1px solid var(--border)', paddingTop: 10 }}>
      <StepNode node={tree} depth={0} />
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        ({tree.columns.join(', ')}) · {plural(tree.row_count, 'tuple')} {where(source)}
      </span>
      <RaTable columns={tree.columns} rows={tree.rows} emptyText="Empty relation" />
    </div>
  );
}
