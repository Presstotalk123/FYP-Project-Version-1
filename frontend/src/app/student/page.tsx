'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useDebouncedValue } from '@mantine/hooks';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { notifications } from '@mantine/notifications';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { ERDiagramQuestionListItem } from '@/types/er-diagram.types';
import { questionService } from '@/services/question.service';
import { attemptService } from '@/services/attempt.service';
import { erDiagramService } from '@/services/er-diagram.service';
import { settingsService } from '@/services/settings.service';
import { queryKeys } from '@/services/query-keys';
import { useERAbility } from '@/hooks/use-er-ability';
import { toERQuestionSubject } from '@/permissions/er-ability';

// The pooled-questions shape mirrors /admin/problems: every source is mapped
// into one uid-namespaced row list, sorted by creation date, and category /
// search / difficulty all filter client-side across the pool. Labs and
// assessments deliberately stay on their own pages.
type StudentProblemType = 'sql-question' | 'erd-question';
type CategoryFilter = 'all' | 'sql' | 'erd';

interface PooledQuestion {
  uid: string;
  id: number;
  title: string;
  problemType: StudentProblemType;
  /** Lowercase; used for both filtering and the badge class. */
  difficulty: string;
  created_by?: number;
  createdByRole?: string;
  created_at: string;
  completed?: boolean;
  attempts_count?: number;
  /** ERD only. SQL counts its attempts; ERD records no per-attempt tally, so all
   *  the list can say is that something was graded but did not pass. */
  attempted?: boolean;
}

const difficultyClass: Record<string, string> = {
  easy: 'easy',
  medium: 'medium',
  hard: 'hard',
};

const capitalize = (value: string): string =>
  value.charAt(0).toUpperCase() + value.slice(1);

const IconSearch = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
  </svg>
);
const IconCheck = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
);
const IconRefresh = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
  </svg>
);
const IconTrash = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
    <path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
  </svg>
);

export default function StudentDashboard() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const ability = useERAbility();
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [difficulty, setDifficulty] = useState<string>('all');
  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 500);
  const [deletingErdId, setDeletingErdId] = useState<number | null>(null);

  // Session-cached (see providers.tsx). SQL is fetched once UNFILTERED — all
  // filtering is client-side across the pool, matching /admin/problems — so the
  // param-encoded key is pinned to its no-filter variant (SqlWorkspace's prefix
  // invalidation still hits it). Progress is invalidated when a question is
  // solved in the workspace; `erdQuestions` is shared with the staff Problems
  // page and force-refetched by ERQuestionForm after a save.
  const questionsQuery = useQuery({
    queryKey: queryKeys.studentQuestions({ difficulty: 'all', search: '' }),
    queryFn: () => questionService.getQuestions({}),
  });
  const progressQuery = useQuery({
    queryKey: queryKeys.studentProgress,
    queryFn: () => attemptService.getProgress(),
  });
  const erdQuery = useQuery({
    queryKey: queryKeys.erdQuestions,
    queryFn: () => erDiagramService.getQuestions(),
  });
  const erdProgressQuery = useQuery({
    queryKey: queryKeys.studentErdProgress,
    queryFn: () => erDiagramService.getProgress(),
  });
  // Decides whether the author badge is worth showing (see the badge row below).
  // Deliberately not in the loading gate: the list must not wait on it, and until
  // it resolves the badge is simply absent.
  const erdSettingsQuery = useQuery({
    queryKey: queryKeys.erdSettings,
    queryFn: () => settingsService.getErdSettings(),
  });
  const showAuthorBadge = erdSettingsQuery.data?.student_authoring_enabled ?? false;

  const pool = useMemo<PooledQuestion[]>(() => {
    const sqlQuestions = questionsQuery.data ?? [];
    const erdQuestions = erdQuery.data ?? [];
    const progressData = progressQuery.data ?? [];
    const progressMap = new Map(progressData.map((p) => [p.question_id, p]));
    // Only attempted questions come back, so a missing entry means untouched.
    const erdProgressMap = new Map(
      (erdProgressQuery.data ?? []).map((p) => [p.question_id, p]),
    );

    return [
      ...sqlQuestions.map((q) => {
        const prog = progressMap.get(q.id);
        return {
          uid: `sql-${q.id}`,
          id: q.id,
          title: q.title,
          problemType: 'sql-question' as StudentProblemType,
          difficulty: q.difficulty.toLowerCase(),
          created_at: q.created_at,
          completed: prog?.completed || false,
          attempts_count: prog?.attempts_count || 0,
        };
      }),
      ...erdQuestions.map((e: ERDiagramQuestionListItem) => {
        const prog = erdProgressMap.get(e.id);
        return {
          uid: `erd-${e.id}`,
          id: e.id,
          title: e.title,
          problemType: 'erd-question' as StudentProblemType,
          difficulty: e.difficulty_label.toLowerCase(),
          created_by: e.created_by,
          createdByRole: e.created_by_role,
          created_at: e.created_at,
          completed: prog?.completed ?? false,
          attempted: prog !== undefined,
        };
      }),
    ].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  }, [questionsQuery.data, erdQuery.data, progressQuery.data, erdProgressQuery.data]);

  // Counts reflect the unfiltered pool, like the Problems sidebar.
  const categoryCounts = useMemo(() => {
    const sql = pool.filter((p) => p.problemType === 'sql-question').length;
    const erd = pool.filter((p) => p.problemType === 'erd-question').length;
    return { all: pool.length, sql, erd };
  }, [pool]);

  const filtered = useMemo(() => {
    const term = debouncedSearch.trim().toLowerCase();
    return pool.filter((p) => {
      if (category === 'sql' && p.problemType !== 'sql-question') return false;
      if (category === 'erd' && p.problemType !== 'erd-question') return false;
      if (term && !p.title.toLowerCase().includes(term)) return false;
      if (difficulty !== 'all' && p.difficulty !== difficulty) return false;
      return true;
    });
  }, [pool, category, debouncedSearch, difficulty]);

  const loading = questionsQuery.isLoading || progressQuery.isLoading || erdQuery.isLoading;
  const loadError = questionsQuery.error || progressQuery.error || erdQuery.error;
  const error = loadError
    ? ((loadError as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Failed to load questions')
    : null;
  const refreshing = questionsQuery.isFetching || progressQuery.isFetching || erdQuery.isFetching;
  const refresh = () => {
    questionsQuery.refetch();
    progressQuery.refetch();
    erdQuery.refetch();
  };

  const handleQuestionClick = (item: PooledQuestion) => {
    router.push(item.problemType === 'erd-question' ? `/er-diagram/${item.id}` : `/student/workspace/${item.id}`);
  };

  const handleDeleteErdQuestion = async (questionId: number) => {
    if (!window.confirm(`Delete ER question #${questionId}?`)) return;
    try {
      setDeletingErdId(questionId);
      await erDiagramService.deleteQuestion(questionId);
      // Remove from the cached raw list in place — no re-fetch; the derived
      // pool re-renders. Same key as the staff Problems page.
      queryClient.setQueryData<ERDiagramQuestionListItem[]>(queryKeys.erdQuestions, (old) =>
        old?.filter((item) => item.id !== questionId)
      );
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      notifications.show({
        color: 'red',
        message: e.response?.data?.detail || e.message || 'Failed to delete ER question',
      });
    } finally {
      setDeletingErdId(null);
    }
  };

  const categories: { key: CategoryFilter; label: string; count: number }[] = [
    { key: 'all', label: 'All questions', count: categoryCounts.all },
    { key: 'sql', label: 'SQL', count: categoryCounts.sql },
    { key: 'erd', label: 'ERD', count: categoryCounts.erd },
  ];

  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <DashboardLayout>
        <div style={{ display: 'flex', gap: '28px', alignItems: 'flex-start', minHeight: '100%' }}>
          {/* Left category sidebar — same anatomy as /admin/problems */}
          <div style={{ width: '180px', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <span style={{ fontSize: '12px', fontWeight: 650, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '4px', padding: '0 12px', letterSpacing: '0.05em' }}>
              Categories
            </span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {categories.map((cat) => {
                const active = category === cat.key;
                return (
                  <button
                    key={cat.key}
                    onClick={() => setCategory(cat.key)}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '10px 12px',
                      borderRadius: 'var(--radius)',
                      border: 'none',
                      background: active ? 'var(--surface-brand)' : 'transparent',
                      color: active ? 'var(--brand-lilac)' : 'var(--brand-charcoal)',
                      fontWeight: active ? 750 : 650,
                      fontSize: '14px',
                      width: '100%',
                      cursor: 'pointer',
                      textAlign: 'left',
                      transition: 'background 140ms ease, color 140ms ease',
                    }}
                  >
                    <span>{cat.label}</span>
                    <span style={{ fontSize: '12px', opacity: 0.8 }}>{cat.count}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Main content */}
          <div style={{ flex: 1, minWidth: 0 }}>
            {/* Header */}
            <div className="page-head">
              <div>
                <h2>Questions</h2>
                <p>All SQL and ER diagram practice questions in one place.</p>
              </div>
              <div className="button-row">
                <button className="btn btn-secondary" onClick={refresh} disabled={refreshing} title="Reload latest data from the server">
                  <IconRefresh />
                  {refreshing ? 'Refreshing…' : 'Refresh'}
                </button>
              </div>
            </div>

            {/* Filters */}
            <div className="filters">
              <select
                className="da-select"
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value)}
                style={{ width: 200 }}
                aria-label="Filter by difficulty"
              >
                <option value="all">All Difficulties</option>
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>
              <div style={{ position: 'relative', flex: 1, maxWidth: 420 }}>
                <span style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }}>
                  <IconSearch />
                </span>
                <input
                  type="text"
                  className="da-input"
                  placeholder="Search questions…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  style={{ width: '100%', paddingLeft: 34 }}
                  aria-label="Search questions"
                />
              </div>
            </div>

            {/* Loading */}
            {loading && (
              <div className="loading-center">
                <div className="spinner" />
                <span>Loading questions…</span>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="da-alert alert-error" role="alert">
                <strong>Error</strong>
                <span>{error}</span>
              </div>
            )}

            {/* Pooled questions grid */}
            {!loading && !error && (
              filtered.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', textAlign: 'center', marginTop: 40 }}>
                  {pool.length === 0 ? 'No questions available yet.' : 'No questions match your filters.'}
                </p>
              ) : (
                <div className="grid-3">
                  {filtered.map((item) => (
                    <article
                      key={item.uid}
                      className="card question-card"
                      onClick={() => handleQuestionClick(item)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => e.key === 'Enter' && handleQuestionClick(item)}
                      aria-label={`${item.problemType === 'erd-question' ? 'ER question' : 'Question'}: ${item.title}`}
                    >
                      <div className="button-row" style={{ marginBottom: 8 }}>
                        {/* Clamped to two lines, as this title was when it sat in
                            its own paragraph below — titles are free text and a
                            long one would otherwise set the height of every card
                            in its grid row. `flex: 1` holds the delete button right. */}
                        <h3 style={{
                          margin: 0, fontSize: 15, flex: 1, minWidth: 0,
                          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                        }}>
                          {item.title}
                        </h3>
                        {item.problemType === 'erd-question' &&
                          item.created_by !== undefined &&
                          ability.can('delete', toERQuestionSubject({ created_by: item.created_by })) && (
                            <button
                              className="btn btn-ghost"
                              style={{ minHeight: 26, padding: '0 6px', flexShrink: 0 }}
                              disabled={deletingErdId === item.id}
                              aria-label={`Delete ER question ${item.id}`}
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDeleteErdQuestion(item.id);
                              }}
                              onKeyDown={(e) => e.stopPropagation()}
                            >
                              <IconTrash />
                            </button>
                          )}
                      </div>

                      {/* One row, read left to right: who wrote it (only when that can
                          vary — see below), what kind of question it is, how hard, then
                          the student's own progress. Wrapping, not shrinking — the
                          badges do not all fit across a narrow card.

                          `marginTop: auto` pins the row to the bottom of the card, which
                          .question-card makes a flex column for exactly this. Titles
                          clamp to two lines but may take one, and the grid stretches
                          every card to the tallest in its row; without this the badges
                          would sit at whatever height each title happened to end. */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 'auto' }}>
                        {/* Author badge, shown only while staff allow students to write
                            ERD questions. With authoring off every question is staff-
                            written, so the badge would say "Staff" on every card it can
                            appear on and distinguish nothing.

                            ERD only: QuestionListItem carries no author role, and SQL
                            questions are staff-only anyway (create_question is gated by
                            require_staff_role). Admins count as staff deliberately —
                            what a student cares about is whether a peer wrote it, not
                            which kind of account did. */}
                        {showAuthorBadge &&
                          item.problemType === 'erd-question' &&
                          item.createdByRole && (
                            <span className="badge neutral">
                              {item.createdByRole === 'student' ? 'Student' : 'Staff'}
                            </span>
                          )}
                        {/* Tested per type rather than as an either/or, so a third
                            problem type added later shows no badge until someone gives
                            it one, instead of silently inheriting SQL's.

                            Blue rather than /admin/problems' green for SQL: there the
                            type and difficulty sit in separate table columns, here they
                            are adjacent, and badge-success is the same green as easy. */}
                        {item.problemType === 'erd-question' && (
                          <span className="badge brand-badge">ERD</span>
                        )}
                        {item.problemType === 'sql-question' && (
                          <span className="badge badge-info">SQL</span>
                        )}
                        <span className={`badge ${difficultyClass[item.difficulty] || 'neutral'}`}>
                          {capitalize(item.difficulty)}
                        </span>
                        {item.problemType === 'sql-question' &&
                          (item.completed ? (
                            <span className="badge badge-success">
                              <IconCheck />
                              Completed
                            </span>
                          ) : (item.attempts_count || 0) > 0 ? (
                            <span className="badge neutral">
                              {item.attempts_count} {(item.attempts_count || 0) === 1 ? 'attempt' : 'attempts'}
                            </span>
                          ) : null)}
                        {/* Same Completed badge as SQL, off the grader's "pass" verdict.
                            The fallback is "Attempted" rather than a count: an ERD
                            conversation keeps only the latest grade, so there is no
                            attempt tally to show. */}
                        {item.problemType === 'erd-question' &&
                          (item.completed ? (
                            <span className="badge badge-success">
                              <IconCheck />
                              Completed
                            </span>
                          ) : item.attempted ? (
                            <span className="badge neutral">Attempted</span>
                          ) : null)}
                      </div>
                    </article>
                  ))}
                </div>
              )
            )}
          </div>
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
