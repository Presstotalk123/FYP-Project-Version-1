"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Alert, Container, Group, Loader, Stack, Text, Title } from "@mantine/core";
import { IconAlertCircle } from "@tabler/icons-react";
import { ProtectedRoute } from "@/components/common/ProtectedRoute";
import { DashboardLayout } from "@/components/common/DashboardLayout";
import { ERQuestionForm } from "@/components/admin/ERQuestionForm";
import { UserRole } from "@/types/user.types";
import type { ERDiagramQuestion } from "@/types/er-diagram.types";
import { erDiagramService } from "@/services/er-diagram.service";

/**
 * Edit a question-bank ERD question — the counterpart of
 * /admin/questions/[id] for SQL questions, reached from Problems → Edit.
 */
export default function EditERQuestionPage() {
  const params = useParams<{ id: string }>();
  const questionId = Number(params?.id ?? 0);

  const [question, setQuestion] = useState<ERDiagramQuestion | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchQuestion = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await erDiagramService.getQuestionById(questionId);
        setQuestion(data);
      } catch (err) {
        const e = err as { response?: { data?: { detail?: string } }; message?: string };
        setError(e.response?.data?.detail || e.message || "Failed to load question");
      } finally {
        setLoading(false);
      }
    };

    if (Number.isFinite(questionId) && questionId > 0) {
      fetchQuestion();
    } else {
      setError("Invalid question id");
      setLoading(false);
    }
  }, [questionId]);

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <Container size="xl" py="xl">
          <Stack gap="lg">
            {/* No back arrow: leaving is Cancel, beside the form's own action
                button, as on the SQL question pages. */}
            <div>
              <Title order={2}>Edit ER Diagram Question</Title>
              <Text c="dimmed" mt={6}>
                {question ? question.title : "Loading…"}
              </Text>
            </div>

            {loading ? (
              <Group justify="center" py="xl">
                <Loader />
              </Group>
            ) : error || !question ? (
              <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
                {error || "Question not found"}
              </Alert>
            ) : (
              <ERQuestionForm question={question} />
            )}
          </Stack>
        </Container>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
