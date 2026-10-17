'use client';

import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { SimpleGrid } from '@mantine/core';
import { DescriptionMarkdown } from '@/components/common/DescriptionMarkdown';
import { raQueryKeys, raService } from '@/services/ra.service';
import { RaCheckResponse, RaError, RaSubmitResponse, RaVerdict as Verdict } from '@/types/ra.types';
import { RaEditor } from './RaEditor';
import { RA_DIFFICULTY_LABEL } from './RaOff';
import { RaRelations } from './RaRelations';
import { RaStepStructure } from './RaStepStructure';
import { RaSteps } from './RaSteps';
import { RaTable } from './RaTable';
import { RaVerdict } from './RaVerdict';

const VERDICT_BADGE: Record<Verdict, { text: string; cls: string }> = {
  correct: { text: 'Correct', cls: 'badge-success' },
  wrong_columns: { text: 'Wrong attributes', cls: 'badge-danger' },
  wrong_result: { text: 'Wrong result', cls: 'badge-danger' },
  wrong_in_general: { text: 'Not correct in general', cls: 'badge-danger' },
  invalid_expression: { text: 'Error', cls: 'badge-danger' },
};

function draftKey(id: number) {
  return `ra-draft-${id}`;
}

function readDraft(id: number): string {
  try {
    return window.localStorage.getItem(draftKey(id)) ?? '';
  } catch {
    return '';
  }
}

/**
 * Solving one RA question: the description and schema, an editor with Check (run step
 * by step, not graded) and Submit (graded and recorded), the verdict with its evidence,
 * every step with "Show structure", and earlier attempts.
 */
export function RaQuestionWorkspace({ questionId }: { questionId: number }) {
  const queryClient = useQueryClient();
  const questionQuery = useQuery({
    queryKey: raQueryKeys.question(questionId),
    queryFn: () => raService.getQuestion(questionId),
    staleTime: 0,
  });
  const attemptsQuery = useQuery({
    queryKey: raQueryKeys.attempts(questionId),
    queryFn: () => raService.myAttempts(questionId),
    staleTime: 0,
  });
  const question = questionQuery.data;

  const [answer, setAnswer] = useState('');
  const [busy, setBusy] = useState<'check' | 'submit' | null>(null);
  const [checked, setChecked] = useState<RaCheckResponse | null>(null);
  const [submitted, setSubmitted] = useState<RaSubmitResponse | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);

  // Restore this question's unsent answer (per browser; a convenience, never relied on).
  useEffect(() => {
    setAnswer(readDraft(questionId));
  }, [questionId]);
  useEffect(() => {
    try {
      window.localStorage.setItem(draftKey(questionId), answer);
    } catch {
      // storage unavailable: drafts just aren't kept
    }
  }, [questionId, answer]);

  const editorError: RaError | null = checked?.error
    ?? (submitted?.grade?.verdict === 'invalid_expression' ? submitted.grade.error : null);

  const run = async (kind: 'check' | 'submit') => {
    if (!answer.trim() || busy) return;
    setBusy(kind);
    setRequestError(null);
    try {
      if (kind === 'check') {
        setSubmitted(null);
        setChecked(await raService.checkAnswer(questionId, answer));
      } else {
        setChecked(null);
        setSubmitted(await raService.submitAnswer(questionId, answer));
        void queryClient.invalidateQueries({ queryKey: raQueryKeys.attempts(questionId) });
        void queryClient.invalidateQueries({ queryKey: raQueryKeys.question(questionId) });
        void queryClient.invalidateQueries({ queryKey: raQueryKeys.questions });
      }
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
      setRequestError(typeof detail === 'string' ? detail : 'Could not reach the server.');
    } finally {
      setBusy(null);
    }
  };

  if (questionQuery.isLoading) return <p style={{ color: 'var(--text-muted)' }}>Loading…</p>;
  if (!question) return <div className="alert-error">This question does not exist or is not available.</div>;

  const attempts = attemptsQuery.data ?? [];

  return (
    <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
      {/* Question */}
      <section className="card" style={{ padding: 16, display: 'grid', gap: 14, alignContent: 'start', minWidth: 0 }}>
        <div style={{ display: 'grid', gap: 8 }}>
          <h2 style={{ margin: 0, fontSize: 22 }}>{question.title}</h2>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <span className="badge brand-badge">RA</span>
            <span className={`badge ${question.difficulty}`}>{RA_DIFFICULTY_LABEL[question.difficulty]}</span>
            {question.solved && <span className="badge badge-success">✓ Solved</span>}
          </div>
        </div>
        <DescriptionMarkdown content={question.description} fontSize={14} />
        <div style={{ display: 'grid', gap: 8 }}>
          <h3 style={{ margin: 0, fontSize: 15 }}>Schema</h3>
          <RaRelations relations={question.relations} />
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
            {question.has_data
              ? 'Underlined attributes form the key. Your answer must be right on this data and also in general: it is checked on many other databases too.'
              : 'Underlined attributes form the key. There is no data: Check runs your answer on an example database, and Submit checks it on many generated databases.'}
          </p>
        </div>
      </section>

      {/* Answer */}
      <section style={{ display: 'grid', gap: 12, alignContent: 'start', minWidth: 0 }}>
        <RaEditor
          value={answer}
          onChange={setAnswer}
          onRun={() => void run('check')}
          error={editorError}
          height={240}
          toolbar={(
            <>
              <button className="btn btn-secondary" style={{ minHeight: 32, padding: '0 12px', fontSize: 13 }}
                onClick={() => void run('check')} disabled={!!busy || !answer.trim()}
                title="Run your answer step by step. Not graded, not recorded.">
                {busy === 'check' ? 'Checking…' : 'Check (not graded)'}
              </button>
              <button className="btn btn-brand" style={{ minHeight: 32, padding: '0 14px', fontSize: 13 }}
                onClick={() => void run('submit')} disabled={!!busy || !answer.trim()}>
                {busy === 'submit' ? 'Grading…' : 'Submit'}
              </button>
              <button className="btn btn-secondary" style={{ minHeight: 32, padding: '0 12px', fontSize: 13 }}
                onClick={() => { setAnswer(''); setChecked(null); setSubmitted(null); }} disabled={!!busy}>
                Clear
              </button>
            </>
          )}
        />

        {requestError && <div className="alert-error">{requestError}</div>}

        {checked && !checked.ok && checked.error && (
          <div className="alert-error" style={{ fontSize: 13, display: 'grid', gap: 4 }}>
            <strong>
              {checked.error.line ? `Line ${checked.error.line}${checked.error.col ? `, column ${checked.error.col}` : ''}: ` : ''}
              {checked.error.message}
            </strong>
            {checked.error.hint && <span>{checked.error.hint}</span>}
          </div>
        )}

        {checked?.ok && checked.result && (
          <div className="card" style={{ padding: 16, display: 'grid', gap: 14, minWidth: 0 }}>
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
              Not graded. {checked.source === 'sample'
                ? "Evaluated on the question's data."
                : 'Evaluated on an example generated database (the question has no data):'}
            </p>
            {checked.source === 'generated' && <RaRelations relations={checked.relations} />}
            <RaTable caption={`Result — ${checked.result.row_count} ${checked.result.row_count === 1 ? 'tuple' : 'tuples'}`}
              columns={checked.result.columns} rows={checked.result.rows} emptyText="Empty relation" />
            <div style={{ display: 'grid', gap: 8 }}>
              <h3 style={{ margin: 0, fontSize: 15 }}>Steps</h3>
              <RaSteps steps={checked.result.steps} />
            </div>
          </div>
        )}

        {submitted && (
          <div className="card" style={{ padding: 16, display: 'grid', gap: 16, minWidth: 0 }}>
            {submitted.grade ? (
              <RaVerdict grade={submitted.grade} />
            ) : (
              <div className="alert-info"><strong>Submitted.</strong> Your answer has been recorded.</div>
            )}
            {submitted.grade && submitted.grade.steps.length > 0 && (
              <div style={{ display: 'grid', gap: 8 }}>
                <h3 style={{ margin: 0, fontSize: 15 }}>Your steps</h3>
                {question.show_step_direction && (
                  <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
                    Each step is compared with the model solution&apos;s steps by what it computes, not by its name.
                    ✓ matches a step · ◐ same kind of step but different tuples · ○ no matching step (fine for a different method).
                  </p>
                )}
                <RaStepStructure feedback={submitted.grade.steps} steps={submitted.structure?.steps ?? null}
                  source={submitted.structure_source} showDirection={question.show_step_direction} />
              </div>
            )}
          </div>
        )}

        {attempts.length > 0 && (
          <details className="card" style={{ padding: 12 }}>
            <summary style={{ cursor: 'pointer', fontWeight: 700, fontSize: 14 }}>
              Your attempts ({attempts.length})
            </summary>
            <div style={{ display: 'grid', gap: 6, marginTop: 10 }}>
              {attempts.map((a) => (
                <div key={a.id} style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', fontSize: 13 }}>
                  <span style={{ color: 'var(--text-muted)', minWidth: 140 }}>{new Date(a.created_at).toLocaleString()}</span>
                  {a.verdict ? (
                    <span className={`badge ${VERDICT_BADGE[a.verdict].cls}`}>{VERDICT_BADGE[a.verdict].text}</span>
                  ) : <span className="badge neutral">Submitted</span>}
                  <code style={{ flex: '1 1 200px', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {a.answer.replace(/\n/g, ' ; ')}
                  </code>
                  <button className="btn btn-ghost" style={{ minHeight: 26, padding: '0 8px', fontSize: 12 }}
                    onClick={() => setAnswer(a.answer)}>
                    Load
                  </button>
                </div>
              ))}
            </div>
          </details>
        )}
      </section>
    </SimpleGrid>
  );
}
