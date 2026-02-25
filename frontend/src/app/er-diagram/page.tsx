"use client";

import { useEffect, useState } from "react";
import { Alert, Button, Container, Group, Loader, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { IconAlertCircle, IconPlus } from "@tabler/icons-react";
import { QuestionCard, QuestionCardData } from "@/components/QuestionCard";
import { useAuth } from "@/contexts/AuthContext";
import { erDiagramService } from "@/services/er-diagram.service";

export default function ERDiagramPage() {
  const { isStaff } = useAuth();
  const [questions, setQuestions] = useState<QuestionCardData[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingQuestionId, setDeletingQuestionId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchQuestions = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await erDiagramService.getQuestions();
        setQuestions(
          data.map((item) => ({
            id: item.id,
            title: item.title,
            summary: item.problem_statement,
            description: item.problem_statement,
            difficulty: item.difficulty_label,
          }))
        );
      } catch (err) {
        const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
        setError(axiosErr.response?.data?.detail || axiosErr.message || "Failed to load ER questions");
      } finally {
        setLoading(false);
      }
    };

    fetchQuestions();
  }, []);

  const handleDeleteQuestion = async (questionId: number) => {
    if (!isStaff) {
      return;
    }

    const shouldDelete = window.confirm(`Delete ER question #${questionId}?`);
    if (!shouldDelete) {
      return;
    }

    try {
      setDeletingQuestionId(questionId);
      setError(null);
      await erDiagramService.deleteQuestion(questionId);
      setQuestions((prev) => prev.filter((item) => item.id !== questionId));
    } catch (err) {
      const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
      setError(axiosErr.response?.data?.detail || axiosErr.message || "Failed to delete ER question");
    } finally {
      setDeletingQuestionId(null);
    }
  };

  return (
    <Container size="lg" py="xl">
      <Stack gap="md">
        <Group justify="space-between" align="flex-start">
          <div>
            <Title order={2}>ER Diagram Practice</Title>
            <Text c="dimmed" mt={6}>
              Pick a question and sketch the entities, relationships, and keys.
            </Text>
          </div>
          <Button
            variant="light"
            rightSection={<IconPlus size={16} />}
            component="a"
            href="/er-diagram/add"
          >
            Add Question
          </Button>
        </Group>

        {loading ? (
          <Group justify="center" py="xl">
            <Loader />
          </Group>
        ) : null}

        {error ? (
          <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
            {error}
          </Alert>
        ) : null}

        {!loading && !error ? (
          questions.length > 0 ? (
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
              {questions.map((question) => (
                <QuestionCard
                  key={question.id}
                  data={question}
                  showDeleteButton={isStaff}
                  deleteLoading={deletingQuestionId === question.id}
                  onDelete={handleDeleteQuestion}
                />
              ))}
            </SimpleGrid>
          ) : (
            <Text c="dimmed">No ER questions saved yet.</Text>
          )
        ) : null}
      </Stack>
    </Container>
  );
}