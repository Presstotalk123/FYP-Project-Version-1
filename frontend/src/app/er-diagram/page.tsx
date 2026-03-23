"use client";

import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Container, Group, Loader, SimpleGrid, Stack, Tabs, Text, Title } from "@mantine/core";
import { IconAlertCircle, IconPlus } from "@tabler/icons-react";
import { QuestionCard, QuestionCardData } from "@/components/QuestionCard";
import { useERAbility } from "@/hooks/use-er-ability";
import { toERQuestionSubject } from "@/permissions/er-ability";
import { erDiagramService } from "@/services/er-diagram.service";

type ERQuestionCardData = QuestionCardData & {
  created_by: number;
  created_by_role: "student" | "staff";
};

export default function ERDiagramPage() {
  const ability = useERAbility();
  const [questions, setQuestions] = useState<ERQuestionCardData[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingQuestionId, setDeletingQuestionId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const studentCreatedQuestions = useMemo(
    () => questions.filter((question) => question.created_by_role === "student"),
    [questions]
  );
  const staffCreatedQuestions = useMemo(
    () => questions.filter((question) => question.created_by_role === "staff"),
    [questions]
  );

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
            created_by: item.created_by,
            created_by_role: item.created_by_role,
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
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } }; message?: string };
      if (axiosErr.response?.status === 403) {
        setError(axiosErr.response?.data?.detail || "Only the question owner or staff can delete this question");
      } else {
        setError(axiosErr.response?.data?.detail || axiosErr.message || "Failed to delete ER question");
      }
    } finally {
      setDeletingQuestionId(null);
    }
  };

  const renderQuestions = (questionList: ERQuestionCardData[], emptyMessage: string) => {
    if (questionList.length === 0) {
      return <Text c="dimmed">{emptyMessage}</Text>;
    }

    return (
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
        {questionList.map((question) => (
          <QuestionCard
            key={question.id}
            data={question}
            showDeleteButton={ability.can("delete", toERQuestionSubject(question))}
            deleteLoading={deletingQuestionId === question.id}
            onDelete={handleDeleteQuestion}
          />
        ))}
      </SimpleGrid>
    );
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
          <Tabs defaultValue="student-created">
            <Tabs.List>
              <Tabs.Tab value="student-created">Student-created</Tabs.Tab>
              <Tabs.Tab value="staff-created">Staff-created</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value="student-created" pt="md">
              {renderQuestions(studentCreatedQuestions, "No student-created ER questions saved yet.")}
            </Tabs.Panel>
            <Tabs.Panel value="staff-created" pt="md">
              {renderQuestions(staffCreatedQuestions, "No staff-created ER questions saved yet.")}
            </Tabs.Panel>
          </Tabs>
        ) : null}
      </Stack>
    </Container>
  );
}
