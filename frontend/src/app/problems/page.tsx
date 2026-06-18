'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Alert,
  Box,
  Button,
  Group,
  Loader,
  Select,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { IconAlertCircle, IconPlus, IconSearch } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { CategorySidebar } from '@/components/problems/CategorySidebar';
import { ProblemsList, ProblemRow } from '@/components/problems/ProblemsList';
import { useAuth } from '@/contexts/AuthContext';
import { problemService } from '@/services/problem.service';
import { attemptService } from '@/services/attempt.service';
import { erDiagramService } from '@/services/er-diagram.service';
import { sqlLabQuestionService } from '@/services/sqlLabQuestion.service';
import api from '@/services/api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import {
  ProblemAuthorFilter,
  ProblemCounts,
  ProblemDifficulty,
  ProblemListItem,
  ProblemType,
} from '@/types/problem.types';

const EMPTY_COUNTS: ProblemCounts = { all: 0, sql: 0, erd: 0, sqllab: 0 };

export default function ProblemsPage() {
  const router = useRouter();
  const { user, isStaff } = useAuth();

  const [items, setItems] = useState<ProblemListItem[]>([]);
  const [counts, setCounts] = useState<ProblemCounts>(EMPTY_COUNTS);
  const [completedSqlIds, setCompletedSqlIds] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const [category, setCategory] = useState<ProblemType | 'all'>('all');
  const [difficulty, setDifficulty] = useState<string | null>('all');
  const [author, setAuthor] = useState<string | null>('all');
  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 400);

  const loadProblems = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await problemService.getProblems({
        type: category === 'all' ? undefined : category,
        difficulty: difficulty && difficulty !== 'all' ? (difficulty as ProblemDifficulty) : undefined,
        author: author && author !== 'all' ? (author as ProblemAuthorFilter) : undefined,
        search: debouncedSearch || undefined,
      });
      setItems(data.items);
      setCounts(data.counts);
    } catch (err) {
      const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
      setError(axiosErr.response?.data?.detail || axiosErr.message || 'Failed to load problems');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProblems();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, difficulty, author, debouncedSearch]);

  // Completion ticks come from SQL progress; ERD has no progress model.
  useEffect(() => {
    attemptService
      .getProgress()
      .then((progress) =>
        setCompletedSqlIds(new Set(progress.filter((p) => p.completed).map((p) => p.question_id)))
      )
      .catch(() => setCompletedSqlIds(new Set()));
  }, []);

  const rows: ProblemRow[] = useMemo(
    () =>
      items.map((item) => ({
        ...item,
        completed: item.type === 'sql' && completedSqlIds.has(item.id),
      })),
    [items, completedSqlIds]
  );

  const openProblem = (row: ProblemRow) => {
    if (row.type === 'sql') {
      router.push(isStaff ? `/admin/questions/${row.id}` : `/student/workspace/${row.id}`);
    } else if (row.type === 'sqllab') {
      router.push(`/sql-lab/${row.id}`);
    } else {
      router.push(`/er-diagram/${row.id}`);
    }
  };

  const editProblem = (row: ProblemRow) => {
    if (row.type === 'sql') router.push(`/admin/questions/${row.id}`);
  };

  const deleteProblem = async (row: ProblemRow) => {
    const label = row.type === 'sql' ? 'SQL' : row.type === 'sqllab' ? 'SQL lab' : 'ERD';
    if (!window.confirm(`Delete this ${label} question?`)) return;
    const key = `${row.type}-${row.id}`;
    try {
      setDeletingId(key);
      if (row.type === 'sql') {
        await api.delete(API_ENDPOINTS.QUESTIONS.DETAIL(row.id));
      } else if (row.type === 'sqllab') {
        await sqlLabQuestionService.remove(row.id);
      } else {
        await erDiagramService.deleteQuestion(row.id);
      }
      notifications.show({ color: 'green', message: 'Question deleted' });
      await loadProblems();
    } catch (err) {
      const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
      notifications.show({
        color: 'red',
        message: axiosErr.response?.data?.detail || axiosErr.message || 'Delete failed',
      });
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <ProtectedRoute>
      <Box p="xl">
        <Group justify="space-between" align="flex-start" mb="lg">
          <div>
            <Title order={2}>Problems</Title>
            <Text c="dimmed" mt={4}>
              All SQL, ER diagram, and SQL-lab questions in one place
            </Text>
          </div>
          <Button leftSection={<IconPlus size={16} />} onClick={() => router.push('/problems/new')}>
            Create question
          </Button>
        </Group>

        <Group align="flex-start" gap="xl" wrap="nowrap">
          <CategorySidebar counts={counts} selected={category} onSelect={setCategory} />

          <Stack gap="md" style={{ flex: 1, minWidth: 0 }}>
            <Group>
              <TextInput
                placeholder="Search questions..."
                leftSection={<IconSearch size={16} />}
                value={search}
                onChange={(e) => setSearch(e.currentTarget.value)}
                style={{ flex: 1, maxWidth: 360 }}
              />
              <Select
                data={[
                  { value: 'all', label: 'All difficulties' },
                  { value: 'easy', label: 'Easy' },
                  { value: 'medium', label: 'Medium' },
                  { value: 'hard', label: 'Hard' },
                ]}
                value={difficulty}
                onChange={setDifficulty}
                style={{ width: 170 }}
                allowDeselect={false}
              />
              <Select
                data={[
                  { value: 'all', label: 'Author: all' },
                  { value: 'staff', label: 'Author: staff' },
                  { value: 'students', label: 'Author: students' },
                ]}
                value={author}
                onChange={setAuthor}
                style={{ width: 170 }}
                allowDeselect={false}
              />
            </Group>

            {error && (
              <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
                {error}
              </Alert>
            )}

            {loading ? (
              <Group justify="center" py="xl">
                <Loader />
              </Group>
            ) : (
              <ProblemsList
                rows={rows}
                isStaff={isStaff}
                currentUserId={user?.id ?? null}
                deletingId={deletingId}
                onOpen={openProblem}
                onEdit={editProblem}
                onDelete={deleteProblem}
              />
            )}
          </Stack>
        </Group>
      </Box>
    </ProtectedRoute>
  );
}
