'use client';

import { useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
// The other icons on this page are hand-rolled SVGs, the convention across the
// plain-HTML admin pages. Tabler's stroke and currentColor defaults match them,
// so only the size needs stating — the siblings are 15px to suit .icon-btn.
import { IconTrash, IconDatabase, IconHierarchy, IconChartDots3, IconChevronDown } from '@tabler/icons-react';
import { Menu } from '@mantine/core';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { useAuth } from '@/contexts/AuthContext';
import { questionService } from '@/services/question.service';
import { labService } from '@/services/lab.service';
import { erDiagramService } from '@/services/er-diagram.service';
import { queryKeys } from '@/services/query-keys';

type ProblemType = 'sql-question' | 'sql-lab' | 'graph-lab' | 'erd-question';
type CategoryFilter = 'all' | 'sql' | 'erd' | 'graph';

interface Problem {
  uid: string;
  id: number;
  title: string;
  problemType: ProblemType;
  difficulty?: string;
  created_by?: number;
  createdByRole?: string;
  isPublished?: boolean;
  created_at: string;
  editUrl: string;
}

// Publish only applies to SQL questions and staff-created ERD questions.
// Student-created ERDs stay visible to students regardless, so they get no publish control.
const isPublishable = (p: Problem): boolean => {
  if (p.problemType === 'sql-question') return true;
  if (p.problemType === 'erd-question') {
    return p.createdByRole === 'staff' || p.createdByRole === 'admin';
  }
  return false;
};

// Coloured by family, not by row type: blue for SQL, brand purple for ERD, so a
// question carries the same colour here as on the student list. The label is
// what separates a question from a lab — the colour was never doing that work.
const typeBadge: Record<ProblemType, { label: string; className: string }> = {
  'sql-question': { label: 'SQL Question', className: 'badge-info' },
  'sql-lab': { label: 'SQL Lab', className: 'badge-info' },
  'graph-lab': { label: 'Graph Lab', className: 'badge-warn' },
  'erd-question': { label: 'ERD Question', className: 'brand-badge' },
};

/* ── SVG icons ── */
const IconPlus = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
  </svg>
);
const IconSearch = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
  </svg>
);
const IconEdit = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
  </svg>
);
const IconRefresh = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
  </svg>
);
// Upload/paper-plane style icon for "Publish"
const IconPublish = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 19V5"/><path d="M5 12l7-7 7 7"/>
  </svg>
);
// Bar-chart icon for "Submission analytics" (ERD questions only)
const IconChart = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
  </svg>
);
// Eye-off style icon for "Unpublish" (hide from students)
const IconUnpublish = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
    <line x1="1" y1="1" x2="23" y2="23"/>
  </svg>
);
// Question types offered from the "Create Question" dropdown, same 4 choices
// (and destinations) the old /admin/problems/new chooser page offered as cards.
const createQuestionTypes: { label: string; icon: React.ReactNode; destination: string }[] = [
  { label: 'SQL question', icon: <IconDatabase size={16} />, destination: '/admin/questions/new' },
  { label: 'ERD question', icon: <IconHierarchy size={16} />, destination: '/er-diagram/add' },
  { label: 'SQL lab question', icon: <IconDatabase size={16} />, destination: '/admin/labs/wizard' },
  { label: 'Graph question', icon: <IconChartDots3 size={16} />, destination: '/admin/labs/wizard?type=graph' },
];

export default function ProblemsPage() {
  const router = useRouter();
  const { user } = useAuth();

  const queryClient = useQueryClient();
  const [publishing, setPublishing] = useState<Record<string, boolean>>({});
  const [actionError, setActionError] = useState<string | null>(null);
  // The whole Problem, not just an id: the confirmation names what is going and
  // the handler needs the type to know which endpoint deletes it.
  const [deleteTarget, setDeleteTarget] = useState<Problem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [search, setSearch] = useState('');
  const [difficulty, setDifficulty] = useState<string | null>(null);
  const [authorFilter, setAuthorFilter] = useState<string | null>(null);

  // Session-cached (see providers.tsx). `questions` is shared with the Dashboard
  // and `labs` with Manage Labs, so a tour of the admin area fetches each once.
  const questionsQuery = useQuery({ queryKey: queryKeys.questions, queryFn: () => questionService.getQuestions() });
  const labsQuery = useQuery({ queryKey: queryKeys.labs, queryFn: () => labService.getLabs() });
  const erdQuery = useQuery({ queryKey: queryKeys.erdQuestions, queryFn: () => erDiagramService.getQuestions() });

  const loading = questionsQuery.isLoading || labsQuery.isLoading || erdQuery.isLoading;
  const loadFailed = !!(questionsQuery.error || labsQuery.error || erdQuery.error);
  const error = actionError ?? (loadFailed ? 'Failed to load problems' : null);
  const refreshing = questionsQuery.isFetching || labsQuery.isFetching || erdQuery.isFetching;

  const refresh = () => {
    setActionError(null);
    questionsQuery.refetch();
    labsQuery.refetch();
    erdQuery.refetch();
  };

  const problems = useMemo<Problem[]>(() => {
    const sqlQuestions = questionsQuery.data ?? [];
    const labs = labsQuery.data ?? [];
    const erdQuestions = erdQuery.data ?? [];

    return [
        ...sqlQuestions.map((q) => ({
          uid: `sql-${q.id}`,
          id: q.id,
          title: q.title,
          problemType: 'sql-question' as ProblemType,
          difficulty: q.difficulty,
          created_by: q.created_by,
          isPublished: q.is_published,
          created_at: q.created_at,
          editUrl: `/admin/questions/${q.id}`,
        })),
        ...labs
          .filter((l) => l.lab_type === 'sql')
          .map((l) => ({
            uid: `lab-sql-${l.id}`,
            id: l.id,
            title: l.title,
            problemType: 'sql-lab' as ProblemType,
            difficulty: undefined,
            created_at: l.created_at,
            editUrl: `/admin/labs/${l.id}/wizard`,
          })),
        ...labs
          .filter((l) => l.lab_type === 'graph')
          .map((l) => ({
            uid: `lab-graph-${l.id}`,
            id: l.id,
            title: l.title,
            problemType: 'graph-lab' as ProblemType,
            difficulty: undefined,
            created_at: l.created_at,
            editUrl: `/admin/labs/${l.id}/wizard`,
          })),
        ...erdQuestions.map((e) => ({
          uid: `erd-${e.id}`,
          id: e.id,
          title: e.title,
          problemType: 'erd-question' as ProblemType,
          difficulty: e.difficulty_label,
          created_by: e.created_by,
          createdByRole: e.created_by_role,
          isPublished: e.is_published,
          created_at: e.created_at,
          editUrl: `/er-diagram/${e.id}/edit`,
        })),
      ].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  }, [questionsQuery.data, labsQuery.data, erdQuery.data]);

  const togglePublish = async (problem: Problem) => {
    const nextPublished = !problem.isPublished;
    setPublishing((prev) => ({ ...prev, [problem.uid]: true }));
    setActionError(null);
    try {
      if (problem.problemType === 'sql-question') {
        if (nextPublished) {
          await questionService.publishQuestion(problem.id);
        } else {
          await questionService.unpublishQuestion(problem.id);
        }
        // Update the cached source list in place — keeps the optimistic feel
        // without a re-fetch, and the derived `problems` list re-renders.
        queryClient.setQueryData<typeof questionsQuery.data>(queryKeys.questions, (old) =>
          old?.map((q) => (q.id === problem.id ? { ...q, is_published: nextPublished } : q))
        );
      } else if (problem.problemType === 'erd-question') {
        if (nextPublished) {
          await erDiagramService.publishQuestion(problem.id);
        } else {
          await erDiagramService.unpublishQuestion(problem.id);
        }
        queryClient.setQueryData<typeof erdQuery.data>(queryKeys.erdQuestions, (old) =>
          old?.map((e) => (e.id === problem.id ? { ...e, is_published: nextPublished } : e))
        );
      }
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      setActionError(e.response?.data?.detail || 'Failed to update publish status');
    } finally {
      setPublishing((prev) => ({ ...prev, [problem.uid]: false }));
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    const target = deleteTarget;
    setDeleting(true);
    setActionError(null);
    try {
      // One list, four backing resources — the row's type picks the endpoint,
      // then the row is dropped from that source list. Editing the cache rather
      // than refetching matches togglePublish above, and keeps the other three
      // lists untouched.
      if (target.problemType === 'sql-question') {
        await questionService.deleteQuestion(target.id);
        queryClient.setQueryData<typeof questionsQuery.data>(queryKeys.questions, (old) =>
          old?.filter((q) => q.id !== target.id)
        );
      } else if (target.problemType === 'sql-lab' || target.problemType === 'graph-lab') {
        await labService.deleteLab(target.id);
        queryClient.setQueryData<typeof labsQuery.data>(queryKeys.labs, (old) =>
          old?.filter((l) => l.id !== target.id)
        );
      } else {
        await erDiagramService.deleteQuestion(target.id);
        queryClient.setQueryData<typeof erdQuery.data>(queryKeys.erdQuestions, (old) =>
          old?.filter((e) => e.id !== target.id)
        );
      }
      setDeleteTarget(null);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      setActionError(e.response?.data?.detail || 'Failed to delete');
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  const categoryCounts = useMemo(() => {
    const sql = problems.filter(
      (p) => p.problemType === 'sql-question' || p.problemType === 'sql-lab'
    ).length;
    const erd = problems.filter((p) => p.problemType === 'erd-question').length;
    const graph = problems.filter((p) => p.problemType === 'graph-lab').length;
    return { all: problems.length, sql, erd, graph };
  }, [problems]);

  const filtered = useMemo(() => {
    return problems.filter((p) => {
      if (category === 'sql' && p.problemType !== 'sql-question' && p.problemType !== 'sql-lab')
        return false;
      if (category === 'erd' && p.problemType !== 'erd-question') return false;
      if (category === 'graph' && p.problemType !== 'graph-lab') return false;

      if (search && !p.title.toLowerCase().includes(search.toLowerCase())) return false;

      if (difficulty && difficulty !== 'all') {
        if (!p.difficulty) return false;
        if (p.difficulty.toLowerCase() !== difficulty.toLowerCase()) return false;
      }

      if (authorFilter === 'mine') {
        if (!user || p.created_by !== user.id) return false;
      }

      return true;
    });
  }, [problems, category, search, difficulty, authorFilter, user]);

  const categories: { key: CategoryFilter; label: string; count: number }[] = [
    { key: 'all', label: 'All problems', count: categoryCounts.all },
    { key: 'sql', label: 'SQL', count: categoryCounts.sql },
    { key: 'erd', label: 'ERD', count: categoryCounts.erd },
    { key: 'graph', label: 'Graph', count: categoryCounts.graph },
  ];

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <div style={{ display: 'flex', gap: '28px', alignItems: 'flex-start', minHeight: '100%' }}>
          {/* Left Category Sidebar */}
          <div style={{ width: '180px', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: '8px', position: 'sticky', top: '84px', alignSelf: 'flex-start' }}>
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

          {/* Main Content */}
          <div style={{ flex: 1, minWidth: 0 }}>
            {/* Page Header */}
            <div className="page-head">
              <div>
                <h2>Problems</h2>
                <p>All SQL, ER diagram, and SQL-lab questions in one place.</p>
              </div>
              <div className="button-row">
                <button className="btn btn-secondary" onClick={refresh} disabled={refreshing} title="Reload latest data from the server">
                  <IconRefresh />
                  {refreshing ? 'Refreshing…' : 'Refresh'}
                </button>
                <Menu shadow="md" position="bottom-end" withinPortal>
                  <Menu.Target>
                    <button className="btn btn-brand">
                      <IconPlus />
                      Create Question
                      <IconChevronDown size={14} />
                    </button>
                  </Menu.Target>
                  <Menu.Dropdown>
                    {createQuestionTypes.map((t) => (
                      <Menu.Item
                        key={t.label}
                        leftSection={t.icon}
                        onClick={() => router.push(t.destination)}
                      >
                        {t.label}
                      </Menu.Item>
                    ))}
                  </Menu.Dropdown>
                </Menu>
              </div>
            </div>

            {/* Toolbar */}
            <div className="filters" style={{ marginBottom: '18px' }}>
              {/* Search */}
              <div style={{ position: 'relative', flex: 1, maxWidth: '320px' }}>
                <span style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', display: 'flex', alignItems: 'center' }}>
                  <IconSearch />
                </span>
                <input
                  type="text"
                  className="da-input"
                  placeholder="Search questions..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  style={{ paddingLeft: '36px', width: '100%' }}
                />
              </div>

              {/* Difficulty */}
              <select
                className="da-select"
                value={difficulty ?? 'all'}
                onChange={(e) => setDifficulty(e.target.value)}
                style={{ width: '160px' }}
              >
                <option value="all">All difficulties</option>
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>

              {/* Author Filter */}
              <select
                className="da-select"
                value={authorFilter ?? 'all'}
                onChange={(e) => setAuthorFilter(e.target.value)}
                style={{ width: '160px' }}
              >
                <option value="all">Author: all</option>
                <option value="mine">Author: mine</option>
              </select>
            </div>

            {/* Loading */}
            {loading && (
              <div className="loading-center">
                <div className="spinner" />
                <span>Loading problems…</span>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="da-alert alert-error" role="alert">
                <strong>Error</strong>
                <span>{error}</span>
              </div>
            )}

            {/* Gated on the fetch, not on `error`: an action that fails — a
                delete the backend refuses, a publish that errors — reports in
                the banner above and leaves the list alone. Only a failed load
                means there is nothing to show. */}
            {!loading && !loadFailed && (
              <>
                {filtered.length === 0 ? (
                  <div className="da-alert alert-info">
                    <strong>No Problems</strong>
                    <span>No problems found matching the selected filters.</span>
                  </div>
                ) : (
                  <div className="table-wrap">
                    <table className="da-table">
                      <thead>
                        <tr>
                          <th>Title</th>
                          <th>Type</th>
                          <th>Difficulty</th>
                          <th>Status</th>
                          <th>Created</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.map((problem) => {
                          const badge = typeBadge[problem.problemType];
                          return (
                            <tr key={problem.uid}>
                              <td style={{ fontWeight: 600 }}>{problem.title}</td>
                              <td>
                                <span className={`badge ${badge.className}`}>
                                  {badge.label}
                                </span>
                              </td>
                              <td>
                                {problem.difficulty ? (
                                  <span className={`badge ${problem.difficulty.toLowerCase()}`}>
                                    {problem.difficulty.charAt(0).toUpperCase() + problem.difficulty.slice(1).toLowerCase()}
                                  </span>
                                ) : (
                                  <span style={{ color: 'var(--text-muted)' }}>—</span>
                                )}
                              </td>
                              <td>
                                {isPublishable(problem) ? (
                                  <span className={`badge ${problem.isPublished ? 'badge-success' : 'badge-warn'}`}>
                                    {problem.isPublished ? 'Published' : 'Draft'}
                                  </span>
                                ) : (
                                  <span style={{ color: 'var(--text-muted)' }}>—</span>
                                )}
                              </td>
                              <td>{new Date(problem.created_at).toLocaleDateString()}</td>
                              <td>
                                <div className="actions">
                                  {isPublishable(problem) && (
                                    <button
                                      className="icon-btn"
                                      title={problem.isPublished ? 'Unpublish (hide from students)' : 'Publish (show to students)'}
                                      onClick={() => togglePublish(problem)}
                                      disabled={!!publishing[problem.uid]}
                                      style={{ color: problem.isPublished ? '#d97706' : '#16a34a' }}
                                    >
                                      {problem.isPublished ? <IconUnpublish /> : <IconPublish />}
                                    </button>
                                  )}
                                  <button
                                    className="icon-btn"
                                    title="Edit"
                                    onClick={() => router.push(problem.editUrl)}
                                    style={{ color: '#6366f1' }}
                                  >
                                    <IconEdit />
                                  </button>
                                  {problem.problemType === 'erd-question' && (
                                    <button
                                      className="icon-btn"
                                      title="Submission analytics"
                                      aria-label={`Analytics for ${problem.title}`}
                                      onClick={() => router.push(`/admin/er-analytics/${problem.id}`)}
                                      style={{ color: '#0d9488' }}
                                    >
                                      <IconChart />
                                    </button>
                                  )}
                                  {problem.problemType === 'sql-question' && (
                                    <button
                                      className="icon-btn"
                                      title="Student analytics"
                                      aria-label={`Analytics for ${problem.title}`}
                                      onClick={() => router.push(`/admin/sql-analytics/${problem.id}`)}
                                      style={{ color: '#0d9488' }}
                                    >
                                      <IconChart />
                                    </button>
                                  )}
                                  {(problem.problemType === 'sql-lab' || problem.problemType === 'graph-lab') && (
                                    <button
                                      className="icon-btn"
                                      title="Student analytics"
                                      aria-label={`Analytics for ${problem.title}`}
                                      onClick={() => router.push(`/admin/lab-analytics/${problem.id}`)}
                                      style={{ color: '#0d9488' }}
                                    >
                                      <IconChart />
                                    </button>
                                  )}
                                  <button
                                    className="icon-btn"
                                    title="Delete"
                                    aria-label={`Delete ${problem.title}`}
                                    onClick={() => setDeleteTarget(problem)}
                                    style={{ color: '#ef4444' }}
                                  >
                                    <IconTrash size={15} />
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* Names the row and its kind: unlike /admin/questions this list mixes
            questions and labs, so "this question" would not always be true. */}
        {deleteTarget && (
          <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="delete-problem-title">
            <div className="modal">
              <h3 id="delete-problem-title">Delete {typeBadge[deleteTarget.problemType].label}</h3>
              <p>
                Are you sure you want to delete <strong>{deleteTarget.title}</strong>? This action
                cannot be undone.
              </p>
              <div className="button-row" style={{ justifyContent: 'flex-end' }}>
                <button
                  className="btn btn-secondary"
                  onClick={() => setDeleteTarget(null)}
                  disabled={deleting}
                >
                  Cancel
                </button>
                <button className="btn btn-danger" onClick={handleDelete} disabled={deleting}>
                  {deleting ? 'Deleting…' : 'Delete'}
                </button>
              </div>
            </div>
          </div>
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
