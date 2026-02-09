'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Title,
  Button,
  Stack,
  Group,
  Table,
  Badge,
  ActionIcon,
  Loader,
  Alert,
  Text,
  Modal,
  ScrollArea,
} from '@mantine/core';
import {
  IconPlus,
  IconEdit,
  IconTrash,
  IconAlertCircle,
} from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { Question } from '@/types/question.types';
import { questionService } from '@/services/question.service';
import api from '@/services/api.service';
import { API_ENDPOINTS } from '@/config/api.config';

const difficultyColors: Record<string, string> = {
  easy: 'green',
  medium: 'yellow',
  hard: 'red',
};

export default function AdminQuestionsPage() {
  const router = useRouter();

  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [questionToDelete, setQuestionToDelete] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchQuestions();
  }, []);

  const fetchQuestions = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await questionService.getQuestions();
      setQuestions(data);
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      setError(error.response?.data?.detail || 'Failed to load questions');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!questionToDelete) return;

    setDeleting(true);
    try {
      await api.delete(API_ENDPOINTS.QUESTIONS.DETAIL(questionToDelete));
      notifications.show({
        title: 'Success',
        message: 'Question deleted successfully',
        color: 'green',
      });
      setDeleteModalOpen(false);
      setQuestionToDelete(null);
      fetchQuestions();
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: error.response?.data?.detail || 'Failed to delete question',
        color: 'red',
      });
    } finally {
      setDeleting(false);
    }
  };

  const openDeleteModal = (questionId: number) => {
    setQuestionToDelete(questionId);
    setDeleteModalOpen(true);
  };

  return (
    <ProtectedRoute requiredRole={UserRole.STAFF}>
      <DashboardLayout>
        <Stack gap="lg">
          {/* Header */}
          <Group justify="space-between">
            <div>
              <Title order={2}>Manage Questions</Title>
              <Text mt="xs" c="dimmed">
                Create, edit, and manage SQL practice questions
              </Text>
            </div>
            <Button
              leftSection={<IconPlus size={16} />}
              onClick={() => router.push('/admin/questions/new')}
            >
              Create Question
            </Button>
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

          {/* Questions table */}
          {!loading && !error && (
            <>
              {questions.length === 0 ? (
                <Text c="dimmed" ta="center" mt="xl">
                  No questions created yet. Click "Create Question" to add one.
                </Text>
              ) : (
                <ScrollArea>
                  <Table striped highlightOnHover withTableBorder>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>ID</Table.Th>
                        <Table.Th>Title</Table.Th>
                        <Table.Th>Difficulty</Table.Th>
                        <Table.Th>Created At</Table.Th>
                        <Table.Th style={{ width: 120 }}>Actions</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {questions.map((question) => (
                        <Table.Tr key={question.id}>
                          <Table.Td>{question.id}</Table.Td>
                          <Table.Td>{question.title}</Table.Td>
                          <Table.Td>
                            <Badge
                              color={difficultyColors[question.difficulty]}
                              variant="light"
                            >
                              {question.difficulty.charAt(0).toUpperCase() +
                                question.difficulty.slice(1)}
                            </Badge>
                          </Table.Td>
                          <Table.Td>
                            {new Date(question.created_at).toLocaleDateString()}
                          </Table.Td>
                          <Table.Td>
                            <Group gap="xs">
                              <ActionIcon
                                variant="subtle"
                                color="blue"
                                onClick={() =>
                                  router.push(`/admin/questions/${question.id}`)
                                }
                              >
                                <IconEdit size={16} />
                              </ActionIcon>
                              <ActionIcon
                                variant="subtle"
                                color="red"
                                onClick={() => openDeleteModal(question.id)}
                              >
                                <IconTrash size={16} />
                              </ActionIcon>
                            </Group>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </ScrollArea>
              )}
            </>
          )}
        </Stack>

        {/* Delete confirmation modal */}
        <Modal
          opened={deleteModalOpen}
          onClose={() => setDeleteModalOpen(false)}
          title="Delete Question"
        >
          <Stack gap="md">
            <Text>
              Are you sure you want to delete this question? This action cannot be
              undone.
            </Text>
            <Group justify="flex-end">
              <Button
                variant="default"
                onClick={() => setDeleteModalOpen(false)}
                disabled={deleting}
              >
                Cancel
              </Button>
              <Button color="red" onClick={handleDelete} loading={deleting}>
                Delete
              </Button>
            </Group>
          </Stack>
        </Modal>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
