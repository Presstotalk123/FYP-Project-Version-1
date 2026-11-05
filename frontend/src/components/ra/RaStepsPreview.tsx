'use client';

import { useState } from 'react';
import { raService } from '@/services/ra.service';
import { RaStepSpecStaff, RaTryStepsResponse } from '@/types/ra.types';
import { RaStepBoxes } from './RaStepBoxes';
import { RaStepMarkingSummary } from './RaStepMarking';

/**
 * The staff form's live preview of a multi-step part: exactly what students see (each
 * prompt and its empty box, updating as the steps are edited). Staff can fill in the boxes
 * and "Grade this answer" to see the marks a student would get; nothing is saved.
 */
export function RaStepsPreview({ steps, schemaSql, dataSql, exampleDataSql, compareBags, names, busy }: {
  steps: RaStepSpecStaff[];
  schemaSql: string;
  dataSql: string;
  exampleDataSql: string | null;
  compareBags: boolean;
  names: string[];
  busy: boolean;
}) {
  const [values, setValues] = useState<string[]>([]);
  const [tried, setTried] = useState<RaTryStepsResponse | null>(null);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const boxes = steps.map((_, i) => values[i] ?? '');
  // The students' view: names and prompts only (never the model answers).
  const shown = steps.map((s, i) => ({
    name: i === steps.length - 1 ? null : (s.name?.trim() || `R${i + 1}`), prompt: s.prompt || '(no prompt yet)', marks: s.marks,
  }));

  const grade = async () => {
    setWorking(true);
    setMessage(null);
    try {
      const r = await raService.trySteps({
        schema_sql: schemaSql, data_sql: dataSql, example_data_sql: dataSql.trim() ? null : exampleDataSql,
        compare_bags: compareBags, steps, step_answers: boxes,
      });
      setTried(r);
      if (!r.ok && r.error) {
        setMessage(r.error_step != null
          ? `Step ${r.error_step + 1} of your steps has an error: ${r.error.message}`
          : `Fix the ${r.error_source === 'steps' ? 'steps' : r.error_source === 'data' ? 'INSERT statements' : 'schema'} first: ${r.error.message}`);
      }
    } catch {
      setMessage('Could not reach the server.');
    } finally {
      setWorking(false);
    }
  };

  return (
    <details open>
      <summary style={{ cursor: 'pointer', fontWeight: 700, fontSize: 13 }}>Preview: what students see</summary>
      <div style={{ display: 'grid', gap: 10, marginTop: 8, padding: 12, borderRadius: 'var(--radius)', background: 'var(--surface-muted)' }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Students see these prompts and boxes. Try an answer to see the marks it would get, graded exactly as a
          student&apos;s Submit with the question&apos;s settings. Nothing is saved.
        </span>
        <RaStepBoxes steps={shown} values={boxes} names={names} checked={null} checkSource={null}
          marking={tried?.marking ?? null} showDirection onRun={() => void grade()}
          onChange={(i, v) => {
            setValues(() => {
              const next = [...boxes];
              next[i] = v;
              return next;
            });
            setTried(null);
          }}
          toolbar={(
            <button type="button" className="btn btn-secondary" style={{ minHeight: 32, padding: '0 12px', fontSize: 13 }}
              onClick={() => void grade()} disabled={busy || working || !schemaSql.trim() || !boxes.some((b) => b.trim())}>
              {working ? 'Marking…' : 'Grade this answer'}
            </button>
          )} />
        {message && <div className="alert-error" style={{ fontSize: 13 }}>{message}</div>}
        {tried?.ok && tried.grade && tried.marking && (
          <div className="card" style={{ padding: 12 }}>
            <RaStepMarkingSummary marking={tried.marking} grade={tried.grade} />
          </div>
        )}
      </div>
    </details>
  );
}
