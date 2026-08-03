'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useDebouncedValue } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { Question, Difficulty } from '@/types/question.types';
import { questionService } from '@/services/question.service';
import { attemptService } from '@/services/attempt.service';
import { queryKeys } from '@/services/query-keys';

interface QuestionWithProgress extends Question {
  completed?: boolean;
  attempts_count?: number;
}

const difficultyClass: Record<string, string> = {
  easy: 'easy',
  medium: 'medium',
  hard: 'hard',
};

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

export default function StudentDashboard() {
  const router = useRouter();
  const [difficulty, setDifficulty] = useState<string>('all');
  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 500);

  // Session-cached (see providers.tsx). The questions key encodes the active
  // filters, so each difficulty/search combo is fetched once then served from
  // cache on return. Progress is a separate key, invalidated when a question is
  // solved in the workspace (see SqlWorkspace.tsx).
  const questionsQuery = useQuery({
    queryKey: queryKeys.studentQuestions({ difficulty, search: debouncedSearch }),
    queryFn: () => {
      const params: { difficulty?: Difficulty; search?: string } = {};
      if (difficulty && difficulty !== 'all') params.difficulty = difficulty as Difficulty;
      if (debouncedSearch) params.search = debouncedSearch;
      return questionService.getQuestions(params);
    },
  });
  const progressQuery = useQuery({
    queryKey: queryKeys.studentProgress,
    queryFn: () => attemptService.getProgress(),
  });

  const questions = useMemo<QuestionWithProgress[]>(() => {
    const questionsData = questionsQuery.data ?? [];
    const progressData = progressQuery.data ?? [];
    const progressMap = new Map(progressData.map((p) => [p.question_id, p]));
    return questionsData.map((q) => {
      const prog = progressMap.get(q.id);
      return { ...q, completed: prog?.completed || false, attempts_count: prog?.attempts_count || 0 };
    });
  }, [questionsQuery.data, progressQuery.data]);

  const loading = questionsQuery.isLoading || progressQuery.isLoading;
  const loadError = questionsQuery.error || progressQuery.error;
  const error = loadError
    ? ((loadError as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Failed to load questions')
    : null;
  const refreshing = questionsQuery.isFetching || progressQuery.isFetching;
  const refresh = () => {
    questionsQuery.refetch();
    progressQuery.refetch();
  };

  const handleQuestionClick = (questionId: number) => {
    router.push(`/student/workspace/${questionId}`);
  };

  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <DashboardLayout>
        {/* Header */}
        <div className="page-head">
          <div>
            <h2>SQL Questions</h2>
            <p>Select a question to start practicing your SQL skills.</p>
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

        {/* Questions grid */}
        {!loading && !error && (
          questions.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', textAlign: 'center', marginTop: 40 }}>
              No questions available yet.
            </p>
          ) : (
            <div className="grid-3">
              {questions.map((question) => (
                <article
                  key={question.id}
                  className="card question-card"
                  onClick={() => handleQuestionClick(question.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && handleQuestionClick(question.id)}
                  aria-label={`Question ${question.id}: ${question.title}`}
                >
                  <div className="button-row" style={{ marginBottom: 8 }}>
                    <h3 style={{ margin: 0, fontSize: 15 }}>Q{question.id}</h3>
                    <span className={`badge ${difficultyClass[question.difficulty] || 'neutral'}`}>
                      {question.difficulty.charAt(0).toUpperCase() + question.difficulty.slice(1)}
                    </span>
                  </div>
                  <p style={{ fontSize: 14, lineHeight: 1.55, marginBottom: 10, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {question.title}
                  </p>
                  {question.completed ? (
                    <span className="badge badge-success">
                      <IconCheck />
                      Completed
                    </span>
                  ) : (question.attempts_count || 0) > 0 ? (
                    <span className="badge neutral">
                      {question.attempts_count} {(question.attempts_count || 0) === 1 ? 'attempt' : 'attempts'}
                    </span>
                  ) : null}
                </article>
              ))}
            </div>
          )
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
