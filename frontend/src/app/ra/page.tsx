'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { RA_DIFFICULTY_LABEL, RaOff } from '@/components/ra/RaOff';
import { useAuth } from '@/contexts/AuthContext';
import { useRaStatus } from '@/hooks/use-ra-status';
import { raQueryKeys, raService } from '@/services/ra.service';
import { RaQuestionListItem } from '@/types/ra.types';

/**
 * Relational Algebra home: the RA questions (students: published ones, with their
 * progress; staff: all, with drafts marked and authoring controls) and the Playground.
 */
export default function RaHomePage() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <RaHome />
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function RaHome() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { isStaff } = useAuth();
  const { enabled, loading: statusLoading } = useRaStatus();
  const questionsQuery = useQuery({
    queryKey: raQueryKeys.questions,
    queryFn: () => raService.listQuestions(),
    enabled,
    staleTime: 0, // progress changes after every submission
  });
  const [deleting, setDeleting] = useState<number | null>(null);

  if (statusLoading) return null;
  if (!enabled) return <RaOff />;

  const questions = questionsQuery.data ?? [];

  const remove = async (q: RaQuestionListItem) => {
    if (!window.confirm(`Delete “${q.title}”? Students will no longer see it.`)) return;
    setDeleting(q.id);
    try {
      await raService.deleteQuestion(q.id);
      queryClient.setQueryData<RaQuestionListItem[]>(raQueryKeys.questions, (old) => (old ?? []).filter((x) => x.id !== q.id));
    } finally {
      setDeleting(null);
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h2>Relational Algebra</h2>
          <p>
            Write answers step by step, as on the lecture slides. Your answer is graded on what it computes,
            so any correct method is accepted.
          </p>
        </div>
        <div className="button-row">
          <Link className="btn btn-secondary" href="/ra/playground">Playground</Link>
          {isStaff && <Link className="btn btn-brand" href="/ra/questions/new">New question</Link>}
        </div>
      </div>

      {questionsQuery.isLoading && <p style={{ color: 'var(--text-muted)' }}>Loading questions…</p>}
      {questionsQuery.error && <div className="alert-error">Could not load the questions.</div>}
      {!questionsQuery.isLoading && !questionsQuery.error && questions.length === 0 && (
        <p style={{ color: 'var(--text-muted)', textAlign: 'center', marginTop: 40 }}>
          No relational algebra questions yet.
          {isStaff && ' Create one with “New question”, or run backend/scripts/seed_ra_local.py.'}
        </p>
      )}

      <div className="grid-3">
        {questions.map((q) => (
          <article
            key={q.id}
            className="card question-card"
            role="button"
            tabIndex={0}
            onClick={() => router.push(`/ra/questions/${q.id}`)}
            onKeyDown={(e) => e.key === 'Enter' && router.push(`/ra/questions/${q.id}`)}
            aria-label={`Relational algebra question: ${q.title}`}
          >
            <div className="button-row" style={{ marginBottom: 8 }}>
              <h3 style={{
                margin: 0, fontSize: 15, flex: 1, minWidth: 0,
                display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
              }}>
                {q.title}
              </h3>
              {isStaff && (
                <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                  <button
                    className="btn btn-ghost"
                    style={{ minHeight: 26, padding: '0 8px', fontSize: 12 }}
                    onClick={(e) => { e.stopPropagation(); router.push(`/ra/questions/${q.id}/edit`); }}
                    onKeyDown={(e) => e.stopPropagation()}
                  >
                    Edit
                  </button>
                  <button
                    className="btn btn-ghost"
                    style={{ minHeight: 26, padding: '0 8px', fontSize: 12 }}
                    disabled={deleting === q.id}
                    aria-label={`Delete ${q.title}`}
                    onClick={(e) => { e.stopPropagation(); void remove(q); }}
                    onKeyDown={(e) => e.stopPropagation()}
                  >
                    Delete
                  </button>
                </div>
              )}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 'auto' }}>
              <span className="badge brand-badge">RA</span>
              <span className={`badge ${q.difficulty}`}>{RA_DIFFICULTY_LABEL[q.difficulty] ?? q.difficulty}</span>
              {!q.has_data && <span className="badge neutral" title="No data: answers are checked on generated databases">Schema only</span>}
              {isStaff && !q.is_published && <span className="badge badge-warn">Draft</span>}
              {q.parts_total > 1 && (
                <span className="badge neutral" title="Sub-questions on the same schema">{q.parts_total} parts</span>
              )}
              {q.solved ? (
                <span className="badge badge-success">✓ Solved</span>
              ) : q.parts_total > 1 && q.parts_solved > 0 ? (
                <span className="badge neutral">{q.parts_solved} of {q.parts_total} solved</span>
              ) : q.attempts > 0 ? (
                <span className="badge neutral">{q.attempts} {q.attempts === 1 ? 'attempt' : 'attempts'}</span>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
