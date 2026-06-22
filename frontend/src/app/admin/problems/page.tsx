'use client';

import { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import {
  Title,
  Button,
  Stack,
  Group,
  Table,
  Badge,
  Loader,
  Alert,
  Text,
  TextInput,
  Select,
  Menu,
  ActionIcon,
  Box,
  Checkbox,
  UnstyledButton,
} from '@mantine/core';
import {
  IconPlus,
  IconSearch,
  IconDotsVertical,
  IconEdit,
  IconAlertCircle,
} from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { useAuth } from '@/contexts/AuthContext';
import { questionService } from '@/services/question.service';
import { labService } from '@/services/lab.service';
import { erDiagramService } from '@/services/er-diagram.service';

type ProblemType = 'sql-question' | 'sql-lab' | 'graph-lab' | 'erd-question';
type CategoryFilter = 'all' | 'sql' | 'erd' | 'graph';

interface Problem {
  uid: string;
  id: number;
  title: string;
  problemType: ProblemType;
  difficulty?: string;
  created_by?: number;
  created_at: string;
  editUrl: string;
}

const typeBadge: Record<ProblemType, { label: string; color: string }> = {
  'sql-question': { label: 'SQL Question', color: 'teal' },
  'sql-lab': { label: 'SQL Lab', color: 'cyan' },
  'graph-lab': { label: 'Graph Lab', color: 'orange' },
  'erd-question': { label: 'ERD', color: 'violet' },
};

const difficultyColor: Record<string, string> = {
  easy: 'green',
  medium: 'yellow',
  hard: 'red',
  Easy: 'green',
  Medium: 'yellow',
  Hard: 'red',
};

export default function ProblemsPage() {
  const router = useRouter();
  const { user } = useAuth();

  const [problems, setProblems] = useState<Problem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [search, setSearch] = useState('');
  const [difficulty, setDifficulty] = useState<string | null>(null);
  const [authorFilter, setAuthorFilter] = useState<string | null>(null);

  useEffect(() => {
    fetchAll();
  }, []);

  const fetchAll = async () => {
    try {
      setLoading(true);
      setError(null);

      const [sqlQuestions, labs, erdQuestions] = await Promise.all([
        questionService.getQuestions(),
        labService.getLabs(),
        erDiagramService.getQuestions(),
      ]);

      const merged: Problem[] = [
        ...sqlQuestions.map((q) => ({
          uid: `sql-${q.id}`,
          id: q.id,
          title: q.title,
          problemType: 'sql-question' as ProblemType,
          difficulty: q.difficulty,
          created_by: q.created_by,
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
          created_at: e.created_at,
          editUrl: `/er-diagram/${e.id}`,
        })),
      ].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

      setProblems(merged);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail || 'Failed to load problems');
    } finally {
      setLoading(false);
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
        <Group align="flex-start" gap="xl" style={{ minHeight: '100%' }}>
          {/* Left category sidebar */}
          <Box style={{ width: 160, flexShrink: 0 }}>
            <Text size="xs" fw={600} tt="uppercase" c="dimmed" mb="xs" px="xs">
              Categories
            </Text>
            <Stack gap={2}>
              {categories.map((cat) => (
                <UnstyledButton
                  key={cat.key}
                  onClick={() => setCategory(cat.key)}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '6px 10px',
                    borderRadius: 6,
                    background:
                      category === cat.key
                        ? 'var(--mantine-color-blue-light)'
                        : 'transparent',
                    color:
                      category === cat.key
                        ? 'var(--mantine-color-blue-filled)'
                        : 'inherit',
                    fontWeight: category === cat.key ? 600 : 400,
                    fontSize: 14,
                    width: '100%',
                  }}
                >
                  <span>{cat.label}</span>
                  <Text
                    size="sm"
                    c={category === cat.key ? 'blue' : 'dimmed'}
                    fw={category === cat.key ? 600 : 400}
                  >
                    {cat.count}
                  </Text>
                </UnstyledButton>
              ))}
            </Stack>
          </Box>

          {/* Main content */}
          <Box style={{ flex: 1, minWidth: 0 }}>
            {/* Page header */}
            <Group justify="space-between" mb="lg">
              <div>
                <Title order={2}>Problems</Title>
                <Text c="dimmed" size="sm" mt={4}>
                  All SQL, ER diagram, and SQL-lab questions in one place
                </Text>
              </div>
              <Button
                leftSection={<IconPlus size={16} />}
                onClick={() => router.push('/admin/problems/new')}
              >
                Create question
              </Button>
            </Group>

            {/* Toolbar */}
            <Group mb="md" gap="sm">
              <TextInput
                placeholder="Search questions..."
                leftSection={<IconSearch size={16} />}
                value={search}
                onChange={(e) => setSearch(e.currentTarget.value)}
                style={{ flex: 1, maxWidth: 320 }}
              />
              <Select
                data={[
                  { value: 'all', label: 'All difficulties' },
                  { value: 'easy', label: 'Easy' },
                  { value: 'medium', label: 'Medium' },
                  { value: 'hard', label: 'Hard' },
                ]}
                value={difficulty ?? 'all'}
                onChange={(v) => setDifficulty(v)}
                style={{ width: 160 }}
              />
              <Select
                data={[
                  { value: 'all', label: 'Author: all' },
                  { value: 'mine', label: 'Author: mine' },
                ]}
                value={authorFilter ?? 'all'}
                onChange={(v) => setAuthorFilter(v)}
                style={{ width: 160 }}
              />
            </Group>

            {/* Loading */}
            {loading && (
              <Stack align="center" justify="center" style={{ minHeight: 200 }}>
                <Loader size="lg" />
                <Text c="dimmed">Loading problems...</Text>
              </Stack>
            )}

            {/* Error */}
            {error && (
              <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
                {error}
              </Alert>
            )}

            {/* Table */}
            {!loading && !error && (
              <>
                {filtered.length === 0 ? (
                  <Text c="dimmed" ta="center" mt="xl">
                    No problems found.
                  </Text>
                ) : (
                  <Table highlightOnHover withTableBorder>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th style={{ width: 40 }}>#</Table.Th>
                        <Table.Th style={{ width: 32 }}></Table.Th>
                        <Table.Th>Title</Table.Th>
                        <Table.Th style={{ width: 140 }}>Type</Table.Th>
                        <Table.Th style={{ width: 100 }}>Difficulty</Table.Th>
                        <Table.Th style={{ width: 40 }}></Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {filtered.map((problem, index) => {
                        const badge = typeBadge[problem.problemType];
                        const diffColor = problem.difficulty
                          ? difficultyColor[problem.difficulty]
                          : undefined;

                        return (
                          <Table.Tr key={problem.uid}>
                            <Table.Td>
                              <Text size="sm" c="dimmed">
                                {index + 1}
                              </Text>
                            </Table.Td>
                            <Table.Td>
                              <Checkbox size="xs" />
                            </Table.Td>
                            <Table.Td>
                              <Text size="sm">{problem.title}</Text>
                            </Table.Td>
                            <Table.Td>
                              <Badge
                                color={badge.color}
                                variant="light"
                                size="sm"
                                style={{ maxWidth: 110, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                              >
                                {badge.label}
                              </Badge>
                            </Table.Td>
                            <Table.Td>
                              {problem.difficulty && diffColor ? (
                                <Badge color={diffColor} variant="light" size="sm">
                                  {problem.difficulty.charAt(0).toUpperCase() +
                                    problem.difficulty.slice(1).toLowerCase()}
                                </Badge>
                              ) : (
                                <Text size="sm" c="dimmed">
                                  –
                                </Text>
                              )}
                            </Table.Td>
                            <Table.Td>
                              <Menu position="bottom-end" withinPortal>
                                <Menu.Target>
                                  <ActionIcon variant="subtle" color="gray" size="sm">
                                    <IconDotsVertical size={14} />
                                  </ActionIcon>
                                </Menu.Target>
                                <Menu.Dropdown>
                                  <Menu.Item
                                    leftSection={<IconEdit size={14} />}
                                    onClick={() => router.push(problem.editUrl)}
                                  >
                                    Edit
                                  </Menu.Item>
                                </Menu.Dropdown>
                              </Menu>
                            </Table.Td>
                          </Table.Tr>
                        );
                      })}
                    </Table.Tbody>
                  </Table>
                )}
              </>
            )}
          </Box>
        </Group>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
