'use client';

import { useEffect, useState } from 'react';
import { raService } from '@/services/ra.service';
import { RaAttempt, RaCheckResponse, RaPart, RaQuestion, RaSubmitResponse } from '@/types/ra.types';
import { RaStepBoxes } from './RaStepBoxes';
import { RaStepMarkingSummary } from './RaStepMarking';

function draftKey(questionId: number, partId: number) {
  return `ra-steps-draft-${questionId}-${partId}`;
}

function readDraft(key: string): string[] | null {
  try {
    const raw = window.localStorage.getItem(key);
    const value = raw ? JSON.parse(raw) : null;
    return Array.isArray(value) ? value.map((v) => String(v ?? '')) : null;
  } catch {
    return null;
  }
}

function fit(values: string[], n: number) {
  return Array.from({ length: n }, (_, i) => values[i] ?? '');
}

/**
 * Answering one part of a multi-step question: one box per step, Check (every box run on
 * the shown data, not graded) and Submit (marked per step, recorded), then the marks and
 * the earlier attempts. Each part keeps its own boxes: an unsent draft per browser,
 * otherwise the student's last submitted ones.
 */
export function RaStepsAnswer({ question, part, attempts, attemptsLoaded, multiPart, onSubmitted }: {
  question: RaQuestion;
  part: RaPart;
  attempts: RaAttempt[];
  attemptsLoaded: boolean;
  multiPart: boolean;
  onSubmitted: () => void;
}) {
  const steps = part.steps ?? [];
  const [valuesBy, setValuesBy] = useState<Record<number, string[]>>({});
  const [checkedBy, setCheckedBy] = useState<Record<number, RaCheckResponse | null>>({});
  const [submittedBy, setSubmittedBy] = useState<Record<number, RaSubmitResponse | null>>({});
  const [busy, setBusy] = useState<'check' | 'submit' | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);

  const values = fit(valuesBy[part.id] ?? [], steps.length);
  const checked = checkedBy[part.id] ?? null;
  const submitted = submittedBy[part.id] ?? null;
  const filled = values.some((v) => v.trim());

  // Bring back this part's boxes: the unsent draft, else the last submission.
  useEffect(() => {
    if (part.id in valuesBy) return;
    const draft = readDraft(draftKey(question.id, part.id));
    if (draft == null && !attemptsLoaded) return;
    const last = attempts.find((a) => a.part_id === part.id && a.step_answers)?.step_answers ?? [];
    setValuesBy((m) => ({ ...m, [part.id]: fit(draft ?? last, steps.length) }));
  }, [part.id, valuesBy, attempts, attemptsLoaded, question.id, steps.length]);
  useEffect(() => {
    if (!(part.id in valuesBy)) return;
    try {
      window.localStorage.setItem(draftKey(question.id, part.id), JSON.stringify(valuesBy[part.id]));
    } catch {
      // storage unavailable: drafts just aren't kept
    }
  }, [question.id, part.id, valuesBy]);

  const setValue = (index: number, value: string) => {
    setValuesBy((m) => {
      const next = fit(m[part.id] ?? [], steps.length);
      next[index] = value;
      return { ...m, [part.id]: next };
    });
  };
  const setAll = (next: string[]) => setValuesBy((m) => ({ ...m, [part.id]: fit(next, steps.length) }));

  const limit = question.max_submissions;
  const used = submitted?.submissions_used ?? part.submissions_used;
  const limitReached = limit != null && used >= limit;

  const run = async (kind: 'check' | 'submit') => {
    if (!filled || busy) return;
    setBusy(kind);
    setRequestError(null);
    try {
      if (kind === 'check') {
        setSubmittedBy((m) => ({ ...m, [part.id]: null }));
        setCheckedBy((m) => ({ ...m, [part.id]: null }));
        const result = await raService.checkSteps(question.id, part.id, values);
        setCheckedBy((m) => ({ ...m, [part.id]: result }));
      } else {
        setCheckedBy((m) => ({ ...m, [part.id]: null }));
        const result = await raService.submitSteps(question.id, part.id, values);
        setSubmittedBy((m) => ({ ...m, [part.id]: result }));
        onSubmitted();
      }
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
      setRequestError(typeof detail === 'string' ? detail : 'Could not reach the server.');
    } finally {
      setBusy(null);
    }
  };

  const mine = attempts.filter((a) => a.part_id === part.id);
  const button = { minHeight: 32, padding: '0 12px', fontSize: 13 };

  return (
    <div style={{ display: 'grid', gap: 12, minWidth: 0 }}>
      <div className="alert-info" style={{ fontSize: 13 }}>
        Answer in the steps below, one expression per box. A later step can use an earlier one by its name
        ({steps.filter((s) => s.name).map((s) => s.name).join(', ')}). A correct final answer earns all the
        marks; otherwise each step you get right earns its own.
      </div>
      <RaStepBoxes steps={steps} values={values} onChange={setValue}
        names={question.relations.flatMap((r) => [r.name, ...r.columns])} onRun={() => void run('check')}
        checked={checked?.boxes ?? null} checkSource={checked?.source ?? null}
        marking={submitted?.marking ?? null} showDirection={question.show_step_direction}
        toolbar={(
          <>
            <button className="btn btn-secondary" style={button} onClick={() => void run('check')}
              disabled={!!busy || !filled} title="Run every step on the data. Not graded, not recorded.">
              {busy === 'check' ? 'Checking…' : 'Check (not graded)'}
            </button>
            <button className="btn btn-brand" style={{ ...button, padding: '0 14px' }} onClick={() => void run('submit')}
              disabled={!!busy || !filled || limitReached}
              title={limitReached ? 'You have used all your submissions for this question.' : undefined}>
              {busy === 'submit' ? 'Marking…' : 'Submit'}
            </button>
            <button className="btn btn-secondary" style={button} disabled={!!busy} onClick={() => {
              setAll([]);
              setCheckedBy((m) => ({ ...m, [part.id]: null }));
              setSubmittedBy((m) => ({ ...m, [part.id]: null }));
            }}>
              Clear
            </button>
            {limit != null && (
              <span style={{ fontSize: 13, marginLeft: 'auto', color: limitReached ? 'var(--error)' : 'var(--text-muted)' }}>
                {limitReached ? `No submissions left${multiPart ? ' for this part' : ''}` : `${used} of ${limit} submissions used${multiPart ? ' for this part' : ''}`} · Check is free
              </span>
            )}
          </>
        )} />

      {requestError && <div className="alert-error">{requestError}</div>}

      {submitted && (
        <div className="card" style={{ padding: 16, display: 'grid', gap: 12, minWidth: 0 }}>
          {submitted.grade && submitted.marking ? (
            <RaStepMarkingSummary marking={submitted.marking} grade={submitted.grade} />
          ) : (
            <div className="alert-info"><strong>Submitted.</strong> Your answer has been recorded.</div>
          )}
        </div>
      )}

      {mine.length > 0 && (
        <details className="card" style={{ padding: 12 }}>
          <summary style={{ cursor: 'pointer', fontWeight: 700, fontSize: 14 }}>
            Your attempts{multiPart ? ' at this part' : ''} ({mine.length})
          </summary>
          <div style={{ display: 'grid', gap: 6, marginTop: 10 }}>
            {mine.map((a) => (
              <div key={a.id} style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', fontSize: 13 }}>
                <span style={{ color: 'var(--text-muted)', minWidth: 140 }}>{new Date(a.created_at).toLocaleString()}</span>
                {a.marks_earned != null ? (
                  <span className={`badge ${a.is_correct ? 'badge-success' : a.marks_earned > 0 ? 'badge-warn' : 'badge-danger'}`}>
                    {a.marks_earned} of {part.marks} marks
                  </span>
                ) : <span className="badge neutral">Submitted</span>}
                <code style={{ flex: '1 1 200px', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {a.answer.replace(/\n/g, ' ; ')}
                </code>
                <button className="btn btn-ghost" style={{ minHeight: 26, padding: '0 8px', fontSize: 12 }}
                  disabled={!a.step_answers} onClick={() => a.step_answers && setAll(a.step_answers)}>
                  Load
                </button>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
