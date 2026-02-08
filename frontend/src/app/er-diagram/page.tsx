import { Container, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { QuestionCard } from "@/components/QuestionCard";
import { erQuestions } from "@/data/er-questions";

export default function ERDiagramPage() {
  return (
    <Container size="lg" py="xl">
      <Stack gap="md">
        <div>
          <Title order={2}>ER Diagram Practice</Title>
          <Text c="dimmed" mt={6}>
            Pick a question and sketch the entities, relationships, and keys.
          </Text>
        </div>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
          {erQuestions.map((question) => (
            <QuestionCard key={question.id} data={question} />
          ))}
        </SimpleGrid>
      </Stack>
    </Container>
  );
}
