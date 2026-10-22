'use client';

import { useEffect, useMemo, useState } from 'react';
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

function draftKey(questionId: number, partId: number) {
  return `ra-draft-${questionId}-${partId}`;
}

function readDraft(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function partName(label: string, index: number) {
  return label.trim() || `${index + 1}`;
}

/**
 * Solving one RA question: the description and schema, then for each part (a question
 * may have several, (i), (ii), … on the same schema) an editor with Check (run step by
 * step, not graded) and Submit (graded and recorded), the verdict with its evidence,
 * every step with "Show structure", and earlier attempts. Each part keeps its own
 * answer: an unsent one per browser, otherwise the student's last submitted one.
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
  const parts = useMemo(() => question?.parts ?? [], [question]);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const partIndex = Math.max(0, parts.findIndex((p) => p.id === selectedId));
  const part = parts[partIndex];
  const partId = part?.id;

  // Per part: the answer being written, and the last Check / Submit result.
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [checkedBy, setCheckedBy] = useState<Record<number, RaCheckResponse | null>>({});
  const [submittedBy, setSubmittedBy] = useState<Record<number, RaSubmitResponse | null>>({});
  const [busy, setBusy] = useState<'check' | 'submit' | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);

  const answer = partId != null ? answers[partId] ?? '' : '';
  const checked = partId != null ? checkedBy[partId] ?? null : null;
  const submitted = partId != null ? submittedBy[partId] ?? null : null;
  const setAnswer = (value: string) => {
    if (partId != null) setAnswers((a) => ({ ...a, [partId]: value }));
  };

  // The first time a part is shown, bring back the student's own answer to it: the unsent
  // one in this browser, else their latest submission. A new part starts empty.
  const attemptsLoaded = !attemptsQuery.isLoading;
  useEffect(() => {
    if (partId == null || partId in answers) return;
    const draft = readDraft(draftKey(questionId, partId))
      ?? (parts.length === 1 ? readDraft(`ra-draft-${questionId}`) : null);    // before questions had parts
    const lastSubmitted = (attemptsQuery.data ?? []).find((a) => a.part_id === partId)?.answer;
    if (draft == null && !attemptsLoaded) return;                            // wait for the attempts
    setAnswers((a) => ({ ...a, [partId]: draft || lastSubmitted || '' }));
  }, [partId, answers, attemptsLoaded, attemptsQuery.data, parts.length, questionId]);
  useEffect(() => {
    if (partId == null || !(partId in answers)) return;
    try {
      window.localStorage.setItem(draftKey(questionId, partId), answers[partId]);
    } catch {
      // storage unavailable: drafts just aren't kept
    }
  }, [questionId, partId, answers]);

  const editorError: RaError | null = checked?.error
    ?? (submitted?.grade?.verdict === 'invalid_expression' ? submitted.grade.error : null);

  const goTo = (index: number) => {
    const next = parts[index];
    if (next) {
      setSelectedId(next.id);
      setRequestError(null);
    }
  };

  const run = async (kind: 'check' | 'submit') => {
    if (partId == null || !answer.trim() || busy) return;
    setBusy(kind);
    setRequestError(null);
    try {
      if (kind === 'check') {
        setSubmittedBy((m) => ({ ...m, [partId]: null }));
        const result = await raService.checkAnswer(questionId, partId, answer);
        setCheckedBy((m) => ({ ...m, [partId]: result }));
      } else {
        setCheckedBy((m) => ({ ...m, [partId]: null }));
        const result = await raService.submitAnswer(questionId, partId, answer);
        setSubmittedBy((m) => ({ ...m, [partId]: result }));
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
  if (!question || !part) return <div className="alert-error">This question does not exist or is not available.</div>;

  const multi = parts.length > 1;
  const name = partName(part.label, partIndex);
  const attempts = (attemptsQuery.data ?? []).filter((a) => a.part_id === part.id || (!multi && a.part_id == null));
  const limit = question.max_submissions;
  const used = submitted?.submissions_used ?? part.submissions_used;
  const limitReached = limit != null && used >= limit;
  const solvedCount = parts.filter((p) => p.solved).length;
  const totalMarks = parts.reduce((sum, p) => sum + p.marks, 0);

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
            {multi && !question.solved && !question.hide_correctness && (
              <span className="badge neutral">{solvedCount} of {parts.length} parts solved</span>
            )}
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
        {multi && (
          <div className="card" style={{ padding: 12, display: 'grid', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <button className="btn btn-secondary" style={navButton} onClick={() => goTo(partIndex - 1)}
                disabled={partIndex === 0 || !!busy}>
                ← Previous part
              </button>
              <select className="da-select" style={{ flex: '1 1 180px', minWidth: 0 }} value={part.id}
                onChange={(e) => goTo(parts.findIndex((p) => p.id === Number(e.target.value)))} disabled={!!busy}
                aria-label="Choose the part to answer">
                {parts.map((p, i) => (
                  <option key={p.id} value={p.id}>
                    Part {partName(p.label, i)} · {p.marks} {p.marks === 1 ? 'mark' : 'marks'}
                    {p.solved ? ' · ✓ solved' : p.attempts > 0 ? ' · attempted' : ''}
                  </option>
                ))}
              </select>
              <button className="btn btn-secondary" style={navButton} onClick={() => goTo(partIndex + 1)}
                disabled={partIndex === parts.length - 1 || !!busy}>
                Next part →
              </button>
            </div>
            <div style={{ display: 'grid', gap: 6 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <strong style={{ fontSize: 15 }}>Part {name}</strong>
                <span className="badge neutral">{part.marks} of {totalMarks} marks</span>
                {part.solved && <span className="badge badge-success">✓ Solved</span>}
              </div>
              {part.description.trim() && <DescriptionMarkdown content={part.description} fontSize={14} />}
            </div>
          </div>
        )}
        <RaEditor
          value={answer}
          onChange={setAnswer}
          onRun={() => void run('check')}
          error={editorError}
          height={240}
          names={question.relations.flatMap((r) => [r.name, ...r.columns])}
          toolbar={(
            <>
              <button className="btn btn-secondary" style={{ minHeight: 32, padding: '0 12px', fontSize: 13 }}
                onClick={() => void run('check')} disabled={!!busy || !answer.trim()}
                title="Run your answer step by step. Not graded, not recorded.">
                {busy === 'check' ? 'Checking…' : 'Check (not graded)'}
              </button>
              <button className="btn btn-brand" style={{ minHeight: 32, padding: '0 14px', fontSize: 13 }}
                onClick={() => void run('submit')} disabled={!!busy || !answer.trim() || limitReached}
                title={limitReached ? 'You have used all your submissions for this question.' : undefined}>
                {busy === 'submit' ? 'Grading…' : 'Submit'}
              </button>
              <button className="btn btn-secondary" style={{ minHeight: 32, padding: '0 12px', fontSize: 13 }}
                onClick={() => {
                  setAnswer('');
                  setCheckedBy((m) => ({ ...m, [part.id]: null }));
                  setSubmittedBy((m) => ({ ...m, [part.id]: null }));
                }} disabled={!!busy}>
                Clear
              </button>
              {limit != null && (
                <span style={{ fontSize: 13, marginLeft: 'auto', color: limitReached ? 'var(--error)' : 'var(--text-muted)' }}>
                  {limitReached ? `No submissions left${multi ? ' for this part' : ''}` : `${used} of ${limit} submissions used${multi ? ' for this part' : ''}`} · Check is free
                </span>
              )}
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
              Your attempts{multi ? ` at part ${name}` : ''} ({attempts.length})
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

const navButton: React.CSSProperties = { minHeight: 32, padding: '0 12px', fontSize: 13 };
