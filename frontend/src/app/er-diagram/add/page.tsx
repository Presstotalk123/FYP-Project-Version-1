"use client";

import { Container, Stack, Text, Title } from "@mantine/core";
import { ERQuestionForm } from "@/components/admin/ERQuestionForm";

/**
 * Create a question-bank ERD question. Reached from Problems → Create question
 * → ERD question (staff), or directly by students when authoring is enabled.
 *
 * The authoring UI itself lives in ERQuestionForm, shared with the edit page —
 * the same split QuestionForm uses for SQL questions.
 */
export default function AddERDiagramQuestionPage() {
  return (
    <Container size="xl" py="xl">
      <Stack gap="lg">
        {/* No back arrow: leaving is Cancel, beside the form's own action
            button, as on the SQL question pages. The form routes it by role,
            the same way it routes a successful save. */}
        <div>
          <Title order={2}>Add ER Diagram Question</Title>
          <Text c="dimmed" mt={6}>
            Create a new ER diagram practice question.
          </Text>
        </div>

        <ERQuestionForm />
      </Stack>
    </Container>
  );
}
