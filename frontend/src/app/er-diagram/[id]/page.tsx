"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Alert, Container, Group, Loader } from "@mantine/core";
import { IconAlertCircle } from "@tabler/icons-react";
import { ERDiagramWorkspace } from "@/components/ERDiagramWorkspace";
import { erDiagramService } from "@/services/er-diagram.service";
import type { ERDiagramWorkspaceQuestion } from "@/components/ERDiagramWorkspace";

export default function ERDiagramQuestionPage() {
  const params = useParams<{ id: string }>();
  const [question, setQuestion] = useState<ERDiagramWorkspaceQuestion | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchQuestion = async () => {
      try {
        setLoading(true);
        setError(null);
        const id = Number(params.id);
        if (!Number.isFinite(id)) {
          throw new Error("Invalid question id");
        }
        const data = await erDiagramService.getQuestionById(id);
        setQuestion({
          id: data.id,
          title: data.title,
          description: data.problem_statement,
          difficulty: data.difficulty_label,
          rubric_md: data.rubric_md || "",
          rubric_json: data.rubric_json || null,
          show_rubric_on_attempt: data.show_rubric_on_attempt,
        });
      } catch (err) {
        const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
        setError(axiosErr.response?.data?.detail || axiosErr.message || "Failed to load question");
      } finally {
        setLoading(false);
      }
    };

    fetchQuestion();
  }, [params.id]);

  if (loading) {
    return (
      <Container py="xl">
        <Group justify="center">
          <Loader />
        </Group>
      </Container>
    );
  }

  if (error || !question) {
    return (
      <Container py="xl">
        <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
          {error || "Question not found"}
        </Alert>
      </Container>
    );
  }

  return <ERDiagramWorkspace question={question} />;
}
