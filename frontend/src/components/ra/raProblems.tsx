'use client';

/**
 * Relational Algebra inside the shared question lists: the staff Problems page
 * (app/admin/problems) and the students' Questions page (app/student). RA has no tab of
 * its own; it is a "Relational Algebra" category in each page's left panel, shown while
 * RA_ENABLED is on. Everything RA-specific those pages need lives here, so their own
 * edits stay small.
 */
import { ReactNode } from 'react';
import { IconMathFunction } from '@tabler/icons-react';
import { QueryClient, useQuery } from '@tanstack/react-query';
import { useRaStatus } from '@/hooks/use-ra-status';
import { raQueryKeys, raService } from '@/services/ra.service';
import { RaQuestionListItem } from '@/types/ra.types';

export const RA_CATEGORY = 'ra' as const;
export const RA_CATEGORY_LABEL = 'Relational Algebra';
export const RA_PROBLEM_TYPE = 'ra-question' as const;
export const RA_BADGE = { label: 'RA Question', className: 'badge-ra' };

/** The "Create Question ▾" entry on the Problems page. */
export const RA_CREATE_TYPE = {
  label: 'Relational algebra question', icon: <IconMathFunction size={16} />, destination: '/ra/questions/new',
};

export const raQuestionUrl = (id: number) => `/ra/questions/${id}`;
export const raEditUrl = (id: number) => `/ra/questions/${id}/edit`;
export const raAnalyticsUrl = (id: number) => `/ra/analytics/${id}`;

// Lists sort newest first by created_at; a question without one goes last.
const created = (q: RaQuestionListItem) => q.created_at ?? new Date(0).toISOString();

/** The RA questions for the current user (none while RA is off): staff get every bank question, students the published ones. */
export function useRaQuestions() {
  const { enabled } = useRaStatus();
  const query = useQuery({
    queryKey: raQueryKeys.questions,
    queryFn: () => raService.listQuestions(),
    enabled,
    staleTime: 0, // progress changes after every submission
  });
  return {
    enabled,
    questions: enabled ? query.data ?? [] : [],
    isLoading: enabled && query.isLoading,
    isFetching: enabled && query.isFetching,
    error: enabled ? query.error : null,
    refetch: () => (enabled ? query.refetch() : undefined),
  };
}

/** Rows for the staff Problems table. */
export function raStaffRows(questions: RaQuestionListItem[]) {
  return questions.map((q) => ({
    uid: `ra-${q.id}`,
    id: q.id,
    title: q.title,
    problemType: RA_PROBLEM_TYPE,
    difficulty: q.difficulty,
    created_by: q.created_by ?? undefined,
    isPublished: q.is_published,
    created_at: created(q),
    editUrl: raEditUrl(q.id),
  }));
}

/** Cards for the students' Questions page. */
export function raStudentItems(questions: RaQuestionListItem[]) {
  return questions.map((q) => ({
    uid: `ra-${q.id}`,
    id: q.id,
    title: q.title,
    problemType: RA_PROBLEM_TYPE,
    difficulty: q.difficulty,
    created_at: created(q),
    completed: q.solved,
    attempts_count: q.attempts,
    parts_total: q.parts_total,
    parts_solved: q.parts_solved,
  }));
}

export async function setRaPublished(queryClient: QueryClient, id: number, published: boolean) {
  await raService.setPublished(id, published);
  queryClient.setQueryData<RaQuestionListItem[]>(raQueryKeys.questions, (old) =>
    old?.map((q) => (q.id === id ? { ...q, is_published: published } : q)));
}

export async function deleteRaQuestion(queryClient: QueryClient, id: number) {
  await raService.deleteQuestion(id);
  queryClient.setQueryData<RaQuestionListItem[]>(raQueryKeys.questions, (old) => old?.filter((q) => q.id !== id));
}

/** ``?category=ra`` in the address (where the old /ra page sends people), if present. */
export function raCategoryFromUrl(): typeof RA_CATEGORY | null {
  try {
    return new URLSearchParams(window.location.search).get('category') === RA_CATEGORY ? RA_CATEGORY : null;
  } catch {
    return null;
  }
}

/** The badges an RA card shows after its difficulty: parts, then the page's own Completed badge / progress / attempts. */
export function RaCardBadges({ item, completedBadge }: {
  item: { completed?: boolean; attempts_count?: number; parts_total?: number; parts_solved?: number };
  completedBadge: ReactNode;
}) {
  const parts = item.parts_total ?? 1;
  const solved = item.parts_solved ?? 0;
  const attempts = item.attempts_count ?? 0;
  return (
    <>
      {parts > 1 && <span className="badge neutral" title="Sub-questions on the same schema">{parts} parts</span>}
      {item.completed ? completedBadge : parts > 1 && solved > 0 ? (
        <span className="badge neutral">{solved} of {parts} solved</span>
      ) : attempts > 0 ? (
        <span className="badge neutral">{attempts} {attempts === 1 ? 'attempt' : 'attempts'}</span>
      ) : null}
    </>
  );
}
