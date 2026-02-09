'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Title,
  Text,
  Stack,
  Group,
  Select,
  TextInput,
  Grid,
  Card,
  Badge,
  Loader,
  Alert,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { IconSearch, IconCheck, IconAlertCircle } from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { Question, Difficulty } from '@/types/question.types';
import { Progress } from '@/types/attempt.types';
import { questionService } from '@/services/question.service';
import { attemptService } from '@/services/attempt.service';

interface QuestionWithProgress extends Question {
  completed?: boolean;
  attempts_count?: number;
}

const difficultyColors: Record<string, string> = {
  easy: 'green',
  medium: 'yellow',
  hard: 'red',
};

export default function StudentDashboard() {
  const router = useRouter();

  // State
  const [questions, setQuestions] = useState<QuestionWithProgress[]>([]);
  const [progress, setProgress] = useState<Progress[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter state
  const [difficulty, setDifficulty] = useState<string | null>('all');
  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 500);

  // Fetch data
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);

        const params: { difficulty?: Difficulty; search?: string } = {};
        if (difficulty && difficulty !== 'all') {
          params.difficulty = difficulty as Difficulty;
        }
        if (debouncedSearch) {
          params.search = debouncedSearch;
        }

        const [questionsData, progressData] = await Promise.all([
          questionService.getQuestions(params),
          attemptService.getProgress(),
        ]);

        // Merge progress into questions
        const progressMap = new Map(
          progressData.map((p) => [p.question_id, p])
        );
        const questionsWithProgress = questionsData.map((q) => {
          const prog = progressMap.get(q.id);
          return {
            ...q,
            completed: prog?.completed || false,
            attempts_count: prog?.attempts_count || 0,
          };
        });

        setQuestions(questionsWithProgress);
        setProgress(progressData);
      } catch (err) {
        const error = err as { response?: { data?: { detail?: string } } };
        setError(error.response?.data?.detail || 'Failed to load questions');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [difficulty, debouncedSearch]);

  // Handle card click
  const handleQuestionClick = (questionId: number) => {
    router.push(`/student/workspace/${questionId}`);
  };

  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <DashboardLayout>
        <Stack gap="lg">
          {/* Header */}
          <div>
            <Title order={2}>SQL Questions</Title>
            <Text mt="sm" c="dimmed">
              Select a question to start practicing your SQL skills
            </Text>
          </div>

          {/* Filters */}
          <Group>
            <Select
              placeholder="Filter by difficulty"
              data={[
                { label: 'All Difficulties', value: 'all' },
                { label: 'Easy', value: 'easy' },
                { label: 'Medium', value: 'medium' },
                { label: 'Hard', value: 'hard' },
              ]}
              value={difficulty}
              onChange={setDifficulty}
              style={{ width: 200 }}
            />
            <TextInput
              placeholder="Search questions..."
              leftSection={<IconSearch size={16} />}
              value={search}
              onChange={(e) => setSearch(e.currentTarget.value)}
              style={{ flex: 1, maxWidth: 400 }}
            />
          </Group>

          {/* Loading state */}
          {loading && (
            <Stack align="center" justify="center" style={{ minHeight: '300px' }}>
              <Loader size="lg" />
              <Text c="dimmed">Loading questions...</Text>
            </Stack>
          )}

          {/* Error state */}
          {error && (
            <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
              {error}
            </Alert>
          )}

          {/* Questions grid */}
          {!loading && !error && (
            <>
              {questions.length === 0 ? (
                <Text c="dimmed" ta="center" mt="xl">
                  No questions available yet.
                </Text>
              ) : (
                <Grid>
                  {questions.map((question) => (
                    <Grid.Col key={question.id} span={{ base: 12, sm: 6, md: 4 }}>
                      <Card
                        withBorder
                        radius="md"
                        p="md"
                        style={{ cursor: 'pointer', height: '100%' }}
                        onClick={() => handleQuestionClick(question.id)}
                      >
                        <Stack gap="xs">
                          <Group justify="space-between" align="center">
                            <Title order={4}>Q{question.id}</Title>
                            <Badge
                              color={difficultyColors[question.difficulty]}
                              variant="light"
                            >
                              {question.difficulty.charAt(0).toUpperCase() +
                                question.difficulty.slice(1)}
                            </Badge>
                          </Group>

                          <Text size="sm" lineClamp={2}>
                            {question.title}
                          </Text>

                          {/* Completion status */}
                          {question.completed ? (
                            <Badge
                              color="green"
                              variant="filled"
                              leftSection={<IconCheck size={12} />}
                            >
                              Completed
                            </Badge>
                          ) : (question.attempts_count || 0) > 0 ? (
                            <Badge color="gray" variant="light">
                              {question.attempts_count}{' '}
                              {(question.attempts_count || 0) === 1 ? 'attempt' : 'attempts'}
                            </Badge>
                          ) : null}
                        </Stack>
                      </Card>
                    </Grid.Col>
                  ))}
                </Grid>
              )}
            </>
          )}
        </Stack>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
