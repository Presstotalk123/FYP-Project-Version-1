"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Alert, Container, Group, Loader } from "@mantine/core";
import { IconAlertCircle } from "@tabler/icons-react";
import { ERDiagramWorkspace, type ERDiagramWorkspaceQuestion } from "@/components/ERDiagramWorkspace";
import { erLabsService } from "@/services/erLabs.service";
import type { ERRubricJson } from "@/types/er-diagram.types";

export default function ErLabQuestionAttemptPage() {
  const params = useParams<{ id: string; qid: string }>();
  const router = useRouter();
  const labId = Number(params.id);
  const qid = Number(params.qid);

  const [question, setQuestion] = useState<ERDiagramWorkspaceQuestion | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        setLoading(true);
        setError(null);

        // Verify an active session before showing the workspace.
        try {
          await erLabsService.getSession(labId);
        } catch {
          if (!cancelled) router.push(`/er-diagram/lab/${labId}/join`);
          return;
        }

        const q = await erLabsService.getQuestion(labId, qid);
        if (cancelled) return;

        setQuestion({
          id: q.id,
          title: q.title,
          description: q.problem_statement,
          difficulty: q.difficulty_label,
          rubric_md: q.rubric_md || "",
          rubric_json: (q.rubric_json ?? null) as ERRubricJson | null,
          show_rubric_on_attempt: q.show_rubric_on_attempt,
        });
      } catch (err) {
        if (cancelled) return;
        const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
        setError(axiosErr.response?.data?.detail || axiosErr.message || "Failed to load question");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [labId, qid, router]);

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

  return (
    <ERDiagramWorkspace
      question={question}
      labContext={{ er_lab_id: labId, er_lab_question_id: qid }}
    />
  );
}
