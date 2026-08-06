"use client";

import { ActionIcon, Container, Group, Stack, Text, Title } from "@mantine/core";
import { IconArrowLeft } from "@tabler/icons-react";
import { useAuth } from "@/contexts/AuthContext";
import { ERQuestionForm } from "@/components/admin/ERQuestionForm";

/**
 * Create a question-bank ERD question. Reached from Problems → Create question
 * → ERD question (staff), or directly by students when authoring is enabled.
 *
 * The authoring UI itself lives in ERQuestionForm, shared with the edit page —
 * the same split QuestionForm uses for SQL questions.
 */
export default function AddERDiagramQuestionPage() {
  const { isStaff } = useAuth();
  return (
    <Container size="xl" py="xl">
      <Stack gap="lg">
        <Group align="baseline" gap="sm">
          <ActionIcon
            component="a"
            href={isStaff ? "/admin/problems" : "/student"}
            variant="subtle"
            size="sm"
            aria-label={isStaff ? "Back to problems" : "Back to questions"}
          >
            <IconArrowLeft size={18} />
          </ActionIcon>
          <div>
            <Title order={2}>Add ER Diagram Question</Title>
            <Text c="dimmed" mt={6}>
              Create a new ER diagram practice question.
            </Text>
          </div>
        </Group>

        <ERQuestionForm />
      </Stack>
    </Container>
  );
}
